"""Viewport-local diagnostic overlay. Never changes materials or attributes."""

import bpy
from bpy.app.handlers import persistent

from . import mesh


_views = {}
_cache = {}
_handlers = []
_shader = None
_sessions = []


def invalidate(*args):
    _cache.clear()
    redraw()


def redraw():
    if not hasattr(bpy.data, 'window_managers'):
        return
    for manager in bpy.data.window_managers:
        for window in manager.windows:
            for area in window.screen.areas:
                if area.type == 'VIEW_3D':
                    area.tag_redraw()


def mode(context):
    return _views.get(context.area.as_pointer(), 'OFF') if context.area else 'OFF'


def set_mode(context, value):
    if context.area is None or context.area.type != 'VIEW_3D':
        raise ValueError('Preview requires a 3D Viewport')
    if value == 'OFF':
        _views.pop(context.area.as_pointer(), None)
    else:
        _views[context.area.as_pointer()] = value
    invalidate()


def diagnostic_color(color, component, space):
    if component == 'RGB':
        return (*mesh.convert(color, to_srgb=True)[:3], 1.0)
    values = mesh.convert(color, to_srgb=True) if space == 'SRGB' else color
    value = max(0.0, min(1.0, values['RGBA'.index(component)]))
    return (value, value, value, 1.0)


def geometry(obj, depsgraph, name, component, space):
    """Copy evaluated positions/colors; release the temporary mesh on every path."""
    if obj.data.is_editmode:
        obj.update_from_editmode()
    evaluated = obj.evaluated_get(depsgraph)
    temporary = evaluated.to_mesh(preserve_all_data_layers=True, depsgraph=depsgraph)
    try:
        attribute = temporary.color_attributes.get(name)
        if attribute is None:
            raise ValueError(f'{obj.name}: evaluated mesh has no "{name}" attribute')
        temporary.calc_loop_triangles()
        positions, colors = [], []
        for triangle in temporary.loop_triangles:
            if temporary.polygons[triangle.polygon_index].hide:
                continue
            for loop_index in triangle.loops:
                vertex = temporary.loops[loop_index].vertex_index
                index = vertex if attribute.domain == 'POINT' else loop_index
                positions.append(tuple(temporary.vertices[vertex].co))
                colors.append(diagnostic_color(tuple(attribute.data[index].color), component, space))
        return positions, colors
    finally:
        evaluated.to_mesh_clear()


def _draw():
    global _shader
    context = bpy.context
    component = mode(context)
    if component == 'OFF' or not hasattr(context.scene, 'mbt_vertex_color'):
        return
    if context.space_data.shading.type != 'SOLID':
        return
    attribute = mesh.active_attribute(context)
    if attribute is None:
        return
    name = attribute.name
    import gpu
    from gpu_extras.batch import batch_for_shader
    settings = context.scene.mbt_vertex_color
    try:
        objects = mesh.targets(context, settings, unique=False)
    except ValueError:
        return
    if _shader is None:
        _shader = gpu.shader.from_builtin('SMOOTH_COLOR')
    previous = (gpu.state.depth_test_get(), gpu.state.depth_mask_get(), gpu.state.blend_get())
    try:
        gpu.state.depth_test_set('LESS_EQUAL')
        gpu.state.depth_mask_set(False)
        gpu.state.blend_set('NONE')
        depsgraph = context.evaluated_depsgraph_get()
        for obj in objects:
            if not obj.visible_get(view_layer=context.view_layer, viewport=context.space_data):
                continue
            key = (context.view_layer.as_pointer(), obj.as_pointer(), name,
                   component, settings.space)
            if key not in _cache:
                try:
                    positions, colors = geometry(obj, depsgraph, name, component, settings.space)
                    _cache[key] = (batch_for_shader(_shader, 'TRIS', {'pos': positions, 'color': colors})
                                   if positions else None, '')
                except (ValueError, RuntimeError, ReferenceError) as exc:
                    _cache[key] = (None, str(exc))
            batch, error = _cache[key]
            if batch:
                with gpu.matrix.push_pop():
                    gpu.matrix.multiply_matrix(obj.matrix_world)
                    _shader.bind()
                    batch.draw(_shader)
    finally:
        gpu.state.depth_test_set(previous[0])
        gpu.state.depth_mask_set(previous[1])
        gpu.state.blend_set(previous[2])


def _label():
    context = bpy.context
    component = mode(context)
    if component == 'OFF':
        return
    import blf
    attribute = mesh.active_attribute(context)
    text = f'Vertex Color · {attribute.name if attribute else "No attribute"} · {component}'
    if context.space_data.shading.type != 'SOLID':
        text += ' — switch to Solid shading'
    errors = [error for batch, error in _cache.values() if error]
    if errors:
        text += ' — ' + errors[0]
    blf.position(0, 24, 48, 0)
    blf.size(0, 14 * context.preferences.system.ui_scale)
    blf.color(0, 1, 1, 1, 1)
    blf.draw(0, text)


@persistent
def _depsgraph(scene, depsgraph):
    if _views and any(update.is_updated_geometry for update in depsgraph.updates):
        invalidate()


@persistent
def reset(*args):
    for transaction in tuple(_sessions):
        transaction.restore()
    _sessions.clear()
    _views.clear()
    invalidate()


def register():
    if not bpy.app.background:
        try:
            _handlers.append(bpy.types.SpaceView3D.draw_handler_add(_draw, (), 'WINDOW', 'POST_VIEW'))
            _handlers.append(bpy.types.SpaceView3D.draw_handler_add(_label, (), 'WINDOW', 'POST_PIXEL'))
        except Exception:
            unregister()
            raise
    bpy.app.handlers.depsgraph_update_post.append(_depsgraph)
    bpy.app.handlers.load_pre.append(reset)
    bpy.app.handlers.undo_pre.append(reset)
    bpy.app.handlers.redo_pre.append(reset)


def unregister():
    global _shader
    reset()
    for handler in _handlers:
        bpy.types.SpaceView3D.draw_handler_remove(handler, 'WINDOW')
    _handlers.clear()
    _shader = None
    for collection, function in ((bpy.app.handlers.depsgraph_update_post, _depsgraph),
                                 (bpy.app.handlers.load_pre, reset),
                                 (bpy.app.handlers.undo_pre, reset),
                                 (bpy.app.handlers.redo_pre, reset)):
        if function in collection:
            collection.remove(function)