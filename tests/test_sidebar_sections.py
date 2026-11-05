"""Pure selection tests with Python; integration checks in disposable Blender."""

import importlib
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('section_data', ROOT / 'core' / 'section_data.py')
data = importlib.util.module_from_spec(spec)
spec.loader.exec_module(data)


class SelectionTests(unittest.TestCase):
    def test_click_isolates(self):
        self.assertEqual(data.decode_selection(data.select_section(data.DEFAULT_SELECTION, 'align')), ['align'])

    def test_shift_appends_and_preserves_survivors(self):
        value = json.dumps(['uv_tools', 'tools'])
        value = data.select_section(value, 'align', True)
        self.assertEqual(data.decode_selection(value), ['uv_tools', 'tools', 'align'])
        value = data.select_section(value, 'tools', True)
        self.assertEqual(data.decode_selection(value), ['uv_tools', 'align'])
        value = data.select_section(value, 'tools', True)
        self.assertEqual(data.decode_selection(value), ['uv_tools', 'align', 'tools'])

    def test_empty_selection_is_retained(self):
        self.assertEqual(data.decode_selection(data.select_section('["tools"]', 'tools', True)), [])

    def test_corrupt_and_stale_settings(self):
        for value in ('invalid', '{}', 'null', None):
            self.assertEqual(data.decode_selection(value), list(data.SECTION_BY_KEY))
        self.assertEqual(data.decode_selection('["tools", "missing", "tools", [], 2]'), ['tools'])
        with self.assertRaises(ValueError):
            data.select_section('[]', 'missing')

    def test_distinct_catalog(self):
        self.assertEqual(len(set(entry[2] for entry in data.SECTIONS)), len(data.SECTIONS))
        self.assertEqual(len(set(entry[3] for entry in data.SECTIONS)), len(data.SECTIONS))


class Layout:
    def __init__(self, records): self.records = records
    def row(self, **kwargs): return Layout(self.records)
    def column(self, **kwargs): return Layout(self.records)
    def split(self, **kwargs):
        self.records.append(('split', kwargs))
        return Layout(self.records)
    def __setattr__(self, name, value):
        object.__setattr__(self, name, value)
        if name != 'records':
            self.records.append(('layout', {name: value}))
    def box(self):
        self.records.append(('box', {}))
        return Layout(self.records)
    def separator(self, **kwargs): pass
    def label(self, **kwargs): self.records.append(('label', kwargs))
    def prop(self, obj, name, **kwargs): assert hasattr(obj, name), name
    def prop_enum(self, obj, name, value, **kwargs):
        assert value in obj.bl_rna.properties[name].enum_items.keys(), value
    def menu(self, name, **kwargs):
        assert hasattr(bpy.types, name), name
        self.records.append(('menu', kwargs))
    def operator(self, name, **kwargs):
        self.records.append((name, kwargs))
        category, action = name.split('.')
        assert getattr(getattr(bpy.ops, category), action).get_rna_type()
        return SimpleNamespace()


