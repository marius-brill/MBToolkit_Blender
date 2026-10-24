"""Native Modifier Properties, favorites, overview and bottom-relative pins."""

from types import SimpleNamespace
from functools import lru_cache
import math
import bpy
from bpy.app.handlers import persistent
from bpy.props import CollectionProperty, IntProperty, StringProperty, BoolProperty, EnumProperty

from ..core.addon import get_prefs
from ..core.gn import modifier_inputs, legacy_modifier_input_exists
from ..core.registry import register_classes, unregister_classes

INDEX_PROPERTY = 'mbt_modifier_index'
SUPPORTED_TYPES = {'MESH', 'CURVE', 'CURVES', 'FONT', 'SURFACE', 'LATTICE',
                   'VOLUME', 'POINTCLOUD', 'GREASEPENCIL', 'EMPTY'}
CATEGORIES = ('Edit', 'Generate', 'Deform', 'Normals', 'Physics', 'Color')
_native_draw = None
_native_panel = None
_busy = False
_blocked = set()
_keymap_items = []
_expanded_selection = {}
_modifier_timings = {}


def _timing_key(scene, view_layer, obj):
    return (scene.session_uid, view_layer.name, obj.session_uid)


def _capture_timings(depsgraph, objects):
    """Copy native evaluation timings; never evaluate geometry or retain evaluated IDs."""
    changed = False
    for obj in objects:
        key = _timing_key(depsgraph.scene.original, depsgraph.view_layer, obj)
        try:
            values = {}
            for modifier in obj.evaluated_get(depsgraph).modifiers:
                seconds = modifier.execution_time
                values[modifier.persistent_uid] = (
                    seconds * 1000.0 if modifier.show_viewport
                    and math.isfinite(seconds) and seconds >= 0 else None)
            if _modifier_timings.get(key) != values:
                _modifier_timings[key] = values
                changed = True
        except (ReferenceError, RuntimeError):
            changed = _modifier_timings.pop(key, None) is not None or changed
    if changed:
        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                if area.type in {'PROPERTIES', 'VIEW_3D'}:
                    area.tag_redraw()


@persistent
def _timings_changed(scene, depsgraph):
    if depsgraph.mode != 'VIEWPORT':
        return
    objects = {}
    for update in depsgraph.updates:
        obj = update.id.original
        if isinstance(obj, bpy.types.Object) and update.is_updated_geometry:
            objects[obj.session_uid] = obj
    _capture_timings(depsgraph, objects.values())


@persistent
def _frame_timings_changed(scene, depsgraph):
    if depsgraph.mode == 'VIEWPORT':
        _capture_timings(depsgraph, (obj.original for obj in depsgraph.objects))


def _init_timings():
    # One-shot initialization after registration/load/undo, never a polling timer.
    if bpy.context.view_layer is not None:
        depsgraph = bpy.context.evaluated_depsgraph_get()
        _frame_timings_changed(depsgraph.scene, depsgraph)
    return None


def _timing_label(context, obj, modifier):
    values = _modifier_timings.get(_timing_key(context.scene, context.view_layer, obj), {})
    ms = values.get(modifier.persistent_uid) if modifier.show_viewport else None
    return f'{ms:.2f} ms' if ms is not None else '— ms'


def _editable(obj):
    return obj is not None and obj.is_editable


def _get_index(obj):
    return next((i for i, m in enumerate(obj.modifiers) if m == obj.modifiers.active), 0)


def _set_index(obj, index):
    if _editable(obj) and 0 <= index < len(obj.modifiers):
        try:
            obj.modifiers.active = obj.modifiers[index]
            _sync_expanded_selection(obj)
        except (AttributeError, TypeError, ValueError, RuntimeError):
            pass


