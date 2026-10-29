"""Import the explicit unpacked texture contract without guessing filenames."""
from pathlib import Path
import bpy
from .jobs import PainterError, read_job


def owned(material, obj):
    return material is not None and (material.get('mbt_painter_object') == obj.name or
        bool(obj.get('mbt_painter_id') and material.get('mbt_painter_object_id') == obj['mbt_painter_id']))


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

    # Preload every image and stage every graph before changing any object's slots.
    staged, loaded = [], []
    shared_images = {}
    missing = []
    try:
        for obj, entry, files in targets:
            images = {}
            for channel, path in files.items():
                # Dedicated datablocks avoid changing color spaces of unrelated image users.
                key = (channel, path)
                image = shared_images.get(key)
                if image is None:
                    image = bpy.data.images.load(str(path), check_existing=False)
                    loaded.append(image)
                    image.colorspace_settings.name = 'sRGB' if channel == 'base_color' else 'Non-Color'
                    shared_images[key] = image
                images[channel] = image
            material = bpy.data.materials.new('MBT_' + entry['texture_set'])
            staged.append((obj, entry, material, images))
            material['mbt_painter_object'] = obj.name
            if entry.get('object_id'):
                material['mbt_painter_object_id'] = entry['object_id']
            material['mbt_painter_job'] = job['job_id']
            build_nodes(material, entry, images, job['normal_format'])
            missing.extend(f'{obj.name}/{key}' for key in entry['textures'] if key not in files)
    except Exception:
        for _, _, material, _ in staged:
            bpy.data.materials.remove(material)
        for image in loaded:
            bpy.data.images.remove(image)
        raise

    for obj, entry, staged_material, images in staged:
        existing = next((slot.material for slot in obj.material_slots if owned(slot.material, obj)), None)
        material = staged_material
        if existing is not None and existing.users == 1 and obj.data.users == 1:
            old_images = {node.image for node in existing.node_tree.nodes
                          if node.type == 'TEX_IMAGE' and node.image} if existing.use_nodes else set()
            build_nodes(existing, entry, images, job['normal_format'])
            existing['mbt_painter_job'] = job['job_id']
            bpy.data.materials.remove(staged_material)
            material = existing
            for image in old_images:
                if image.users == 0:
                    bpy.data.images.remove(image)
        # Isolate linked duplicates before altering mesh slots or face material indices.
        if obj.data.users > 1:
            obj.data = obj.data.copy()
        obj.data.materials.clear()
        obj.data.materials.append(material)
        obj.material_slots[0].link = 'DATA'
        for polygon in obj.data.polygons:
            polygon.material_index = 0
    message = f'Updated materials on {len(staged)} low-poly objects.'
    if missing:
        message += ' Optional maps missing: ' + ', '.join(missing)
    return message