def integration():
    assert bpy.app.background, 'Use a disposable background Blender process'
    sys.path.insert(0, str(ROOT.parent))
    addon = importlib.import_module(ROOT.name)
    sidebar = bpy.context.preferences.themes[0].regions.sidebars
    original_backgrounds = {name: tuple(getattr(sidebar, name)) for name in ('back', 'tab_back')}
    sidebar.back[3] = 0.35
    sidebar.tab_back[3] = 0.45
    # Theme colors are byte-quantized, so retain Blender's stored values.
    saved_alpha = {name: getattr(sidebar, name)[3] for name in original_backgrounds}
    addon.register()
    entry = bpy.context.preferences.addons.new()
    entry.module = ROOT.name
    prefs = entry.preferences
    panels = addon.panels
    try:
        for name, original in original_backgrounds.items():
            assert tuple(getattr(sidebar, name))[:3] == original[:3]
            assert getattr(sidebar, name)[3] == saved_alpha[name]
        assert not addon.feature_manager._errors, addon.feature_manager._errors
        assert set(panels.visible_sections(prefs)) == {'tools', 'align', 'script_runner', 'scene_stats'}
        panel_options = getattr(panels.MBT_PT_main, 'bl_options', set())
        assert 'HIDE_HEADER' not in panel_options
        assert 'HIDE_BACKDROP' not in panel_options
        header_records = []
        panels.MBT_PT_main.draw_header_preset(
            SimpleNamespace(layout=Layout(header_records)), bpy.context)
        assert header_records == [('mbt.open_prefs', {'text': '', 'icon': 'PREFERENCES'})]
        assert not hasattr(bpy.types, 'MBT_PT_tools')
        for key, *_ in data.SECTIONS:
            assert panels.MBT_OT_select_section.description(
                bpy.context, SimpleNamespace(section=key)) == data.SECTION_BY_KEY[key][1]
            glyph = panels.section_icons.pixels(key, data.SECTION_BY_KEY[key][3])
            assert len(glyph) == 32 * 32 * 4
            assert all(0 <= channel <= 1 for channel in glyph)
            assert any(glyph[3::4])
            transparent = opaque = 0
            color = data.SECTION_BY_KEY[key][3]
            for offset in range(0, len(glyph), 4):
                r, g, b, alpha = glyph[offset:offset + 4]
                assert all(abs(channel - accent * alpha) < 1e-7
                           for channel, accent in zip((r, g, b), color))
                if alpha == 0:
                    transparent += 1
                    assert (r, g, b) == (0, 0, 0)
                elif alpha == 1:
                    opaque += 1
            assert transparent > 200 and opaque > 60, (key, transparent, opaque)
            assert panels.section_icons.icon_kwargs(key)['icon'] in {
                item.identifier for item in bpy.types.UILayout.bl_rna.functions['label'].parameters['icon'].enum_items}
        def alpha_at(key, x, y):
            glyph = panels.section_icons.pixels(key, data.SECTION_BY_KEY[key][3])
            return glyph[((31 - y) * 32 + x) * 4 + 3]
        assert alpha_at('uv_tools', 8, 8) == 1.0
        assert alpha_at('uv_tools', 16, 8) == 0.0
        assert alpha_at('uv_tools', 16, 16) == 1.0
        assert alpha_at('align', 16, 16) == 0.0  # No crossing shafts.
        assert alpha_at('align', 6, 16) == 1.0
        assert alpha_at('align', 16, 26) == 1.0
        assert alpha_at('substance_painter', 16, 8) == 1.0
        assert alpha_at('substance_painter', 16, 24) == 0.0  # Crescent opening.
        assert bpy.ops.mbt.select_section(section='align') == {'FINISHED'}
        assert bpy.ops.mbt.select_section(section='tools', extend=True) == {'FINISHED'}
        assert panels.visible_sections(prefs) == ['align', 'tools']
        assert bpy.ops.mbt.select_section(section='align', extend=True) == {'FINISHED'}
        assert bpy.ops.mbt.select_section(section='align', extend=True) == {'FINISHED'}
        assert panels.visible_sections(prefs) == ['tools', 'align']
        records = []
        panels.MBT_PT_main.draw(SimpleNamespace(layout=Layout(records)), bpy.context)
        headings = [kw['text'] for kind, kw in records if kind == 'label']
        assert headings.index('Tools') < headings.index('Align')
        assert 'MBToolkit' not in headings
        assert not any(kind == 'mbt.open_prefs' for kind, kw in records)
        assert any(kw.get('scale_x') == 2.0 for kind, kw in records if kind == 'layout')
        assert any(kw.get('scale_y') == 2.0 for kind, kw in records if kind == 'layout')
        assert any(kw.get('emboss') == 'NORMAL' for kind, kw in records if kind == 'layout')
        assert sum(kind == 'box' for kind, kw in records) == 2
        buttons = [kw for kind, kw in records if kind == 'mbt.select_section']
        assert len(buttons) == 4 and sum(kw['depress'] for kw in buttons) == 2
        assert all(kw['emboss'] for kw in buttons)
        narrow = SimpleNamespace(region=SimpleNamespace(width=160), preferences=bpy.context.preferences)
        wide = SimpleNamespace(region=SimpleNamespace(width=900), preferences=bpy.context.preferences)
        assert 1 <= panels.selector_columns(narrow, 8) < 8
        assert panels.selector_columns(wide, 8) == 8
        assert sidebar.back[3] == saved_alpha['back']
        assert sidebar.tab_back[3] == saved_alpha['tab_back']
        print('PASS no outer wrapper / unchanged sidebar theme / ordered cards / highlighted toolbar / colored glyphs')

        operator = SimpleNamespace(section='script_runner', extend=False)
        operator.execute = lambda context: panels.MBT_OT_select_section.execute(operator, context)
        assert panels.MBT_OT_select_section.invoke(operator, bpy.context, SimpleNamespace(shift=True)) == {'FINISHED'}
        assert panels.visible_sections(prefs) == ['tools', 'align', 'script_runner']
        expanded = []
        panels.MBT_PT_main.draw(SimpleNamespace(layout=Layout(expanded)), bpy.context)
        assert sum(kind == 'box' for kind, kw in expanded) == 3
        assert bpy.ops.mbt.select_section(section='align', extend=True) == {'FINISHED'}
        contracted = []
        panels.MBT_PT_main.draw(SimpleNamespace(layout=Layout(contracted)), bpy.context)
        assert sum(kind == 'box' for kind, kw in contracted) == 2
        assert panels.visible_sections(prefs) == ['tools', 'script_runner']
        assert bpy.ops.mbt.select_section(section='align', extend=True) == {'FINISHED'}
        # Restore the expected order for subsequent feature lifecycle checks.
        prefs.sidebar_sections = json.dumps(['tools', 'align', 'script_runner'])
        saved = prefs.sidebar_sections
        prefs.enable_tools = False
        addon.feature_manager.sync(prefs)
        assert panels.visible_sections(prefs) == ['align', 'script_runner']
        assert prefs.sidebar_sections == saved
        prefs.enable_tools = True
        addon.feature_manager.sync(prefs)
        assert panels.visible_sections(prefs) == ['tools', 'align', 'script_runner']
        assert bpy.ops.mbt.select_section(section='uv_tools') == {'CANCELLED'}
        manager = importlib.import_module(f'{ROOT.name}.features.n_panel')
        manager._tick()
        assert not manager._error, manager._error
        assert panels.MBT_PT_main.is_registered
        print('PASS Shift event / disabled feature filtering / retained order / whole-tab manager coexistence')

        addon.unregister()
        assert sidebar.back[3] == saved_alpha['back']
        assert sidebar.tab_back[3] == saved_alpha['tab_back']
        addon.register()
        prefs = entry.preferences  # RNA instances must be reacquired after class registration.
        assert prefs.sidebar_sections == saved
        assert panels.visible_sections(prefs) == ['tools', 'align', 'script_runner']
        assert bpy.ops.mbt.select_section(section='tools') == {'FINISHED'}
        assert bpy.ops.mbt.select_section(section='tools', extend=True) == {'FINISHED'}
        records = []
        panels.MBT_PT_main.draw(SimpleNamespace(layout=Layout(records)), bpy.context)
        assert any(kw.get('text') == 'Choose a section above' for kind, kw in records)
        assert not any(kind == 'box' for kind, kw in records)
        print('PASS registration cycles / settings retention / empty selection')
    finally:
        if panels.MBT_PT_main.is_registered:
            addon.unregister()
        bpy.context.preferences.addons.remove(entry)
        assert sidebar.back[3] == saved_alpha['back']
        assert sidebar.tab_back[3] == saved_alpha['tab_back']
        for name, color in original_backgrounds.items():
            setattr(sidebar, name, color)
    assert not panels.MBT_PT_main.is_registered
    assert not panels.MBT_OT_select_section.is_registered
    assert panels.section_icons._previews is None
    print('ALL SIDEBAR SECTION INTEGRATION TESTS PASSED')


if __name__ == '__main__':
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(SelectionTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        raise AssertionError('Selection tests failed')
    try:
        import bpy
    except ImportError:
        print('Blender unavailable: integration checks skipped')
    else:
        integration()