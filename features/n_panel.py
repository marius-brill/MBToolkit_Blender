"""Preferences-only management of Python-defined 3D View sidebar categories."""

import bpy
import traceback
from bpy.props import BoolProperty, EnumProperty, IntProperty

from ..core.addon import get_prefs
from ..core.sidebar_data import MBT_NPanelTab
from ..core.registry import register_classes, unregister_classes, registration_owner


_originals = {}
_signature = None
_pending = False
_running = False
_error = ''
_MISSING = object()


def panel_classes():
    """Include indirect subclasses; ignore stale classes left by add-on reloads."""
    found, seen = [], set()

    def visit(base):
        for cls in base.__subclasses__():
            if cls in seen:
                continue
            seen.add(cls)
            if (getattr(cls, 'is_registered', False) and
                    'bl_rna' in cls.__dict__ and
                    getattr(cls, 'bl_space_type', '') == 'VIEW_3D' and
                    getattr(cls, 'bl_region_type', '') == 'UI'):
                found.append(cls)
            visit(cls)

    visit(bpy.types.Panel)
    return found


def panel_id(cls):
    return getattr(cls, 'bl_idname', '') or cls.__name__


def ordered_classes(panels):
    """Parents must register first, even when declared after their children."""
    result, remaining = [], list(panels)
    ids = {panel_id(cls) for cls in remaining}
    while remaining:
        ready = [cls for cls in remaining
                 if getattr(cls, 'bl_parent_id', '') not in ids]
        if not ready:
            raise RuntimeError('Cyclic sidebar panel parent relationship')
        for cls in ready:
            result.append(cls)
            remaining.remove(cls)
            ids.remove(panel_id(cls))
    return result


def roots(panels):
    return [cls for cls in panels if not getattr(cls, 'bl_parent_id', '')
            and getattr(cls, 'bl_category', '')]


def refresh(prefs):
    """Keep unavailable tabs in preferences so their saved settings survive."""
    panels = panel_classes()
    categories = ['Item']
    for cls in sorted(roots(panels), key=lambda cls: _original_order(cls)):
        category = cls.bl_category
        if category not in categories:
            categories.append(category)
    existing = {item.name for item in prefs.n_panel_tabs}
    for category in categories:
        if category not in existing:
            item = prefs.n_panel_tabs.add()
            item.name = category
    # Item includes a native panel and cannot be hidden with the Python API.
    index = next(i for i, item in enumerate(prefs.n_panel_tabs) if item.name == 'Item')
    if index:
        prefs.n_panel_tabs.move(index, 0)
    return panels


def _original_order(cls):
    for base in cls.__mro__:
        value = (_originals[base]['order'] if base in _originals else
                 base.__dict__.get('bl_order', _MISSING))
        if value is not _MISSING:
            return value
    return 0


def _original_poll(cls):
    # A newly enabled panel can inherit from an already wrapped panel class.
    for base in cls.__mro__:
        value = (_originals[base]['poll'] if base in _originals else
                 base.__dict__.get('poll', _MISSING))
        if value is not _MISSING:
            return value.__get__(None, cls) if hasattr(value, '__get__') else value
    return None


def _set_attribute(cls, name, value):
    if value is _MISSING:
        if name in cls.__dict__:
            delattr(cls, name)
    else:
        setattr(cls, name, value)


def _restore_attributes():
    errors = []
    for cls, original in _originals.items():
        for name, value in (('poll', original['poll']), ('bl_order', original['order'])):
            try:
                _set_attribute(cls, name, value)
            except Exception as exc:
                errors.append(f'{panel_id(cls)}.{name}: {exc}')
    if errors:
        raise RuntimeError('; '.join(errors))


def _register_panel(cls):
    # Preserve explicit ownership; infer implicit ownership from the enabled
    # defining package, not whichever add-on happened to run the timer.
    with registration_owner(cls.__module__, getattr(cls, 'bl_owner_id', None)):
        bpy.utils.register_class(cls)


