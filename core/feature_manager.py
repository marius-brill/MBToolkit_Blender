"""Lazy optional-feature lifecycle; no eager feature runtime imports."""

from importlib import import_module
import traceback
import bpy

from .addon import ADDON_ID, get_prefs

# key, label, default, module paths (dependency order)
FEATURES = (
    ('script_runner', 'Script Runner', True, ('script_runner',)),
    ('tools', 'Rename / Clean Up', True, ('rename', 'clean_up')),
    ('align', 'Align', True, ('align',)),
    ('n_panel', 'Sidebar Tab Manager', True, ('n_panel',)),
    ('pie_menus', 'Pie Menus', True, ('pie_menus',)),
    ('modifier_list', 'Modifier Tools', True, ('modifier_list',)),
    ('scene_stats', 'Scene Performance', True, ('scene_stats',)),
    ('uv_tools', 'UV Tools', False, ('uv_tools',)),
    ('vertex_color', 'Vertex Color', False, ('vertex_color',)),
    ('substance_painter', 'Substance Painter Bridge / Bake', False, ('substance_painter',)),
    ('geonodes', 'Geometry Nodes / Low-to-High', False, ('geonodes',)),
    ('resample', 'Resample', False, ('resample',)),
)

_active = {}
_errors = {}
_running = False
_syncing = False


def is_enabled(key):
    return key in _active


def error(key):
    return _errors.get(key, '')


def sync(prefs=None):
    global _syncing
    if not _running or _syncing:
        return
    # addon_utils.enable uses RestrictBlend: feature runtimes may read scene data.
    # Wait for our timer rather than partially registering them in that context.
    if not hasattr(bpy.data, 'window_managers'):
        return
    prefs = prefs or get_prefs()
    _syncing = True
    try:
        manager = _active.get('n_panel')
        if manager:
            manager[0].restore()
        for key, label, default, paths in FEATURES:
            wanted = getattr(prefs, 'enable_' + key, default) if prefs else default
            if not wanted and key in _active:
                for module in reversed(_active[key]):
                    module.unregister()
                del _active[key]
                _errors.pop(key, None)
            elif wanted and key not in _active:
                loaded = []
                try:
                    for path in paths:
                        module = import_module(f'{ADDON_ID}.features.{path}')
                        module.register()
                        loaded.append(module)
                    _active[key] = loaded
                    _errors.pop(key, None)
                except Exception as exc:
                    for module in reversed(loaded):
                        module.unregister()
                    _errors[key] = str(exc)
                    traceback.print_exc()
        from ..ui import panels
        panels.refresh()
    finally:
        _syncing = False


def changed(self, context):
    if context is not None:
        context.preferences.is_dirty = True
    # RNA class changes must happen outside the property callback / UI draw.
    if _running and not bpy.app.timers.is_registered(_apply_pending):
        bpy.app.timers.register(_apply_pending, first_interval=0.0)


def _apply_pending():
    if not hasattr(bpy.data, 'window_managers'):
        return 0.1
    sync()
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            area.tag_redraw()
    return None


def register():
    global _running
    _running = True
    sync()
    # A fresh enable may create the preferences entry after register returns.
    if not bpy.app.timers.is_registered(_apply_pending):
        bpy.app.timers.register(_apply_pending, first_interval=0.0)


def unregister():
    global _running
    _running = False
    if bpy.app.timers.is_registered(_apply_pending):
        bpy.app.timers.unregister(_apply_pending)
    manager = _active.get('n_panel')
    if manager:
        manager[0].restore()
    for modules in reversed(tuple(_active.values())):
        for module in reversed(modules):
            module.unregister()
    _active.clear()
    _errors.clear()