"""Editor-owned measurement sessions, revision scheduling and independent selection.

Handlers record Python revisions only. One persistent controller resolves live
window/area/region contexts; no job retains Blender editor or evaluated-ID wrappers.
Soft changes never cancel a running scan. Full-scope captures are intentional until
dependency-aware incremental invalidation has its own proven correctness model.
"""

from collections import deque
from dataclasses import dataclass, field
import time
import traceback

import bpy
from bpy.app.handlers import persistent
from bpy.props import (BoolProperty, CollectionProperty, EnumProperty, FloatProperty,
                       IntProperty, PointerProperty, StringProperty)

from ...core.addon import get_prefs
from .collectors import MESH_TYPES, collect_object

DEBOUNCE = 0.4
MAX_WAIT = 1.5
POLL_INTERVAL = 0.15
BATCH_BUDGET = 0.008
MAX_BATCH_OBJECTS = 32
DEFAULTS = {'stats_timings': True, 'stats_tri_budget': 1000000, 'stats_ms_budget': 16.0}
SESSIONS = {}
TRACE = deque(maxlen=200)
_scene_revisions = {}
_enabled = False
_heartbeat = 0.0
_cursor = 0
_selection_owner = object()


def setting(context, name):
    return getattr(get_prefs(context), name, DEFAULTS[name])


class MBT_StatsRow(bpy.types.PropertyGroup):
    name: StringProperty()
    uid: StringProperty()
    obj: PointerProperty(type=bpy.types.Object)
    tris: IntProperty(default=-1)
    ms: FloatProperty(default=-1)
    error: StringProperty()
    selected: BoolProperty(default=False)


class MBT_StatsState(bpy.types.PropertyGroup):
    name: StringProperty()
    rows: CollectionProperty(type=MBT_StatsRow)
    # Presentation only. User commands are queued by an explicit activation operator.
    index: IntProperty(default=-1, min=-1)
    auto: BoolProperty(name='Auto', default=True,
        description='Refresh after scene changes; disable for manual scans')
    running: BoolProperty(default=False)
    stale: BoolProperty(default=True)
    status: StringProperty(default='Waiting for first capture')
    phase: StringProperty(default='WAITING')
    progress: FloatProperty(default=0, min=0, max=1, subtype='FACTOR')
    sort: EnumProperty(name='Sort', items=(('TRIS', 'Tris', 'Highest triangles first'),
                       ('PERF', 'ms', 'Highest modifier milliseconds first')), default='TRIS')


classes = (MBT_StatsRow, MBT_StatsState)


@dataclass
class Session:
    key: str
    scene_uid: str = ''
    binding: tuple = ()
    membership: tuple = ()
    seen_scene_revision: int = -1
    requested: int = 1
    committed: int = 0
    first_dirty: float = field(default_factory=time.monotonic)
    last_dirty: float = field(default_factory=time.monotonic)
    job: object = None
    snapshot: object = None
    row_indices: dict = field(default_factory=dict)
    selection: object = None
    projected_index: int = -1
    selection_command: object = None
    presentation_key: object = None
    presentation: object = None
    last_probe: float = 0.0
    retry_at: float = 0.0
    commits: int = 0
    reason: str = 'Initial capture'
    error: str = ''


def trace(session, event, **details):
    TRACE.append({'time': time.monotonic(), 'session': session.key if session else None,
                  'event': event, **details})


def editor_key(context):
    if context.window is None or context.area is None or context.area.type != 'VIEW_3D':
        raise RuntimeError('Scene Performance requires its owning 3D Viewport')
    return f'{context.window.as_pointer()}:{context.area.as_pointer()}'


def state(context, create=True):
    key = editor_key(context)
    states = context.window_manager.mbt_stats_sessions
    ui = states.get(key)
    if ui is None and create:
        ui = states.add()
        ui.name = key
    return ui


def session(context):
    key = editor_key(context)
    if key not in SESSIONS:
        SESSIONS[key] = Session(key)
        state(context)
        trace(SESSIONS[key], 'created')
    return SESSIONS[key]


def viewport_contexts():
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                region = next((r for r in area.regions if r.type == 'WINDOW'), None)
                if region is not None:
                    yield window, area, region


