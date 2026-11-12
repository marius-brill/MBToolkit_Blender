"""Disposable Blender only: --factory-startup --python-exit-code 1 --python this_file.

Background checks exercise load events synchronously. GUI execution additionally
waits for the real event loop to initialize features after File > New.
"""
import importlib
from pathlib import Path
import sys
import tempfile
import traceback
from types import SimpleNamespace
from unittest.mock import patch

import addon_utils
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon = importlib.import_module(ROOT.name)
manager = addon.feature_manager
OUTPUT = Path(tempfile.gettempdir()) / 'mbt_lifecycle_recovery_result.txt'
draws = 0
draw_errors = []


def observe_draw(self, context):
    global draws
    try:
        addon.panels.MBT_PT_main.draw(self, context)
        draws += 1
    except Exception:
        draw_errors.append(traceback.format_exc())


def run():
    addon_utils.enable(ROOT.name, default_set=True, persistent=True)
    prefs = manager.get_prefs()
    assert prefs is not None
    assert not manager._active, 'Real addon enable should defer restricted initialization'
    assert bpy.app.timers.is_registered(manager._apply_pending)
    with patch.object(manager, 'get_prefs', return_value=None):
        assert manager._apply_pending() == 0.1
    bpy.ops.wm.read_homefile(use_empty=True)
    assert bpy.app.timers.is_registered(manager._apply_pending)
    manager._apply_pending()
    expected = {key for key, _, default, _ in manager.FEATURES if default}
    assert set(manager._active) == expected, manager._errors
    sidebar = importlib.import_module(ROOT.name + '.features.n_panel')
    sidebar._tick()
    prefs = manager.get_prefs()
    prefs.n_panel_tabs['MBToolkit'].visible = False
    assert not addon.panels.MBT_PT_main.poll(bpy.context)
    with patch.object(sidebar, 'restore', side_effect=AssertionError('Unrelated sync rebuilt panels')):
        manager.sync(prefs)
    assert not addon.panels.MBT_PT_main.poll(bpy.context)
    prefs.n_panel_tabs['MBToolkit'].visible = True

    # A real load must reschedule even after the one-shot initialization completed.
    if bpy.app.timers.is_registered(manager._apply_pending):
        bpy.app.timers.unregister(manager._apply_pending)
    with tempfile.TemporaryDirectory(prefix='mbt_lifecycle_') as directory:
        blend = str(Path(directory) / 'load.blend')
        bpy.ops.wm.save_as_mainfile(filepath=blend)
        for _ in range(2):
            bpy.ops.wm.open_mainfile(filepath=blend)
            assert bpy.app.timers.is_registered(manager._apply_pending)
            manager._apply_pending()
            assert set(manager._active) == expected, manager._errors
            assert addon.panels.MBT_PT_main.is_registered
            assert not manager._errors, manager._errors

    # One failing teardown must not block another feature or lose retry state.
    calls = []
    broken = SimpleNamespace(__name__='broken', unregister=lambda: (_ for _ in ()).throw(RuntimeError('injected teardown')))
    healthy = SimpleNamespace(__name__='healthy', unregister=lambda: calls.append('healthy'))
    with patch.object(manager, 'FEATURES', (('broken', '', False, ()), ('healthy', '', False, ()))), \
            patch.object(manager, '_active', {'broken': [broken], 'healthy': [healthy]}), \
            patch.object(manager, '_cleanup', {}), patch.object(manager, '_errors', {}):
        manager.sync(SimpleNamespace())
        assert calls == ['healthy']
        assert 'broken' in manager._cleanup
        assert 'injected teardown' in manager.error('broken')
        broken.unregister = lambda: calls.append('recovered')
        manager.sync(SimpleNamespace())
        assert not manager._cleanup and not manager._errors

    # Rollback errors must not replace the original failure or block later features.
    first = SimpleNamespace(__name__='first', register=lambda: None,
                            unregister=lambda: (_ for _ in ()).throw(RuntimeError('injected rollback')))
    second = SimpleNamespace(__name__='second',
                             register=lambda: (_ for _ in ()).throw(RuntimeError('injected register')))
    later = SimpleNamespace(__name__='later', register=lambda: calls.append('later'))
    modules = {'first': first, 'second': second, 'later': later}
    with patch.object(manager, 'FEATURES', (('broken', '', True, ('first', 'second')),
                                           ('later', '', True, ('later',)))), \
            patch.object(manager, 'import_module', side_effect=lambda name: modules[name.rsplit('.', 1)[-1]]), \
            patch.object(manager, '_active', {}), patch.object(manager, '_cleanup', {}), \
            patch.object(manager, '_errors', {}):
        manager.sync(SimpleNamespace())
        assert 'injected register' in manager.error('broken')
        assert 'injected rollback' in manager.error('broken')
        assert 'broken' in manager._cleanup
        assert manager.is_enabled('later')

    sidebar._tick()
    real_register = bpy.utils.register_class
    target = addon.panels.MBT_PT_baking
    def fail_one(cls):
        if cls is target:
            raise RuntimeError('injected panel failure')
        return real_register(cls)
    with patch.object(bpy.utils, 'register_class', side_effect=fail_one):
        try:
            sidebar.restore()
        except RuntimeError as exc:
            assert 'injected panel failure' in str(exc)
        else:
            raise AssertionError('Expected injected panel failure')
    assert addon.panels.MBT_PT_main.is_registered, 'One failed panel hid an unrelated panel'
    assert not target.is_registered
    real_register(target)
    sidebar.restore()
    assert not sidebar._originals
    addon_utils.disable(ROOT.name, default_set=True)
    assert manager._load_post not in bpy.app.handlers.load_post
    assert not bpy.app.timers.is_registered(manager._apply_pending)
    assert not bpy.app.timers.is_registered(sidebar._tick)
    assert manager._apply_pending() is None
    print('PASS deferred enable / File New / repeated file loads / visibility / isolated failures / cleanup')


def gui_finish():
    try:
        assert manager._active, 'Event-loop initialization did not run after File New'
        assert not manager._errors, manager._errors
        assert addon.panels.MBT_PT_main.is_registered
        assert not bpy.app.timers.is_registered(manager._apply_pending)
        assert draws > 0, 'Real UI layout did not draw'
        assert not draw_errors, '\n'.join(draw_errors)
        bpy.types.VIEW3D_HT_header.remove(observe_draw)
        addon_utils.disable(ROOT.name, default_set=True)
        OUTPUT.write_text('PASS lifecycle recovery / real GUI event-loop initialization / UI drawing\n', encoding='utf-8')
    except Exception:
        OUTPUT.write_text(traceback.format_exc(), encoding='utf-8')
    bpy.ops.wm.quit_blender()
    return None


if __name__ == '__main__':
    if not bpy.app.background and OUTPUT.exists():
        OUTPUT.unlink()
    run()
    if not bpy.app.background:
        addon_utils.enable(ROOT.name, default_set=True, persistent=True)
        bpy.ops.wm.read_homefile(use_empty=True)
        manager.schedule_sync()
        manager.schedule_sync()
        assert bpy.app.handlers.load_post.count(manager._load_post) == 1
        bpy.types.VIEW3D_HT_header.append(observe_draw)
        bpy.app.timers.register(gui_finish, first_interval=2.0)