"""Controlled UI guard/open safety checks; --live-ui probes without changing projects."""
import importlib
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import ModuleType
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]


def main():
    project = ModuleType('substance_painter.project')
    ui = ModuleType('substance_painter.ui')
    window = Mock()
    window.isEnabled.return_value = True
    window.isVisible.return_value = False
    ui.get_main_window = Mock(return_value=window)
    ui.show_main_window = Mock()
    timer = Mock()
    qt = ModuleType('PySide6.QtCore')
    qt.QTimer = Mock(return_value=timer)
    modules = {'substance_painter': ModuleType('substance_painter'),
               'substance_painter.project': project, 'substance_painter.ui': ui,
               'substance_painter.textureset': ModuleType('substance_painter.textureset'),
               'PySide6': ModuleType('PySide6'), 'PySide6.QtCore': qt}
    with patch.dict(sys.modules, modules):
        namespace = {}
        exec(compile((ROOT / 'features/substance_painter/painter_remote.py').read_text(), 'remote', 'exec'), namespace)
        assert json.loads(namespace['_mbt_guard_acquire']())['state'] == 'RESERVED'
        window.setEnabled.assert_called_once_with(False)
        window.hide.assert_called_once()
        assert 'already reserved' in json.loads(namespace['_mbt_guard_acquire']())['error']
        assert namespace['_mbt_guard_window']
        watchdog = timer.timeout.connect.call_args.args[0]
        namespace['_mbt_guard_deadline'] = 0
        watchdog()
        assert '_mbt_guard_window' not in namespace
        window.setEnabled.assert_called_with(True)
        ui.show_main_window.assert_called_once()
        assert json.loads(namespace['_mbt_guard_release']())['state'] == 'RELEASED'
        ui.get_main_window.side_effect = RuntimeError('UI unavailable')
        assert 'UI unavailable' in json.loads(namespace['_mbt_guard_acquire']())['error']
        ui.get_main_window.side_effect = None
        with TemporaryDirectory() as folder:
            path = Path(folder) / 'asset.spp'
            project.is_busy = Mock(return_value=False)
            project.is_open = Mock(return_value=False)
            project.open = Mock()
            assert 'does not exist' in json.loads(namespace['_mbt_open_project'](str(path)))['error']
            path.touch()
            assert json.loads(namespace['_mbt_open_project'](str(path)))['state'] == 'OPENED'
            project.open.assert_called_once_with(str(path.resolve()))
            project.is_open.return_value = True
            project.file_path = Mock(return_value=str(Path(folder) / 'unrelated.spp'))
            assert 'unrelated' in json.loads(namespace['_mbt_open_project'](str(path)))['error']
            project.open.assert_called_once()
            project.is_busy.return_value = True
            assert 'busy' in json.loads(namespace['_mbt_open_project'](str(path)))['error']
    print('PASS: protected window, duplicate reservation, watchdog recovery, UI failures, safe project opening', flush=True)
    if '--live-ui' in sys.argv:
        sys.path.insert(0, str(ROOT.parent))
        bridge = importlib.import_module(ROOT.name + '.features.substance_painter.bridge')
        client, info = bridge.connect(60041, bridge.detect_executable(), allow_launch=True)
        print('LIVE API:', info, flush=True)
        try:
            result = client.execute('_mbt_guard_acquire()')
            assert result['state'] == 'RESERVED'
            actual = client.execute('__import__("json").dumps({"enabled": _mbt_guard_window[0].isEnabled(), "visible": _mbt_guard_window[0].isVisible()})')
            assert actual == {'enabled': False, 'visible': False}, actual
        finally:
            client.execute('_mbt_guard_release()')
        print('PASS LIVE: Painter window disabled/hidden and restored; project untouched', flush=True)


if __name__ == '__main__':
    main()