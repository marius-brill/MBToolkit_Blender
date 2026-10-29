"""Disposable GUI real-layout test; auto-quits, result under system temp."""
import importlib
from pathlib import Path
import sys
import tempfile
import traceback
from types import SimpleNamespace

import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon = importlib.import_module(ROOT.name)
painter = importlib.import_module(ROOT.name + '.features.substance_painter')
runtime = painter.operators.runtime
OUTPUT = Path(tempfile.gettempdir()) / 'mbt_painter_ui_result.txt'
errors = []
draws = 0
stage = 0


def draw(self, context):
    global draws
    try:
        painter.draw(self.layout, context)
        draws += 1
    except Exception:
        errors.append(traceback.format_exc())


def check():
    global stage
    try:
        if stage == 0:
            addon.register()
            entry = bpy.context.preferences.addons.new()
            entry.module = ROOT.name
            entry.preferences.enable_substance_painter = True
            addon.feature_manager.sync(SimpleNamespace(enable_substance_painter=True))
            icons = addon.panels.section_icons
            assert len(icons._previews) == 8
            assert len(icons._action_previews) == 2
            assert icons.icon_kwargs('painter_app')['icon_value'] != icons.icon_kwargs('substance_painter')['icon_value']
            bpy.types.VIEW3D_HT_header.append(draw)
            bpy.context.scene.mbt_painter.report = 'Testing blue status and wrapped preparation message'
        elif stage == 1:
            assert draws > 0 and not errors, errors
            settings = bpy.context.scene.mbt_painter
            bpy.ops.mbt.painter_texture_set(action='ADD')
            bpy.ops.mbt.painter_texture_set(action='ADD')
            settings.texture_collection = settings.texture_sets[0].collection
            settings.bake_settings = True
            settings.advanced = True
            settings.preparation_timings = '[{"stage": "Snapshot high mesh: UI fixture", "seconds": 1.25}]'
            settings.bake_maps = {'NORMAL', 'ID'}
        elif stage == 2:
            assert not errors, errors
            runtime.start_preparation(bpy.context, 'AUTO')
            # Keep the busy state for redraw without evaluating test inputs.
            bpy.app.timers.unregister(runtime._timer)
        elif stage == 3:
            assert not errors, errors
            runtime.cleanup()
            bpy.context.scene.mbt_painter.report = 'Saved bake job.json is missing: test path. Restore the bake folder or choose New Project Next Bake.'
        else:
            assert not errors, errors
            runtime.cleanup()
            bpy.types.VIEW3D_HT_header.remove(draw)
            addon.unregister()
            OUTPUT.write_text(f'PASS: Painter real-layout collapsed/expanded/busy states, icons, status; {draws} draws\n')
            bpy.ops.wm.quit_blender()
            return None
        for area in bpy.context.screen.areas:
            area.tag_redraw()
        stage += 1
        return 1.0
    except Exception:
        OUTPUT.write_text(traceback.format_exc())
        bpy.ops.wm.quit_blender()
        return None


bpy.app.timers.register(check, first_interval=1.0)