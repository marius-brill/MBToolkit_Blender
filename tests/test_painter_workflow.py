"""Unified workflow regression tests. Disposable background Blender only."""
import importlib
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon = importlib.import_module(ROOT.name)
jobs = importlib.import_module(ROOT.name + '.features.substance_painter.jobs')
matching = importlib.import_module(ROOT.name + '.features.substance_painter.matching')


def fails(function, text):
    try:
        function()
    except jobs.PainterError as error:
        assert text in str(error), str(error)
    else:
        raise AssertionError('Expected ' + text)


def main():
    assert bpy.app.background
    addon.register()
    addon.feature_manager.sync(type('Settings', (), {'enable_substance_painter': True})())
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    bpy.ops.mesh.primitive_cube_add()
    low = bpy.context.object
    low.name = 'body_low'
    old = tuple(low.users_collection)
    bpy.ops.mbt.painter_assign(role='LOW')
    settings = bpy.context.scene.mbt_painter
    assert list(low.users_collection) == [settings.low_collection]
    assert all(low.name not in collection.objects for collection in old)
    bpy.ops.mesh.primitive_cube_add()
    high = bpy.context.object
    high.name = 'body_high'
    bpy.ops.mbt.painter_assign(role='HIGH')
    assert list(high.users_collection) == [settings.high_collection]
    names, pairs = matching.resolve(bpy.context, [low], [high])
    assert pairs[high] == low and names[low].endswith('_low')
    assert names[high] == names[low][:-4] + '_high'
    low.name, high.name = 'Retopo', 'Sculpt'
    assert matching.resolve(bpy.context, [low], [high])[1][high] == low
    bpy.ops.mesh.primitive_cube_add()
    other = bpy.context.object
    other.name = 'Other'
    fails(lambda: matching.resolve(bpy.context, [low, other], [high]), 'ambiguous')
    high.mbt_bake_target = low
    fails(lambda: matching.resolve(bpy.context, [low, other], [high]), 'No high')
    bpy.data.objects.remove(other, do_unlink=True)
    with TemporaryDirectory() as folder:
        settings.output_dir = folder
        jobs.prepare(bpy.context, automatic=True)
        first = jobs.read_job(settings.last_job)
        assert first['match_method'] == 'BY_NAME'
        assert first['project_file'] == settings.project_file
        assert high.mbt_bake_target == low
        high.location.x = 0.01
        bpy.context.view_layer.update()
        jobs.prepare(bpy.context, automatic=True)
        second = jobs.read_job(settings.last_job)
        assert first['project_file'] == second['project_file']
        assert first['low_mesh'] != second['low_mesh']
        assert first['texture_sets'][0]['texture_set'] == second['texture_sets'][0]['texture_set']
        assert Path(second['high_mesh']).is_file()
        low.name = 'RenamedLow'
        jobs.prepare(bpy.context, automatic=True)
        renamed = jobs.read_job(settings.last_job)
        assert renamed['texture_sets'][0]['texture_set'] == second['texture_sets'][0]['texture_set']
        assert renamed['mesh_names'][low.name] == second['mesh_names']['Retopo']
        settings.normal_format = 'DIRECTX'
        fails(lambda: jobs.prepare(bpy.context, automatic=True), 'Normal format changed')
        settings.normal_format = 'OPENGL'
        bpy.ops.mesh.primitive_cube_add()
        extra_low = bpy.context.object
        extra_low.name = 'Extra_low'
        bpy.ops.mbt.painter_assign(role='LOW')
        bpy.ops.mesh.primitive_cube_add()
        extra_high = bpy.context.object
        extra_high.name = 'Extra_high'
        bpy.ops.mbt.painter_assign(role='HIGH')
        fails(lambda: jobs.prepare(bpy.context, automatic=True), 'Low mesh membership changed')
        # Prepare a new two-low association, then simulate damaged internal names.
        settings.project_file = ''
        settings.last_job = ''
        jobs.prepare(bpy.context, automatic=True)
        two_low = jobs.read_job(settings.last_job)
        damaged = json.loads(json.dumps(two_low))
        damaged['mesh_names'][extra_low.name] = damaged['mesh_names'][low.name]
        with patch.object(jobs, 'read_job', return_value=damaged), \
                patch.object(jobs, 'export_meshes') as export:
            fails(lambda: jobs.prepare(bpy.context, automatic=True), 'Final bake mesh names collide')
            export.assert_not_called()
        damaged = json.loads(json.dumps(two_low))
        assert two_low['texture_sets'][1]['texture_set'] == two_low['texture_sets'][0]['texture_set']
        damaged['texture_sets'][1]['texture_set'] = 'UnexpectedSet'
        with patch.object(jobs, 'read_job', return_value=damaged), \
                patch.object(jobs, 'export_meshes') as export:
            fails(lambda: jobs.prepare(bpy.context, automatic=True), 'texture-set names collide')
            export.assert_not_called()
        bpy.data.objects.remove(extra_high, do_unlink=True)
        bpy.data.objects.remove(extra_low, do_unlink=True)
        settings.project_file = ''
        settings.last_job = ''
        jobs.prepare(bpy.context, automatic=True)
        project = settings.project_file
        settings.project_file = ''
        settings.project_template = str(Path(folder) / 'missing.spt')
        fails(lambda: jobs.prepare(bpy.context, automatic=True), '.spt')
        settings.project_template = ''
        settings.project_file = project
        mapping = Path(folder) / 'export.json'
        mapping.write_text(json.dumps({'preset': 'resource://custom', 'channels': {}}))
        settings.export_config = str(mapping)
        fails(lambda: jobs.prepare(bpy.context, automatic=True), 'mapping')
        settings.export_config = ''
        material = bpy.data.materials.new('ArtistMaterial')
        low.data.materials.append(material)
        fails(lambda: jobs.prepare(bpy.context, automatic=True), 'protected')
        low.data.materials.clear()
        bpy.ops.mbt.painter_new_project()
        assert not settings.project_file and not settings.last_job
    addon.unregister()
    print('PASS: collection moves, matching, snapshots, project reuse, normal/membership guards, final-name collisions, template/export preflight', flush=True)


