"""Disposable GUI event test; requires --enable-event-simulate, no --background."""

import importlib
from pathlib import Path
import sys
import tempfile
import traceback

import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon = importlib.import_module(ROOT.name)
feature = importlib.import_module(ROOT.name + '.features.modifier_list')
RESULT = Path(tempfile.gettempdir()) / 'mbt_modifier_actions_live_result.txt'
positions = []
count = 0
cursor = (0, 0)


def fail():
    RESULT.write_text(traceback.format_exc(), encoding='utf-8')
    bpy.ops.wm.quit_blender()


def start():
    try:
        addon.register()
        bpy.context.window.event_simulate(type='ESC', value='PRESS')
        bpy.context.window.event_simulate(type='ESC', value='RELEASE')
        entry = bpy.context.preferences.addons.new()
        entry.module = ROOT.name
        feature.rebuild_keymap()
        obj = bpy.context.object
        obj.modifiers.clear()
        obj.modifiers.new('Hover Apply Probe', 'BEVEL')
        area = next(a for a in bpy.context.screen.areas if a.type == 'PROPERTIES')
        area.spaces.active.context = 'MODIFIER'
        area.tag_redraw()
        bpy.app.timers.register(prepare, first_interval=1.0)
    except Exception:
        fail()
    return None


def prepare():
    try:
        area = next(a for a in bpy.context.screen.areas if a.type == 'PROPERTIES')
        region = next(r for r in area.regions if r.type == 'WINDOW')
        # Scan the settings side of the Properties editor using real hover and
        # key events; toolbar/list occupy its upper portion.
        x = region.x + int(region.width * 0.65)
        positions.extend((x, y) for y in range(region.y + region.height - 320, region.y + 30, -10))
        bpy.app.timers.register(move, first_interval=0.1)
    except Exception:
        fail()
    return None


def move():
    global cursor
    try:
        if not bpy.context.object.modifiers:
            RESULT.write_text('PASS Ctrl+A applies selected modifier through real hover/key events', encoding='utf-8')
            bpy.ops.wm.quit_blender()
            return None
        assert positions, 'Ctrl+A never applied over scanned modifier settings'
        x, y = positions.pop(0)
        cursor = x, y
        bpy.context.window.event_simulate(type='MOUSEMOVE', value='NOTHING', x=x, y=y)
        bpy.app.timers.register(key, first_interval=0.1)
    except Exception:
        fail()
    return None


def key():
    try:
        x, y = cursor
        bpy.context.window.event_simulate(type='A', value='PRESS', ctrl=True, x=x, y=y)
        bpy.context.window.event_simulate(type='A', value='RELEASE', ctrl=True, x=x, y=y)
        bpy.app.timers.register(move, first_interval=0.15)
    except Exception:
        fail()
    return None


bpy.app.timers.register(start, first_interval=2.0)