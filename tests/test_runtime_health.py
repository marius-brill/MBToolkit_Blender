"""Disposable background Blender regression checks; never save user preferences."""
import importlib
import json
from pathlib import Path
import sys
from unittest.mock import patch

import addon_utils
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon = importlib.import_module(ROOT.name)
registry = importlib.import_module(ROOT.name + '.core.registry')
diagnostics = importlib.import_module(ROOT.name + '.core.diagnostics')


def run():
    addon_utils.enable(ROOT.name, default_set=True, persistent=True)
    manager = addon.feature_manager
    manager._apply_pending()
    prefs = manager.get_prefs()
    sidebar = importlib.import_module(ROOT.name + '.features.n_panel')
    pie = importlib.import_module(ROOT.name + '.features.pie_menus.keymap')
    modifier = importlib.import_module(ROOT.name + '.features.modifier_list')
    before = json.dumps(diagnostics.snapshot(), sort_keys=True)
    assert json.dumps(diagnostics.snapshot(), sort_keys=True) == before
    assert bpy.ops.mbt.copy_diagnostics() == {'FINISHED'}
    # Background Blender has no OS clipboard backend.
    assert diagnostics.snapshot()['features']['align']['active']
    print('PASS read-only snapshot and copy diagnostics operator')

    for module, timer in ((sidebar, sidebar._tick), (pie, pie._delayed_init),
                          (modifier, modifier._init_keymap)):
        if bpy.app.timers.is_registered(timer):
            bpy.app.timers.unregister(timer)
    bpy.app.handlers.load_post.remove(manager._load_post)
    assert bpy.ops.mbt.retry_initialization() == {'FINISHED'}
    manager._apply_pending()
    assert manager._load_post in bpy.app.handlers.load_post
    assert bpy.app.timers.is_registered(sidebar._tick)
    assert bpy.app.timers.is_registered(pie._delayed_init)
    assert bpy.app.timers.is_registered(modifier._init_keymap)
    bpy.ops.wm.read_homefile(use_empty=True)
    assert bpy.app.timers.is_registered(pie._delayed_init)
    assert bpy.app.timers.is_registered(modifier._init_keymap)
    print('PASS active-runtime reconciliation and interrupted shortcut initialization')

    # Do not resurrect intentionally removed panels, e.g. third-party hiding.
    sidebar.restore()
    target = addon.panels.MBT_PT_baking
    bpy.utils.unregister_class(target)
    diagnostics.reconcile()
    assert not target.is_registered
    assert not diagnostics.snapshot()['panels'][target.__name__]
    with registry.registration_owner(ROOT.name, ROOT.name):
        bpy.utils.register_class(target)

    # A failure within a feature, not merely between feature modules, rolls back.
    for key, failing_module in (
            ('geonodes', ROOT.name + '.features.geonodes.crease_by_angle'),
            ('uv_tools', ROOT.name + '.features.uv_suite.operators')):
        setattr(prefs, 'enable_' + key, True)
        module = importlib.import_module(failing_module)
        real_register = bpy.utils.register_class
        failed_class = module.classes[-1]
        def fail(cls):
            if cls is failed_class:
                raise RuntimeError('injected partial registration')
            real_register(cls)
        with patch.object(bpy.utils, 'register_class', side_effect=fail):
            manager.sync(prefs)
        assert not manager.is_enabled(key)
        assert 'injected partial registration' in manager.error(key)
        assert all(not cls.is_registered for cls in module.classes)
        if key == 'uv_tools':
            assert not hasattr(bpy.types.Scene, 'mbt_uv')
        manager.sync(prefs)
        assert manager.is_enabled(key), manager.error(key)
        setattr(prefs, 'enable_' + key, False)
        manager.sync(prefs)
    print('PASS partial Geometry Nodes / UV rollback and retry without duplicate classes')
    addon_utils.disable(ROOT.name, default_set=True)
    assert not bpy.app.timers.is_registered(pie._delayed_init)
    assert not bpy.app.timers.is_registered(modifier._init_keymap)
    print('ALL RUNTIME HEALTH TESTS PASSED')


if __name__ == '__main__':
    assert bpy.app.background
    run()