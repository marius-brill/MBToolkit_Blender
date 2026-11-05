"""Import the explicit unpacked texture contract without guessing filenames."""
from pathlib import Path
import bpy
from .jobs import PainterError, read_job


def owned(material, obj):
    return material is not None and (material.get('mbt_painter_object') == obj.name or
        obj.name in material.get('mbt_painter_member_names', {}) or
        bool(obj.get('mbt_painter_id') and (material.get('mbt_painter_object_id') == obj['mbt_painter_id'] or
             obj['mbt_painter_id'] in material.get('mbt_painter_members', []))))


def build_nodes(material, entry, images, normal_format):
    material.use_nodes = True
    nodes, links = material.node_tree.nodes, material.node_tree.links
    nodes.clear()
    output = nodes.new('ShaderNodeOutputMaterial')
    output.location = (700, 100)
    shader = nodes.new('ShaderNodeBsdfPrincipled')
    shader.location = (400, 100)
    links.new(shader.outputs['BSDF'], output.inputs['Surface'])
    uv = nodes.new('ShaderNodeUVMap')
    uv.uv_map = entry['uv_map']
    uv.location = (-1000, 100)
    for index, (channel, image) in enumerate(images.items()):
        texture = nodes.new('ShaderNodeTexImage')
        texture.name = 'MBT_' + channel
        texture.label = channel.replace('_', ' ').title()
        texture.image = image
        texture.location = (-750, 500 - index * 280)
        links.new(uv.outputs['UV'], texture.inputs['Vector'])
        socket = {'base_color': 'Base Color', 'roughness': 'Roughness', 'metallic': 'Metallic'}.get(channel)
        if socket:
            links.new(texture.outputs['Color'], shader.inputs[socket])
        elif channel == 'normal':
            normal = nodes.new('ShaderNodeNormalMap')
            normal.uv_map = entry['uv_map']
            normal.location = (100, -400)
            color = texture.outputs['Color']
            if normal_format == 'DIRECTX':
                separate = nodes.new('ShaderNodeSeparateColor')
                combine = nodes.new('ShaderNodeCombineColor')
                invert = nodes.new('ShaderNodeMath')
                separate.mode = combine.mode = 'RGB'
                invert.operation = 'SUBTRACT'
                invert.inputs[0].default_value = 1
                separate.location, invert.location, combine.location = (-450, -450), (-250, -600), (-100, -450)
                links.new(color, separate.inputs[0])
                links.new(separate.outputs[0], combine.inputs[0])
                links.new(separate.outputs[1], invert.inputs[1])
                links.new(invert.outputs[0], combine.inputs[1])
                links.new(separate.outputs[2], combine.inputs[2])
                color = combine.outputs[0]
            links.new(color, normal.inputs['Color'])
            links.new(normal.outputs['Normal'], shader.inputs['Normal'])
        else:
            texture.label = 'AO — inspection only (not multiplied into Base Color)'


