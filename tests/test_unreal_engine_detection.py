"""Ordinary Python discovery tests; also checks real RNA operators in Blender."""

import importlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('mbt_engine_common', ROOT / 'features/unreal_bridge/common.py')
common = importlib.util.module_from_spec(spec)
spec.loader.exec_module(common)


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='mbt_engine_detection_')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.engine = self.make_engine('UE_5.7')
        self.project = self.base / 'Test.uproject'
        self.project.write_text(json.dumps({'EngineAssociation': '5.7'}))

    def make_engine(self, name, version=(5, 7, 4)):
        root = self.base / name
        client = root / common.REMOTE_CLIENT
        client.parent.mkdir(parents=True)
        client.write_text('# fixture; never executed')
        build = root / 'Engine/Build/Build.version'
        build.parent.mkdir(parents=True)
        build.write_text(json.dumps(dict(zip(('MajorVersion', 'MinorVersion', 'PatchVersion'), version))))
        editor = root / 'Engine/Binaries/Win64/UnrealEditor.exe'
        editor.parent.mkdir(parents=True)
        editor.touch()
        return root

    def test_manual_variants_and_invalid_override(self):
        for value in (self.engine, self.engine / 'Engine',
                      self.engine / 'Engine/Binaries/Win64',
                      self.engine / 'Engine/Binaries/Win64/UnrealEditor.exe',
                      '"' + str(self.engine) + '"'):
            self.assertEqual(common.engine_root(self.project, value), self.engine)
        with self.assertRaisesRegex(common.BridgeError, 'Invalid Unreal engine path'):
            common.engine_root(self.project, self.base / 'missing')

    def test_launcher_registry_standard_discovery(self):
        launcher = self.base / 'Epic/UnrealEngineLauncher/LauncherInstalled.dat'
        launcher.parent.mkdir(parents=True)
        launcher.write_text(json.dumps({'InstallationList': [
            {'AppName': 'UE_5.7', 'InstallLocation': str(self.engine)},
            {'AppName': 'UE_5.6', 'InstallLocation': str(self.base / 'stale')},
            {'AppName': 'FabPlugin_5.7', 'InstallLocation': str(self.engine)}]}))
        env = {name: str(self.base) for name in
               ('PROGRAMDATA', 'ProgramFiles', 'ProgramW6432', 'ProgramFiles(x86)')}
        with patch.dict(os.environ, env), patch.object(common, '_registry_engines', return_value=[]):
            records = common.installed_engines()
            self.assertEqual(len(records), 1)
            self.assertEqual(common.engine_root(self.project), self.engine)
            self.project.write_text(json.dumps({'EngineAssociation': '5.8'}))
            with self.assertRaisesRegex(common.BridgeError, 'No installed engine matches'):
                common.engine_root(self.project)
            launcher.write_text('broken json')
            self.assertEqual(common.installed_engines(), [])
            standard = self.base / 'Epic Games/UE_5.7'
            standard.parent.mkdir()
            self.engine.rename(standard)
            self.assertEqual(common.installed_engines()[0]['root'], standard)
            standard.rename(self.engine)
        # Source-build GUID and duplicate registrations refer to the same root.
        with patch.object(common, '_registry_engines', return_value=[
                ('{BUILD-GUID}', str(self.engine)), ('5.7', str(self.engine))]):
            self.project.write_text(json.dumps({'EngineAssociation': '{BUILD-GUID}'}))
            self.assertEqual(common.engine_root(self.project), self.engine)

    def test_ambiguity(self):
        other = self.make_engine('OtherBuild')
        with patch.object(common, 'installed_engines', return_value=[
                {'root': root, 'version': (5, 7, 4), 'associations': {'5.7'}}
                for root in (self.engine, other)]):
            with self.assertRaisesRegex(common.BridgeError, 'Multiple installed engines'):
                common.engine_root(self.project)

    def test_blender_controls_when_available(self):
        try:
            import bpy
        except ImportError:
            self.skipTest('Blender RNA checks require Blender')
        sys.path.insert(0, str(ROOT.parent))
        bridge = importlib.import_module(f'{ROOT.name}.features.unreal_bridge')
        bridge.register()
        try:
            settings = bpy.context.scene.mbt_unreal
            settings.project = str(self.project)
            settings.discovery_endpoint = '239.0.0.1:6768'
            self.assertIn('239.0.0.1:6768', settings.discovery_status)
            settings.discovery_endpoint = 'invalid'
            self.assertIn('must be IPv4 multicast', settings.discovery_status)
            settings.discovery_endpoint = ''
            for value in (self.engine / 'Engine', self.engine / 'Engine/Binaries/Win64/UnrealEditor.exe'):
                settings.engine = str(value)
                self.assertIn('UE 5.7.4:', settings.engine_status)
                self.assertEqual(bpy.ops.mbt.unreal_engine_path(filepath=str(value)), {'FINISHED'})
                self.assertEqual(Path(settings.engine), self.engine)
            settings.engine = '"' + str(self.engine) + '"'
            self.assertIn('UE 5.7.4:', settings.engine_status)
            settings.engine = str(self.base / 'missing')
            self.assertIn('Invalid Unreal engine path', settings.engine_status)
            settings.engine = str(self.engine)
            records = [{'root': self.engine, 'version': (5, 7, 4), 'associations': {'5.7'}}]
            with patch.object(bridge, 'installed_engines', return_value=records):
                self.assertEqual(bpy.ops.mbt.unreal_detect_engine(), {'FINISHED'})
            self.assertEqual(Path(settings.engine), self.engine)
            self.assertEqual(len(settings.builds), 1)
        finally:
            bridge.unregister()


if __name__ == '__main__':
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(EngineTests)
    if not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful():
        raise SystemExit(1)
    print('LOCAL INSTALLED BUILDS:', common.installed_engines())