def binding(context):
    props = context.scene.mbt
    local = context.space_data.local_view
    collection = context.collection if props.stats_scope == 'COLLECTION' else None
    return (str(context.scene.session_uid), context.view_layer.as_pointer(),
            local.as_pointer() if local else 0, props.stats_scope,
            str(collection.session_uid) if collection else '', props.stats_recursive,
            context.scene.frame_current, setting(context, 'stats_timings'))


def targets(context):
    props = context.scene.mbt
    if props.stats_scope == 'SELECTED':
        objects = [obj for obj in context.view_layer.objects if obj.select_get(view_layer=context.view_layer)]
    elif props.stats_scope == 'COLLECTION':
        objects = context.collection.all_objects if props.stats_recursive else context.collection.objects
    else:
        objects = [obj for obj in context.view_layer.objects
                   if obj.visible_get(view_layer=context.view_layer, viewport=context.space_data)]
    layer = context.view_layer.objects
    return sorted((obj for obj in objects if obj.name in layer
                   and (obj.type in MESH_TYPES or len(obj.modifiers))),
                  key=lambda obj: (obj.name.casefold(), obj.session_uid))


def mark_dirty(s, reason):
    now = time.monotonic()
    if s.requested == s.committed:
        s.first_dirty = now
    s.requested += 1
    s.last_dirty = now
    s.reason = reason
    trace(s, 'dirty', revision=s.requested, reason=reason)


def request_refresh(context, reason='Explicit change'):
    mark_dirty(session(context), reason)


def observe(context, s, force=False):
    current = binding(context)
    if current != s.binding:
        trace(s, 'rebind', old=s.binding, new=current)
        s.binding = current
        s.scene_uid = current[0]
        s.job = None
        s.snapshot = None
        s.presentation_key = None
        s.row_indices.clear()
        s.selection = None
        s.membership = ()
        s.seen_scene_revision = -1
        ui = state(context)
        ui.rows.clear()
        ui.index = -1
        s.projected_index = -1
        ui.running = False
        mark_dirty(s, 'Context changed')
    revision = _scene_revisions.get(s.scene_uid, 0)
    if revision != s.seen_scene_revision:
        s.seen_scene_revision = revision
        mark_dirty(s, 'Dependency graph changed')
    now = time.monotonic()
    if force or now - s.last_probe >= 0.5:
        s.last_probe = now
        membership = tuple((str(obj.session_uid), obj.name) for obj in targets(context))
        if membership != s.membership:
            s.membership = membership
            mark_dirty(s, 'Scope membership or names changed')


def sync_selection(context, s=None):
    """Read the view layer, not snapshot freshness, mode, or Auto state."""
    s = s or session(context)
    ui = state(context)
    active = context.view_layer.objects.active
    uid = str(active.session_uid) if active is not None else ''
    # Active and selected are distinct in Blender; deselect-all must clear highlight.
    if active is not None and not active.select_get(view_layer=context.view_layer):
        uid = ''
    selected = set()
    for row in ui.rows:
        obj = row.obj
        value = bool(obj and obj.name in context.view_layer.objects
                     and obj.select_get(view_layer=context.view_layer))
        if row.selected != value:
            row.selected = value
        if value:
            selected.add(row.uid)
    signature = (uid, frozenset(selected))
    index = s.row_indices.get(uid, -1)
    if ui.index != index or signature != s.selection:
        ui.index = index
        s.projected_index = index
        s.selection = signature
        context.area.tag_redraw()
        trace(s, 'selection', active=uid, index=index)


def queue_selection(context, uid, extend=False):
    s = session(context)
    s.selection_command = (uid, extend)
    ensure_controller()


def reconcile_list_input(context, s):
    """UIList keyboard/background clicks change presentation, not the scene in draw.

    Convert a changed index to a queued command only if the viewport active object
    has not changed since the last projection. Viewport changes always win races.
    """
    ui = state(context)
    if ui.index == s.projected_index or not 0 <= ui.index < len(ui.rows):
        return
    obj = context.view_layer.objects.active
    uid = (str(obj.session_uid) if obj and obj.select_get(view_layer=context.view_layer) else '')
    if s.selection is not None and uid == s.selection[0] and s.selection_command is None:
        s.selection_command = (ui.rows[ui.index].uid, False)


