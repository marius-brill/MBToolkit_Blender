"""Source-preserving, evaluated static mesh FBX snapshots."""

from pathlib import Path
import hashlib
import math

import bpy
from mathutils import Matrix

from .common import BridgeError, asset_name, same_path


def selected_roots(context):
    selected = set(context.selected_objects)
    roots = []
    for obj in selected:
        if obj.type != 'EMPTY':
            continue
        parent = obj.parent
        while parent and not (parent in selected and parent.type == 'EMPTY'):
            parent = parent.parent
        if parent is None:
            roots.append(obj)
    return sorted(roots, key=lambda obj: obj.name)


def descendants(root):
    result, pending = [], list(root.children)
    while pending:
        obj = pending.pop()
        pending.extend(obj.children)
        if obj.type == 'MESH':
            result.append(obj)
    return sorted(result, key=lambda obj: obj.name)


def validate_roots(context):
    if context.mode != 'OBJECT':
        raise BridgeError('Switch to Object Mode before sending')
    roots = selected_roots(context)
    if not roots:
        raise BridgeError('Select an Empty with child meshes')
    names = set()
    for root in roots:
        name = asset_name(root.name)
        if name.casefold() in names:
            raise BridgeError('Selected Empty names must be unique, ignoring case')
        names.add(name.casefold())
        if not descendants(root):
            raise BridgeError(f'{name}: no mesh descendants')
        if abs(root.matrix_world.determinant()) < 1e-12:
            raise BridgeError(f'{name}: Empty transform has zero scale')
    return roots


def export_root(context, root, filepath, scale=1.0, project=''):
    """Join copies, not sources, so the project need not enable Combine Meshes."""
    if not math.isfinite(scale) or scale <= 0:
        raise BridgeError('Export Scale must be a finite number greater than zero')
    scene = bpy.data.scenes.new('MBT_Unreal_Export')
    scene.unit_settings.system = context.scene.unit_settings.system
    scene.unit_settings.scale_length = context.scene.unit_settings.scale_length
    objects = []
    baseline = set(bpy.data.meshes)
    proxies, bindings = {}, {}
    try:
        depsgraph = context.evaluated_depsgraph_get()
        inverse = root.matrix_world.inverted()
        for source in descendants(root):
            if source.name not in context.view_layer.objects:
                raise BridgeError(f'{source.name}: mesh is outside the active view layer')
            evaluated = source.evaluated_get(depsgraph)
            mesh = bpy.data.meshes.new_from_object(evaluated, preserve_all_data_layers=True,
                                                 depsgraph=depsgraph)
            if not mesh.polygons:
                raise BridgeError(f'{source.name}: evaluated mesh has no faces')
            # Replace linked preview materials on copies only. Stable ASCII tokens
            # survive FBX/Interchange names, even for duplicate Unreal asset names.
            for index, slot in enumerate(evaluated.material_slots):
                material = slot.material
                if index >= len(mesh.materials):
                    continue
                if material and material.get('mbt_unreal_path'):
                    if not project or not same_path(material.get('mbt_unreal_project', ''), project):
                        raise BridgeError(f'{source.name}: linked Unreal material belongs to another project')
                    path = material['mbt_unreal_path']
                    token = 'MBT_UE_' + hashlib.sha256(path.encode()).hexdigest()[:24]
                    if token not in proxies:
                        proxies[token] = bpy.data.materials.new(token)
                    mesh.materials[index] = proxies[token]
                    bindings[proxies[token].name] = path
                elif material:
                    mesh.materials[index] = material
            transform = Matrix.Scale(scale, 4) @ inverse @ evaluated.matrix_world
            mesh.transform(transform)
            if transform.determinant() < 0:
                mesh.flip_normals()
            obj = bpy.data.objects.new('MBT_Unreal_Part', mesh)
            objects.append(obj)
            scene.collection.objects.link(obj)
            obj.matrix_world = Matrix.Identity(4)
        layer = scene.view_layers[0]
        layer.update()
        with context.temp_override(scene=scene, view_layer=layer):
            for obj in objects:
                obj.select_set(True, view_layer=layer)
            layer.objects.active = objects[0]
            if len(objects) > 1:
                with context.temp_override(object=objects[0], active_object=objects[0],
                                           selected_objects=objects, selected_editable_objects=objects):
                    bpy.ops.object.join()
            # Filename and Interchange DestinationName carry the exact Empty name.
            result = bpy.ops.export_scene.fbx(
                filepath=str(filepath), check_existing=False, use_selection=False,
                object_types={'MESH'}, use_mesh_modifiers=False, bake_anim=False,
                use_triangles=True, mesh_smooth_type='FACE', axis_forward='-Y', axis_up='Z',
                apply_unit_scale=True, add_leaf_bones=False, path_mode='AUTO')
        if result != {'FINISHED'} or not Path(filepath).is_file():
            raise BridgeError(f'{root.name}: FBX export failed')
        return bindings
    finally:
        # Join may already have removed some copies and created replacement data.
        for obj in list(scene.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.scenes.remove(scene)
        for mesh in set(bpy.data.meshes) - baseline:
            if mesh.users == 0:
                bpy.data.meshes.remove(mesh)
        for material in proxies.values():
            if material.users == 0:
                bpy.data.materials.remove(material)