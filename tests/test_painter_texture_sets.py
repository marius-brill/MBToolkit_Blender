"""Collection texture sets; run in a disposable background Blender process."""
import importlib
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon = importlib.import_module(ROOT.name)
jobs = importlib.import_module(ROOT.name + '.features.substance_painter.jobs')
materials = importlib.import_module(ROOT.name + '.features.substance_painter.materials')


def main():
    assert bpy.app.background
    addon.register()
    addon.feature_manager.sync(type('Preferences', (), {'enable_substance_painter': True})())
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    settings = bpy.context.scene.mbt_painter

    def pair(name):
        objects = []
        for role in ('LOW', 'HIGH'):
            bpy.ops.mesh.primitive_cube_add()
            obj = bpy.context.object
            obj.name = name + '_' + role.lower()
            assert bpy.ops.mbt.painter_assign(role=role) == {'FINISHED'}
            objects.append(obj)
        return objects

    first = pair('Body')
    second = pair('Trim')
    assert len(settings.texture_sets) == 1
    default = settings.texture_sets[0]
    assert settings.low_collection in default.collection.children_recursive
    settings.resolution = '1024'
    settings.front_distance = 0.02
    assert default.resolution == '1024'
    bpy.ops.mbt.painter_texture_set(action='ADD')
    details = settings.texture_sets[1]
    details.collection.name = 'Details'
    third = pair('Detail')
    settings.resolution = '512'
    settings.bake_maps = {'NORMAL'}
    settings.front_distance = 0.05
    settings.texture_collection = default.collection
    assert settings.active_texture_set == 0 and settings.resolution == '1024'
    assert abs(settings.front_distance - 0.02) < 1e-6
    settings.texture_collection = details.collection
    assert settings.resolution == '512' and settings.bake_maps == {'NORMAL'}
    with TemporaryDirectory() as folder:
        settings.output_dir = folder
        jobs.prepare(bpy.context, automatic=True)
        job = jobs.read_job(settings.last_job)
        assert len(job['texture_sets']) == 3 and len(job['set_definitions']) == 2
        by_object = {entry['object']: entry for entry in job['texture_sets']}
        assert by_object[first[0].name]['texture_set'] == by_object[second[0].name]['texture_set']
        assert by_object[third[0].name]['texture_set'] != by_object[first[0].name]['texture_set']
        definitions = {entry['set_id']: entry for entry in job['set_definitions']}
        assert definitions[default.set_id]['resolution'] == 1024
        assert definitions[details.set_id]['resolution'] == 512
        assert definitions[details.set_id]['bake_maps'] == ['NORMAL']
        assert abs(definitions[details.set_id]['baking']['front_distance'] - 0.05) < 1e-6
        # Inspect the actual FBX: both default lows must reference one material.
        scene = bpy.data.scenes.new('VerifyTextureSets')
        with bpy.context.temp_override(scene=scene, view_layer=scene.view_layers[0]):
            bpy.ops.import_scene.fbx(filepath=job['low_mesh'])
            imported = [obj for obj in scene.objects if obj.type == 'MESH']
            assert len(imported) == 3
            assert len({obj.data.materials[0] for obj in imported}) == 2
        for obj in list(scene.objects):
            mesh = obj.data
            bpy.data.objects.remove(obj, do_unlink=True)
            bpy.data.meshes.remove(mesh)
        bpy.data.scenes.remove(scene)
        # Remove imported test materials so they do not occupy export names.
        for material in list(bpy.data.materials):
            if material.users == 0:
                bpy.data.materials.remove(material)
        jobs.prepare(bpy.context, automatic=True)
        job = jobs.read_job(settings.last_job)
        settings.resolution = '2048'
        jobs.update_bake_settings(settings.last_job, settings)
        updated = jobs.read_job(settings.last_job)
        assert next(entry for entry in updated['set_definitions'] if entry['set_id'] == details.set_id)['resolution'] == 2048
        for filename in {path for entry in job['texture_sets'] for path in entry['textures'].values()}:
            image = bpy.data.images.new('TextureSetTest', width=4, height=4)
            image.filepath_raw = filename
            image.file_format = 'PNG'
            image.save()
            bpy.data.images.remove(image)
        materials.import_maps(bpy.context)
        a = first[0].data.materials[0].node_tree.nodes['MBT_base_color'].image
        b = second[0].data.materials[0].node_tree.nodes['MBT_base_color'].image
        c = third[0].data.materials[0].node_tree.nodes['MBT_base_color'].image
        assert a == b and a != c
        jobs.prepare(bpy.context, automatic=True)
        # Legacy projects cannot silently merge existing painted sets.
        legacy = jobs.read_job(settings.last_job)
        legacy.pop('set_definitions')
        Path(settings.last_job).write_text(json.dumps(legacy), encoding='utf-8')
        try:
            jobs.prepare(bpy.context, automatic=True)
        except jobs.PainterError as error:
            assert 'New Project' in str(error)
        else:
            raise AssertionError('Legacy painted sets silently merged')
        parent = details.collection
        bpy.ops.mbt.painter_texture_set(action='REMOVE')
        assert len(settings.texture_sets) == 1 and parent.name in bpy.data.collections
        assert third[0].name in bpy.data.objects
        blend = str(Path(folder) / 'texture_sets.blend')
        saved_parent = settings.texture_collection.name
        bpy.ops.wm.save_as_mainfile(filepath=blend)
        bpy.ops.wm.open_mainfile(filepath=blend)
        settings = bpy.context.scene.mbt_painter
        assert len(settings.texture_sets) == 1
        assert settings.texture_collection.name == saved_parent
        assert settings.resolution == '1024'
        assert settings.texture_sets[0].resolution == '1024'
    addon.unregister()
    print('PASS: shared default set, collection hierarchy, set switching/settings, real FBX materials, shared image import, rebake, legacy guard, non-destructive removal', flush=True)


if __name__ == '__main__':
    main()