"""Executed inside Unreal; reuse project pipelines with linked-material safeguards."""

import os
import re
import hashlib

import unreal


def linked_import_pipelines(source, existing=None):
    """Copy project/saved pipelines; never mutate project defaults or saved data.

    FBX marker materials only carry slot identities, not shaders to import. On
    linked meshes disable material/texture creation before factories run, rather
    than deleting assets afterward (which could delete somebody else's work).
    """
    if existing:
        originals = existing.get_editor_property('asset_import_data').get_pipelines()
        stack = unreal.InterchangePipelineStack()
        stack.set_editor_property('pipelines', [unreal.SoftObjectPath(pipeline.get_path_name()) for pipeline in originals])
        pipelines = list(unreal.InterchangeProjectSettingsScript.get_pipeline_array_from_pipeline_stack(stack))
    else:
        pipelines = list(unreal.InterchangeProjectSettingsScript.get_pipeline_stack_from_source_data(False, source))
    configured = False
    for pipeline in pipelines:
        if isinstance(pipeline, unreal.InterchangeGenericAssetsPipeline):
            material = pipeline.get_editor_property('material_pipeline')
        elif isinstance(pipeline, unreal.InterchangeGenericMaterialPipeline):
            material = pipeline
        else:
            continue
        material.set_editor_property('import_materials', False)
        texture = material.get_editor_property('texture_pipeline')
        if texture:
            texture.set_editor_property('import_textures', False)
        configured = True
    if not configured:
        raise RuntimeError('Cannot safely disable FBX placeholder material creation in this custom pipeline stack. '
                           'No import attempted; use an Interchange Generic Assets/Material pipeline for linked meshes')
    return pipelines


def material_preview(path):
    material = unreal.load_asset(path)
    if not isinstance(material, unreal.MaterialInterface):
        raise RuntimeError('Not an Unreal material: ' + path)
    library = unreal.MaterialEditingLibrary
    instance = isinstance(material, unreal.MaterialInstance)
    prefix = 'get_material_instance_' if instance else 'get_material_default_'
    base = material.get_base_material()
    preview = {'path': material.get_path_name(), 'textures': {}, 'warnings': []}
    aliases = {'base_color': ('basecolor', 'albedo', 'diffuse', 'color', 'tint', 'basecolortint'),
               'roughness': ('roughness',), 'metallic': ('metallic', 'metalness'),
               'normal': ('normal', 'normalmap')}
    cache = os.path.join(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_saved_dir()),
                         'MBToolkit', 'UnrealBridge', 'MaterialPreviews')
    os.makedirs(cache, exist_ok=True)
    for kind in ('vector', 'scalar', 'texture'):
        names = getattr(library, 'get_' + kind + '_parameter_names')(base)
        for name in names:
            normalized = re.sub('[^a-z0-9]', '', str(name).casefold())
            keys = ('base_color',) if kind == 'vector' else (('roughness', 'metallic') if kind == 'scalar' else tuple(aliases))
            key = next((key for key in keys if normalized in aliases[key]), None)
            if key is None:
                continue
            value = getattr(library, prefix + kind + '_parameter_value')(material, name)
            if kind == 'vector':
                preview[key] = [value.r, value.g, value.b, 1.0]
            elif kind == 'scalar':
                preview[key] = max(0.0, min(1.0, value))
            elif isinstance(value, unreal.Texture2D):
                filename = os.path.join(cache, hashlib.sha256(value.get_path_name().encode()).hexdigest() + '.tga')
                task = unreal.AssetExportTask()
                task.object = value
                task.filename = filename
                task.automated = True
                task.prompt = False
                task.replace_identical = True
                task.exporter = unreal.TextureExporterTGA()
                if unreal.Exporter.run_asset_export_task(task) and os.path.isfile(filename):
                    preview['textures'][key] = filename
                else:
                    preview['warnings'].append('Could not export texture ' + value.get_path_name())
    return {'message': 'Approximate material preview ready', 'preview': preview}


