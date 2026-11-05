"""Workspace separation, naming and visibility; disposable background Blender only."""
import importlib
from pathlib import Path
import sys
from types import SimpleNamespace

import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
sys.path.insert(0, str(ROOT / 'tests'))
import test_sidebar_sections as sidebar_tests

sidebar_tests.bpy = bpy
Layout = sidebar_tests.Layout


def main():
    assert bpy.app.background
    addon = importlib.import_module(ROOT.name)
    addon.register()
    entry = bpy.context.preferences.addons.new()
    entry.module = ROOT.name
    prefs = entry.preferences
    prefs.enable_substance_painter = True
    addon.feature_manager.sync(prefs)
    panels = addon.panels
    sets = importlib.import_module(ROOT.name + '.features.substance_painter.texture_sets')
    try:
        assert panels.MBT_PT_baking.bl_category != panels.MBT_PT_main.bl_category
        assert panels.MBT_PT_baking.poll(bpy.context)
        assert not hasattr(prefs, 'sidebar_workspace')
        records = []
        panels.MBT_PT_baking.draw(SimpleNamespace(layout=Layout(records)), bpy.context)
        assert any(kind == 'mbt.painter_assign' for kind, _ in records)
        assert not any(kind == 'mbt.select_section' for kind, _ in records)
        assert bpy.ops.mbt.select_section(section='align') == {'FINISHED'}
        records = []
        panels.MBT_PT_main.draw(SimpleNamespace(layout=Layout(records)), bpy.context)
        assert any(kind == 'mbt.select_section' for kind, _ in records)
        assert sum(kind == 'mbt.select_section' for kind, _ in records) == sum(
            addon.feature_manager.is_enabled(section[0])
            for section in panels.SECTIONS if section[0] != 'substance_painter')
        assert not any(kind == 'mbt.painter_connect' for kind, _ in records)
        assert bpy.ops.mbt.painter_texture_set(action='ADD') == {'FINISHED'}
        settings = bpy.context.scene.mbt_painter
        first = settings.texture_sets[0]
        assert first.collection.name == 'TextureSet1'
        assert first.low_collection.name == 'TextureSet1_low'
        assert first.high_collection.name == 'TextureSet1_high'
        assert first.low_collection.color_tag == 'COLOR_05'
        assert first.high_collection.color_tag == 'COLOR_02'
        # Reserve a name independently: generated names must never get .001 suffixes.
        bpy.data.collections.new('TextureSet2_high')
        assert bpy.ops.mbt.painter_texture_set(action='ADD') == {'FINISHED'}
        assert settings.texture_collection.name == 'TextureSet3'
        visibility = []

        class VisibilityLayout(Layout):
            def row(self, **kwargs):
                return VisibilityLayout(self.records)

            def prop(self, obj, name, **kwargs):
                assert hasattr(obj, name)
                self.records.append((obj, name, kwargs))

        low = settings.low_collection
        layers = sets.layer_collections(bpy.context, low)
        assert len(layers) == 1
        layers[0].hide_viewport = True
        low.hide_viewport = True
        sets.draw_visibility(VisibilityLayout(visibility), bpy.context, low)
        assert (layers[0], 'hide_viewport', {'text': '', 'icon': 'HIDE_OFF'}) in visibility
        assert (layers[0], 'exclude', {'text': '', 'icon': 'CHECKBOX_HLT'}) in visibility
        assert not any(record[0] == low and record[1] == 'hide_viewport'
                       for record in visibility if len(record) == 3)
        layers[0].exclude = True
        visibility.clear()
        sets.draw_visibility(VisibilityLayout(visibility), bpy.context, low)
        assert any(record[1] == 'exclude' for record in visibility if len(record) == 3)
        assert settings.ui_tab == 'BAKE'
        records = []
        panels.MBT_PT_baking.draw(SimpleNamespace(layout=Layout(records)), bpy.context)
        assert sum(kind == 'split' and kw.get('factor') == 0.72 for kind, kw in records) == 3
        manager = importlib.import_module(ROOT.name + '.features.n_panel')
        manager.refresh(prefs)
        assert 'MBT Baking' in prefs.n_panel_tabs
        prefs.enable_substance_painter = False
        addon.feature_manager.sync(prefs)
        assert not panels.MBT_PT_baking.poll(bpy.context)
        prefs.enable_substance_painter = True
        addon.feature_manager.sync(prefs)
        assert panels.MBT_PT_baking.poll(bpy.context)
        print('PASS: separate Tools/Baking panels, Bake tab, lifecycle, numbered names, role colors, hidden/excluded collection controls')
    finally:
        addon.unregister()
        bpy.context.preferences.addons.remove(entry)


if __name__ == '__main__':
    main()