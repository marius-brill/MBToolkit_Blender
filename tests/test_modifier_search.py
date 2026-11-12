"""Disposable Blender test: --background --factory-startup --python this_file."""

import importlib
from pathlib import Path
import sys
from types import SimpleNamespace

import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon = importlib.import_module(ROOT.name)
feature = importlib.import_module(f'{ROOT.name}.features.modifier_list')


class Layout:
    def __init__(self):
        self.calls = []
        self.enabled = True

    def row(self, **kwargs):
        return self

    column = row
    box = row

    def prop(self, data, name, **kwargs):
        assert name in data.bl_rna.properties or name.startswith('["')
        self.calls.append(('prop', data, name, kwargs))

    def split(self, **kwargs):
        self.calls.append(('split', kwargs))
        return self

    def label(self, **kwargs):
        self.calls.append(('label', kwargs))

    def operator(self, idname, **kwargs):
        op = SimpleNamespace()
        self.calls.append(('operator', idname, kwargs, op))
        return op

    def template_list(self, *args, **kwargs):
        self.calls.append(('list',))

    def template_modifiers(self):
        self.calls.append(('native',))

    def context_pointer_set(self, *args):
        pass


def run():
    assert bpy.app.background
    addon.register()
    try:
        obj = bpy.context.object
        obj.modifiers.clear()
        first = obj.modifiers.new('First', 'BEVEL')
        tail = obj.modifiers.new('Pinned Tail', 'SUBSURF')
        assert not hasattr(bpy.types.WindowManager, 'mbt_modifier_settings_mode')
        assert not hasattr(bpy.types.WindowManager, 'mbt_modifier_search')
        choices = feature._modifier_search_items('MESH')
        assert choices is feature._modifier_search_items('MESH')
        assert {e[0] for e in choices} == {feature.entry_key(e) for e in feature.catalog('MESH')}
        assert any(e[0] == 'object.modifier_add:BEVEL' for e in choices)
        assert any(e[0].startswith('object.modifier_add_node_group:') for e in choices)
        assert not feature._modifier_search_items('CAMERA')
        layout = Layout()
        feature.draw_add_search(layout, bpy.context, obj)
        assert ('split', {'factor': 2 / 3, 'align': True}) in layout.calls
        buttons = [c for c in layout.calls if c[0] == 'operator']
        assert [c[1] for c in buttons] == ['mbt.modifier_search', 'mbt.modifier_add_menu']
        assert buttons[0][2]['depress'] is False
        assert buttons[0][3].object_name == obj.name
        assert not any(c[0] == 'label' for c in layout.calls)
        assert feature.MBT_OT_modifier_search.poll(bpy.context)
        bpy.ops.object.mode_set(mode='EDIT')
        assert not feature.MBT_OT_modifier_search.poll(bpy.context)
        bpy.ops.object.mode_set(mode='OBJECT')

        assert bpy.ops.mbt.modifier_lock(uid=tail.persistent_uid) == {'FINISHED'}
        assert bpy.ops.mbt.modifier_search('EXEC_DEFAULT', choice='object.modifier_add:BEVEL',
                                         object_name=obj.name, object_uid=str(obj.session_uid)) == {'FINISHED'}
        added = obj.modifiers.active
        assert added != first and added.type == 'BEVEL'
        assert obj.modifiers[-1] == tail
        assert added.show_expanded and not first.show_expanded and not tail.show_expanded
        count = len(obj.modifiers)
        assert bpy.ops.mbt.modifier_search('EXEC_DEFAULT', choice='object.modifier_add:BEVEL',
                                         object_name=obj.name, object_uid='-1') == {'CANCELLED'}
        assert len(obj.modifiers) == count
        pinned = bpy.data.objects.new('SearchPinned', bpy.data.meshes.new('SearchPinned'))
        bpy.context.collection.objects.link(pinned)
        assert bpy.ops.mbt.modifier_search('EXEC_DEFAULT', choice='object.modifier_add:BEVEL',
                                         object_name=pinned.name) == {'FINISHED'}
        assert len(pinned.modifiers) == 1 and len(obj.modifiers) == count

        layout = Layout()
        feature._draw_native(SimpleNamespace(layout=layout), bpy.context)
        assert layout.calls[-1] == ('native',)
        first.show_expanded = True
        feature._enforce_pending()
        assert first.show_expanded, 'Manual expansion survives unchanged selection'
        obj.mbt_modifier_index = 0
        assert first.show_expanded and not added.show_expanded and not tail.show_expanded
        obj.modifiers.clear()
        feature._draw_native(SimpleNamespace(layout=Layout()), bpy.context)
        # Real preferences select the shared RNA editor by default; absent
        # preferences above must continue to use Blender's native stack.
        entry = bpy.context.preferences.addons.new()
        entry.module = ROOT.name
        try:
            prefs = entry.preferences
            assert prefs.modifier_settings_mode == 'SELECTED'
            first = obj.modifiers.new('Selected Bevel', 'BEVEL')
            second = obj.modifiers.new('Other Subdivision', 'SUBSURF')
            for index, modifier, expected in ((0, first, 'width'), (1, second, 'levels')):
                obj.mbt_modifier_index = index
                layout = Layout()
                feature._draw_native(SimpleNamespace(layout=layout), bpy.context)
                assert ('native',) not in layout.calls
                props = [c for c in layout.calls if c[0] == 'prop']
                assert not any(c[1] == prefs and c[2] == 'modifier_settings_mode' for c in props)
                assert any(c[1] == modifier and c[2] == expected for c in props)
                assert not any(isinstance(c[1], bpy.types.Modifier) and c[1] != modifier for c in props)
            # Reordering and deletion keep the editor bound to the real active modifier.
            obj.modifiers.move(1, 0)
            assert obj.modifiers.active == second
            layout = Layout()
            feature._draw_native(SimpleNamespace(layout=layout), bpy.context)
            assert any(c[:3] == ('prop', second, 'levels') for c in layout.calls)
            obj.modifiers.remove(second)
            feature._enforce_pending()
            feature._draw_native(SimpleNamespace(layout=Layout()), bpy.context)
            prefs.modifier_settings_mode = 'NATIVE'
            layout = Layout()
            feature._draw_native(SimpleNamespace(layout=layout), bpy.context)
            assert layout.calls[-1] == ('native',)
            assert not any(c[0] == 'prop' and isinstance(c[1], bpy.types.Modifier) for c in layout.calls)
            # The popup stays selected-only even when Properties uses native UI.
            layout = Layout()
            feature.MBT_OT_modifier_popup.draw(SimpleNamespace(layout=layout), bpy.context)
            assert ('native',) not in layout.calls
            assert any(c[:3] == ('prop', first, 'width') for c in layout.calls)
            prefs.modifier_settings_mode = 'SELECTED'
            obj.modifiers.clear()
            layout = Layout()
            feature._draw_native(SimpleNamespace(layout=layout), bpy.context)
            assert ('native',) not in layout.calls
            assert not any(c[0] == 'prop' and isinstance(c[1], bpy.types.Modifier) for c in layout.calls)
        finally:
            bpy.context.preferences.addons.remove(entry)
        print('PASS floating search / selection / pinned target / locks / selected settings / native fallback / popup isolation / empty stack')
    finally:
        addon.unregister()
    assert not hasattr(bpy.types.WindowManager, 'mbt_modifier_search')
    assert not hasattr(bpy.types.WindowManager, 'mbt_modifier_settings_mode')
    assert not feature._modifier_search_items.cache_info().currsize
    assert not hasattr(bpy.types, 'MBT_OT_modifier_search')
    print('ALL MODIFIER SEARCH CHECKS PASSED')


if __name__ == '__main__':
    run()