def _sync_expanded_selection(obj):
    """Follow selection once, without overwriting manual expansion on every draw."""
    if not _editable(obj) or not hasattr(obj, 'modifiers'):
        return
    active = obj.modifiers.active
    signature = (active.persistent_uid if active else None,
                 tuple(m.persistent_uid for m in obj.modifiers))
    if _expanded_selection.get(obj.session_uid) == signature:
        return
    for modifier in obj.modifiers:
        if not modifier.is_property_readonly('show_expanded'):
            modifier.show_expanded = modifier == active
    _expanded_selection[obj.session_uid] = signature


class MBT_ModifierLock(bpy.types.PropertyGroup):
    uid: IntProperty()
    index: IntProperty(min=0)
    from_bottom: BoolProperty(default=False)
    native_pin: BoolProperty(default=False)


def _sync_native_pins(obj):
    """Native pins are authoritative; custom pins retain other bottom offsets."""
    mods = {m.persistent_uid: m for m in obj.modifiers}
    for i in reversed(range(len(obj.mbt_modifier_locks))):
        lock = obj.mbt_modifier_locks[i]
        modifier = mods.get(lock.uid)
        if modifier is None or (lock.native_pin and not modifier.use_pin_to_last):
            obj.mbt_modifier_locks.remove(i)
    locks = {p.uid: p for p in obj.mbt_modifier_locks}
    for uid, modifier in mods.items():
        if modifier.use_pin_to_last:
            lock = locks.get(uid)
            if lock is None:
                lock = obj.mbt_modifier_locks.add()
                lock.uid = uid
            lock.index, lock.from_bottom, lock.native_pin = 0, True, True
        elif uid in locks and locks[uid].index == 0 and not locks[uid].native_pin:
            # Upgrade saved last-position locks to Blender's native pin.
            modifier.use_pin_to_last = True
            locks[uid].native_pin = True


def _migrate_locks(obj):
    for lock in obj.mbt_modifier_locks:
        if not lock.from_bottom:
            modifier = next((m for m in obj.modifiers if m.persistent_uid == lock.uid), None)
            if modifier is not None:
                lock.index = len(obj.modifiers) - 1 - list(obj.modifiers).index(modifier)
            lock.from_bottom = True


def _signature(obj):
    return (obj.session_uid, tuple((m.persistent_uid, m.use_pin_to_last) for m in obj.modifiers),
            tuple((p.uid, p.index, p.from_bottom) for p in obj.mbt_modifier_locks))


def enforce_locks(obj):
    """Build one target permutation, retaining the unlocked modifiers' order."""
    if not _editable(obj):
        return
    _migrate_locks(obj)
    _sync_native_pins(obj)
    if not obj.mbt_modifier_locks:
        return
    mods = list(obj.modifiers)
    by_uid = {m.persistent_uid: m for m in mods}
    for i in reversed(range(len(obj.mbt_modifier_locks))):
        if obj.mbt_modifier_locks[i].uid not in by_uid:
            obj.mbt_modifier_locks.remove(i)
    if not mods:
        return
    signature = _signature(obj)
    if signature in _blocked:
        return
    target = [None] * len(mods)
    locked = set()
    for lock in sorted(obj.mbt_modifier_locks, key=lambda p: (p.index, not p.native_pin, p.uid)):
        if lock.uid in locked:
            continue
        desired = max(0, len(mods)-1-lock.index)
        available = [i for i, item in enumerate(target) if item is None]
        slot = min(available, key=lambda i: (abs(i-desired), i))
        target[slot] = by_uid[lock.uid]
        locked.add(lock.uid)
    remaining = iter(m for m in mods if m.persistent_uid not in locked)
    target = [m if m is not None else next(remaining) for m in target]
    if target == mods:
        return
    native_pins = [m for m in mods if m.use_pin_to_last]
    try:
        # The final permutation preserves native pins. Temporarily release their
        # move restriction so custom second-last/etc. pins can be restored too.
        for modifier in native_pins:
            modifier.use_pin_to_last = False
        for index, modifier in enumerate(target):
            current = list(obj.modifiers).index(modifier)
            if current != index:
                obj.modifiers.move(current, index)
        if list(obj.modifiers) != target:
            raise ValueError('Blender rejected the requested modifier order')
    except (RuntimeError, ValueError, TypeError) as exc:
        _blocked.add(_signature(obj))
        print(f'MBToolkit: cannot enforce modifier locks on {obj.name}: {exc}')
    finally:
        for modifier in native_pins:
            modifier.use_pin_to_last = True


