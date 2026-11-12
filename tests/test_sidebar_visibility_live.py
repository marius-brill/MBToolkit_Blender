"""Disposable GUI only: --factory-startup --python-exit-code 1 --python this_file.

Observe the real sidebar Panel instance and runtime category enum, never a header
proxy. No user preferences are saved. The result is written to system temp.
"""
import importlib
import json
from pathlib import Path
import sys
import tempfile
import traceback

import addon_utils
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon = importlib.import_module(ROOT.name)
OUTPUT = Path(tempfile.gettempdir()) / 'mbt_sidebar_visibility_result.json'
stage = 0
draws = []
observations = []
original_draw = addon.panels.MBT_PT_main.draw


def observe(self, context):
    draws.append({'region': context.region.type, 'owner': self.bl_owner_id})
    original_draw(self, context)


def viewport():
    window = bpy.context.window_manager.windows[0]
    area = next(area for area in window.screen.areas if area.type == 'VIEW_3D')
    return window, area, next(region for region in area.regions if region.type == 'UI')


def categories():
    window, area, region = viewport()
    with bpy.context.temp_override(window=window, area=area, region=region):
        # The static RNA enum returns UNSUPPORTED; the live value is authoritative.
        return region.active_panel_category


def select_toolkit():
    window, area, region = viewport()
    with bpy.context.temp_override(window=window, area=area, region=region):
        area.spaces.active.show_region_ui = True
        region.active_panel_category = 'MBToolkit'
        area.tag_redraw()


def tick():
    global stage
    try:
        if stage == 0:
            addon_utils.enable(ROOT.name, default_set=True, persistent=True)
            addon.feature_manager.get_prefs().n_panel_enabled = False
            addon.panels.MBT_PT_main.draw = observe
            _, area, _ = viewport()
            area.spaces.active.show_region_ui = True
            area.tag_redraw()
        elif stage == 1:
            prefs = addon.feature_manager.get_prefs()
            pie = prefs.pies.add()
            pie.name = 'Lifecycle Test Pie'
            pie.key = 'F8'
            select_toolkit()
        elif stage in {2, 4, 6, 9, 13}:
            assert draws, 'Actual sidebar panel never drew'
            assert all(item['region'] == 'UI' for item in draws)
            assert all(item['owner'] == ROOT.name for item in draws), 'Sidebar rebuild lost add-on ownership'
            if stage in {9, 13}:
                report = importlib.import_module(ROOT.name + '.core.diagnostics').snapshot()
                assert report['runtime']['pie_menus.keymap']['shortcut_count'] == 1
                assert report['runtime']['modifier_list']['shortcut_count'] == 1
            observations.append({'stage': stage, 'draws': list(draws), 'categories': categories()})
            print('REAL SIDEBAR:', observations[-1], flush=True)
            draws.clear()
            sidebar = importlib.import_module(ROOT.name + '.features.n_panel')
            if stage == 2:
                # Workspace owner filter must retain panels explicitly allowed.
                bpy.context.workspace.use_filter_by_owner = True
                bpy.ops.wm.owner_enable(owner_id=ROOT.name)
                addon.feature_manager.get_prefs().n_panel_enabled = True
                sidebar.apply(addon.feature_manager.get_prefs())
                select_toolkit()
            elif stage == 4:
                sidebar.restore()
                select_toolkit()
            elif stage == 6:
                # A file load must recover through the event loop, no manual sync.
                bpy.ops.wm.read_homefile(use_empty=True)
            elif stage == 9:
                bpy.context.workspace.use_filter_by_owner = True
                if ROOT.name in bpy.context.workspace.owner_ids:
                    bpy.ops.wm.owner_disable(owner_id=ROOT.name)
                _, area, _ = viewport()
                area.tag_redraw()
            else:
                assert bpy.ops.mbt.copy_diagnostics() == {'FINISHED'}
                report = json.loads(bpy.context.window_manager.clipboard)
                assert report['features']['align']['active']
                addon.panels.MBT_PT_main.draw = original_draw
                addon_utils.disable(ROOT.name, default_set=True)
                OUTPUT.write_text(json.dumps({'status': 'PASS', 'observations': observations}, indent=2), encoding='utf-8')
                bpy.ops.wm.quit_blender()
                return None
        elif stage == 7:
            window, area, region = viewport()
            with bpy.context.temp_override(window=window, area=area, region=region):
                area.spaces.active.show_region_ui = True
                area.tag_redraw()
        elif stage == 8:
            select_toolkit()
        elif stage == 10:
            # Allow an intermediate redraw while the owner filter settles.
            draws.clear()
            _, area, _ = viewport()
            area.tag_redraw()
        elif stage == 11:
            assert not draws, 'Excluded workspace owner still drew in the actual sidebar'
            bpy.ops.wm.owner_enable(owner_id=ROOT.name)
            _, area, _ = viewport()
            area.tag_redraw()
        elif stage == 12:
            select_toolkit()
        stage += 1
        return 0.8
    except Exception:
        OUTPUT.write_text(json.dumps({'status': 'FAIL', 'error': traceback.format_exc(),
                                      'observations': observations}, indent=2), encoding='utf-8')
        traceback.print_exc()
        bpy.ops.wm.quit_blender()
        return None


assert not bpy.app.background, 'This test requires a disposable GUI process'
if OUTPUT.exists():
    OUTPUT.unlink()
bpy.app.timers.register(tick, first_interval=0.5, persistent=True)