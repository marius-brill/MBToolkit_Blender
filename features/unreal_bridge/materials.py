"""Local preview proxies. Unreal materials remain authoritative and unmodified."""

import bpy
import bmesh

from .common import BridgeError, same_path
from .export import descendants


def linked_material(project, path):
    return next((material for material in bpy.data.materials
                 if material.get('mbt_unreal_path') == path and
                 same_path(material.get('mbt_unreal_project', ''), project)), None)


def create_preview(project, preview):
    material = linked_material(project, preview['path'])
    if material is None:
        material = bpy.data.materials.new('UE_' + preview['path'].rsplit('.', 1)[-1])
    material['mbt_unreal_path'] = preview['path']
    material['mbt_unreal_project'] = project
    material['mbt_unreal_preview_ready'] = 'textures' in preview
    material['mbt_unreal_preview'] = 'Approximate parameter preview; not an Unreal shader conversion'
    material.use_fake_user = True
    material.use_nodes = True
    tree = material.node_tree
    tree.nodes.clear()
    output = tree.nodes.new('ShaderNodeOutputMaterial')
    output.location = (600, 0)
    shader = tree.nodes.new('ShaderNodeBsdfPrincipled')
    shader.location = (300, 0)
    tree.links.new(shader.outputs['BSDF'], output.inputs['Surface'])
    color = preview.get('base_color', [0.5, 0.5, 0.5, 1.0])
    material.diffuse_color = color
    shader.inputs['Base Color'].default_value = color
    for key, socket in (('roughness', 'Roughness'), ('metallic', 'Metallic')):
        shader.inputs[socket].default_value = preview.get(key, 0.5 if key == 'roughness' else 0.0)
    for index, (key, path) in enumerate(preview.get('textures', {}).items()):
        image = bpy.data.images.load(path, check_existing=False)
        image.colorspace_settings.name = 'sRGB' if key == 'base_color' else 'Non-Color'
        # Keep previews visible after moving/saving the blend or clearing UE caches.
        image.pack()
        node = tree.nodes.new('ShaderNodeTexImage')
        node.image = image
        node.label = 'Unreal ' + key
        node.location = (-600, -index * 300)
        if key == 'normal':
            flip = tree.nodes.new('ShaderNodeVectorMath')
            flip.operation = 'MULTIPLY_ADD'
            flip.inputs[1].default_value = (1, -1, 1)
            flip.inputs[2].default_value = (0, 1, 0)
            flip.location = (-300, -index * 300)
            normal = tree.nodes.new('ShaderNodeNormalMap')
            normal.location = (0, -index * 300)
            tree.links.new(node.outputs['Color'], flip.inputs[0])
            tree.links.new(flip.outputs['Vector'], normal.inputs['Color'])
            tree.links.new(normal.outputs['Normal'], shader.inputs['Normal'])
        else:
            socket = {'base_color': 'Base Color', 'roughness': 'Roughness', 'metallic': 'Metallic'}[key]
            tree.links.new(node.outputs['Color'], shader.inputs[socket])
    return material


def assign(context, material):
    if context.mode not in {'OBJECT', 'EDIT_MESH'}:
        raise BridgeError('Assign materials in Object Mode or mesh Edit Mode')
    if context.mode == 'EDIT_MESH':
        objects = list(context.objects_in_mode_unique_data)
    else:
        objects = set(obj for obj in context.selected_objects if obj.type == 'MESH')
        for obj in context.selected_objects:
            if obj.type == 'EMPTY':
                objects.update(descendants(obj))
        objects = sorted(objects, key=lambda obj: obj.name)
    if not objects:
        raise BridgeError('Select meshes, an Empty with mesh children, or faces in Edit Mode')
    if any(obj.library or obj.data.library for obj in objects):
        raise BridgeError('Cannot assign materials to linked library meshes')
    changed = 0
    for obj in objects:
        if context.mode == 'EDIT_MESH':
            mesh = bmesh.from_edit_mesh(obj.data)
            faces = [face for face in mesh.faces if face.select]
            if not faces:
                continue
        else:
            # Do not unexpectedly change unselected objects sharing mesh data.
            if obj.data.users > 1:
                obj.data = obj.data.copy()
            faces = obj.data.polygons
        index = next((i for i, slot in enumerate(obj.material_slots) if slot.material == material), None)
        if index is None:
            index = len(obj.data.materials)
            obj.data.materials.append(material)
        for face in faces:
            face.material_index = index
        obj.active_material_index = index
        if context.mode == 'EDIT_MESH':
            bmesh.update_edit_mesh(obj.data)
        changed += 1
    if not changed:
        raise BridgeError('No selected faces to assign')
    return changed