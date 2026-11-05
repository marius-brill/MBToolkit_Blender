"""Run ONLY in disposable Blender: --background --factory-startup --python-exit-code 1."""

import importlib
from pathlib import Path
import sys
from types import SimpleNamespace

import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon = importlib.import_module(ROOT.name)
manager = addon.feature_manager


class Layout:
    def row(self, **kwargs): return self
    def column(self, **kwargs): return self
    def box(self): return self
    def label(self, **kwargs): pass
    def separator(self): pass
    def prop(self, obj, name, **kwargs): assert hasattr(obj, name), name
    def operator(self, idname, **kwargs):
        category, name = idname.split('.')
        assert getattr(getattr(bpy.ops, category), name).get_rna_type()
        return SimpleNamespace()


def draw(prefs, tab):
    values = {name: getattr(prefs, name) for name in prefs.bl_rna.properties.keys()
              if name not in {'rna_type'}}
    values.update(layout=Layout(), tab=tab)
    addon.preferences.MBT_Preferences.draw(SimpleNamespace(**values), bpy.context)


def run():
    assert bpy.app.background
    assert not any(name.startswith(ROOT.name + '.features.') for name in sys.modules)
    addon.register()
    entry = bpy.context.preferences.addons.new()
    entry.module = ROOT.name
    prefs = entry.preferences
    assert prefs.tab == 'GENERAL'
    assert prefs.n_panel_enabled
    assert not manager._errors, manager._errors
    for key, label, default, paths in manager.FEATURES:
        assert getattr(prefs, 'enable_' + key) == default, key
        assert manager.is_enabled(key) == default, key
        if not default:
            for path in paths:
                assert f'{ROOT.name}.features.{path}' not in sys.modules, path
    draw(prefs, 'GENERAL')
    print('PASS requested defaults / no disabled runtime imports / General UI')

    pie = prefs.pies.add()
    pie.name = 'Preserved Pie'
    tab = prefs.n_panel_tabs.add()
    tab.name = 'Preserved Tab'
    tab.visible = False
    for key, label, default, paths in manager.FEATURES:
        setattr(prefs, 'enable_' + key, False)
    manager.sync(prefs)
    assert not manager._active
    assert not hasattr(bpy.types.Scene, 'mbt_uv')
    assert not hasattr(bpy.types.Scene, 'mbt_painter')
    assert not hasattr(bpy.types.Object, 'mbt_modifier_index')
    assert addon.panels._registered == [addon.panels.MBT_PT_main, addon.panels.MBT_PT_baking]
    assert not addon.panels.MBT_PT_baking.poll(bpy.context)
    for name in ('GENERAL', 'MODIFIERS', 'PIES', 'PERFORMANCE', 'UV', 'N_PANEL', 'PAINTER', 'ABOUT'):
        draw(prefs, name)
    pie.key = 'Q'  # Must not rebuild disabled keymaps.
    assert not importlib.import_module(f'{ROOT.name}.features.pie_menus.keymap')._items
    print('PASS all-off cleanup / disabled settings UI / retained storage')

    for key, label, default, paths in manager.FEATURES:
        for cycle in range(2):
            setattr(prefs, 'enable_' + key, True)
            manager.sync(prefs)
            assert manager.is_enabled(key), (key, manager._errors)
            assert len(manager._active) == 1, manager._active
            setattr(prefs, 'enable_' + key, False)
            manager.sync(prefs)
            assert not manager._active, key
        print('PASS independent enable / disable / re-enable:', key)
    assert prefs.pies[0].name == 'Preserved Pie'
    assert any(item.name == 'Preserved Tab' and not item.visible for item in prefs.n_panel_tabs)
    # Saved settings must govern registration, not just a post-startup timer.
    addon.unregister()
    addon.register()
    assert not manager._active
    assert not manager._errors
    addon.unregister()
    assert not bpy.app.timers.is_registered(manager._apply_pending)
    bpy.context.preferences.addons.remove(entry)
    print('ALL FEATURE PREFERENCES TESTS PASSED')


if __name__ == '__main__':
    if '--write-preferences' in sys.argv:
        import os
        import addon_utils
        assert 'BLENDER_USER_CONFIG' in os.environ, 'Use an isolated configuration!'
        addon_utils.enable(ROOT.name, default_set=True)
        prefs = bpy.context.preferences.addons[ROOT.name].preferences
        for key, label, default, paths in manager.FEATURES:
            setattr(prefs, 'enable_' + key, key == 'scene_stats' and '--mixed' in sys.argv)
        manager.sync(prefs)
        bpy.ops.wm.save_userpref()
        print('PASS isolated preferences written')
    elif '--read-preferences' in sys.argv:
        prefs = bpy.context.preferences.addons[ROOT.name].preferences
        manager._apply_pending()
        expected = {'scene_stats'} if '--mixed' in sys.argv else set()
        assert set(manager._active) == expected, manager._active
        assert not manager._errors, manager._errors
        for key, label, default, paths in manager.FEATURES:
            assert getattr(prefs, 'enable_' + key) == (key in expected)
            if key not in expected:
                for path in paths:
                    assert f'{ROOT.name}.features.{path}' not in sys.modules, path
        print('PASS fresh startup: saved preferences / only selected runtime imports:', expected)
    elif '--enable-defaults' in sys.argv:
        import addon_utils
        addon_utils.enable(ROOT.name, default_set=False)
        manager._apply_pending()
        assert not manager._errors, manager._errors
        assert {key for key, *_ in manager.FEATURES if manager.is_enabled(key)} == {
            key for key, label, default, paths in manager.FEATURES if default}
        addon_utils.disable(ROOT.name)
        assert not manager._active
        print('PASS real addon enable: restricted registration / deferred defaults / disable')
    else:
        run()