def _enforce_pending():
    global _busy
    if _busy or bpy.app.is_job_running('RENDER'):
        return 0.2
    _busy = True
    try:
        for obj in tuple(bpy.data.objects):
            try:
                enforce_locks(obj)
                _sync_expanded_selection(obj)
            except (ReferenceError, RuntimeError, TypeError, ValueError) as exc:
                print(f'MBToolkit: modifier lock update skipped: {exc}')
        live_objects = {obj.session_uid for obj in bpy.data.objects}
        for key in tuple(_modifier_timings):
            if key[2] not in live_objects:
                del _modifier_timings[key]
    finally:
        _busy = False
    return None


@persistent
def _stack_changed(*args):
    if not _busy and not bpy.app.timers.is_registered(_enforce_pending):
        bpy.app.timers.register(_enforce_pending, first_interval=0.05)


@persistent
def _reset_locks(*args):
    _blocked.clear()
    _expanded_selection.clear()
    _modifier_timings.clear()
    if not bpy.app.timers.is_registered(_init_timings):
        bpy.app.timers.register(_init_timings, first_interval=0.05)
    _stack_changed()


class _Catalog:
    """Read installed native menu definitions without hardcoding compatibility."""
    def __init__(self, category, output):
        self.category, self.output = category, output

    def operator(self, idname, **kwargs):
        entry = {'category': self.category, 'operator': idname, 'args': {},
                 'label': kwargs.get('text', ''), 'icon': kwargs.get('icon', 'MODIFIER')}
        self.output.append(entry)

        class Arguments:
            def __setattr__(self, name, value):
                entry['args'][name] = value
        return Arguments()

    def template_modifier_asset_menu_items(self, **kwargs):
        # Dynamic catalogs are drawn directly in the real overview popup.
        pass


@lru_cache(maxsize=16)
def catalog(obj_type):
    from bl_ui import properties_data_modifier as native
    output = []
    for category in CATEGORIES:
        cls = getattr(native, 'OBJECT_MT_modifier_add_' + category.lower())
        proxy = SimpleNamespace(layout=_Catalog(category, output), bl_label=cls.bl_label,
                                operator_modifier_add=cls.operator_modifier_add,
                                operator_modifier_add_asset=cls.operator_modifier_add_asset)
        draw = cls.draw
        draw_funcs = getattr(draw, '_draw_funcs', None)
        if draw_funcs is not None:
            # Menu.append/prepend wraps draw with real-UI context handling.
            # Read only Blender's definition, not third-party UI callbacks.
            # Prepending means the native function is not necessarily first.
            draw = next(func for func in draw_funcs
                        if func.__module__ == cls.__module__
                        and func.__qualname__ == cls.__name__ + '.draw')
        draw(proxy, SimpleNamespace(object=SimpleNamespace(type=obj_type)))
    if obj_type in {'EMPTY', 'MESH', 'CURVE', 'CURVES', 'FONT', 'VOLUME', 'POINTCLOUD', 'GREASEPENCIL'}:
        output.append({'category': 'Generate', 'operator': 'object.modifier_add',
                       'args': {'type': 'NODES'}, 'label': 'Geometry Nodes', 'icon': 'GEOMETRY_NODES'})
    return output


def entry_key(entry):
    return entry['operator'] + ':' + str(entry['args'].get('type', entry['args'].get('relative_asset_identifier', '')))


