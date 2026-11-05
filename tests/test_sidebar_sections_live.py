"""Disposable GUI smoke test: --factory-startup --python this_file. Auto-quits."""

import importlib
from pathlib import Path
import sys
import traceback

import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon = importlib.import_module(ROOT.name)
OUTPUT = Path('C:/tmp/mbt_sidebar_sections_live_result.txt')
stage = 0
draw_count = 0
draw_errors = []
sidebar_colors = {}


class MBT_TEST_PT_section_preview(bpy.types.Panel):
    bl_label = 'Toolkit Section Preview'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'WINDOW'

    def draw(self, context):
        global draw_count
        try:
            addon.panels.MBT_PT_main.draw(self, context)
            draw_count += 1
        except Exception:
            draw_errors.append(traceback.format_exc())


def check():
    global stage
    try:
        if stage == 0:
            sidebar = bpy.context.preferences.themes[0].regions.sidebars
            sidebar_colors.update({name: tuple(getattr(sidebar, name))
                                   for name in ('back', 'tab_back')})
            addon.register()
            entry = bpy.context.preferences.addons.new()
            entry.module = ROOT.name
            icons = addon.panels.section_icons
            assert all(tuple(getattr(sidebar, name)) == color
                       for name, color in sidebar_colors.items())
            for key, section in addon.panels.SECTION_BY_KEY.items():
                assert addon.panels.MBT_OT_select_section.description(
                    bpy.context, type('Section', (), {'section': key})()) == section[1]
            assert len(icons._previews) == len(addon.panels.SECTION_BY_KEY)
            assert len({icons.icon_kwargs(key)['icon_value']
                        for key in addon.panels.SECTION_BY_KEY}) == len(addon.panels.SECTION_BY_KEY)
            for preview in icons._previews.values():
                assert tuple(preview.icon_size) == (32, 32)
                assert any(preview.icon_pixels_float[3::4])
                rgba = list(preview.icon_pixels_float)
                for offset in range(0, len(rgba), 4):
                    assert all(channel <= rgba[offset + 3] + 1e-6
                               for channel in rgba[offset:offset + 3])
            bpy.types.VIEW3D_HT_header.append(MBT_TEST_PT_section_preview.draw)
            for area in bpy.context.window.screen.areas:
                if area.type == 'VIEW_3D':
                    area.spaces.active.show_region_ui = True
                    area.tag_redraw()
        elif stage == 1:
            bpy.ops.mbt.select_section(section='align')
            bpy.ops.mbt.select_section(section='tools', extend=True)
            assert addon.panels.visible_sections(entry_prefs()) == ['align', 'tools']
        elif stage == 2:
            assert draw_count > 0, 'Preview panel was not drawn'
            assert not draw_errors, '\n'.join(draw_errors)
            bpy.types.VIEW3D_HT_header.remove(MBT_TEST_PT_section_preview.draw)
            addon.unregister()
            sidebar = bpy.context.preferences.themes[0].regions.sidebars
            assert all(tuple(getattr(sidebar, name)) == color
                       for name, color in sidebar_colors.items())
            assert addon.panels.section_icons._previews is None
            OUTPUT.write_text('PASS GUI colored preview registration / real layout draw / selection / cleanup\n', encoding='utf-8')
            bpy.ops.wm.quit_blender()
            return None
        stage += 1
        return 1.5
    except Exception:
        OUTPUT.write_text(traceback.format_exc(), encoding='utf-8')
        bpy.ops.wm.quit_blender()
        return None


def entry_prefs():
    return bpy.context.preferences.addons[ROOT.name].preferences


bpy.app.timers.register(check, first_interval=1.0)