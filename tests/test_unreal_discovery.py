"""Ordinary Python endpoint/config tests, no editor or network required."""

import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('mbt_discovery_common', ROOT / 'features/unreal_bridge/common.py')
common = importlib.util.module_from_spec(spec)
spec.loader.exec_module(common)
SECTION = '[/Script/PythonScriptPlugin.PythonScriptPluginSettings]\n'


class DiscoveryTests(unittest.TestCase):
    def test_config_and_override_precedence(self):
        with tempfile.TemporaryDirectory(prefix='mbt_discovery_') as folder:
            root = Path(folder)
            project = root / 'Test.uproject'
            config = root / 'Config/DefaultEngine.ini'
            config.parent.mkdir()
            self.assertEqual(common.project_discovery(project)['endpoint'], '239.0.0.1:6766')
            config.write_text(SECTION + 'bRemoteExecution=True\nRemoteExecutionMulticastGroupEndpoint=239.0.0.1:6768\n')
            info = common.project_discovery(project)
            self.assertEqual(info['endpoint'], '239.0.0.1:6768')
            self.assertTrue(info['enabled'])
            saved = root / 'Saved/Config/WindowsEditor/Engine.ini'
            saved.parent.mkdir(parents=True)
            saved.write_text(SECTION + 'RemoteExecutionMulticastGroupEndpoint="239.0.0.1:6770" ; comment\nbRemoteExecution=False\n')
            self.assertEqual(common.project_discovery(project)['endpoint'], '239.0.0.1:6770')
            self.assertFalse(common.project_discovery(project)['enabled'])
            self.assertEqual(common.project_discovery(project, override='239.0.0.1:6772')['endpoint'], '239.0.0.1:6772')
            self.assertEqual(common.project_discovery(project, override='239.0.0.1:6772')['source'], 'Blender override')

    def test_endpoint_validation(self):
        self.assertEqual(common.discovery_endpoint('239.0.0.1:6768'), ('239.0.0.1', 6768))
        for value in ('127.0.0.1:6768', 'example.com:6768', '239.0.0.1:0',
                      '239.0.0.1:65536', '239.0.0.1', 'bad:port'):
            with self.assertRaises(common.BridgeError):
                common.discovery_endpoint(value)


if __name__ == '__main__':
    unittest.main()