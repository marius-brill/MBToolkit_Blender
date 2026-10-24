"""Run in disposable --background --factory-startup Blender only."""

import importlib
from pathlib import Path
import sys

import bpy
from bl_ui import properties_data_modifier as native

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
MODULE = sys.argv[sys.argv.index('--') + 1] if '--' in sys.argv else ROOT.name
modifiers = importlib.import_module(f'{MODULE}.features.modifier_list')


def run():
    assert bpy.app.background
    menus = [getattr(native, 'OBJECT_MT_modifier_add_' + category.lower())
             for category in modifiers.CATEGORIES]
    originals = [menu.draw for menu in menus]
    modifiers.catalog.cache_clear()
    baseline = {kind: modifiers.catalog(kind) for kind in sorted(modifiers.SUPPORTED_TYPES)}
    assert any(entry['args'].get('type') == 'BEVEL' for entry in baseline['MESH'])
    assert any(entry['args'].get('type') == 'NODES' for entry in baseline['MESH'])
    calls = []

    def appended(self, context):
        calls.append('append')
        raise AssertionError('Third-party draw callback must not run during catalog extraction')

    def prepended(self, context):
        calls.append('prepend')
        raise AssertionError('Third-party draw callback must not run during catalog extraction')

    try:
        for menu in menus:
            menu.append(appended)
            menu.prepend(prepended)
        wrappers = [menu.draw for menu in menus]
        callbacks = [tuple(menu.draw._draw_funcs) for menu in menus]
        modifiers.catalog.cache_clear()
        for kind, expected in baseline.items():
            assert modifiers.catalog(kind) == expected, kind
        assert not calls, calls
        for menu, wrapper, functions in zip(menus, wrappers, callbacks):
            assert menu.draw is wrapper
            assert tuple(menu.draw._draw_funcs) == functions
        print('PASS wrapped menus: all object types, prepend/append isolation, unchanged callbacks')

        for menu in menus:
            menu.remove(appended)
            menu.remove(prepended)
        modifiers.catalog.cache_clear()
        for kind, expected in baseline.items():
            assert modifiers.catalog(kind) == expected, kind
        print('PASS menus remain wrapped after third-party callbacks are removed')
    finally:
        for menu, original in zip(menus, originals):
            menu.draw = original
        modifiers.catalog.cache_clear()
    print(f'ALL MODIFIER CATALOG CHECKS PASSED ({MODULE})')


if __name__ == '__main__':
    run()