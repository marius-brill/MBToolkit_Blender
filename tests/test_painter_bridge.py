"""Bridge tests. Run with Blender --background --factory-startup --python-exit-code 1.

Pass -- --live to launch installed Painter and create a disposable cube project.
Live testing refuses any open Painter project and leaves its test project open.
"""
import base64
import importlib
import json
from pathlib import Path
import sys
import tempfile
import threading
import types
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest.mock import patch

import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon = importlib.import_module(ROOT.name)
bridge = importlib.import_module(f'{ROOT.name}.features.substance_painter.bridge')
jobs = importlib.import_module(f'{ROOT.name}.features.substance_painter.jobs')


def transport_tests():
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            assert self.path == '/run.json'
            payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            script = base64.b64decode(payload['python']).decode('utf-8')
            self.send_response(200)
            self.end_headers()
            self.wfile.write(json.dumps({'echo': script}).encode())

        def log_message(self, *args):
            pass

    server = HTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        client = bridge.Client(server.server_port)
        assert client.execute('Unicode: café')['echo'] == 'Unicode: café'
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
    with patch.object(bridge.subprocess, 'Popen') as popen:
        with tempfile.NamedTemporaryFile(suffix='.exe') as exe, patch.dict(
                bridge.os.environ, {'OCIO': 'blender-config.ocio', 'MBT_KEEP': 'unchanged'}):
            bridge.launch(exe.name)
            assert bridge.os.environ['OCIO'] == 'blender-config.ocio'
        args = popen.call_args.args[0]
        assert args[1:] == ['--enable-remote-scripting']
        assert not popen.call_args.kwargs.get('shell', False)
        assert 'OCIO' not in popen.call_args.kwargs['env']
        assert popen.call_args.kwargs['env']['MBT_KEEP'] == 'unchanged'
    stages = []
    with patch.object(bridge.socket, 'create_connection', side_effect=[
            ConnectionRefusedError('IPv4 unavailable'), __import__('contextlib').nullcontext()]) as socket_connect:
        client = bridge.Client()
        client.check_endpoint()
        assert client.host == '::1'
        assert [call.args[0][0] for call in socket_connect.call_args_list] == ['127.0.0.1', '::1']
    with patch.object(bridge.Client, 'check_endpoint'), patch.object(bridge.Client, 'execute',
            return_value={'mbt_ping': 1}), patch.object(bridge.Client, 'install', return_value={'can_create': True}):
        _, info = bridge.connect(60041, progress=stages.append)
        assert info['can_create'] and len(stages) == 3
    with patch.object(bridge.Client, 'check_endpoint'), patch.object(bridge.Client, 'execute',
            side_effect=bridge.BridgeError('Script failed')), patch.object(bridge, 'launch') as launcher:
        try:
            bridge.connect(60041, allow_launch=True)
        except bridge.BridgeError as error:
            assert 'Script failed' in str(error)
        else:
            raise AssertionError('Script failure hidden')
        launcher.assert_not_called()
    print('PASS: localhost HTTP transport, Unicode, safe launch arguments', flush=True)


def live():
    client, info = bridge.connect(60041, bridge.detect_executable(), allow_launch=True)
    print('LIVE PROBE:', info, flush=True)
    assert info['can_create'], info
    if info['project_open'] or info['busy']:
        print('LIVE SKIPPED: existing project/busy Painter was left untouched', flush=True)
        return
    addon.register()
    addon.feature_manager.sync(type('Settings', (), {'enable_substance_painter': True})())
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    bpy.ops.mesh.primitive_cube_add()
    low = bpy.context.object
    low.name = 'BridgeTestLow'
    bpy.ops.mbt.painter_assign(role='LOW')
    bpy.ops.mesh.primitive_cube_add()
    bpy.context.object.name = 'BridgeTestHigh'
    bpy.ops.mbt.painter_assign(role='HIGH')
    settings = bpy.context.scene.mbt_painter
    # Keep this directory: the test project is left open in Painter for inspection.
    folder = tempfile.mkdtemp(prefix='MBToolkit_Painter_Live_')
    settings.output_dir = folder
    settings.resolution = '512'
    jobs.prepare(bpy.context)
    result = bridge.send(client, settings.last_job)
    print('LIVE RESULT:', result, flush=True)
    assert Path(result['project_file']).is_file()
    try:
        bridge.send(client, settings.last_job)
    except bridge.BridgeError as error:
        assert 'open project' in str(error), str(error)
    else:
        raise AssertionError('Existing project was not protected')
    addon.unregister()
    print('PASS: live Painter project creation/save and open-project protection', flush=True)


