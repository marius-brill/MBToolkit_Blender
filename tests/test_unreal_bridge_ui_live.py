"""Disposable GUI Blender only: draw the actual sidebar, then quit."""

import importlib
from pathlib import Path
import sys
import tempfile

import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
bridge = importlib.import_module(f'{ROOT.name}.features.unreal_bridge')
result = Path(tempfile.gettempdir()) / 'mbt_unreal_ui_result.txt'
draws = []
states = set()
original = bridge.MBT_PT_unreal.draw


def draw(self, context):
    try:
        original(self, context)
        draws.append(True)
        states.add(context.scene.mbt_unreal.show_connection)
    except Exception as exc:
        result.write_text('FAIL: ' + repr(exc))
        raise


bridge.MBT_PT_unreal.draw = draw
bridge.register()
bpy.context.scene.mbt_unreal.report = 'Test status wrapping: ' + 'long message ' * 15


def finish():
    if draws and states == {True, False}:
        result.write_text('PASS real Unreal sidebar draw / expanded and collapsed connection setup / status wrapping')
    else:
        result.write_text('FAIL panel did not draw both connection setup states: ' + repr(states))
    bpy.types.VIEW3D_HT_header.remove(draw)
    bridge.unregister()
    bpy.ops.wm.quit_blender()


def start():
    bpy.types.VIEW3D_HT_header.append(draw)
    for area in bpy.context.screen.areas:
        if area.type == 'VIEW_3D':
            area.spaces.active.show_region_ui = True
            area.tag_redraw()
    def collapse():
        bpy.context.scene.mbt_unreal.show_connection = False
        for area in bpy.context.screen.areas:
            area.tag_redraw()
    bpy.app.timers.register(collapse, first_interval=1)
    bpy.app.timers.register(finish, first_interval=3)


bpy.app.timers.register(start, first_interval=1)