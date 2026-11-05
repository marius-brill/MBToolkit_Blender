"""Ordinary-Python controlled tests for the connect-only live diagnostic."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('probe_painter_remote', ROOT / 'tests/probe_painter_remote.py')
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


def main():
    class Unavailable(RuntimeError):
        pass
    client = Mock(host='::1', port=60041)
    client.execute.side_effect = [{'mbt_ping': 1}, {'api': {'version': 'test'}, 'projection': {}}]
    bridge = SimpleNamespace(Client=Mock(return_value=client), BridgeError=RuntimeError,
                             ConnectionUnavailable=Unavailable, launch=Mock(),
                             detect_executable=Mock(return_value='Painter.exe'))
    with patch.object(probe, 'load_bridge', return_value=bridge):
        result = probe.probe()
        assert result['host'] == '::1' and not result['project_modified']
        client.check_endpoint.assert_called_once_with()
        # The entire helper source runs in a fresh namespace, not Painter globals.
        expression = client.execute.call_args.args[0]
        assert expression.endswith('({})') and 'exec(' in expression
        client.execute.reset_mock()
        client.execute.return_value = {'mbt_ping': 0}
        client.execute.side_effect = None
        try:
            probe.probe()
        except RuntimeError as error:
            assert 'handshake' in str(error)
        else:
            raise AssertionError('Invalid handshake accepted')
        assert client.execute.call_count == 1
    client.check_endpoint.side_effect = Unavailable('offline')
    with patch.object(probe, 'painter_running', return_value=True):
        try:
            probe.ensure_endpoint(bridge, client, allow_launch=True)
        except RuntimeError as error:
            assert 'already running' in str(error)
        else:
            raise AssertionError('Existing Painter was not protected')
        bridge.launch.assert_not_called()
    client.check_endpoint.side_effect = [Unavailable('offline'), None]
    with patch.object(probe, 'painter_running', return_value=False):
        assert probe.ensure_endpoint(bridge, client, allow_launch=True)
        bridge.launch.assert_called_once_with('Painter.exe')
    bridge.launch.reset_mock()
    client.check_endpoint.side_effect = Unavailable('offline')
    with patch.object(probe, 'painter_running', return_value=False), patch.object(probe.time, 'sleep'):
        bridge.launch.return_value.poll.return_value = 1
        try:
            probe.ensure_endpoint(bridge, client, allow_launch=True)
        except RuntimeError as error:
            assert 'exited' in str(error)
        else:
            raise AssertionError('Exited launcher accepted')
    client.check_endpoint.side_effect = Unavailable('offline')
    bridge.launch.reset_mock()
    with patch.object(probe, 'painter_running', return_value=False):
        try:
            probe.ensure_endpoint(bridge, client, allow_launch=True, startup_timeout=0)
        except RuntimeError as error:
            assert 'timed out' in str(error)
        else:
            raise AssertionError('Startup timeout ignored')
    print('PASS: connect-only remote probe, isolated namespace, IPv6 reporting and handshake failure')


if __name__ == '__main__':
    main()