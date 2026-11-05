"""Disposable Blender checks: default integration, or -- write / read / gui.

Persistence modes require BLENDER_USER_CONFIG containing mbt_script_test_config.
GUI mode runs without --background and writes a result to the system temp folder.
"""

import importlib
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace

import addon_utils
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
MODE = sys.argv[sys.argv.index('--') + 1] if '--' in sys.argv else 'integration'
if MODE in {'write', 'read'}:
    assert 'mbt_script_test_config' in os.environ.get('BLENDER_USER_CONFIG', ''), 'Use disposable config only'
    assert 'mbt_script_test_config' in bpy.utils.user_resource('CONFIG'), 'Blender fell back to the real config; aborting'
addon_utils.enable(ROOT.name, default_set=MODE != 'read')
addon = importlib.import_module(ROOT.name)
runner = importlib.import_module(f'{ROOT.name}.features.script_runner')
prefs = runner.get_prefs()
addon.feature_manager.sync(prefs)


def action(kind, uid=''):
    return bpy.ops.mbt.script_favorite(action=kind, uid=uid)


def execute(cls, **kwargs):
    reports = []
    operator = SimpleNamespace(report=lambda level, message: reports.append((level, message)), **kwargs)
    result = cls.execute(operator, bpy.context)
    return result, reports


def integration():
    assert bpy.app.background
    with tempfile.TemporaryDirectory(prefix='mbt_script_runner_') as directory:
        folder = Path(directory)
        first, second = folder / 'first.py', folder / 'second.py'
        first.write_text("import bpy\nbpy.context.scene['mbt_script_result'] = 1\n", encoding='utf-8')
        second.write_text("import bpy\nbpy.context.scene['mbt_script_result'] = 2\n", encoding='utf-8')
        scene = bpy.context.scene
        scene.mbt.script_path = str(first)
        assert action('TOGGLE') == {'FINISHED'}
        first_uid = prefs.script_favorites[0].uid
        assert prefs.script_favorites[0].path == str(first)
        assert bpy.context.preferences.is_dirty
        assert runner.current_favorite(prefs, str(folder / '.' / 'first.py')).uid == first_uid
        if os.name == 'nt':
            assert runner.current_favorite(prefs, str(first).upper()).uid == first_uid
        scene.mbt.script_path = str(second)
        action('TOGGLE')
        second_uid = prefs.script_favorites[1].uid
        assert first_uid != second_uid
        assert action('SELECT', first_uid) == {'FINISHED'}
        assert scene.mbt.script_path == str(first)
        assert 'mbt_script_result' not in scene  # Selecting must never execute code.
        assert bpy.ops.mbt.script_run() == {'FINISHED'}
        assert scene['mbt_script_result'] == 1
        first.write_text("import bpy\nbpy.context.scene['mbt_script_result'] = 3\n", encoding='utf-8-sig')
        bpy.ops.mbt.script_run()
        assert scene['mbt_script_result'] == 3  # Fresh source, including UTF-8 BOM.
        assert action('UP', second_uid) == {'FINISHED'}
        assert prefs.script_favorites[0].uid == second_uid
        assert action('DOWN', second_uid) == {'FINISHED'}
        assert prefs.script_favorites[1].uid == second_uid
        assert bpy.ops.mbt.script_favorite_edit(uid=first_uid, label='My favorite', path=str(first)) == {'FINISHED'}
        assert prefs.script_favorites[0].label == 'My favorite'
        result, reports = execute(runner.MBT_OT_script_favorite_edit, uid=first_uid, label='Duplicate', path=str(second))
        assert result == {'CANCELLED'} and 'already' in reports[0][1]
        first.unlink()
        assert action('SELECT', first_uid) == {'FINISHED'}
        assert len(prefs.script_favorites) == 2  # Missing bookmarks are preserved.
        result, reports = execute(runner.MBT_OT_script_run)
        assert result == {'CANCELLED'} and 'not found' in reports[0][1]
        replacement = folder / 'replacement.py'
        replacement.write_text('pass\n', encoding='utf-8')
        assert bpy.ops.mbt.script_favorite_edit(uid=first_uid, label='Relinked', path=str(replacement)) == {'FINISHED'}
        assert scene.mbt.script_path == str(replacement)
        replacement.write_bytes(b'\xff\xfe')
        result, reports = execute(runner.MBT_OT_script_run)
        assert result == {'CANCELLED'} and 'Cannot read' in reports[0][1]
        scene.mbt.script_path = str(folder / 'bad.txt')
        result, reports = execute(runner.MBT_OT_script_favorite, action='TOGGLE', uid='')
        assert result == {'CANCELLED'} and '.py' in reports[0][1]
        assert len(prefs.script_favorites) == 2
        scene.mbt.script_path = str(second)
        action('TOGGLE')  # Remove via star, without touching the source file.
        assert len(prefs.script_favorites) == 1 and second.exists()
        prefs.enable_script_runner = False
        addon.feature_manager.sync(prefs)
        assert prefs.script_favorites[0].uid == first_uid
        prefs.enable_script_runner = True
        addon.feature_manager.sync(prefs)
        assert action('REMOVE', first_uid) == {'FINISHED'}
        assert not prefs.script_favorites and replacement.exists()
        result, reports = execute(runner.MBT_OT_script_favorite, action='REMOVE', uid=first_uid)
        assert result == {'CANCELLED'} and reports
    print('PASS favorites CRUD / duplicate validation / selection safety / fresh execution / errors / feature lifecycle')