def _add_button(layout, entry, obj, text=None):
    op = layout.operator('mbt.modifier_add', text=entry['label'] if text is None else text,
                         icon=entry['icon'])
    op.key = entry_key(entry)
    op.object_name = obj.name


class MBT_OT_modifier_add(bpy.types.Operator):
    bl_idname = 'mbt.modifier_add'
    bl_label = 'Add Modifier'
    bl_options = {'REGISTER', 'UNDO'}
    key: StringProperty()
    object_name: StringProperty()

    def execute(self, context):
        obj = bpy.data.objects.get(self.object_name)
        if not _editable(obj) or obj.mode != 'OBJECT' or obj.name not in context.view_layer.objects:
            self.report({'WARNING'}, 'Target must be an editable Object Mode object in this view layer')
            return {'CANCELLED'}
        entry = next((e for e in catalog(obj.type) if entry_key(e) == self.key), None)
        if entry is None:
            self.report({'WARNING'}, 'Modifier is unavailable for this object')
            return {'CANCELLED'}
        try:
            with context.temp_override(object=obj, active_object=obj, selected_objects=[obj],
                                       selected_editable_objects=[obj]):
                op = bpy.ops.object.modifier_add if entry['operator'] == 'object.modifier_add' else bpy.ops.object.modifier_add_node_group
                result = op('EXEC_DEFAULT', **entry['args'])
            enforce_locks(obj)
            return result
        except (RuntimeError, TypeError, ValueError) as exc:
            self.report({'WARNING'}, str(exc))
            return {'CANCELLED'}


class MBT_OT_modifier_add_menu(bpy.types.Operator):
    bl_idname = 'mbt.modifier_add_menu'
    bl_label = 'Add Modifier'
    bl_description = 'All compatible modifiers arranged by category'

    @classmethod
    def poll(cls, context):
        obj = context.object
        return context.window is not None and _editable(obj) and obj.type in SUPPORTED_TYPES and obj.mode == 'OBJECT'

    def invoke(self, context, event):
        return bpy.ops.wm.call_menu(name='MBT_MT_modifier_overview')

    def execute(self, context):
        return bpy.ops.wm.call_menu(name='MBT_MT_modifier_overview')


class MBT_MT_modifier_overview(bpy.types.Menu):
    bl_idname = 'MBT_MT_modifier_overview'
    bl_label = 'Add Modifier'

    def draw(self, context):
        obj = context.object
        if obj is None:
            return
        entries = catalog(obj.type)
        self.layout.operator_context = 'EXEC_DEFAULT'
        columns = self.layout.row()
        for category in CATEGORIES:
            items = [e for e in entries if e['category'] == category]
            if not items:
                continue
            col = columns.column(align=True)
            col.ui_units_x = 13
            col.label(text=category)
            for entry in items:
                _add_button(col, entry, obj)
            col.template_modifier_asset_menu_items(catalog_path=category)


class MBT_OT_modifier_lock(bpy.types.Operator):
    bl_idname = 'mbt.modifier_lock'
    bl_label = 'Lock Modifier Position'
    bl_description = 'Keep this modifier at its current distance from the bottom (last, second-last, etc.)'
    bl_options = {'REGISTER', 'UNDO'}
    uid: IntProperty()

    def execute(self, context):
        obj = context.object
        if not _editable(obj):
            return {'CANCELLED'}
        _migrate_locks(obj)
        _sync_native_pins(obj)
        for i, lock in enumerate(obj.mbt_modifier_locks):
            if lock.uid == self.uid:
                modifier = next((m for m in obj.modifiers if m.persistent_uid == self.uid), None)
                if modifier is not None and modifier.use_pin_to_last:
                    modifier.use_pin_to_last = False
                obj.mbt_modifier_locks.remove(i)
                _blocked.clear()
                return {'FINISHED'}
        modifier = next((m for m in obj.modifiers if m.persistent_uid == self.uid), None)
        if modifier is None:
            return {'CANCELLED'}
        enforce_locks(obj)
        lock = obj.mbt_modifier_locks.add()
        lock.uid = self.uid
        lock.index = len(obj.modifiers)-1-list(obj.modifiers).index(modifier)
        lock.from_bottom = True
        if lock.index == 0:
            modifier.use_pin_to_last = True
            lock.native_pin = True
        _blocked.clear()
        return {'FINISHED'}