def apply_selection(context, s):
    command = s.selection_command
    s.selection_command = None
    if command is None or context.mode != 'OBJECT':
        return False
    uid, extend = command
    obj = next((obj for obj in context.view_layer.objects if str(obj.session_uid) == uid), None)
    if (obj is None or obj.hide_select
            or not obj.visible_get(view_layer=context.view_layer, viewport=context.space_data)):
        trace(s, 'selection_rejected', uid=uid)
        return False
    if not extend:
        for selected in context.view_layer.objects:
            if selected != obj and selected.select_get(view_layer=context.view_layer):
                selected.select_set(False, view_layer=context.view_layer)
    obj.select_set(True, view_layer=context.view_layer)
    context.view_layer.objects.active = obj
    sync_selection(context, s)
    return True


def active_result(context):
    s = session(context)
    ui = state(context)
    if not s.snapshot or not 0 <= ui.index < len(ui.rows):
        return None, None
    row = ui.rows[ui.index]
    return row, s.snapshot['results'].get(row.uid)


def presentation(context):
    s, ui = session(context), state(context)
    key = (s.commits, ui.sort)
    if key != s.presentation_key:
        def sort_key(index):
            row = ui.rows[index]
            value = row.tris if ui.sort == 'TRIS' else row.ms
            return (value < 0, -value, row.name.casefold(), row.uid)
        order = sorted(range(len(ui.rows)), key=sort_key)
        s.presentation = {'indices': order, 'total_tris': sum(max(0, row.tris) for row in ui.rows)}
        s.presentation_key = key
    return s.presentation


def start_scan(context, automatic=False):
    s = session(context)
    observe(context, s, force=True)
    if s.job is not None:
        raise RuntimeError('This viewport already has a running scan')
    if context.mode != 'OBJECT' or bpy.app.is_job_running('RENDER'):
        raise RuntimeError('Scan requires Object Mode and no render')
    objects = targets(context)
    s.job = {'revision': s.requested, 'binding': s.binding,
             'objects': [(str(obj.session_uid), obj.name) for obj in objects],
             'position': 0, 'results': {}, 'automatic': automatic, 'started': time.monotonic()}
    s.error = ''
    ui = state(context)
    ui.running, ui.phase = True, 'SCANNING'
    trace(s, 'scan_started', revision=s.requested, count=len(objects))
    return s.job


def publish(context, s, complete=True):
    job, ui = s.job, state(context)
    s.snapshot = {'results': job['results'], 'complete': complete,
                  'revision': job['revision'], 'binding': job['binding']}
    ui.rows.clear()
    ui.index = -1
    s.projected_index = -1
    s.row_indices.clear()
    for uid, result in job['results'].items():
        obj = context.view_layer.objects.get(result['name'])
        if obj is None or str(obj.session_uid) != uid:
            obj = next((o for o in context.view_layer.objects if str(o.session_uid) == uid), None)
        if obj is None:
            continue
        s.row_indices[uid] = len(ui.rows)
        row = ui.rows.add()
        row.name, row.uid, row.obj = obj.name, uid, obj
        row.tris = result['tris'] if result['tris'] is not None else -1
        row.ms = result['ms'] if result['ms'] is not None else -1
        row.error = result['error']
    if complete:
        s.committed = job['revision']
    s.commits += 1
    s.selection = None
    s.presentation_key = None
    s.job = None
    ui.running = False
    ui.progress = 1 if complete else ui.progress
    sync_selection(context, s)
    trace(s, 'committed' if complete else 'partial', revision=s.committed, requested=s.requested)
    if s.requested > s.committed:
        s.first_dirty = time.monotonic()
    context.area.tag_redraw()


