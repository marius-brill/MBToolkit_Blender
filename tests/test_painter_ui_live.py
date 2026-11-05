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
        addon.panels.MBT_PT_baking.draw(self, context)
        addon.panels.MBT_PT_main.draw(self, context)
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
            assert set(icons._previews) == {section[0] for section in icons.SECTIONS}
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
            settings.projection_report = '{"correction_applied": false, "checked_samples": 256}'
            settings.advanced = True
            settings.preparation_timings = '[{"stage": "Snapshot high mesh: UI fixture", "seconds": 1.25}]'
            settings.bake_maps = {'NORMAL', 'ID'}
            settings.matching_report = 'Sculpt: ambiguous low groups. Best-effort assignment: Body.'
            bpy.ops.mesh.primitive_cube_add()
            mesh = bpy.context.object
            from importlib import import_module
            issue_ui = import_module(ROOT.name + '.features.substance_painter.issues')
            issue_ui.publish(bpy.context, [{'object': mesh.name, 'reason': 'Ambiguous assignment; inspect candidates.',
                'blocking': False, 'targets': [mesh.name], 'candidates': [
                    {'group': 'Body', 'score': 0.01, 'coverage': 0.75, 'sample_count': 128}]}])
        elif stage == 2:
            assert not errors, errors
            runtime.start_preparation(bpy.context, 'AUTO')
            # Keep the busy state for redraw without evaluating test inputs.
            bpy.app.timers.unregister(runtime._timer)
        elif stage == 3:
            assert not errors, errors
            bpy.context.scene.mbt_painter.report = 'Surface matching: ' + 'VeryLongMeshName_' * 30
        elif stage == 4:
            assert not errors, errors
            bpy.context.scene.mbt_painter.report = 'Evaluating low surface: Object_003'
        elif stage == 5:
            assert not errors, errors
            runtime.cleanup()
            bpy.context.scene.mbt_painter.report = 'Preparation failed: ' + 'Issue mesh; ' * 500
        elif stage == 6:
            assert not errors, errors
            runtime.cleanup()
            bpy.context.scene.mbt_painter.report = 'Saved bake job.json is missing: test path. Restore the bake folder or choose New Project Next Bake.'
        else:
            assert not errors, errors
            runtime.cleanup()
            bpy.types.VIEW3D_HT_header.remove(draw)
            addon.unregister()
            OUTPUT.write_text(f'PASS: separate Tools/Baking panels, Bake-only real-layout collapsed/expanded/busy states, icons, visibility, status; {draws} draws\n')
            bpy.ops.wm.quit_blender()
            return None
        # Change stored UI state in the timer, never inside a draw callback.
        bpy.context.scene.mbt_painter.ui_tab = 'BAKE'
        for area in bpy.context.screen.areas:
            area.tag_redraw()
        stage += 1
        return 1.0
    except Exception:
        OUTPUT.write_text(traceback.format_exc())
        bpy.ops.wm.quit_blender()
        return None


bpy.app.timers.register(check, first_interval=1.0)