class MBT_OT_modifier_manage(bpy.types.Operator):
    bl_idname = 'mbt.modifier_manage'
    bl_label = 'Manage Modifier'
    bl_options = {'REGISTER', 'UNDO'}
    uid: IntProperty()
    action: EnumProperty(items=[(x, x.title(), '') for x in ('UP', 'DOWN', 'DELETE')])

    def execute(self, context):
        obj = context.object
        if not _editable(obj) or obj.mode != 'OBJECT':
            self.report({'WARNING'}, 'Requires an editable object in Object Mode')
            return {'CANCELLED'}
        enforce_locks(obj)
        modifier = next((m for m in obj.modifiers if m.persistent_uid == self.uid), None)
        if modifier is None:
            return {'CANCELLED'}
        try:
            if self.action == 'DELETE':
                with context.temp_override(object=obj, active_object=obj, selected_objects=[obj],
                                           selected_editable_objects=[obj]):
                    result = bpy.ops.object.modifier_remove(modifier=modifier.name, use_selected_objects=False)
                enforce_locks(obj)
                return result
            locked = {p.uid for p in obj.mbt_modifier_locks}
            if self.uid in locked:
                self.report({'WARNING'}, 'Unpin this modifier before moving it')
                return {'CANCELLED'}
            mods = list(obj.modifiers)
            available = [i for i, m in enumerate(mods) if m.persistent_uid not in locked]
            index = mods.index(modifier)
            position = available.index(index) + (-1 if self.action == 'UP' else 1)
            if not 0 <= position < len(available):
                return {'CANCELLED'}
            obj.modifiers.move(index, available[position])
            enforce_locks(obj)
            obj.modifiers.active = modifier
            return {'FINISHED'}
        except (RuntimeError, TypeError, ValueError) as exc:
            self.report({'WARNING'}, str(exc))
            return {'CANCELLED'}


def _draw_property(layout, obj, modifier, name, **kwargs):
    if name in modifier.bl_rna.properties:
        row = layout.row(align=True)
        row.enabled = _editable(obj) and not modifier.is_property_readonly(name)
        row.prop(modifier, name, **kwargs)


def modifier_icon(modifier):
    """Use Blender's type enum, including types not in the object's add menu."""
    item = bpy.types.Modifier.bl_rna.properties['type'].enum_items_static.get(modifier.type)
    return item.icon if item is not None and item.icon != 'NONE' else 'MODIFIER'


def favorite_rows(favorites):
    """Keep preference order and wrap after four compact buttons."""
    for start in range(0, len(favorites), 4):
        yield favorites[start:start + 4]


def draw_active_settings(layout, context):
    obj = context.object
    modifier = obj.modifiers.active if obj is not None else None
    if modifier is None:
        return
    box = layout.box()
    box.context_pointer_set('modifier', modifier)
    box.label(text=modifier.name, icon=modifier_icon(modifier))
    box.enabled = _editable(obj)
    box.use_property_split = True
    box.use_property_decorate = True
    _draw_property(box, obj, modifier, 'use_pin_to_last', text='Pin to Last')
    # Native modifier panels are C-defined and template_modifiers draws the
    # entire stack. RNA provides a supported, shared single-modifier editor.
    hidden = set(bpy.types.Modifier.bl_rna.properties.keys())
    for prop in modifier.bl_rna.properties:
        name = prop.identifier
        if modifier.type == 'NODES' and name == 'properties':
            continue  # Dynamic inputs have a dedicated, type-aware drawer.
        if name in hidden or prop.is_hidden or prop.is_readonly or prop.type == 'COLLECTION':
            continue
        if prop.type == 'POINTER' and getattr(modifier, name, None) is not None:
            value = getattr(modifier, name)
            if not isinstance(value, bpy.types.ID):
                if isinstance(value, bpy.types.CurveMapping):
                    box.template_curve_mapping(modifier, name)
                else:
                    _draw_embedded_settings(box, value, prop.name)
                continue
        box.prop(modifier, name)
    if modifier.type == 'NODES':
        _draw_node_inputs(box, modifier)