def scan_step(context, s=None, budget=BATCH_BUDGET, limit=MAX_BATCH_OBJECTS):
    s = s or session(context)
    job = s.job
    if job is None:
        return False
    if binding(context) != job['binding']:
        observe(context, s, force=True)
        return False
    if context.mode != 'OBJECT' or bpy.app.is_job_running('RENDER'):
        return True  # Pause rather than discard valid work.
    # Evaluation may issue notifications; consume the baseline BEFORE reading objects.
    graph = context.evaluated_depsgraph_get()
    deadline = time.perf_counter() + budget
    count = 0
    while job['position'] < len(job['objects']):
        uid, name = job['objects'][job['position']]
        obj = context.view_layer.objects.get(name)
        if obj is None or str(obj.session_uid) != uid:
            obj = next((o for o in context.view_layer.objects if str(o.session_uid) == uid), None)
        if obj is not None:
            try:
                result = collect_object(graph, obj, job['binding'][-1])
            except (RuntimeError, ReferenceError, TypeError, ValueError) as exc:
                result = {'uid': uid, 'name': obj.name, 'tris': None, 'ms': None,
                          'mods': [], 'error': str(exc)}
            job['results'][uid] = result
        job['position'] += 1
        count += 1
        if count >= limit or time.perf_counter() >= deadline:
            break
    ui = state(context)
    ui.progress = job['position'] / max(1, len(job['objects']))
    ui.status = f'Scanning {job["position"]}/{len(job["objects"])}'
    # Observe notifications delivered during evaluation, without cancelling the job.
    observe(context, s)
    if s.job is not job:
        return False
    if job['position'] >= len(job['objects']):
        publish(context, s)
        return False
    return True


def cancel_scan(context, partial=False):
    s, ui = session(context), state(context)
    if s.job:
        if partial and not s.job['automatic']:
            publish(context, s, complete=False)
        else:
            s.job = None
        trace(s, 'cancelled')
    ui.running = False


def set_status(context, s, phase, text):
    ui = state(context)
    changed = ui.phase != phase or ui.status != text
    ui.phase, ui.status = phase, text
    ui.stale = s.snapshot is None or s.requested > s.committed
    ui.running = s.job is not None
    if changed:
        context.area.tag_redraw()


def reconcile(context, s):
    observe(context, s)
    reconcile_list_input(context, s)
    if s.selection_command:
        apply_selection(context, s)
    sync_selection(context, s)
    ui = state(context)
    if s.job and s.job['automatic'] and not ui.auto:
        cancel_scan(context)
    if context.mode != 'OBJECT' or bpy.app.is_job_running('RENDER') or context.screen.is_animation_playing:
        set_status(context, s, 'PAUSED', 'Paused · Object Mode, no playback or render required')
        return False
    if not context.space_data.show_region_ui and (s.job is None or s.job['automatic']):
        set_status(context, s, 'PAUSED', 'Paused · viewport sidebar closed')
        return False
    if s.error and time.monotonic() < s.retry_at:
        set_status(context, s, 'ERROR', s.error)
        return False
    if s.job:
        set_status(context, s, 'SCANNING', f'Scanning {s.job["position"]}/{len(s.job["objects"])}')
        return True
    if not ui.auto:
        set_status(context, s, 'MANUAL', 'Manual · Scan to update' if s.requested > s.committed else 'Manual · current')
        return False
    if s.requested > s.committed:
        now = time.monotonic()
        if now - s.last_dirty >= DEBOUNCE or now - s.first_dirty >= MAX_WAIT:
            start_scan(context, automatic=True)
            return True
        set_status(context, s, 'WAITING', 'Waiting for changes to settle')
    else:
        set_status(context, s, 'READY', f'Ready · {len(ui.rows)} objects')
    return False


def controller():
    global _heartbeat, _cursor
    if not _enabled:
        return None
    _heartbeat = time.monotonic()
    live = set()
    try:
        contexts = list(viewport_contexts())
    except Exception as exc:
        trace(None, 'context_discovery_error', message=str(exc))
        return POLL_INTERVAL
    if contexts:
        offset = _cursor % len(contexts)
        contexts = contexts[offset:] + contexts[:offset]
        _cursor += 1
    deadline = time.perf_counter() + BATCH_BUDGET
    busy = False
    for window, area, region in contexts:
        key = f'{window.as_pointer()}:{area.as_pointer()}'
        live.add(key)
        # Only opened tools acquire sessions; no background scans of unrelated editors.
        if key not in SESSIONS:
            continue
        s = SESSIONS[key]
        try:
            with bpy.context.temp_override(window=window, area=area, region=region):
                # Fulfil panel initialization before any observation/evaluation can fail.
                # Previously initialization depended on observe() reaching state().
                state(bpy.context)
                if reconcile(bpy.context, s):
                    busy = True
                    if time.perf_counter() < deadline:
                        scan_step(bpy.context, s, budget=max(0, deadline-time.perf_counter()))
        except Exception as exc:
            s.job = None
            s.error = f'{type(exc).__name__}: {exc}'
            s.retry_at = time.monotonic() + 2
            trace(s, 'error', message=s.error, traceback=traceback.format_exc())
            try:
                with bpy.context.temp_override(window=window, area=area, region=region):
                    set_status(bpy.context, s, 'ERROR', s.error)
            except (ReferenceError, RuntimeError):
                pass
    for key in tuple(SESSIONS):
        if key not in live:
            trace(SESSIONS[key], 'retired')
            del SESSIONS[key]
    for wm in bpy.data.window_managers:
        if hasattr(wm, 'mbt_stats_sessions'):
            for index in reversed(range(len(wm.mbt_stats_sessions))):
                if wm.mbt_stats_sessions[index].name not in live:
                    wm.mbt_stats_sessions.remove(index)
    return 0.02 if busy else POLL_INTERVAL


