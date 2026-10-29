"""Disposable background-Blender bake tests; -- --live opts into creating a test project."""
import importlib
import json
from pathlib import Path
import sys
import threading
import types
from enum import Enum
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
tests = importlib.import_module('test_painter_bridge')
bridge = tests.bridge


def gating_tests():
    for state in ('FAILED', 'CANCELLED', 'IDLE'):
        client = Mock()
        client.execute.return_value = {'state': state}
        with patch.object(bridge, 'export_maps') as export:
            try:
                bridge.bake(client, 'job.json')
            except bridge.BridgeError:
                pass
            else:
                raise AssertionError('Non-success bake exported: ' + state)
            export.assert_not_called()
            assert client.execute.call_count == 1
    client = Mock()
    cancel = threading.Event()
    with patch.object(bridge, 'export_maps') as export:
        cancel.set()
        try:
            bridge.bake(client, 'job.json', cancel=cancel)
        except bridge.BridgeError as error:
            assert 'before baking' in str(error)
        else:
            raise AssertionError('Pre-cancelled bake started')
        client.execute.assert_not_called()
        export.assert_not_called()
    cancel.clear()
    responses = iter(({'state': 'BAKING'}, {'cancel_requested': True}, {'state': 'CANCELLED'}))
    def cancelled_response(expression):
        cancel.set()
        return next(responses)
    client.execute.side_effect = cancelled_response
    with patch.object(bridge.time, 'sleep'), patch.object(bridge, 'export_maps') as export:
        try:
            bridge.bake(client, 'job.json', cancel=cancel)
        except bridge.BridgeError as error:
            assert 'CANCELLED' in str(error)
        else:
            raise AssertionError('Cancelled bake accepted')
        export.assert_not_called()
        assert client.execute.call_args_list[1].args == ('_mbt_cancel_bake()',)
    client = Mock()
    client.execute.return_value = {'state': 'BAKING'}
    with patch.object(bridge, 'export_maps') as export:
        try:
            bridge.bake(client, 'job.json', timeout=-1)
        except bridge.BridgeError as error:
            assert 'uncertain' in str(error)
        else:
            raise AssertionError('Timeout accepted')
        export.assert_not_called()
    client = Mock()
    client.execute.side_effect = [{'state': 'BAKED'}, {'state': 'FAILED'}]
    with patch.object(bridge, 'export_maps') as export:
        try:
            bridge.bake(client, 'job.json')
        except bridge.BridgeError:
            pass
        else:
            raise AssertionError('Failed save exported')
        export.assert_not_called()
    client = Mock()
    client.execute.side_effect = [{'state': 'BAKING', 'progress': 0.5}, {'state': 'BAKED'},
                                  {'state': 'WAITING'}, {'state': 'SAVED'}]
    with patch.object(bridge.time, 'sleep'), patch.object(bridge, 'export_maps', return_value={'state': 'EXPORTED'}) as export:
        assert bridge.bake(client, 'job.json')['state'] == 'EXPORTED'
        export.assert_called_once_with(client, 'job.json')
    print('PASS: bake failure, cancellation, timeout, save and export gating', flush=True)