def _draw_embedded_settings(layout, settings, label):
    """Expose nested RNA values without traversing ID links or recursive owners."""
    box = layout.box()
    box.label(text=label)
    for prop in settings.bl_rna.properties:
        if (prop.identifier == 'rna_type' or prop.is_hidden or prop.is_readonly
                or prop.type in {'POINTER', 'COLLECTION'}):
            continue
        box.prop(settings, prop.identifier)


class MBT_OT_modifier_render_toggle(bpy.types.Operator):
    bl_idname = 'mbt.modifier_render_toggle'
    bl_label = 'Show Modifier in Render'
    bl_description = 'Toggle render evaluation of this modifier'
    bl_options = {'REGISTER', 'UNDO'}
    uid: IntProperty()

    def execute(self, context):
        obj = context.object
        if not _editable(obj):
            return {'CANCELLED'}
        modifier = next((m for m in obj.modifiers if m.persistent_uid == self.uid), None)
        if modifier is None or modifier.is_property_readonly('show_render'):
            return {'CANCELLED'}
        modifier.show_render = not modifier.show_render
        return {'FINISHED'}


class MBT_OT_modifier_viewport_toggle(bpy.types.Operator):
    bl_idname = 'mbt.modifier_viewport_toggle'
    bl_label = 'Show Modifier in Viewport'
    bl_description = 'Toggle realtime evaluation of this modifier'
    bl_options = {'REGISTER', 'UNDO'}
    uid: IntProperty()

    def execute(self, context):
        obj = context.object
        if not _editable(obj):
            return {'CANCELLED'}
        modifier = next((m for m in obj.modifiers if m.persistent_uid == self.uid), None)
        if modifier is None or modifier.is_property_readonly('show_viewport'):
            return {'CANCELLED'}
        modifier.show_viewport = not modifier.show_viewport
        return {'FINISHED'}


def _draw_node_inputs(layout, modifier):
    group = modifier.node_group
    if group is None:
        return
    inputs = modifier_inputs(modifier)
    for socket in group.interface.items_tree:
        if socket.item_type != 'SOCKET' or socket.in_out != 'INPUT' or socket.hide_in_modifier:
            continue
        if inputs is not None:
            value = getattr(inputs, socket.identifier, None)
            if value is not None and 'value' in value.bl_rna.properties:
                layout.prop(value, 'value', text=socket.name)
            # Geometry/non-value sockets and incomplete RNA are not legacy data.
            continue
        if legacy_modifier_input_exists(modifier, socket.identifier):
            layout.prop(modifier, '["' + socket.identifier + '"]', text=socket.name)


