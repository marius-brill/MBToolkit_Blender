"""Local-only UE Python connection. This module does not access Blender data."""

import importlib.util
import json
from pathlib import Path
import socket
import time

from .common import BridgeError, discovery_endpoint, project_discovery, same_path


def load_client(engine):
    path = Path(engine) / 'Engine/Plugins/Experimental/PythonScriptPlugin/Content/Python/remote_execution.py'
    spec = importlib.util.spec_from_file_location('_mbt_unreal_remote_execution', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def matching_editors(nodes, project):
    """One candidate per protocol node, never one candidate per UDP reply."""
    project = Path(project)
    return list({node['node_id']: node for node in nodes
                 if node.get('node_id') and
                 same_path(node.get('project_root', ''), str(project.parent)) and
                 node.get('project_name', '').casefold() == project.stem.casefold()}.values())


def select_editor(candidates, preferred=''):
    if preferred:
        selected = next((node for node in candidates if node['node_id'] == preferred), None)
        if selected:
            return selected
    if len(candidates) == 1:
        return candidates[0]
    raise BridgeError('Multiple distinct Unreal sessions advertise this project. '
                      'Use Find Editors (refresh beside Editor), choose the intended Editor, and retry. '
                      'No assets were sent. Sessions: ' + ', '.join(node['node_id'] for node in candidates))


def execute(engine, request):
    client = load_client(engine)
    config = client.RemoteExecutionConfig()
    config.multicast_bind_address = '127.0.0.1'
    config.multicast_ttl = 0
    discovery = project_discovery(request['project'], engine, request.get('discovery_endpoint', ''))
    endpoint = discovery['endpoint']
    config.multicast_group_endpoint = discovery_endpoint(endpoint)
    # Avoid collisions with other local bridge clients using Epic's default port.
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        port = probe.getsockname()[1]
    config.command_endpoint = ('127.0.0.1', port)
    session = client.RemoteExecution(config)
    stage = 'discovery'
    try:
        session.start()
        deadline = time.monotonic() + 5.0
        candidates = []
        project = Path(request['project'])
        while time.monotonic() < deadline:
            candidates = matching_editors(session.remote_nodes, project)
            if candidates:
                preferred = request.get('node_id', '')
                if not preferred or any(node['node_id'] == preferred for node in candidates):
                    break
            time.sleep(0.1)
        if not candidates:
            nodes = session.remote_nodes
            if nodes:
                found = ', '.join(str(node.get('project_name', '?')) + ' at ' +
                                  str(node.get('project_root', '?')) for node in nodes)
                raise BridgeError(f'Discovery at {endpoint} found other project(s): {found}. '
                                  f'Expected {project}; open that exact project')
            hint = ' Project config has Python Remote Execution disabled.' if discovery['enabled'] is False else ''
            raise BridgeError(f'No Unreal discovery response at {endpoint} (from {discovery["source"]}).' + hint +
                              ' Check Unreal Python Remote Execution, its multicast endpoint and loopback bind '
                              'address, and the local firewall. Set Discovery Endpoint if runtime settings differ')
        if request['action'] == 'EDITORS':
            return {'message': f'Found {len(candidates)} editor session(s); choose one before sending',
                    'project': str(project), 'editors': candidates}
        selected = select_editor(candidates, request.get('node_id', ''))
        stage = 'command connection'
        session.open_command_connection(selected['node_id'])
        # Epic's client has no public command timeout. Bound its accepted socket so
        # a hung editor cannot leave the worker alive indefinitely.
        channel = session._command_connection._command_channel_socket
        if channel.getpeername()[0] != '127.0.0.1':
            raise BridgeError('Refusing a non-loopback Unreal connection')
        channel.settimeout(600)
        source = Path(__file__).with_name('unreal_side.py').read_text(encoding='utf-8')
        command = ('import json\n_mbt_scope = {}\nexec(' + repr(source) + ', _mbt_scope)\n'
                   'print("MBT_UNREAL_RESULT:" + json.dumps(_mbt_scope["run"](json.loads(' +
                   repr(json.dumps(request)) + '))))')
        stage = 'remote Python command'
        result = session.run_command(command, unattended=True)
        if not result.get('success'):
            raise BridgeError('Unreal remote Python failed: ' + str(result.get('result', result)))
        for line in result.get('output', []):
            text = line.get('output', '')
            if 'MBT_UNREAL_RESULT:' in text:
                payload = json.loads(text.split('MBT_UNREAL_RESULT:', 1)[1])
                payload['project'] = str(project)
                payload['node_id'] = selected['node_id']
                if request['action'] == 'TEST':
                    payload['message'] += ' — discovery ' + endpoint
                return payload
        raise BridgeError('Unreal returned no bridge result. Inspect its Output Log before retrying')
    except socket.timeout as exc:
        raise BridgeError(f'Unreal {stage} timed out at {endpoint}. '
                          'A submitted command may still finish; inspect Unreal before retrying') from exc
    except BridgeError:
        raise
    except (OSError, RuntimeError) as exc:
        raise BridgeError(f'Unreal {stage} failed at {endpoint}: {exc}') from exc
    finally:
        session.stop()