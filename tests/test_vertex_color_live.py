"""Disposable GUI smoke test; result/screenshot in system temp; auto-quits."""

import importlib
from pathlib import Path
import sys
import tempfile
import traceback
from types import SimpleNamespace

import bpy


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
OUTPUT = Path(tempfile.gettempdir()) / 'mbt_vertex_color_live_result.txt'
SCREENSHOT = Path(tempfile.gettempdir()) / 'mbt_vertex_color_live.png'
addon = importlib.import_module(ROOT.name)
stage = 0
errors = []
draws = 0
baseline = []
feature = None


class MBT_TEST_PT_vertex_color(bpy.types.Panel):
    bl_label = 'Vertex Color Test'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Item'
    bl_order = -100

    def draw(self, context):
        global draws
        try:
            addon.panels.MBT_PT_main.draw(self, context)
            self.layout.template_color_picker(context.scene.mbt_vertex_color, 'color', value_slider=True)
            draws += 1
        except Exception:
            errors.append(traceback.format_exc())


def check():
    global stage, feature, baseline
    try:
        area = next(area for area in bpy.context.screen.areas if area.type == 'VIEW_3D')
        region = next(region for region in area.regions if region.type == 'WINDOW')
        with bpy.context.temp_override(area=area, region=region):
            if stage == 0:
                addon.register()
                entry = bpy.context.preferences.addons.new()
                entry.module = ROOT.name
                entry.preferences.enable_vertex_color = True
                addon.feature_manager.sync(entry.preferences)
                entry.preferences.sidebar_sections = '["vertex_color"]'
                feature = importlib.import_module(ROOT.name + '.features.vertex_color')
                bpy.utils.register_class(MBT_TEST_PT_vertex_color)
                bpy.context.window.event_simulate(type='ESC', value='PRESS')
                bpy.context.window.event_simulate(type='ESC', value='RELEASE')
                area.spaces.active.show_region_ui = True
                area.spaces.active.shading.type = 'SOLID'
                bpy.ops.mbt.vertex_color_attribute(action='CREATE', name='Color')
                attribute = bpy.context.object.data.color_attributes.active_color
                for i, value in enumerate(attribute.data):
                    value.color = ((i % 3) / 2, 0.25, 0.65, (i % 4) / 3)
                baseline = [tuple(value.color) for value in attribute.data]
                settings = bpy.context.scene.mbt_vertex_color
                settings.tools = settings.attributes = True
                bpy.ops.mbt.vertex_color_preview(component='RGB')
            elif stage == 1:
                assert draws > 0, 'Native panel did not draw'
                feature.preview._draw()
                assert feature.preview._cache, 'GPU batch was not built'
                assert not any(error for batch, error in feature.preview._cache.values())
                for component in ('R', 'G', 'B', 'A'):
                    bpy.ops.mbt.vertex_color_preview(component=component)
                    feature.preview._draw()
                # Exercise the real live-edit callbacks with a captured dialog invocation.
                operator = SimpleNamespace(color=(1, 1, 1, 1))
                operator.fail = lambda error: (_ for _ in ()).throw(AssertionError(error))
                operator.cancel = lambda context: feature.operators.MBT_OT_vertex_color_edit.cancel(operator, context)
                fake_context = SimpleNamespace(
                    scene=bpy.context.scene, active_object=bpy.context.active_object,
                    mode=bpy.context.mode, selected_objects=bpy.context.selected_objects,
                    window_manager=SimpleNamespace(invoke_props_dialog=lambda *a, **k: {'RUNNING_MODAL'}))
                result = feature.operators.MBT_OT_vertex_color_edit.invoke(operator, fake_context, None)
                assert result == {'RUNNING_MODAL'} and operator._mixed
                operator.color = (0.1, 0.2, 0.3, 1)
                feature.operators._live_color(operator, bpy.context)
                attribute = bpy.context.object.data.color_attributes.active_color
                assert tuple(attribute.data[0].color) != baseline[0]
                operator.cancel(bpy.context)
                assert baseline == [tuple(value.color) for value in attribute.data]
                # Accept without changing the picker must retain a mixed attribute.
                feature.operators.MBT_OT_vertex_color_edit.invoke(operator, fake_context, None)
                feature.operators.MBT_OT_vertex_color_edit.execute(operator, bpy.context)
                assert baseline == [tuple(value.color) for value in attribute.data]
                bpy.ops.ed.undo_push(message='Vertex color baseline')
                bpy.context.scene.mbt_vertex_color.color = (0.9, 0.1, 0.2, 1)
                bpy.ops.mbt.vertex_color_apply(action='FILL')
                bpy.ops.ed.undo_push(message='Vertex color fill')
                bpy.ops.ed.undo()
                attribute = bpy.context.object.data.color_attributes.active_color
                assert baseline == [tuple(value.color) for value in attribute.data]
                bpy.ops.ed.redo()
                attribute = bpy.context.object.data.color_attributes.active_color
                assert baseline != [tuple(value.color) for value in attribute.data]
                bpy.ops.mbt.vertex_color_preview(component='A')
            elif stage == 2:
                feature.preview._draw()
                assert not errors, '\n'.join(errors)
                bpy.ops.screen.screenshot(filepath=str(SCREENSHOT))
            elif stage == 3:
                feature.preview.reset()
                assert not errors, '\n'.join(errors)
                bpy.utils.unregister_class(MBT_TEST_PT_vertex_color)
                addon.unregister()
                assert not feature.preview._handlers and not feature.preview._sessions
                OUTPUT.write_text('PASS native sidebar and picker layout / GPU RGB and RGBA preview / '
                                  'live cancel and mixed accept / undo-redo / cleanup\n', encoding='utf-8')
                bpy.ops.wm.quit_blender()
                return None
            area.tag_redraw()
        stage += 1
        return 1.5
    except Exception:
        OUTPUT.write_text(traceback.format_exc(), encoding='utf-8')
        bpy.ops.wm.quit_blender()
        return None


bpy.app.timers.register(check, first_interval=2.0)