class MBT_UL_modifiers(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index=0, flt_flag=0):
        if item is None:
            return
        if self.layout_type == 'GRID':
            layout.label(text=_timing_label(context, data, item), icon=modifier_icon(item))
            return
        row = layout.row(align=True)
        timing = row.row(align=True)
        timing.ui_units_x = 5
        timing.alignment = 'LEFT'
        timing.label(text=_timing_label(context, data, item))
        _draw_property(row, data, item, 'name', text='', emboss=False, icon=modifier_icon(item))
        buttons = row.row(align=True)
        buttons.alignment = 'RIGHT'
        for name, icon in (('show_on_cage', 'MESH_DATA'), ('show_in_editmode', 'EDITMODE_HLT'),
                           ('show_viewport', 'RESTRICT_VIEW_OFF'), ('show_render', 'RESTRICT_RENDER_OFF')):
            if name in {'show_viewport', 'show_render'}:
                sub = buttons.row(align=True)
                sub.enabled = _editable(data) and not item.is_property_readonly(name)
                operator = 'mbt.modifier_viewport_toggle' if name == 'show_viewport' else 'mbt.modifier_render_toggle'
                sub.operator(operator, text='', icon=icon,
                             depress=getattr(item, name)).uid = item.persistent_uid
                continue
            _draw_property(buttons, data, item, name, text='', icon=icon, toggle=True)
        buttons.enabled = _editable(data)
        pinned = item.use_pin_to_last or any(p.uid == item.persistent_uid and not p.native_pin
                                             for p in data.mbt_modifier_locks)
        buttons.operator('mbt.modifier_lock', text='', icon='PINNED' if pinned else 'UNPINNED',
                         depress=pinned).uid = item.persistent_uid
        delete = buttons.row(align=True)
        delete.enabled = _editable(data) and data.mode == 'OBJECT'
        op = delete.operator('mbt.modifier_manage', text='', icon='X')
        op.uid, op.action = item.persistent_uid, 'DELETE'


def draw(layout, context):
    obj = context.object
    if obj is None:
        return
    prefs = get_prefs(context)
    row = layout.row(align=True)
    if prefs is not None:
        entries = {entry_key(e): e for e in catalog(obj.type)}
        favorites = list(prefs.modifier_favorites)
        flow = row.column(align=True)
        for items in favorite_rows(favorites):
            favorite_row = flow.row(align=True)
            for favorite in items:
                sub = favorite_row.row(align=True)
                sub.scale_y = 1.0
                entry = entries.get(favorite.key)
                sub.enabled = entry is not None and _editable(obj) and obj.mode == 'OBJECT'
                if entry:
                    _add_button(sub, entry, obj)
                else:
                    sub.label(text=favorite.label, icon='MODIFIER')
    row.operator('mbt.open_prefs', text='', icon='PREFERENCES')
    layout.operator_context = 'INVOKE_DEFAULT'
    layout.operator('mbt.modifier_add_menu', icon='ADD')
    stack = layout.row()
    stack.template_list('MBT_UL_modifiers', '', obj, 'modifiers', obj, INDEX_PROPERTY, rows=4)
    controls = stack.column(align=True)
    active = obj.modifiers.active
    locked = {p.uid for p in obj.mbt_modifier_locks} | {m.persistent_uid for m in obj.modifiers if m.use_pin_to_last}
    for action, icon in (('UP', 'TRIA_UP'), ('DOWN', 'TRIA_DOWN')):
        sub = controls.row(align=True)
        sub.enabled = (_editable(obj) and obj.mode == 'OBJECT' and active is not None
                       and active.persistent_uid not in locked)
        op = sub.operator('mbt.modifier_manage', text='', icon=icon)
        op.uid, op.action = active.persistent_uid if active else 0, action
    if not _editable(obj):
        layout.label(text='Read-only object', icon='INFO')
    elif obj.mbt_modifier_locks and _signature(obj) in _blocked:
        layout.label(text='Position lock conflicts with native stack restrictions', icon='ERROR')


def _draw_native(self, context):
    draw(self.layout, context)
    self.layout.template_modifiers()


class MBT_OT_modifier_popup(bpy.types.Operator):
    bl_idname = 'mbt.modifier_popup'
    bl_label = 'Modifiers'
    bl_description = 'Open modifier favorites, stack and selected settings inside the viewport'

    @classmethod
    def poll(cls, context):
        return (context.area is not None and context.area.type == 'VIEW_3D'
                and context.object is not None and context.object.type in SUPPORTED_TYPES)

    def invoke(self, context, event):
        return context.window_manager.invoke_popup(self, width=440)

    def draw(self, context):
        draw(self.layout, context)
        draw_active_settings(self.layout, context)

    def execute(self, context):
        return {'FINISHED'}


