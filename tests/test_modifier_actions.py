"""Modifier header actions; disposable --background --factory-startup Blender."""

import importlib
from pathlib import Path
import sys
from types import SimpleNamespace

import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon = importlib.import_module(ROOT.name)
feature = importlib.import_module(ROOT.name + '.features.modifier_list')


def run():
    assert bpy.app.background
    addon.register()
    entry = bpy.context.preferences.addons.new()
    entry.module = ROOT.name
    try:
        assert entry.preferences.bl_rna.properties['modifier_settings_mode'].default == 'SELECTED'
        assert entry.preferences.modifier_settings_mode == 'SELECTED'
        source = bpy.context.object
        md = source.modifiers.new('Action Bevel', 'BEVEL')
        md.width = 0.123
        target = bpy.data.objects.new('Action Target', source.data.copy())
        bpy.context.collection.objects.link(target)
        target.select_set(True)
        args = dict(object_name=source.name, object_uid=str(source.session_uid), uid=md.persistent_uid)
        # UI pointers can belong to a pinned source other than the active object.
        bpy.context.view_layer.objects.active = target
        assert bpy.ops.mbt.modifier_action(action='COPY', **args) == {'FINISHED'}
        assert len(target.modifiers) == 1 and abs(target.modifiers[0].width - md.width) < 1e-6
        assert bpy.context.object == target and len(source.modifiers) == 1
        assert bpy.ops.mbt.modifier_action(action='DUPLICATE', **args) == {'FINISHED'}
        duplicate = source.modifiers.active
        assert duplicate != md and len(source.modifiers) == 2
        assert abs(duplicate.width - md.width) < 1e-6
        assert bpy.ops.mbt.modifier_action(action='APPLY', **args) == {'FINISHED'}
        assert len(source.modifiers) == 1 and source.modifiers[0] == duplicate
        assert bpy.context.object == target
        assert bpy.ops.mbt.modifier_action(action='APPLY', **args) == {'CANCELLED'}
        args['uid'] = duplicate.persistent_uid
        args['object_uid'] = '-1'
        assert bpy.ops.mbt.modifier_action(action='APPLY', **args) == {'CANCELLED'}
        context = SimpleNamespace(area=SimpleNamespace(type='PROPERTIES'),
            region=SimpleNamespace(type='WINDOW'), space_data=SimpleNamespace(context='MODIFIER'),
            preferences=bpy.context.preferences, mbt_modifier_settings=duplicate)
        assert feature.MBT_OT_modifier_apply_hovered.poll(context)
        context.mbt_modifier_settings = None
        assert not feature.MBT_OT_modifier_apply_hovered.poll(context)
        context.property = (source, duplicate.path_from_id() + '.width', -1)
        assert feature.MBT_OT_modifier_apply_hovered.poll(context)
        context.property = (source, duplicate.path_from_id() + '.name', -1)
        assert not feature.MBT_OT_modifier_apply_hovered.poll(context)
        context.property = None
        context.mbt_modifier_settings = duplicate
        context.area.type = 'VIEW_3D'
        assert not feature.MBT_OT_modifier_apply_hovered.poll(context)
        context.area.type = 'PROPERTIES'
        entry.preferences.modifier_settings_mode = 'NATIVE'
        assert not feature.MBT_OT_modifier_apply_hovered.poll(context)
        print('PASS Apply / Duplicate / Copy to Selected / pinned source / stale targets / settings-only shortcut poll')
    finally:
        bpy.context.preferences.addons.remove(entry)
        addon.unregister()
    assert not feature._settings_keymap_items


if __name__ == '__main__':
    run()