def remote_update_tests():
    import types
    project = types.ModuleType('substance_painter.project')
    textures = types.ModuleType('substance_painter.textureset')
    package = types.ModuleType('substance_painter')
    project.is_busy = lambda: False
    project.is_in_edition_state = lambda: True
    project.is_open = lambda: True
    project.MeshReloadingSettings = lambda **kwargs: kwargs
    project.ReloadMeshStatus = types.SimpleNamespace(SUCCESS=0)
    textures.all_texture_sets = lambda: [types.SimpleNamespace(name=lambda: 'Body')]
    with TemporaryDirectory() as folder, patch.dict(sys.modules, {
            'substance_painter': package, 'substance_painter.project': project,
            'substance_painter.textureset': textures}):
        file = Path(folder) / 'asset.spp'
        file.touch()
        manifest = Path(folder) / 'job.json'
        manifest.write_text(json.dumps({'job_id': 'x', 'project_file': str(file),
            'low_mesh': str(Path(folder) / 'low.fbx'), 'texture_sets': [{'texture_set': 'Body'}]}))
        project.file_path = lambda: str(file)
        callbacks = []
        project.reload_mesh = Mock(side_effect=lambda mesh, settings, callback: callbacks.append(callback))
        namespace = {}
        exec(compile((ROOT / 'features/substance_painter/painter_remote.py').read_text(), 'remote', 'exec'), namespace)
        assert json.loads(namespace['_mbt_update'](str(manifest)))['state'] == 'RELOADING'
        assert project.reload_mesh.call_args.args[1]['preserve_strokes']
        callbacks.pop()(0)
        completed = json.loads(namespace['_mbt_status']())
        assert completed['state'] == 'COMPLETE'
        assert completed['project_file'] == str(file)
        assert completed['texture_sets'] == ['Body']
        namespace['_mbt_update'](str(manifest))
        callbacks.pop()(2)
        assert json.loads(namespace['_mbt_status']())['state'] == 'FAILED'
        project.file_path = lambda: str(Path(folder) / 'unrelated.spp')
        project.reload_mesh.reset_mock()
        assert 'unrelated' in json.loads(namespace['_mbt_update'](str(manifest)))['error']
        project.reload_mesh.assert_not_called()
        project.is_open = lambda: False
        project.open = Mock()
        assert json.loads(namespace['_mbt_update'](str(manifest)))['state'] == 'OPENING'
        project.open.assert_called_once_with(str(file))
        # The transport waits for reload completion and never retries the update.
        bridge = importlib.import_module(ROOT.name + '.features.substance_painter.bridge')
        client = Mock()
        client.timeout = 5
        client.execute.side_effect = [{'state': 'RELOADING'}, {'state': 'RELOADED'}, {'state': 'COMPLETE'}]
        with patch.object(bridge.time, 'sleep'):
            bridge.send(client, str(manifest), update=True)
        assert client.timeout == 5
        assert client.execute.call_args_list[0].args[0].startswith('_mbt_update(')
        assert client.execute.call_count == 3
    print('PASS: asynchronous mesh refresh, stroke preservation, reload failure, unrelated project protection, associated project opening', flush=True)


if __name__ == '__main__':
    main()
    remote_update_tests()