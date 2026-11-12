"""Disposable GUI layout check; omit --background. Does not simulate OS typing."""

import importlib
from pathlib import Path
import sys
import tempfile
import traceback

import bpy

ROOT = Path(__file__).resolve().parents[1]
RESULT = Path(tempfile.gettempdir()) / 'mbt_modifier_search_live_result.txt'
sys.path.insert(0, str(ROOT.parent))
addon = importlib.import_module(ROOT.name)
feature = importlib.import_module(f'{ROOT.name}.features.modifier_list')
observed = set()
errors = []
properties_state = []
round_trips = 0


def draw_properties(self, context):
    try:
        feature._draw_native(self, context)
        prefs = feature.get_prefs(context)
        observed.add(prefs.modifier_settings_mode)
    except Exception:
        errors.append(traceback.format_exc())


def draw_popup(self, context):
    try:
        feature.draw(self.layout, context)
        feature.draw_active_settings(self.layout, context)
        observed.add('popup')
    except Exception:
        errors.append(traceback.format_exc())


def finish_error():
    RESULT.write_text(traceback.format_exc() + '\n' + '\n'.join(errors), encoding='utf-8')
    bpy.ops.wm.quit_blender()


def start():
    try:
        assert not bpy.app.background
        addon.register()
        entry = bpy.context.preferences.addons.new()
        entry.module = ROOT.name
        assert entry.preferences.modifier_settings_mode == 'SELECTED'
        from bl_ui.properties_data_modifier import DATA_PT_modifiers
        DATA_PT_modifiers.draw = draw_properties
        feature.MBT_OT_modifier_popup.draw = draw_popup
        obj = bpy.context.object
        obj.modifiers.new('First', 'BEVEL')
        obj.modifiers.new('Second', 'SUBSURF')
        area = next(a for a in bpy.context.screen.areas if a.type == 'PROPERTIES')
        area.spaces.active.context = 'MODIFIER'
        area.spaces.active.pin_id = obj
        area.spaces.active.use_pin_id = True
        # A second Properties editor checks that both region-local panel lists
        # are reconciled, without sacrificing the viewport used by popup tests.
        second = next(a for a in bpy.context.screen.areas if a.type == 'DOPESHEET_EDITOR')
        second.type = 'PROPERTIES'
        second.spaces.active.context = 'MODIFIER'
        area.tag_redraw()
        bpy.app.timers.register(native, first_interval=1.5)
    except Exception:
        finish_error()
    return None


def native():
    try:
        assert 'SELECTED' in observed, observed
        assert not errors, errors
        properties_state.clear()
        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == 'PROPERTIES':
                    space = area.spaces.active
                    properties_state.append((area, space.as_pointer(), space.pin_id,
                                             space.use_pin_id, space.context,
                                             {r.as_pointer() for r in area.regions}))
        feature.get_prefs().modifier_settings_mode = 'NATIVE'
        bpy.app.timers.register(selected, first_interval=1.0)
    except Exception:
        finish_error()
    return None


def selected():
    try:
        assert 'NATIVE' in observed, observed
        assert not errors, errors
        observed.discard('SELECTED')
        feature.get_prefs().modifier_settings_mode = 'SELECTED'
        bpy.app.timers.register(check_selected, first_interval=1.0)
    except Exception:
        finish_error()
    return None


def check_selected():
    global round_trips
    try:
        assert 'SELECTED' in observed, observed
        assert not errors, errors
        for area, pointer, pin, use_pin, tab, old_regions in properties_state:
            assert area.type == 'PROPERTIES'
            space = area.spaces.active
            assert space.as_pointer() == pointer, 'Properties space was replaced'
            assert (space.pin_id, space.use_pin_id, space.context) == (pin, use_pin, tab)
        owner = feature._empty_panel_owner
        assert owner is not None and not owner.modifiers and not owner.users_collection
        assert bpy.context.object.name == 'Cube'
        round_trips += 1
        bpy.app.timers.register(native if round_trips < 3 else search, first_interval=0.2)
    except Exception:
        finish_error()
    return None


def search():
    try:
        assert {'SELECTED', 'NATIVE'} <= observed, observed
        assert not errors, errors
        assert not hasattr(bpy.types.WindowManager, 'mbt_modifier_settings_mode')
        area = next(a for a in bpy.context.screen.areas if a.type == 'PROPERTIES')
        with bpy.context.temp_override(area=area):
            assert bpy.ops.mbt.modifier_search('INVOKE_DEFAULT',
                                             object_name=bpy.context.object.name) == {'RUNNING_MODAL'}
        observed.add('floating_search')
        bpy.app.timers.register(popup, first_interval=1.5)
    except Exception:
        finish_error()
    return None


def popup():
    try:
        assert 'floating_search' in observed, observed
        assert not errors, errors
        area = next(a for a in bpy.context.screen.areas if a.type == 'VIEW_3D')
        with bpy.context.temp_override(area=area):
            assert bpy.ops.mbt.modifier_popup('INVOKE_DEFAULT') == {'RUNNING_MODAL'}
        bpy.app.timers.register(finish, first_interval=1.5)
    except Exception:
        finish_error()
    return None


def finish():
    try:
        assert 'popup' in observed, observed
        assert not errors, errors
        owner = feature._empty_panel_owner
        assert owner is not None
        owner_name = owner.name
        from bl_ui.properties_data_modifier import DATA_PT_modifiers
        # Restore the wrapper's replaced callback before teardown, allowing the
        # feature to restore Blender's original panel instead of retaining ours.
        DATA_PT_modifiers.draw = feature._draw_native
        feature.MBT_OT_modifier_popup.draw = lambda self, context: None
        addon.unregister()
        assert feature._empty_panel_owner is None
        assert owner_name not in bpy.data.objects
        RESULT.write_text('PASS three native-to-selected round trips / empty template reconciliation / preserved Properties space, pinned object and tab / floating search / popup',
                          encoding='utf-8')
        bpy.ops.wm.quit_blender()
    except Exception:
        finish_error()
    return None


bpy.app.timers.register(start, first_interval=1.0)
print(f'Modifier search GUI result: {RESULT}', flush=True)