def _visible_poll(category, original):
    def poll(cls, context):
        prefs = get_prefs(context)
        if prefs is not None and prefs.n_panel_enabled:
            item = prefs.n_panel_tabs.get(category)
            if item is not None and not item.visible:
                return False
        return bool(original(context)) if original is not None else True
    return classmethod(poll)


def redraw():
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type in {'VIEW_3D', 'PREFERENCES'}:
                area.tag_redraw()


def _affected(panels, managed):
    """Only rebuild managed roots and their registered descendants; leave Item alone."""
    ids = {panel_id(cls) for cls in managed}
    selected = set(managed)
    for cls in ordered_classes(panels):
        if getattr(cls, 'bl_parent_id', '') in ids:
            selected.add(cls)
            ids.add(panel_id(cls))
    return ordered_classes(sorted((cls for cls in panels if cls in selected), key=_original_order))


def _rebuild(ordered, configure):
    """Recover every removed class independently if a third-party class fails."""
    removed = []
    try:
        for cls in reversed(ordered):
            bpy.utils.unregister_class(cls)
            removed.append(cls)
        configure()
        for cls in ordered:
            _register_panel(cls)
    except Exception as exc:
        errors = []
        for cls in reversed(ordered):
            if cls in removed and cls.is_registered:
                try:
                    bpy.utils.unregister_class(cls)
                except Exception as cleanup_exc:
                    errors.append(f'{panel_id(cls)}: {cleanup_exc}')
        try:
            _restore_attributes()
        except Exception as attributes_exc:
            errors.append(str(attributes_exc))
        for cls in ordered:
            if cls in removed and not cls.is_registered:
                try:
                    _register_panel(cls)
                except Exception as recovery_exc:
                    errors.append(f'{panel_id(cls)}: {recovery_exc}')
        detail = '; recovery failures: ' + '; '.join(errors) if errors else ''
        raise RuntimeError(f'{exc}{detail}') from exc


def apply(prefs):
    """Rebuild registered panel types, with rollback if a third-party panel fails."""
    global _signature, _error
    panels = refresh(prefs)
    # Capture only roots: descendants keep their own ordering and poll methods.
    managed = [cls for cls in roots(panels) if cls.bl_category != 'Item']
    ordered = _affected(panels, managed)
    for cls in managed:
        if cls not in _originals:
            _originals[cls] = {
                'poll': cls.__dict__.get('poll', _MISSING),
                'order': cls.__dict__.get('bl_order', _MISSING),
                'bound_poll': _original_poll(cls),
            }
    # No API is used to reach native PanelType memory; native Item stays first.
    def configure():
        _restore_attributes()
        if prefs.n_panel_enabled:
            rank = {item.name: i for i, item in enumerate(prefs.n_panel_tabs)}
            for cls in managed:
                cls.bl_order = rank[cls.bl_category]
                cls.poll = _visible_poll(cls.bl_category, _originals[cls]['bound_poll'])
    try:
        _rebuild(ordered, configure)
    except Exception as exc:
        _error = f'Tab manager stopped: {exc}'
        prefs.n_panel_enabled = False
        raise
    if not prefs.n_panel_enabled:
        _originals.clear()
    _signature = tuple(panels)
    _error = ''
    redraw()


def restore():
    """Only re-register classes still enabled; never revive a disabled add-on."""
    global _signature
    if _originals:
        panels = panel_classes()
        ordered = _affected(panels, [cls for cls in panels if cls in _originals])
        _rebuild(ordered, _restore_attributes)
        _originals.clear()
    _signature = None
    redraw()


def changed(self, context):
    global _pending
    _pending = True
    if context is not None:
        context.preferences.is_dirty = True


