"""Hotkeys for the pie menus. Rebuilt whenever a pie's key settings change."""

import bpy

from ...core.addon import get_prefs

_items = []  # (keymap, keymap_item) pairs we own
_running = False


def clear():
    for km, kmi in _items:
        try:
            km.keymap_items.remove(kmi)
        except Exception:
            pass
    _items.clear()


def rebuild():
    clear()
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon if wm else None
    prefs = get_prefs()
    if kc is None or prefs is None:  # background mode, or prefs not ready yet
        return
    km = kc.keymaps.new(name="3D View", space_type="VIEW_3D")
    for pie in prefs.pies:
        if pie.key == "NONE":
            continue
        kmi = km.keymap_items.new("mbt.call_pie", pie.key, "PRESS", ctrl=pie.ctrl,
                                 shift=pie.shift, alt=pie.alt, oskey=pie.oskey)
        kmi.properties.pie_name = pie.name
        _items.append((km, kmi))


def _delayed_init():
    if not _running:
        return None
    if get_prefs() is None or bpy.context.window_manager is None:
        return 0.2
    if not bpy.app.background and bpy.context.window_manager.keyconfigs.addon is None:
        return 0.2
    rebuild()
    return None  # run once


def register():
    global _running
    _running = True
    # Preferences are not reliably readable while register() is still running.
    if not bpy.app.timers.is_registered(_delayed_init):
        bpy.app.timers.register(_delayed_init, first_interval=0.2, persistent=True)


def unregister():
    global _running
    _running = False
    if bpy.app.timers.is_registered(_delayed_init):
        bpy.app.timers.unregister(_delayed_init)
    clear()
