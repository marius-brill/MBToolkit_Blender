"""Background Blender client check against ONLY the generated disposable UE editor."""

import importlib
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
connection = importlib.import_module(f'{ROOT.name}.features.unreal_bridge.connection')
common = importlib.import_module(f'{ROOT.name}.features.unreal_bridge.common')
project = Path((Path(tempfile.gettempdir()) / 'mbt_unreal_latest_test.txt').read_text())
assert project.parent.name.startswith('mbt_unreal_test_')
engine = common.engine_root(project)
result = connection.execute(engine, {'action': 'TEST', 'project': str(project)})
assert result['message'].casefold().startswith('connected: bridgetest.uproject'), result
request = {'action': 'SEND', 'project': str(project), 'destination': '/Game/RemoteTest',
           'replace': False, 'assets': [{'name': 'SM_BridgeTest',
                                        'file': str(project.parent / 'SM_BridgeTest.fbx')}]}
assert connection.execute(engine, request)['assets'] == ['/Game/RemoteTest/SM_BridgeTest']
request['node_id'] = result['node_id']
request['assets'] = [{'name': 'SM_BatchA', 'file': str(project.parent / 'SM_BridgeTest.fbx')},
                     {'name': 'SM_BatchB', 'file': str(project.parent / 'SM_BridgeTest.fbx')}]
batch = connection.execute(engine, request)
assert batch['assets'] == ['/Game/RemoteTest/SM_BatchA', '/Game/RemoteTest/SM_BatchB'], batch
assert batch['node_id'] == result['node_id']
editors = connection.execute(engine, {'action': 'EDITORS', 'project': str(project)})
assert any(node['node_id'] == result['node_id'] for node in editors['editors'])
print('PASS local discovery / exact project / remote execution / end-to-end import')
# Quit only the disposable project, guarded inside Unreal.
client = connection.load_client(engine)
config = client.RemoteExecutionConfig()
config.multicast_group_endpoint = common.discovery_endpoint(common.project_discovery(project, engine)['endpoint'])
session = client.RemoteExecution(config)
import time
try:
    session.start()
    time.sleep(2)
    node = next(node for node in session.remote_nodes
                if common.same_path(node.get('project_root', ''), str(project.parent)))
    session.open_command_connection(node['node_id'])
    session.run_command('import unreal, os\n'
                        'assert "mbt_unreal_test_" in unreal.Paths.project_dir()\n'
                        'unreal.SystemLibrary.quit_editor()')
finally:
    session.stop()