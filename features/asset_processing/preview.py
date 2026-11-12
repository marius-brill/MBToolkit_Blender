"""Reversible component visibility preview, scoped to one view layer."""
import bpy
from bpy.app.handlers import persistent

_state = []
_selection = None


def capture_selection(context):
    global _selection
    _selection = (context.view_layer, list(context.selected_objects), context.view_layer.objects.active)


def restore():
    global _state, _selection
    for obj, layer, hidden in _state:
        try:
            obj.hide_set(hidden, view_layer=layer)
        except (ReferenceError, RuntimeError, TypeError):
            pass
    _state = []
    if _selection is not None:
        layer, selected, active = _selection
        _selection = None
        try:
            for obj in layer.objects:
                obj.select_set(obj in selected, view_layer=layer)
            layer.objects.active = active if active and active.name in layer.objects else None
        except (ReferenceError, RuntimeError, TypeError):
            pass


def show(context, component, role):
    from .export import high_objects
    restore()
    objects = list(dict.fromkeys(obj for obj in [component.source, component.low] + high_objects(component) if obj))
    target = [component.source] if role == 'SOURCE' else [component.low] if role == 'LOW' else high_objects(component)
    if not any(target):
        raise ValueError('No mesh is available for that preview')
    layer = context.view_layer
    try:
        for obj in objects:
            if obj.name in layer.objects:
                _state.append((obj, layer, obj.hide_get(view_layer=layer)))
                obj.hide_set(obj not in target, view_layer=layer)
    except Exception:
        restore()
        raise


@persistent
def before_save_or_load(_):
    restore()


@persistent
def discard_uv_proposals(_):
    from .uv import clear_all
    clear_all()


def register():
    for handlers in (bpy.app.handlers.save_pre, bpy.app.handlers.load_pre,
                     bpy.app.handlers.undo_pre, bpy.app.handlers.redo_pre):
        if before_save_or_load not in handlers:
            handlers.append(before_save_or_load)
    for handlers in (bpy.app.handlers.save_pre, bpy.app.handlers.load_pre):
        if discard_uv_proposals not in handlers:
            handlers.append(discard_uv_proposals)


def unregister():
    restore()
    discard_uv_proposals(None)
    for handlers in (bpy.app.handlers.save_pre, bpy.app.handlers.load_pre,
                     bpy.app.handlers.undo_pre, bpy.app.handlers.redo_pre):
        if before_save_or_load in handlers:
            handlers.remove(before_save_or_load)
    for handlers in (bpy.app.handlers.save_pre, bpy.app.handlers.load_pre):
        if discard_uv_proposals in handlers:
            handlers.remove(discard_uv_proposals)