def import_maps(context):
    if context.mode != 'OBJECT':
        raise PainterError('Switch to Object Mode before importing maps')
    settings = context.scene.mbt_painter
    job = read_job(settings.last_job)
    targets = []
    for entry in job['texture_sets']:
        obj = context.scene.objects.get(entry['object'])
        if entry.get('object_id'):
            candidates = [target for target in context.scene.objects
                          if target.get('mbt_painter_id') == entry['object_id']]
            if len(candidates) != 1:
                raise PainterError('Missing or duplicate import target identity: ' + entry['object'])
            obj = candidates[0]
        if obj is None or obj.type != 'MESH':
            raise PainterError(f"Low-poly object not found in this scene: {entry['object']}")
        if obj.library or obj.data.library:
            raise PainterError(f'{obj.name}: linked data is not supported')
        if entry['uv_map'] not in obj.data.uv_layers:
            raise PainterError(f"{obj.name}: missing UV map {entry['uv_map']}")
        if not settings.replace_materials and any(
                slot.material and not owned(slot.material, obj) for slot in obj.material_slots):
            raise PainterError(f'{obj.name}: existing materials protected; enable Replace Existing Materials')
        files = {key: Path(path) for key, path in entry['textures'].items() if Path(path).is_file()}
        if not files or set(files) == {'ao'}:
            directories = sorted({str(Path(path).parent) for path in entry['textures'].values()})
            found = sorted({item.name for directory in directories if Path(directory).is_dir()
                            for item in Path(directory).glob('*') if item.is_file()})
            expected = ', '.join(Path(path).name for path in entry['textures'].values())
            raise PainterError(f"{obj.name}: no shader maps found. Active job: {settings.last_job}. "
                               f"Texture folders: {'; '.join(directories)}. Expected: {expected}. "
                               f"Found: {', '.join(found[:30]) or '(no files)'}. "
                               'Check filenames and the active job, or use Export from Painter / Import.')
        targets.append((obj, entry, files))

    groups = {}
    for obj, entry, files in targets:
        key = entry.get('set_id') or entry['texture_set']
        members = groups.setdefault(key, [])
        if members and (members[0][1]['textures'] != entry['textures'] or
                        members[0][1]['texture_set'] != entry['texture_set']):
            raise PainterError('Inconsistent maps for texture set: ' + entry['texture_set'])
        members.append((obj, entry, files))

    # Preload every image and stage every graph before changing any object's slots.
    staged, loaded = [], []
    shared_images = {}
    missing = []
    try:
        for key, members in groups.items():
            obj, entry, files = members[0]
            graph_entry = dict(entry)
            if len({item[1]['uv_map'] for item in members}) > 1:
                # An empty name uses each object's active-render UV for both sampling
                # and tangent-space normals; no destructive UV renaming is needed.
                graph_entry['uv_map'] = ''
            images = {}
            for channel, path in files.items():
                # Dedicated datablocks avoid changing color spaces of unrelated image users.
                image_key = (channel, path)
                image = shared_images.get(image_key)
                if image is None:
                    image = bpy.data.images.load(str(path), check_existing=False)
                    loaded.append(image)
                    image.colorspace_settings.name = 'sRGB' if channel == 'base_color' else 'Non-Color'
                    shared_images[image_key] = image
                images[channel] = image
            material = bpy.data.materials.new('MBT_' + entry['texture_set'])
            staged.append((members, graph_entry, material, images))
            material['mbt_painter_set'] = key
            material['mbt_painter_members'] = {item[1]['object_id']: True for item in members if item[1].get('object_id')}
            material['mbt_painter_member_names'] = {item[0].name: True for item in members
                                                    if not item[1].get('object_id')}
            material['mbt_painter_job'] = job['job_id']
            build_nodes(material, graph_entry, images, job['normal_format'])
            missing.extend(f"{entry['texture_set']}/{channel}" for channel in entry['textures'] if channel not in files)
    except Exception:
        for _, _, material, _ in staged:
            bpy.data.materials.remove(material)
        for image in loaded:
            bpy.data.images.remove(image)
        raise

    old_materials, old_images = set(), set()
    for members, entry, staged_material, images in staged:
        member_objects = {item[0] for item in members}
        candidates = {slot.material for obj in member_objects for slot in obj.material_slots
                      if owned(slot.material, obj)}
        old_materials.update(candidates)
        for candidate in candidates:
            if candidate.use_nodes:
                old_images.update(node.image for node in candidate.node_tree.nodes
                                  if node.type == 'TEX_IMAGE' and node.image)
        def safe_to_reuse(candidate):
            if candidate.library:
                return False
            users = {obj for obj in bpy.data.objects if any(slot.material == candidate for slot in obj.material_slots)}
            meshes = {obj.data for obj in users if obj.type == 'MESH'}
            return (users <= member_objects and
                    candidate.users == len(meshes) and
                    all(mesh.users == sum(obj.data == mesh for obj in users) for mesh in meshes))
        existing = next((candidate for candidate in candidates if safe_to_reuse(candidate)), None)
        material = staged_material
        if existing is not None:
            build_nodes(existing, entry, images, job['normal_format'])
            for key in list(existing.keys()):
                if key.startswith('mbt_painter_'):
                    del existing[key]
            for key in staged_material.keys():
                existing[key] = staged_material[key]
            bpy.data.materials.remove(staged_material)
            material = existing
        for obj, member_entry, _ in members:
            # Isolate linked duplicates before altering slots, face indices or UV selection.
            if obj.data.users > 1:
                obj.data = obj.data.copy()
            if not entry['uv_map']:
                obj.data.uv_layers[member_entry['uv_map']].active_render = True
            obj.data.materials.clear()
            obj.data.materials.append(material)
            obj.material_slots[0].link = 'DATA'
            for polygon in obj.data.polygons:
                polygon.material_index = 0
    for material in old_materials:
        if material.users == 0:
            bpy.data.materials.remove(material)
    for image in old_images:
        if image.users == 0:
            bpy.data.images.remove(image)
    message = f'Updated {len(staged)} texture-set materials on {len(targets)} low-poly objects.'
    if missing:
        message += ' Optional maps missing: ' + ', '.join(missing)
    return message