def rebuild_keymap():
    for km, item in _keymap_items:
        km.keymap_items.remove(item)
    _keymap_items.clear()
    prefs = get_prefs()
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon if wm is not None else None
    if kc is None or prefs is None or prefs.modifier_popup_key == 'NONE':
        return
    km = kc.keymaps.new(name='3D View', space_type='VIEW_3D')
    item = km.keymap_items.new('mbt.modifier_popup', prefs.modifier_popup_key, 'PRESS',
                              shift=prefs.modifier_popup_shift, ctrl=prefs.modifier_popup_ctrl,
                              alt=prefs.modifier_popup_alt, oskey=prefs.modifier_popup_oskey)
    _keymap_items.append((km, item))


def _init_keymap():
    rebuild_keymap()
    return None


classes = (MBT_ModifierLock, MBT_UL_modifiers, MBT_OT_modifier_add,
           MBT_MT_modifier_overview, MBT_OT_modifier_add_menu, MBT_OT_modifier_lock, MBT_OT_modifier_manage,
           MBT_OT_modifier_popup, MBT_OT_modifier_viewport_toggle, MBT_OT_modifier_render_toggle)


def register():
    global _native_panel, _native_draw
    register_classes(classes)
    bpy.types.Object.mbt_modifier_index = IntProperty(get=_get_index, set=_set_index, min=0, options={'SKIP_SAVE'})
    bpy.types.Object.mbt_modifier_locks = CollectionProperty(type=MBT_ModifierLock)
    from bl_ui.properties_data_modifier import DATA_PT_modifiers
    _native_panel = DATA_PT_modifiers
    _native_draw = DATA_PT_modifiers.draw
    DATA_PT_modifiers.draw = _draw_native
    bpy.app.handlers.depsgraph_update_post.append(_stack_changed)
    bpy.app.handlers.depsgraph_update_post.append(_timings_changed)
    bpy.app.handlers.frame_change_post.append(_frame_timings_changed)
    for handlers in (bpy.app.handlers.load_post, bpy.app.handlers.undo_post, bpy.app.handlers.redo_post):
        handlers.append(_reset_locks)
    _stack_changed()
    bpy.app.timers.register(_init_keymap, first_interval=0.2)
    bpy.app.timers.register(_init_timings, first_interval=0.05)


def unregister():
    global _native_panel, _native_draw
    if bpy.app.timers.is_registered(_init_keymap):
        bpy.app.timers.unregister(_init_keymap)
    if bpy.app.timers.is_registered(_init_timings):
        bpy.app.timers.unregister(_init_timings)
    for km, item in _keymap_items:
        km.keymap_items.remove(item)
    _keymap_items.clear()
    if _native_panel is not None and _native_panel.draw is _draw_native:
        _native_panel.draw = _native_draw
    _native_panel = _native_draw = None
    for handlers, callback in ((bpy.app.handlers.depsgraph_update_post, _stack_changed),
                              (bpy.app.handlers.depsgraph_update_post, _timings_changed),
                              (bpy.app.handlers.frame_change_post, _frame_timings_changed),
                              (bpy.app.handlers.load_post, _reset_locks),
                              (bpy.app.handlers.undo_post, _reset_locks),
                              (bpy.app.handlers.redo_post, _reset_locks)):
        if callback in handlers:
            handlers.remove(callback)
    if bpy.app.timers.is_registered(_enforce_pending):
        bpy.app.timers.unregister(_enforce_pending)
    _blocked.clear()
    _expanded_selection.clear()
    _modifier_timings.clear()
    catalog.cache_clear()
    del bpy.types.Object.mbt_modifier_locks
    del bpy.types.Object.mbt_modifier_index
    unregister_classes(classes)