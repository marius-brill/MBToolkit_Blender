"""Lazy optional-feature lifecycle; no eager feature runtime imports."""

from importlib import import_module
import traceback
import bpy
from bpy.app.handlers import persistent

from .addon import ADDON_ID, get_prefs
from .registry import registration_owner

# key, label, default, module paths (dependency order)
FEATURES = (
    ('script_runner', 'Script Runner', True, ('script_runner',)),
    ('tools', 'Tools / Concepting', True, ('rename', 'clean_up', 'concepting')),
    ('align', 'Align', True, ('align',)),
    ('n_panel', 'Sidebar Tab Manager', True, ('n_panel',)),
    ('pie_menus', 'Pie Menus', True, ('pie_menus',)),
    ('modifier_list', 'Modifier Tools', True, ('modifier_list',)),
    ('scene_stats', 'Scene Performance', True, ('scene_stats',)),
    ('uv_tools', 'UV Tools', False, ('uv_tools',)),
    ('vertex_color', 'Vertex Color', False, ('vertex_color',)),
    ('substance_painter', 'Substance Painter Bridge / Bake', False, ('substance_painter',)),
    ('unreal_bridge', 'Blender to Unreal Bridge', False, ('unreal_bridge',)),
    ('geonodes', 'Geometry Nodes / Low-to-High', False, ('geonodes',)),
    ('resample', 'Resample', False, ('resample',)),
)

_active = {}
_errors = {}
_cleanup = {}
_running = False
_syncing = False
_repair_pending = False


def is_enabled(key):
    return key in _active


def error(key):
    return _errors.get(key, '')


def _unload(modules):
    """Try every module; keep only failed teardown steps for an explicit retry."""
    failed, errors = [], []
    for module in reversed(modules):
        try:
            module.unregister()
        except Exception as exc:
            failed.insert(0, module)
            errors.append(f'{module.__name__}: {exc}')
            traceback.print_exc()
    return failed, errors


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
        for key, label, default, paths in FEATURES:
            wanted = getattr(prefs, 'enable_' + key, default) if prefs else default
            if key in _cleanup:
                remaining, errors = _unload(_cleanup[key])
                if remaining:
                    _cleanup[key] = remaining
                    _errors[key] = 'Cleanup failed: ' + '; '.join(errors)
                    continue
                del _cleanup[key]
                _errors.pop(key, None)
            if not wanted and key in _active:
                remaining, errors = _unload(_active.pop(key))
                if remaining:
                    _cleanup[key] = remaining
                    _errors[key] = 'Disable failed: ' + '; '.join(errors)
                else:
                    _errors.pop(key, None)
            elif wanted and key not in _active:
                loaded = []
                try:
                    for path in paths:
                        module = import_module(f'{ADDON_ID}.features.{path}')
                        with registration_owner(ADDON_ID, ADDON_ID):
                            module.register()
                        loaded.append(module)
                    _active[key] = loaded
                    _errors.pop(key, None)
                except Exception as exc:
                    traceback.print_exc()
                    remaining, errors = _unload(loaded)
                    if remaining:
                        _cleanup[key] = remaining
                    _errors[key] = str(exc)
                    if errors:
                        _errors[key] += '; rollback failed: ' + '; '.join(errors)
            elif not wanted:
                _errors.pop(key, None)
        from ..ui import panels
        panels.refresh()
    finally:
        _syncing = False


def changed(self, context):
    if context is not None:
        context.preferences.is_dirty = True
    # RNA class changes must happen outside the property callback / UI draw.
    schedule_sync()


def schedule_sync(repair=False):
    global _repair_pending
    _repair_pending = _repair_pending or repair
    if _running and not bpy.app.timers.is_registered(_apply_pending):
        bpy.app.timers.register(_apply_pending, first_interval=0.0, persistent=True)


@persistent
def _load_post(_):
    # Never change RNA registrations inside a file-load handler.
    schedule_sync(repair=True)


def _apply_pending():
    global _repair_pending
    if not _running:
        return None
    if (not hasattr(bpy.data, 'window_managers') or get_prefs() is None
            or bpy.context.window_manager is None):
        return 0.1
    sync()
    if _repair_pending:
        from .diagnostics import reconcile
        reconcile()
        _repair_pending = False
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            area.tag_redraw()
    return None


def register():
    global _running
    _running = True
    if _load_post not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(_load_post)
    sync()
    # A fresh enable may create the preferences entry after register returns.
    schedule_sync()


def unregister():
    global _running, _repair_pending
    _running = False
    _repair_pending = False
    if _load_post in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_load_post)
    if bpy.app.timers.is_registered(_apply_pending):
        bpy.app.timers.unregister(_apply_pending)
    for key, modules in reversed(tuple(_active.items()) + tuple(_cleanup.items())):
        remaining, errors = _unload(modules)
        if errors:
            print(f'MBToolkit teardown ({key}): ' + '; '.join(errors))
    _active.clear()
    _cleanup.clear()
    _errors.clear()