def persistence():
    if MODE == 'write':
        item = prefs.script_favorites.add()
        item.uid, item.label, item.path = 'persistent-id', 'Saved favorite', str(ROOT / 'tests' / 'test_script_runner.py')
        prefs.enable_script_runner = False
        addon.feature_manager.sync(prefs)
        bpy.ops.wm.save_userpref()
        print('PASS saved script favorite while runner disabled')
    else:
        assert not prefs.enable_script_runner
        assert len(prefs.script_favorites) == 1
        item = prefs.script_favorites[0]
        assert (item.uid, item.label) == ('persistent-id', 'Saved favorite')
        assert item.path == str(ROOT / 'tests' / 'test_script_runner.py')
        prefs.enable_script_runner = True
        addon.feature_manager.sync(prefs)
        assert action('SELECT', item.uid) == {'FINISHED'}
        print('PASS favorite restored in new process and available after feature enable')


def gui():
    assert not bpy.app.background
    result_file = Path(tempfile.gettempdir()) / 'mbt_script_runner_ui_result.txt'
    result_file.write_text('RUNNING', encoding='utf-8')
    drawn, errors = set(), []
    for label, path in (('Same name', str(ROOT / 'tests' / 'test_script_runner.py')),
                        ('Same name', str(ROOT / 'missing_favorite.py'))):
        item = prefs.script_favorites.add()
        item.uid, item.label, item.path = label + path, label, path
    bpy.context.scene.mbt.script_path = prefs.script_favorites[0].path
    bpy.context.preferences.use_preferences_save = False

    class MBT_PT_script_test(bpy.types.Panel):
        bl_label = 'Script Runner Test'
        bl_space_type = 'VIEW_3D'
        bl_region_type = 'UI'
        bl_category = 'Script Test'

        def draw(self, context):
            try:
                runner.draw(self.layout, context)
                runner.MBT_MT_script_favorites.draw(self, context)
                runner.MBT_OT_script_favorites_manage.draw(self, context)
                drawn.add('populated')
            except Exception as exc:
                errors.append(repr(exc))

    bpy.types.VIEW3D_HT_header.append(MBT_PT_script_test.draw)
    area = next(a for a in bpy.context.screen.areas if a.type == 'VIEW_3D')
    area.spaces.active.show_region_ui = True
    area.tag_redraw()

    def finish():
        bpy.types.VIEW3D_HT_header.remove(MBT_PT_script_test.draw)
        result_file.write_text('PASS native favorites menu / list / management / sidebar drawing' if drawn and not errors else f'FAIL drawn={drawn} errors={errors}', encoding='utf-8')
        bpy.ops.wm.quit_blender()
    bpy.app.timers.register(finish, first_interval=3.0)


if MODE == 'gui':
    gui()
else:
    try:
        persistence() if MODE in {'write', 'read'} else integration()
    finally:
        addon_utils.disable(ROOT.name, default_set=False)