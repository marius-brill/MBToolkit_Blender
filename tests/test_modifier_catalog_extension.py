"""Disposable GUI check; requires isolated BLENDER_USER_CONFIG/EXTENSIONS paths.

Run with --factory-startup --python-exit-code 1 --python this_file.
Installs a manifest ZIP through Blender's standard extension installer, draws
the modifier-preferences builder in a real test panel with extended native menus,
then quits its own process. Does not simulate the OS drag-and-drop gesture.
"""

import importlib
import os
from pathlib import Path
import tempfile
import traceback
import zipfile

import bpy
from bl_ui import properties_data_modifier as native

ROOT = Path(__file__).resolve().parents[1]
MODULE = 'bl_ext.user_default.mbtoolkit'
OUTPUT = Path(tempfile.gettempdir()) / 'mbt_modifier_extension_result.txt'
draws = []
draw_errors = []
callbacks = []
stage = 0
OUTPUT.write_text('RUNNING', encoding='utf-8')


def foreign_draw(self, context):
    raise AssertionError('Foreign menu callback reached catalog extraction')


def check():
    global stage
    try:
        if stage == 0:
            assert not bpy.app.background
            for variable in ('BLENDER_USER_CONFIG', 'BLENDER_USER_EXTENSIONS'):
                assert 'mbt_extension_test_' in os.environ.get(variable, ''), variable
            with tempfile.TemporaryDirectory(prefix='mbt_extension_zip_') as directory:
                archive = Path(directory) / 'mbtoolkit.zip'
                with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as package:
                    for path in ROOT.rglob('*'):
                        relative = path.relative_to(ROOT)
                        if (path.is_file() and not any(part in {
                                '.git', '.vscode', '__pycache__', 'tests'
                        } for part in relative.parts) and path.suffix != '.zip'):
                            package.write(path, relative.as_posix())
                assert bpy.ops.extensions.package_install_files(
                    'EXEC_DEFAULT', filepath=str(archive), repo='user_default',
                    enable_on_install=True) == {'FINISHED'}
            addon = importlib.import_module(MODULE)
            assert str(Path(addon.__file__).resolve()).startswith(
                str(Path(os.environ['BLENDER_USER_EXTENSIONS']).resolve()))
            prefs = bpy.context.preferences.addons[MODULE].preferences
            prefs.tab = 'MODIFIERS'
            modifiers = importlib.import_module(f'{MODULE}.features.modifier_list')
            for category in modifiers.CATEGORIES:
                menu = getattr(native, 'OBJECT_MT_modifier_add_' + category.lower())
                menu.append(foreign_draw)
                menu.prepend(foreign_draw)
                callbacks.append(menu)
            modifiers.catalog.cache_clear()
            for kind in modifiers.SUPPORTED_TYPES:
                assert isinstance(modifiers.catalog(kind), list)
            def observe_draw(self, context):
                try:
                    addon.preferences.draw_modifier_preferences(self.layout, prefs)
                    draws.append(True)
                except Exception:
                    draw_errors.append(traceback.format_exc())
                    raise

            class MBT_PT_catalog_test(bpy.types.Panel):
                bl_label = 'Installed MBToolkit modifier preferences'
                bl_space_type = 'VIEW_3D'
                bl_region_type = 'UI'
                bl_category = 'Item'
                draw = observe_draw

            bpy.utils.register_class(MBT_PT_catalog_test)
            area = next(area for area in bpy.context.window.screen.areas
                        if area.type == 'VIEW_3D')
            area.spaces.active.show_region_ui = True
            area.tag_redraw()
            stage = 1
            return 2.0
        assert draws, 'The installed extension preferences were not drawn'
        assert not draw_errors, '\n'.join(draw_errors)
        OUTPUT.write_text('PASS standard extension ZIP install / extension namespace / '
                          'wrapped catalogs / Modifiers preferences redraw', encoding='utf-8')
        print(OUTPUT.read_text(encoding='utf-8'))
    except Exception:
        OUTPUT.write_text(traceback.format_exc(), encoding='utf-8')
        traceback.print_exc()
    bpy.ops.wm.quit_blender()
    return None


bpy.app.timers.register(check, first_interval=1.0)