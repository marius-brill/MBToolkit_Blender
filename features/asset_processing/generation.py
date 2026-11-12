"""Bounded DynaBool generation on independent snapshots; never refresh artist lows."""
import hashlib
import math
from contextlib import ExitStack
import bpy
from ...core import gn
from ..geonodes import dynabool
from ..geonodes import resolution
from ..substance_painter.evaluation import available
from ..substance_painter.jobs import singular_transform


def fingerprint(obj):
    """Explicit-operation guard, not a per-redraw mesh scan."""
    digest = hashlib.sha256()
    def add(value):
        digest.update(repr(value).encode('utf-8'))
    add(tuple(tuple(row) for row in obj.matrix_world))
    mesh = obj.data
    for vertex in mesh.vertices:
        add(tuple(vertex.co))
    for polygon in mesh.polygons:
        add((tuple(polygon.vertices), polygon.material_index, polygon.use_smooth))
    for edge in mesh.edges:
        add((tuple(edge.vertices), edge.use_seam))
    for attribute in mesh.attributes:
        if attribute.name == 'position':
            continue
        add((attribute.name, attribute.data_type, attribute.domain))
        for value in attribute.data:
            for field in ('value', 'vector', 'color'):
                if hasattr(value, field):
                    item = getattr(value, field)
                    add(tuple(item) if hasattr(item, '__iter__') else item)
                    break
    add(tuple(material.name_full if material else None for material in mesh.materials))
    for modifier in obj.modifiers:
        add((modifier.type, modifier.name, modifier.show_viewport, modifier.show_render))
        if modifier.type == 'NODES' and modifier.node_group:
            add((modifier.node_group.name, modifier.node_group.get('mbt_rev')))
            add(tuple((node.bl_idname, node.name) for node in modifier.node_group.nodes))
            for node in modifier.node_group.nodes:
                for prop in node.bl_rna.properties:
                    if prop.identifier not in {'location', 'width', 'height', 'select'} and prop.type in {'BOOLEAN', 'INT', 'FLOAT', 'STRING', 'ENUM'}:
                        value = getattr(node, prop.identifier)
                        add((prop.identifier, tuple(value) if getattr(prop, 'is_array', False) else value))
                for socket in node.inputs:
                    if hasattr(socket, 'default_value'):
                        value = socket.default_value
                        add((socket.identifier, tuple(value) if hasattr(value, '__iter__') else value))
            add(tuple((link.from_node.name, link.from_socket.identifier, link.to_node.name,
                       link.to_socket.identifier) for link in modifier.node_group.links))
            for socket in modifier.node_group.interface.items_tree:
                if getattr(socket, 'in_out', '') == 'INPUT' and socket.socket_type != 'NodeSocketGeometry':
                    inputs = gn.modifier_inputs(modifier)
                    add(getattr(inputs, socket.identifier).value if inputs is not None else modifier.get(socket.identifier))
        else:
            # Generated highs have only DynaBool; an added modifier is an artist edit.
            add('foreign modifier')
    return digest.hexdigest()


def owned(obj, component, role):
    return obj is not None and obj.get('mbt_component_id') == component.component_id and obj.get('mbt_asset_role') == role


def discard(obj):
    mesh = obj.data
    bpy.data.objects.remove(obj, do_unlink=True)
    if mesh.users == 0:
        bpy.data.meshes.remove(mesh)


def snapshot(context, source, name):
    depsgraph = context.evaluated_depsgraph_get()
    evaluated = source.evaluated_get(depsgraph)
    mesh = bpy.data.meshes.new_from_object(evaluated, preserve_all_data_layers=True, depsgraph=depsgraph)
    obj = bpy.data.objects.new(name, mesh)
    obj.matrix_world = evaluated.matrix_world.copy()
    context.scene.collection.objects.link(obj)
    return obj


def configure(obj, component):
    modifier = obj.modifiers.new('Asset DynaBool', 'NODES')
    modifier.node_group = dynabool.get_group()
    values = {'Crease Angle': component.crease_angle, 'SubD Level': component.subdivision,
              'Remesh': component.remesh,
              'Voxel Size': obj.get('mbt_resolved_voxel', component.voxel_size) if component.automatic_resolution else component.voxel_size,
              'Resolved Voxel Size': obj.get('mbt_resolved_voxel', 0.0),
              'Automatic Resolution': component.automatic_resolution,
              'Smooth Iterations': component.smoothing, 'Fallback on Failure': False}
    for socket in modifier.node_group.interface.items_tree:
        if getattr(socket, 'in_out', '') == 'INPUT' and socket.name in values:
            gn.set_modifier_input(modifier, socket.identifier, values[socket.name])
    obj.update_tag()