def run(request):
    project = os.path.normcase(os.path.realpath(unreal.Paths.convert_relative_path_to_full(
        unreal.Paths.get_project_file_path())))
    expected = os.path.normcase(os.path.realpath(request['project']))
    if project != expected:
        raise RuntimeError('Connected editor project differs from the selected .uproject; nothing imported')
    version = unreal.SystemLibrary.get_engine_version()
    match = re.match(r'(\d+)\.(\d+)', version)
    if not match or tuple(map(int, match.groups())) < (5, 7):
        raise RuntimeError('MBToolkit Unreal Bridge requires Unreal Engine 5.7 or newer')
    if request['action'] == 'TEST':
        return {'message': 'Connected: ' + os.path.basename(project) + ' — UE ' + version}
    if request['action'] == 'MATERIALS':
        registry = unreal.AssetRegistryHelpers.get_asset_registry()
        assets = registry.get_assets_by_path('/Game', recursive=True)
        classes = {'Material', 'MaterialInstanceConstant', 'MaterialInstance'}
        paths = sorted(str(asset.package_name) + '.' + str(asset.asset_name)
                       for asset in assets if str(asset.asset_class_path.asset_name) in classes)
        return {'message': 'Found ' + str(len(paths)) + ' Unreal materials', 'materials': paths}
    if request['action'] == 'PREVIEW':
        return material_preview(request['material'])
    if request['action'] != 'SEND':
        raise RuntimeError('Unknown bridge action')

    destination = request['destination']
    # Validate the entire batch before changing any assets.
    for item in request['assets']:
        path = destination + '/' + item['name']
        existing = unreal.EditorAssetLibrary.load_asset(path) if unreal.EditorAssetLibrary.does_asset_exist(path) else None
        if existing and not request['replace']:
            raise RuntimeError(path + ' already exists. Enable Replace Existing to reimport')
        if existing and not isinstance(existing, unreal.StaticMesh):
            raise RuntimeError(path + ' exists but is not a Static Mesh')
        if existing and not isinstance(existing.get_editor_property('asset_import_data'),
                                       unreal.InterchangeAssetImportData):
            raise RuntimeError(path + ' was not imported with Interchange; refusing to replace its import settings')
        if not os.path.isfile(item['file']):
            raise RuntimeError('FBX source file is missing: ' + item['file'])
        for material_path in item.get('materials', {}).values():
            if not isinstance(unreal.load_asset(material_path), unreal.MaterialInterface):
                raise RuntimeError('Missing or invalid linked material: ' + material_path)

    imported = []
    manager = unreal.InterchangeManager.get_interchange_manager_scripted()
    for item in request['assets']:
        path = destination + '/' + item['name']
        params = unreal.ImportAssetParameters()
        params.is_automated = True
        params.destination_name = item['name']
        params.replace_existing = request['replace']
        # Unlinked FBX uses the project stack unchanged. Linked FBX needs copied
        # pipelines to prevent marker materials becoming real Unreal assets.
        if unreal.EditorAssetLibrary.does_asset_exist(path):
            params.reimport_asset = unreal.EditorAssetLibrary.load_asset(path)
        source = unreal.InterchangeManager.create_source_data(item['file'])
        pipelines = []
        if item.get('materials'):
            pipelines = linked_import_pipelines(source, params.reimport_asset)
            params.override_pipelines = [unreal.SoftObjectPath(pipeline.get_path_name()) for pipeline in pipelines]
        if not manager.import_asset(destination, source, params):
            raise RuntimeError('Interchange import failed: ' + path)
        mesh = unreal.EditorAssetLibrary.load_asset(path)
        if not isinstance(mesh, unreal.StaticMesh):
            raise RuntimeError('Project pipeline did not create the expected Static Mesh at ' + path +
                               '. Inspect the Unreal Output Log; project pipeline naming may differ')
        bindings = item.get('materials', {})
        matched = set()
        for index, slot in enumerate(mesh.get_editor_property('static_materials')):
            for name in (str(slot.get_editor_property('imported_material_slot_name')),
                         str(slot.material_slot_name)) if bindings else ():
                if name in bindings:
                    mesh.set_material(index, unreal.load_asset(bindings[name]))
                    matched.add(name)
                    break
        if set(bindings) - matched:
            raise RuntimeError('Imported mesh material slots do not match linked Unreal materials: ' +
                               ', '.join(sorted(set(bindings) - matched)) + '. Mesh may already be imported; inspect Unreal')
        if not unreal.EditorAssetLibrary.save_loaded_asset(mesh):
            raise RuntimeError('Imported but could not save ' + path)
        imported.append(path)
    return {'message': 'Imported ' + str(len(imported)) + ' Static Mesh asset(s)', 'assets': imported}