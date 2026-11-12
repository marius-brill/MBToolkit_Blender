"""Metadata preservation, persistence and Model drawing; disposable Blender only."""
import importlib
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
sys.path.insert(0, str(ROOT / 'tests'))
from test_painter_ui_parity import Layout


def snapshot():
    return [(obj.as_pointer(), obj.name, obj.data.as_pointer(),
             tuple(tuple(v.co) for v in obj.data.vertices),
             tuple(tuple(loop.uv) for layer in obj.data.uv_layers for loop in layer.data),
             tuple(slot.material for slot in obj.material_slots), tuple(obj.users_collection),
             obj.mbt_bake_group, obj.mbt_bake_target,
             tuple(obj.matrix_world[:])) for obj in bpy.context.scene.objects if obj.type == 'MESH']


def main():
    assert bpy.app.background, 'Use a disposable background Blender process'
    addon = importlib.import_module(ROOT.name)
    addon.register()
    addon.feature_manager.sync(SimpleNamespace(enable_substance_painter=True))
    painter = importlib.import_module(ROOT.name + '.features.substance_painter')
    preparation = importlib.import_module(ROOT.name + '.features.substance_painter.preparation')
    model = importlib.import_module(ROOT.name + '.features.asset_processing.ui')
    try:
        bpy.ops.mbt.painter_texture_set(action='ADD')
        bake = bpy.context.scene.mbt_painter
        bpy.ops.mesh.primitive_cube_add()
        low = bpy.context.object
        low.name = 'Artist Source'
        bake.low_collection.objects.link(low)
        material = bpy.data.materials.new('Artist Material')
        low.data.materials.append(material)
        high = low.copy()
        high.data = low.data.copy()
        high.name = 'Custom High'
        bake.high_collection.objects.link(high)
        high.mbt_bake_target = low
        before = snapshot()
        scene_objects = set(bpy.context.scene.objects)
        bpy.ops.object.select_all(action='DESELECT')
        low.select_set(True)
        bpy.context.view_layer.objects.active = low
        selection = tuple(bpy.context.selected_objects)
        settings = bpy.context.scene.mbt_assets
        assert not settings.assets
        assert bpy.ops.mbt.asset_edit(action='CREATE') == {'FINISHED'}
        asset = settings.assets[0]
        assert asset.components[0].source == low
        assert asset.components[0].uv_locked
        assert bpy.ops.mbt.asset_edit(action='ADD') == {'FINISHED'}
        assert len(asset.components) == 1
        assert bpy.ops.mbt.asset_edit(action='REMOVE_COMPONENT') == {'FINISHED'}
        assert bpy.ops.mbt.asset_edit(action='REMOVE_ASSET') == {'FINISHED'}
        assert not settings.assets
        # Collection traversal includes nested meshes; no collection changes.
        settings.source_collection = bake.texture_collection
        assert bpy.ops.mbt.asset_edit(action='COLLECTION') == {'FINISHED'}
        assert len(settings.assets[0].components) == 2
        assert bpy.ops.mbt.asset_edit(action='REMOVE_ASSET') == {'FINISHED'}
        assert bpy.ops.mbt.asset_edit(action='ADOPT') == {'FINISHED'}
        asset = settings.assets[0]
        component = asset.components[0]
        assert component.low == low and component.source == low
        assert component.texture_set_id == bake.texture_sets[0].set_id
        assert component.highs[0].mesh == high
        assert bpy.ops.mbt.asset_edit(action='ADOPT') == {'CANCELLED'}
        assert snapshot() == before
        assert set(bpy.context.scene.objects) == scene_objects
        assert tuple(bpy.context.selected_objects) == selection
        # Legacy setup stays legacy: adoption must not call ensure_default/migrate.
        assert bpy.ops.mbt.asset_edit(action='REMOVE_ASSET') == {'FINISHED'}
        bake.texture_sets.clear()
        high.mbt_bake_auto_target = low
        assert bpy.ops.mbt.asset_edit(action='ADOPT') == {'FINISHED'}
        assert not bake.texture_sets
        assert not settings.assets[0].components[0].highs
        assert bpy.ops.mbt.asset_edit(action='REMOVE_ASSET') == {'FINISHED'}
        low.mbt_bake_group = high.mbt_bake_group = 'Explicit Group'
        assert bpy.ops.mbt.asset_edit(action='ADOPT') == {'FINISHED'}
        asset = settings.assets[0]
        component = asset.components[0]
        assert component.highs[0].mesh == high
        low.mbt_bake_group = high.mbt_bake_group = ''
        high.mbt_bake_auto_target = None
        assert snapshot() == before
        # Merely changing tabs or metadata cannot cancel a prepared bake.
        signature = preparation.signature(bpy.context)
        bake.ui_tab = 'MODEL'
        settings.show_component = settings.show_collection = True
        asset.name = 'Housing'
        assert preparation.signature(bpy.context) == signature
        for width in (240, 720):
            context = SimpleNamespace(scene=bpy.context.scene, mode='OBJECT',
                preferences=bpy.context.preferences,
                region=SimpleNamespace(width=width, view2d=SimpleNamespace(region_to_view=lambda x, y: (x, y))))
            for busy in (False, True):
                records = []
                model.draw(Layout(records), context, busy)
                edits = [r for r in records if r[0] == 'operator' and r[1] == 'mbt.asset_edit']
                assert edits and all(r[3] == (not busy) for r in edits)
                assert any(r[0] == 'operator' and r[1] == 'mbt.painter_cancel' for r in records) == busy
        assert snapshot() == before
        with patch.object(painter.operators.runtime, 'busy', return_value=True):
            assert not bpy.ops.mbt.asset_edit.poll()
        ids = (asset.asset_id, component.component_id)
        assert ids[0] and ids[1] and ids[0] != ids[1]
        # Save/reload: UUIDs and pointers survive, no name-based reconstruction.
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / 'assets.blend')
            bpy.ops.wm.save_as_mainfile(filepath=path)
            bpy.ops.wm.open_mainfile(filepath=path)
            settings = bpy.context.scene.mbt_assets
            asset = settings.assets[0]
            component = asset.components[0]
            assert (asset.asset_id, component.component_id) == ids
            assert component.source.name == 'Artist Source'
            component.source.name = 'Renamed Source'
            assert component.low == component.source
            bpy.data.objects.remove(component.source, do_unlink=True)
            bpy.ops.mesh.primitive_cube_add()
            bpy.context.object.name = 'Renamed Source'
            assert component.source is None and component.low is None
            model.draw(Layout([]), bpy.context, False)
        # Feature disable/re-enable restores persisted records, no eager migration.
        addon.feature_manager.sync(SimpleNamespace(enable_substance_painter=False))
        assert not hasattr(bpy.types.Scene, 'mbt_assets')
        addon.feature_manager.sync(SimpleNamespace(enable_substance_painter=True))
        assert bpy.context.scene.mbt_assets.assets[0].asset_id == ids[0]
        assert not addon.feature_manager._errors
        print('PASS: asset CRUD, adoption, source preservation, UUID/pointer persistence, missing sources, UI, busy gating and lifecycle')
    finally:
        addon.unregister()
    assert not hasattr(bpy.types.Scene, 'mbt_assets')


if __name__ == '__main__':
    main()