def remote_tests():
    project = types.ModuleType('substance_painter.project')
    package = types.ModuleType('substance_painter')
    textures = types.ModuleType('substance_painter.textureset')
    package.__version__ = 'mock-11.0.3'
    state = {'open': False, 'edition': False, 'callbacks': [], 'created': 0}
    project.is_open = lambda: state['open']
    project.is_busy = lambda: False
    project.is_in_edition_state = lambda: state['edition']
    project.NormalMapFormat = types.SimpleNamespace(OpenGL='GL', DirectX='DX')
    project.Settings = lambda **kwargs: types.SimpleNamespace(**kwargs)
    project.execute_when_not_busy = lambda callback: state['callbacks'].append(callback)
    def create(**kwargs):
        state['open'] = True
        state['created'] += 1
        state['settings'] = kwargs['settings']
    project.create = create
    project.save_as = lambda path: Path(path).write_text('mock spp', encoding='utf-8')
    textures.all_texture_sets = lambda: [types.SimpleNamespace(name=lambda: 'MBT_Cube')]
    modules = {'substance_painter': package, 'substance_painter.project': project,
               'substance_painter.textureset': textures}
    with patch.dict(sys.modules, modules), tempfile.TemporaryDirectory() as folder:
        namespace = {}
        source = (ROOT / 'features/substance_painter/painter_remote.py').read_text(encoding='utf-8')
        exec(compile(source, 'painter_remote.py', 'exec'), namespace)
        assert json.loads(namespace['_mbt_probe']())['can_create']
        mesh = Path(folder) / 'low.fbx'
        mesh.touch()
        spp = Path(folder) / 'project.spp'
        job = {'schema_version': 1, 'job_id': 'test', 'low_mesh': str(mesh),
               'project_file': str(spp), 'normal_format': 'OPENGL', 'resolution': 1024,
               'texture_sets': [{'object': 'Cube', 'texture_set': 'MBT_Cube'}]}
        manifest = Path(folder) / 'job.json'
        manifest.write_text(json.dumps(job), encoding='utf-8')
        assert json.loads(namespace['_mbt_create'](str(manifest)))['state'] == 'CREATING'
        assert not spp.exists()
        # Exercise Painter export with a controlled API and real output files.
        export = types.ModuleType('substance_painter.export')
        export.ExportStatus = types.SimpleNamespace(Success='ok', Warning='warn')
        project.file_path = lambda: str(spp)
        textures.all_texture_sets = lambda: [types.SimpleNamespace(name=lambda: 'MBT_Cube')]
        job.update(export_preset='MBT_PBR')
        manifest.write_text(json.dumps(job), encoding='utf-8')
        def export_files(config):
            paths = []
            for item in config['exportPresets'][0]['maps']:
                path = Path(config['exportPath']) / (item['fileName'].replace('$textureSet', 'MBT_Cube') + '.png')
                path.touch()
                paths.append(str(path))
            return types.SimpleNamespace(status='ok', message='', textures={('MBT_Cube', ''): paths})
        export.export_project_textures = export_files
        state['edition'] = True
        with patch.dict(sys.modules, {'substance_painter.export': export}):
            result = json.loads(namespace['_mbt_export'](str(manifest)))
            assert result['state'] == 'EXPORTED', result
            assert len(result['texture_sets'][0]['textures']) == 5
            job['texture_sets'].append({'object': 'SecondCube', 'texture_set': 'MBT_Cube'})
            job['set_definitions'] = [{'texture_set': 'MBT_Cube', 'resolution': 512}]
            manifest.write_text(json.dumps(job), encoding='utf-8')
            def shared_export(config):
                assert len(config['exportList']) == 1
                assert config['exportParameters'][-1] == {
                    'filter': {'dataPaths': ['MBT_Cube']}, 'parameters': {'sizeLog2': 9}}
                return export_files(config)
            export.export_project_textures = shared_export
            result = json.loads(namespace['_mbt_export'](str(manifest)))
            assert result['state'] == 'EXPORTED', result
            assert len(result['texture_sets']) == 2
            assert result['texture_sets'][0]['textures'] == result['texture_sets'][1]['textures']
            job.pop('set_definitions')
            manifest.write_text(json.dumps(job), encoding='utf-8')
            project.file_path = lambda: str(Path(folder) / 'wrong.spp')
            assert 'does not match' in json.loads(namespace['_mbt_export'](str(manifest)))['error']
        state['edition'] = False
        assert json.loads(namespace['_mbt_status']())['state'] == 'CREATING'
        state['edition'] = True
        assert json.loads(namespace['_mbt_status']())['state'] == 'COMPLETE'
        assert spp.is_file() and state['settings'].default_texture_resolution == 1024
        result = json.loads(namespace['_mbt_create'](str(manifest)))
        assert 'open project' in result['error'] and state['created'] == 1
        state['open'] = False
        assert 'overwrite' in json.loads(namespace['_mbt_create'](str(manifest)))['error']
        spp.unlink()
        state['edition'] = False
        textures.all_texture_sets = lambda: []
        namespace['_mbt_create'](str(manifest))
        state['edition'] = True
        assert 'Texture sets differ' in json.loads(namespace['_mbt_status']())['error']
        assert not spp.exists()
    print('PASS: remote capabilities, deferred save, settings, project protection, texture-set mismatch', flush=True)


def live_export():
    client, info = bridge.connect(60041)
    if not info['project_open']:
        print('LIVE EXPORT SKIPPED: no open project', flush=True)
        return
    current = client.execute('__import__("json").dumps({"path": _mbt_project.file_path()})')['path']
    manifest = Path(current).parent / 'job.json'
    if not manifest.is_file():
        print('LIVE EXPORT SKIPPED: open project has no adjacent job.json', flush=True)
        return
    addon.register()
    addon.feature_manager.sync(type('Settings', (), {'enable_substance_painter': True})())
    job = jobs.read_job(str(manifest))
    # Disposable Blender scene only; Painter project is neither closed nor saved.
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    for entry in job['texture_sets']:
        bpy.ops.mesh.primitive_cube_add()
        bpy.context.object.name = entry['object']
        bpy.context.object.data.uv_layers.active.name = entry['uv_map']
    settings = bpy.context.scene.mbt_painter
    settings.last_job = str(manifest)
    result = bridge.export_maps(client, str(manifest))
    jobs.record_export(str(manifest), result)
    materials = importlib.import_module(f'{ROOT.name}.features.substance_painter.materials')
    print('LIVE EXPORT:', materials.import_maps(bpy.context), flush=True)
    for obj in bpy.context.scene.objects:
        assert obj.data.materials and obj.data.materials[0].get('mbt_painter_job') == job['job_id']
    addon.unregister()
    print('PASS: live Painter export, returned paths, Blender material import', flush=True)


if __name__ == '__main__':
    transport_tests()
    remote_tests()
    if '--live' in sys.argv:
        live()
    if '--live-export' in sys.argv:
        live_export()