def generate(context, asset, component):
    try:
        result = _generate(context, asset, component)
        component.generation_state = 'Succeeded' if component.high_mode != 'DISABLED' else 'Skipped'
        return result
    except Exception as error:
        component.generation_state = 'Failed'
        name = component.source.name if component.source else component.name
        component.generation_report = f'{name} — Failed: {error}'
        raise


def _generate(context, asset, component):
    source = component.source
    if source is None or source.type != 'MESH' or source.name not in context.scene.objects:
        raise ValueError('Assign a source mesh in this scene')
    if singular_transform(source.matrix_world):
        raise ValueError('Source has a singular transform')
    custom = [reference.mesh for reference in component.highs if reference.mesh]
    if component.high_mode == 'CUSTOM' and (not custom or any(obj == component.low or obj == source or obj.name not in context.scene.objects for obj in custom)):
        raise ValueError('Assign separate custom high meshes before processing')
    previous = component.generated_high
    if previous and previous == source:
        raise ValueError('Source cannot be the generated high; assign a separate source')
    if component.high_mode == 'DYNABOOL' and previous:
        if not owned(previous, component, 'HIGH') or previous.library or previous.data.users != 1:
            raise ValueError('Generated high is shared or not processor-owned; preserve it as Custom High')
        if fingerprint(previous) != component.high_signature:
            raise ValueError('Generated high was edited; preserve it as Custom High instead of overwriting')
    created = []
    from . import tracking
    source_baseline = tracking.source_input(context, component)
    high_baseline = tracking.high_input(context, component) if component.high_mode == 'DYNABOOL' else None
    creating_low = component.low is None
    collection = None
    try:
        with available(context, [source]), ExitStack() as transactions:
            # Existing lows, including edited generated lows, are never refreshed.
            low = component.low
            if low is None:
                low = snapshot(context, source, 'MBT_Work_' + component.component_id[:8] + '_L')
                created.append(low)
            high = None
            if component.high_mode == 'DYNABOOL':
                high = snapshot(context, source, 'MBT_Work_' + component.component_id[:8] + '_H')
                created.append(high)
                if not high.data.polygons or any(not math.isfinite(v) for vertex in high.data.vertices for v in vertex.co):
                    raise ValueError('Source snapshot has empty or non-finite geometry')
                estimate = sum(len(face.vertices) for face in high.data.polygons) * 4 ** max(0, component.subdivision - 1)
                if component.subdivision and estimate > component.max_faces:
                    raise ValueError(f'FACES: subdivision estimate {estimate:,} exceeds limit {component.max_faces:,}; reduce subdivision')
                if component.remesh:
                    resolution.prepare(high.data)
                    # Feature lengths belong to the source, not the smaller edge
                    # segments introduced by the subdivision quality target.
                    source_analysis = resolution.analyze(high.data, component.detail_tolerance, component.crease_angle)
                voxel = 0.0
                high['mbt_resolved_voxel'] = voxel
                configure(high, component)
                modifier = high.modifiers[0]
                remesh_socket = next(s for s in modifier.node_group.interface.items_tree if s.name == 'Remesh')
                gn.set_modifier_input(modifier, remesh_socket.identifier, False)
                high.update_tag()
                context.view_layer.update()
                evaluated = high.evaluated_get(context.evaluated_depsgraph_get())
                mesh = evaluated.to_mesh()
                try:
                    count = len(mesh.polygons)
                    if not count:
                        raise ValueError('SUBDIVISION: empty output')
                    if count > component.max_faces:
                        raise ValueError(f'FACES: subdivision output {count:,} exceeds limit {component.max_faces:,}')
                    analysis = resolution.analyze(mesh, component.detail_tolerance, component.crease_angle) if component.remesh else None
                finally:
                    evaluated.to_mesh_clear()
                gn.set_modifier_input(modifier, remesh_socket.identifier, component.remesh)
                if analysis:
                    voxel = analysis['voxel'] if component.automatic_resolution else component.voxel_size
                error = 0.0
                for attempt in range(4):
                    if not component.remesh:
                        break
                    attempt_info = (f'{"Initial attempt" if attempt == 0 else "Refinement " + str(attempt)}; '
                                    f'voxel {voxel:.6g}; source driver: {source_analysis["driver"]}; '
                                    f'surface driver: {analysis["driver"]}; '
                                    f'dimensions {source_analysis["candidates"]["dimensions"]:.6g}, '
                                    f'tolerance {source_analysis["candidates"]["detail tolerance"]:.6g}, '
                                    f'thickness/gap hint {source_analysis["candidates"]["thickness/gap"]:.6g}, '
                                    f'sharp edge hint {source_analysis["candidates"]["sharp source edge"]:.6g} '
                                    '(hints do not force initial resolution)')
                    if attempt:
                        attempt_info += f'; previous retry reason: {analysis.get("quality_reason", "surface fidelity")}'
                    try:
                        work_gib = resolution.budget(analysis, voxel, component.max_faces, component.max_work_gib)
                    except ValueError as exc:
                        raise ValueError(f'{exc}. {attempt_info}') from exc
                    attempt_info += f'; work estimate {work_gib:.2f} GiB'
                    high['mbt_resolved_voxel'] = voxel
                    modifier = high.modifiers[0]
                    socket = next(s for s in modifier.node_group.interface.items_tree if s.name == 'Resolved Voxel Size')
                    gn.set_modifier_input(modifier, socket.identifier, voxel)
                    visible_voxel = next(s for s in modifier.node_group.interface.items_tree if s.name == 'Voxel Size')
                    gn.set_modifier_input(modifier, visible_voxel.identifier, voxel)
                    high.update_tag()
                    context.view_layer.update()
                    evaluated = high.evaluated_get(context.evaluated_depsgraph_get())
                    mesh = evaluated.to_mesh()
                    try:
                        count = len(mesh.polygons)
                        if not count:
                            raise ValueError(f'REMESH: empty output; check thickness and closed volume. {attempt_info}')
                        if count > component.max_faces:
                            raise ValueError(f'FACES: remesh output {count:,} exceeds limit {component.max_faces:,}. {attempt_info}')
                        accepted, error = resolution.quality(mesh, analysis)
                        if not math.isfinite(error):
                            raise ValueError(f'REMESH: non-finite or nonmanifold output. {attempt_info}')
                    finally:
                        evaluated.to_mesh_clear()
                    if accepted:
                        break
                    if not component.automatic_resolution:
                        raise ValueError(f'QUALITY: manual voxel {voxel:.6g} failed: '
                                         f'{analysis.get("quality_reason", "surface fidelity")}; '
                                         'reduce Voxel Size or enable Automatic Resolution')
                    voxel *= 0.5
                else:
                    raise ValueError(f'QUALITY: after 4 attempts, deviation {error:.6g}, global limit {analysis["tolerance"]:.6g}; '
                                     f'final failed check: {analysis.get("quality_reason", "surface fidelity")}. {attempt_info}')
            if not low.data.polygons:
                raise ValueError('Low mesh has no faces')
            for obj in created:
                obj['mbt_component_id'] = component.component_id
                obj['mbt_asset_role'] = 'HIGH' if obj == high else 'LOW'
            if high or (component.high_mode == 'CUSTOM' and custom):
                from .bake_setup import prepared
                entry = transactions.enter_context(prepared(context, asset, component, low,
                    [previous if previous else high] if high else custom))
                collection = entry.collection
            if high:
                high.mbt_bake_target = low
                if previous:
                    # Keep stable object pointers; exchange validated data/modifiers.
                    original_modifiers = list(previous.modifiers)
                    modifier_name = high.modifiers[0].name
                    old_voxel = previous.get('mbt_resolved_voxel')
                    previous['mbt_resolved_voxel'] = high['mbt_resolved_voxel']
                    try:
                        configure(previous, component)
                    except Exception:
                        if old_voxel is None:
                            del previous['mbt_resolved_voxel']
                        else:
                            previous['mbt_resolved_voxel'] = old_voxel
                        for modifier in list(previous.modifiers):
                            if modifier not in original_modifiers:
                                previous.modifiers.remove(modifier)
                        raise
                    old_mesh = previous.data
                    previous.data = high.data
                    previous.matrix_world = high.matrix_world
                    for modifier in original_modifiers:
                        previous.modifiers.remove(modifier)
                    previous.modifiers[0].name = modifier_name
                    previous.mbt_bake_target = low
                    created.remove(high)
                    bpy.data.objects.remove(high, do_unlink=True)
                    if old_mesh.users == 0:
                        bpy.data.meshes.remove(old_mesh)
                    high = previous
                component.generated_high = high
                component.high_signature = fingerprint(high)
                high.hide_set(True)
            component.low = low
            if creating_low:
                tracking.record(component, 'LOW', source_baseline)
            if high:
                tracking.record(component, 'HIGH', high_baseline)
            if not component.uv_reference:
                from .uv import layout_signature
                component.uv_reference = layout_signature(low.data)
            if collection:
                asset.generated_collection = collection
            component.generation_report = ('High refreshed; low and UVs preserved.' if high else 'Low prepared; custom geometry unchanged.')
            if high and component.remesh:
                component.generation_report += f' {attempt_info}; {count:,} faces; sampled deviation {error:.6g} (limit {analysis["tolerance"]:.6g}). Bake collections registered.'
            elif high:
                component.generation_report += f' Remesh disabled; {count:,} subdivided faces. Bake collections registered.'
            return component.generation_report
    except Exception:
        for obj in created:
            discard(obj)
        raise