def _tick():
    global _pending, _error, _signature
    if not _running:
        return None
    prefs = get_prefs()
    if prefs is None:
        return 0.5
    try:
        panels = panel_classes()
        if _pending or (prefs.n_panel_enabled and tuple(panels) != _signature):
            _pending = False
            if prefs.n_panel_enabled:
                apply(prefs)
            else:
                restore()
        elif not prefs.n_panel_tabs:
            refresh(prefs)
    except Exception as exc:
        _error = f'Tab manager: {exc}'
        traceback.print_exc()
        print(_error)
    return 1.0


class MBT_OT_n_panel(bpy.types.Operator):
    bl_idname = 'mbt.n_panel'
    bl_label = 'Manage Sidebar Tabs'
    bl_options = {'INTERNAL'}

    action: EnumProperty(items=[(x, x.title(), '') for x in ('REFRESH', 'UP', 'DOWN', 'RESET')])
    index: IntProperty(default=-1)

    def execute(self, context):
        global _pending
        prefs = get_prefs(context)
        if prefs is None:
            return {'CANCELLED'}
        try:
            if self.action == 'RESET':
                restore()
                prefs.n_panel_tabs.clear()
                prefs.n_panel_enabled = False
                refresh(prefs)
            else:
                refresh(prefs)
                if self.action in {'UP', 'DOWN'}:
                    target = self.index + (-1 if self.action == 'UP' else 1)
                    if not (1 <= self.index < len(prefs.n_panel_tabs) and
                            1 <= target < len(prefs.n_panel_tabs)):
                        return {'CANCELLED'}
                    prefs.n_panel_tabs.move(self.index, target)
                if prefs.n_panel_enabled:
                    apply(prefs)
            _pending = False
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        context.preferences.is_dirty = True
        redraw()
        return {'FINISHED'}


def draw_preferences(layout, prefs):
    layout.prop(prefs, 'n_panel_enabled')
    row = layout.row(align=True)
    row.operator('mbt.n_panel', text='Refresh', icon='FILE_REFRESH').action = 'REFRESH'
    row.operator('mbt.n_panel', text='Restore Defaults', icon='LOOP_BACK').action = 'RESET'
    layout.label(text='Whole 3D Viewport tabs only. No individual panel controls.')
    layout.label(text='Item is fixed: it contains native Blender controls.', icon='INFO')
    if _error:
        layout.label(text=_error, icon='ERROR')
    available = {cls.bl_category for cls in roots(panel_classes())} | {'Item'}
    box = layout.box()
    if not prefs.n_panel_tabs:
        box.label(text='Click Refresh to discover sidebar tabs.')
    for index, item in enumerate(prefs.n_panel_tabs):
        row = box.row(align=True)
        row.enabled = prefs.n_panel_enabled and item.name in available
        toggle = row.row(align=True)
        toggle.enabled = item.name != 'Item'
        toggle.prop(item, 'visible', text='', icon='HIDE_OFF' if item.visible else 'HIDE_ON')
        row.label(text=item.name + (' (unavailable)' if item.name not in available else ''))
        for action, icon, allowed in (
                ('UP', 'TRIA_UP', index > 1),
                ('DOWN', 'TRIA_DOWN', 0 < index < len(prefs.n_panel_tabs) - 1)):
            button = row.row(align=True)
            button.enabled = allowed
            op = button.operator('mbt.n_panel', text='', icon=icon)
            op.action, op.index = action, index
    layout.label(text='Save Preferences to retain visibility and ordering across restarts.')


classes = (MBT_NPanelTab, MBT_OT_n_panel)


def register():
    global _running
    register_classes((MBT_OT_n_panel,))
    _running = True
    bpy.app.timers.register(_tick, first_interval=0.5, persistent=True)


def unregister():
    global _running, _pending, _error
    _running = False
    if bpy.app.timers.is_registered(_tick):
        bpy.app.timers.unregister(_tick)
    restore()
    _pending = False
    _error = ''
    unregister_classes((MBT_OT_n_panel,))