"""Read-only lifecycle snapshot and narrow, explicit runtime reconciliation."""
import sys
import bpy

from .addon import ADDON_ID, get_prefs
from . import feature_manager


def snapshot(context=None):
    context = context or bpy.context
    prefs = get_prefs(context)
    from ..ui import panels
    features = {}
    for key, _, default, _ in feature_manager.FEATURES:
        modules = feature_manager._active.get(key, ())
        # Inspect already-loaded descendants only: diagnostics must not import
        # optional runtimes or initialize scene state.
        prefixes = tuple(module.__name__ for module in modules)
        descendants = [module for name, module in tuple(sys.modules.items())
                       if any(name == prefix or name.startswith(prefix + '.') for prefix in prefixes)]
        classes = {cls for module in descendants
                   for cls in getattr(module, '__dict__', {}).get('classes', ())}
        missing = sorted(cls.__name__ for cls in classes if not cls.is_registered)
        features[key] = {'requested': getattr(prefs, 'enable_' + key, default) if prefs else None,
                         'active': bool(modules), 'missing_classes': missing,
                         'error': feature_manager.error(key)}
    workspace = getattr(context, 'workspace', None)
    result = {'running': feature_manager._running,
              'sync_timer': bpy.app.timers.is_registered(feature_manager._apply_pending),
              'load_handler': feature_manager._load_post in bpy.app.handlers.load_post,
              'features': features,
              'panels': {cls.__name__: cls.is_registered for cls in panels.classes
                         if issubclass(cls, bpy.types.Panel)},
              'hidden_tabs': [item.name for item in prefs.n_panel_tabs if not item.visible] if prefs else [],
              'sidebar_management': bool(prefs and prefs.n_panel_enabled and feature_manager.is_enabled('n_panel')),
              'workspace_filter': bool(workspace and workspace.use_filter_by_owner),
              'workspace_owners': [item.name for item in workspace.owner_ids] if workspace else []}
    runtime = {}
    for path, timer, items in (('n_panel', '_tick', None),
                               ('modifier_list', '_init_keymap', '_keymap_items'),
                               ('pie_menus.keymap', '_delayed_init', '_items')):
        module = sys.modules.get(f'{ADDON_ID}.features.{path}')
        if module is not None:
            runtime[path] = {'timer': bpy.app.timers.is_registered(getattr(module, timer))}
            if items:
                runtime[path]['shortcut_count'] = len(getattr(module, items))
    result['runtime'] = runtime
    callbacks = {}
    for name in ('load_pre', 'load_post', 'depsgraph_update_post', 'undo_post', 'redo_post'):
        callbacks[name] = [f'{callback.__module__}.{callback.__name__}'
                           for callback in getattr(bpy.app.handlers, name)
                           if getattr(callback, '__module__', '').startswith(ADDON_ID + '.')]
    result['callbacks'] = callbacks
    external_hiding = sys.modules.get('pie_menu_editor.panel_utils')
    result['external_hidden_panels'] = (
        sorted(name for name in external_hiding.__dict__.get('_hidden_panels', {})
               if name in result['panels']) if external_hiding else [])
    for path, functions in (('substance_painter.runtime', ('_load_pre',)),
                             ('scene_performance.runtime', ('restore', 'invalidate'))):
        module = sys.modules.get(f'{ADDON_ID}.features.{path}')
        if module is not None:
            runtime[path] = {'callbacks_present': {
                name: any(getattr(module, name) in getattr(bpy.app.handlers, collection)
                          for collection in ('load_pre', 'load_post', 'depsgraph_update_post'))
                for name in functions}}
    return result


def reconcile():
    """Repair only owned non-destructive runtime infrastructure, not user visibility.

    Missing panels/classes are reported, not resurrected: another panel manager
    may intentionally have unregistered them. No scene property is re-created.
    """
    if feature_manager._load_post not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(feature_manager._load_post)
    if feature_manager.is_enabled('n_panel'):
        module = sys.modules[f'{ADDON_ID}.features.n_panel']
        if not bpy.app.timers.is_registered(module._tick):
            bpy.app.timers.register(module._tick, first_interval=0.5, persistent=True)
    if feature_manager.is_enabled('pie_menus'):
        module = sys.modules[f'{ADDON_ID}.features.pie_menus.keymap']
        module.register()
    if feature_manager.is_enabled('modifier_list'):
        module = sys.modules[f'{ADDON_ID}.features.modifier_list']
        if not bpy.app.timers.is_registered(module._init_keymap):
            bpy.app.timers.register(module._init_keymap, first_interval=0.2, persistent=True)