def configuration_tests():
    usages = Enum('MeshMapUsage', 'Normal AO Curvature Position Thickness WorldSpaceNormal ID Height')
    project = types.ModuleType('substance_painter.project')
    textures = types.ModuleType('substance_painter.textureset')
    baking = types.ModuleType('substance_painter.baking')
    event = types.ModuleType('substance_painter.event')
    package = types.ModuleType('substance_painter')
    callbacks = {}
    event.BakingProcessProgress = 'progress'
    event.BakingProcessEnded = 'ended'
    event.DISPATCHER = types.SimpleNamespace(
        connect_strong=lambda key, callback: callbacks.__setitem__(key, callback),
        disconnect=lambda key, callback: callbacks.pop(key))
    textures.MeshMapUsage = usages
    textures.all_texture_sets = lambda: [types.SimpleNamespace(name=lambda: 'MBT_Test')]
    labels = {'None': 0, 'Always': 0, 'By Mesh Name': 1, 'Distance-based': 0, 'Material Color': 1}
    class Property:
        def enum_values(self):
            return labels
        def enum_value(self, label):
            return labels[label]
    common = {key: Property() for key in ('OutputSize', 'HipolyMesh', 'LowAsHigh',
        'MaxHeight', 'MaxDepth', 'RelativeScale', 'SubSampling', 'FilterMethod', 'CageMode',
        'LowpolySuffix', 'HipolySuffix')}
    color = Property()
    params = Mock()
    params.common.return_value = common
    params.baker.return_value = {'ColorSource': color}
    baking.BakingParameters = Mock()
    baking.BakingParameters.from_texture_set.return_value = params
    baking.CurvatureMethod = types.SimpleNamespace(FromMesh='mesh')
    baking.BakingStatus = types.SimpleNamespace(Success='success', Cancel='cancel')
    baking.bake_selected_textures_async = Mock(return_value=Mock())
    project.is_in_edition_state = lambda: True
    project.is_busy = lambda: False
    project.save = Mock()
    modules = {'substance_painter': package, 'substance_painter.project': project,
        'substance_painter.textureset': textures, 'substance_painter.baking': baking,
        'substance_painter.event': event}
    with TemporaryDirectory() as folder, patch.dict(sys.modules, modules):
        directory = Path(folder)
        high = directory / 'high.fbx'
        high.touch()
        project.file_path = lambda: str(directory / 'test.spp')
        job = {'project_file': project.file_path(), 'high_mesh': str(high), 'job_id': 'test',
            'resolution': 512, 'match_method': 'BY_NAME', 'bake_maps': ['NORMAL', 'CURVATURE', 'ID'],
            'texture_sets': [{'texture_set': 'MBT_Test'}],
            'baking': {'front_distance': 0.01, 'rear_distance': 0.02,
                'relative_distance': True, 'antialiasing': 'None', 'id_source': 'Material Color'}}
        manifest = directory / 'job.json'
        manifest.write_text(json.dumps(job), encoding='utf-8')
        namespace = {}
        source = (ROOT / 'features/substance_painter/painter_remote.py').read_text(encoding='utf-8')
        exec(compile(source, 'painter_remote.py', 'exec'), namespace)
        for status, expected in (('success', 'BAKED'), ('cancel', 'CANCELLED'), ('failure', 'FAILED')):
            assert json.loads(namespace['_mbt_bake'](str(manifest)))['state'] == 'BAKING'
            values = baking.BakingParameters.set.call_args.args[0]
            assert values[common['OutputSize']] == (9, 9)
            assert values[common['HipolyMesh']] == high.resolve().as_uri()
            assert values[common['LowAsHigh']] is False
            assert values[common['MaxDepth']] == 0.02
            assert values[common['FilterMethod']] == 1
            assert values[common['LowpolySuffix']] == '_low'
            assert values[common['HipolySuffix']] == '_high'
            assert values[color] == 1
            params.set_baker_enabled.assert_any_call(usages.Height, False)
            params.set_baker_enabled.assert_any_call(usages.Normal, True)
            callbacks['progress'](types.SimpleNamespace(progress=0.5))
            callbacks['ended'](types.SimpleNamespace(status=status))
            assert not callbacks
            assert json.loads(namespace['_mbt_bake_status']())['state'] == expected
            saved = json.loads(namespace['_mbt_save_baked'](str(manifest)))
            assert (saved.get('state') == 'SAVED') == (expected == 'BAKED')
        baking.bake_selected_textures_async.side_effect = RuntimeError('start failed')
        assert json.loads(namespace['_mbt_bake'](str(manifest)))['state'] == 'FAILED'
        assert json.loads(namespace['_mbt_bake_status']())['state'] == 'FAILED'
        assert not callbacks
        # Distinct sets must not inherit the active Blender set's bake settings.
        baking.bake_selected_textures_async.side_effect = None
        first_set = Mock()
        first_set.name.return_value = 'MBT_Test'
        second_set = Mock()
        second_set.name.return_value = 'MBT_Detail'
        textures.all_texture_sets = lambda: [first_set, second_set]
        textures.Resolution = lambda width, height: (width, height)
        other_common = {key: Property() for key in common}
        other_params = Mock()
        other_params.common.return_value = other_common
        baking.BakingParameters.from_texture_set.side_effect = lambda ts: params if ts == first_set else other_params
        job['texture_sets'].append({'texture_set': 'MBT_Test'})
        job['texture_sets'].append({'texture_set': 'MBT_Detail'})
        job['set_definitions'] = [
            {'texture_set': 'MBT_Test', 'resolution': 1024, 'bake_maps': ['NORMAL'], 'baking': job['baking']},
            {'texture_set': 'MBT_Detail', 'resolution': 2048, 'bake_maps': ['AO'],
             'baking': dict(job['baking'], front_distance=0.15)}]
        manifest.write_text(json.dumps(job), encoding='utf-8')
        params.reset_mock()
        assert json.loads(namespace['_mbt_bake'](str(manifest)))['state'] == 'BAKING'
        values = baking.BakingParameters.set.call_args.args[0]
        assert values[common['OutputSize']] == (10, 10)
        assert values[other_common['OutputSize']] == (11, 11)
        assert values[other_common['MaxHeight']] == 0.15
        first_set.set_resolution.assert_called_once_with((1024, 1024))
        second_set.set_resolution.assert_called_once_with((2048, 2048))
        params.set_baker_enabled.assert_any_call(usages.AO, False)
        other_params.set_baker_enabled.assert_any_call(usages.AO, True)
        other_params.set_baker_enabled.assert_any_call(usages.Normal, False)
        callbacks['ended'](types.SimpleNamespace(status='success'))
    print('PASS: bake configuration, events, terminal states, save gating and startup cleanup', flush=True)