def ensure_controller():
    if _enabled and not bpy.app.background and not bpy.app.timers.is_registered(controller):
        bpy.app.timers.register(controller, first_interval=0.02, persistent=True)


def watch(context):
    """Request deferred RNA initialization and recover a missing controller.

    Timer registration does not mutate scene/UI datablocks. Creating the actual
    collection item remains deferred to the timer, outside Blender's draw lock.
    """
    key = editor_key(context)
    if key not in SESSIONS:
        SESSIONS[key] = Session(key)
        trace(SESSIONS[key], 'requested_from_panel')
    ensure_controller()


def diagnostics():
    return {'timer_registered': bpy.app.timers.is_registered(controller),
            'heartbeat': _heartbeat,
            'sessions': {key: {'binding': s.binding, 'requested': s.requested,
                'committed': s.committed, 'scanning': s.job['revision'] if s.job else None,
                'position': s.job['position'] if s.job else None, 'reason': s.reason,
                'error': s.error, 'commits': s.commits} for key, s in SESSIONS.items()},
            'trace': list(TRACE)}


@persistent
def invalidate(scene=None, depsgraph=None):
    if scene is None:
        return
    # Scene/Object selection-only tags are not measurement changes.
    relevant = depsgraph is None or any(
        (update.is_updated_geometry or update.is_updated_transform)
        if isinstance(update.id, bpy.types.Object) else not isinstance(update.id, bpy.types.Scene)
        for update in depsgraph.updates)
    if relevant:
        uid = str(scene.session_uid)
        _scene_revisions[uid] = _scene_revisions.get(uid, 0) + 1


@persistent
def frame_changed(scene, *args):
    invalidate(scene)


def selection_notice():
    # Poll is authoritative, message bus only reduces perceived latency via redraw.
    for window, area, region in viewport_contexts():
        area.tag_redraw()


def subscribe_selection():
    bpy.msgbus.clear_by_owner(_selection_owner)
    bpy.msgbus.subscribe_rna(key=(bpy.types.LayerObjects, 'active'), owner=_selection_owner,
                            args=(), notify=selection_notice)


@persistent
def reset(*args):
    SESSIONS.clear()
    _scene_revisions.clear()
    for wm in bpy.data.window_managers:
        if hasattr(wm, 'mbt_stats_sessions'):
            wm.mbt_stats_sessions.clear()
    trace(None, 'reset')


@persistent
def restore(*args):
    reset()
    subscribe_selection()
    ensure_controller()


HANDLERS = ((bpy.app.handlers.depsgraph_update_post, invalidate),
            (bpy.app.handlers.frame_change_post, frame_changed),
            (bpy.app.handlers.undo_post, restore), (bpy.app.handlers.redo_post, restore),
            (bpy.app.handlers.load_pre, reset), (bpy.app.handlers.load_post, restore))


def register():
    global _enabled
    bpy.types.WindowManager.mbt_stats_sessions = CollectionProperty(type=MBT_StatsState, options={'SKIP_SAVE'})
    _enabled = True
    for handlers, callback in HANDLERS:
        if callback not in handlers:
            handlers.append(callback)
    restore()


def unregister():
    global _enabled
    _enabled = False
    if bpy.app.timers.is_registered(controller):
        bpy.app.timers.unregister(controller)
    bpy.msgbus.clear_by_owner(_selection_owner)
    reset()
    for handlers, callback in HANDLERS:
        if callback in handlers:
            handlers.remove(callback)
    if hasattr(bpy.types.WindowManager, 'mbt_stats_sessions'):
        del bpy.types.WindowManager.mbt_stats_sessions