if __name__ == '__main__':
    tests.transport_tests()
    tests.remote_tests()
    gating_tests()
    configuration_tests()
    if '--live' in sys.argv:
        tests.live()
        client, info = bridge.connect(60041)
        if not info['project_open'] or info['busy']:
            print('LIVE BAKE SKIPPED: Painter needs a ready disposable test project', flush=True)
            sys.exit(0)
        current = client.execute('__import__("json").dumps({"path": _mbt_project.file_path()})')['path']
        if not current or not Path(current).parent.parent.name.startswith('MBToolkit_Painter_Live_'):
            print('LIVE BAKE SKIPPED: only disposable MBToolkit live-test projects may be baked', flush=True)
            sys.exit(0)
        expression = '''__import__('json').dumps({
            'common': {k: {'value': str(v.value()), 'enums': v.enum_values()} for k,v in
                __import__('substance_painter.baking', fromlist=['']).BakingParameters.from_texture_set(
                _mbt_textureset.all_texture_sets()[0]).common().items()},
            'usages': [name for name in dir(_mbt_textureset.MeshMapUsage) if not name.startswith('_')]})'''
        print('BAKE DISCOVERY', client.execute(expression), flush=True)
        manifest = Path(current).parent / 'job.json'
        job = tests.jobs.read_job(str(manifest))
        print('ID DISCOVERY', client.execute('''__import__('json').dumps({k: v.enum_values() for k,v in
            __import__('substance_painter.baking', fromlist=['']).BakingParameters.from_texture_set(
            _mbt_textureset.all_texture_sets()[0]).baker(_mbt_textureset.MeshMapUsage.ID).items()})'''), flush=True)
        job['baking'] = {'front_distance': 0.01, 'rear_distance': 0.01, 'relative_distance': True,
                         'antialiasing': 'None', 'id_source': 'Material Color'}
        manifest.write_text(json.dumps(job), encoding='utf-8')
        result = bridge.bake(client, str(manifest), progress=lambda msg: print(msg, flush=True))
        tests.jobs.record_export(str(manifest), result)
        print('PASS: LIVE BAKE + SAVE + EXPORT', result, flush=True)
        tests.live_export()