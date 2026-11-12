"""Protected UV proposals and read-only diagnostics; disposable background Blender."""
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


def refuses(function, text):
    try:
        function()
        raise AssertionError('Expected refusal: ' + text)
    except (ValueError, RuntimeError) as error:
        assert text in str(error), str(error)


def main():
    assert bpy.app.background
    addon = importlib.import_module(ROOT.name)
    addon.register()
    addon.feature_manager.sync(SimpleNamespace(enable_substance_painter=True))
    generation = importlib.import_module(ROOT.name + '.features.asset_processing.generation')
    uv = importlib.import_module(ROOT.name + '.features.asset_processing.uv')
    validation = importlib.import_module(ROOT.name + '.features.asset_processing.validation')
    model = importlib.import_module(ROOT.name + '.features.asset_processing.ui')
    try:
        assert not hasattr(bpy.types.Scene, 'mbt_uv'), 'Processor must not register optional UV tools'
        bpy.ops.mesh.primitive_cube_add()
        source = bpy.context.object
        source.name = 'Housing Source'
        material = bpy.data.materials.new('Artist Textured Material')
        material.use_nodes = True
        image = bpy.data.images.new('Artist Texture', 16, 16)
        texture = material.node_tree.nodes.new('ShaderNodeTexImage')
        texture.image = image
        source.data.materials.append(material)
        source.data.uv_layers.new(name='Artist Secondary Layout')
        source.data.uv_layers.active_index = 0
        bpy.ops.mbt.asset_edit(action='CREATE')
        settings = bpy.context.scene.mbt_assets
        asset = settings.assets[0]
        component = asset.components[0]
        component.high_mode = 'DISABLED'
        source.data.edges[0].use_seam = True
        generation.generate(bpy.context, asset, component)
        low = component.low
        secondary = tuple(tuple(loop.uv) for loop in low.data.uv_layers[1].data)
        source_before = generation.fingerprint(source)
        low_before = generation.fingerprint(low)
        selection = tuple(bpy.context.selected_objects)
        active = bpy.context.active_object
        uv.build(bpy.context, asset, component)
        assert component.uv_preview and component.uv_preview.hide_get()
        assert generation.fingerprint(source) == source_before
        assert generation.fingerprint(low) == low_before
        assert tuple(bpy.context.selected_objects) == selection and bpy.context.active_object == active
        assert bpy.context.mode == 'OBJECT'
        assert component.uv_preview.data.edges[0].use_seam
        refuses(lambda: uv.apply(bpy.context, asset, component), 'protected')
        component.uv_locked = False
        low.data.vertices[0].co.x += 0.1
        refuses(lambda: uv.apply(bpy.context, asset, component), 'changed')
        low.data.vertices[0].co.x -= 0.1
        uv.build(bpy.context, asset, component)
        # A tampered proposal must not overwrite working geometry or layout.
        component.uv_preview.data.vertices[0].co.z += 0.2
        refuses(lambda: uv.apply(bpy.context, asset, component), 'geometry changed')
        uv.build(bpy.context, asset, component)
        uv.apply(bpy.context, asset, component)
        assert component.uv_preview is None
        assert component.uv_reference == uv.layout_signature(low.data)
        assert generation.fingerprint(source) == source_before
        assert low.data.edges[0].use_seam
        assert low.data.materials[0] == material and texture.image == image
        assert tuple(tuple(loop.uv) for loop in low.data.uv_layers[1].data) == secondary
        component.uv_locked = True
        reviewed = uv.layout_signature(low.data)
        validation.validate(bpy.context, asset)
        assert uv.layout_signature(low.data) == reviewed
        assert not any(row.stage == 'UV' and row.severity == 'ERROR' for row in asset.issues)
        low.data.uv_layers.active.data[0].uv.x += 0.05
        validation.validate(bpy.context, asset)
        assert any('Protected UV layout changed' in row.reason for row in asset.issues)
        # Preserve mode blocks processing without touching data.
        component.uv_mode = 'PRESERVE'
        stable = generation.fingerprint(low)
        assert bpy.ops.mbt.asset_process(action='UV_PREPARE') == {'FINISHED'}
        assert generation.fingerprint(low) == stable
        refuses(lambda: uv.build(bpy.context, asset, component), 'Preserve')
        # Failure during packing leaves originals and no stray proposal objects.
        component.uv_mode = 'ASSISTED'
        before = (len(bpy.data.objects), len(bpy.data.meshes))
        with patch.object(uv.operations, 'pack', side_effect=RuntimeError('injected packing failure')):
            refuses(lambda: uv.build(bpy.context, asset, component), 'injected')
        assert before == (len(bpy.data.objects), len(bpy.data.meshes))
        assert generation.fingerprint(low) == stable
        assert bpy.context.mode == 'OBJECT'
        # Protected edge refusal, even when seam generator wants it.
        attribute = low.data.attributes.new(uv.PROTECTED_ATTRIBUTE, 'BOOLEAN', 'EDGE')
        for edge, value in zip(low.data.edges, attribute.data):
            edge.use_seam = False
            value.value = True
        refuses(lambda: uv.build(bpy.context, asset, component), 'protected edge')
        low.data.attributes.remove(attribute)
        # Two components sharing a texture set pack jointly.
        bpy.ops.mesh.primitive_cube_add(location=(3, 0, 0))
        second_source = bpy.context.object
        bpy.ops.mbt.asset_edit(action='ADD')
        second = asset.components[1]
        second.high_mode = 'DISABLED'
        generation.generate(bpy.context, asset, second)
        component.uv_mode = second.uv_mode = 'AUTOMATIC'
        component.uv_locked = second.uv_locked = False
        uv.build(bpy.context, asset, component)
        assert second.uv_preview and second.uv_batch == component.uv_batch
        uv.apply(bpy.context, asset, component)
        validation.validate(bpy.context, asset)
        assert not any('overlapping triangle' in row.reason for row in asset.issues)
        assert not any(row.stage == 'UV' and row.severity == 'ERROR' for row in asset.issues)
        # Lock on any shared member blocks automatic processing.
        second.uv_locked = True
        assert bpy.ops.mbt.asset_process(action='UV_PREPARE') == {'CANCELLED'}
        second.uv_locked = False
        assert bpy.ops.mbt.asset_process(action='UV_PREPARE') == {'FINISHED'}
        # Read-only validation and expanded layout draw never change meshes.
        component.uv_mode = second.uv_mode = 'ASSISTED'
        settings.show_uv = settings.show_validation = settings.show_inspector = True
        validation.validate(bpy.context, asset)
        before = [generation.fingerprint(item.low) for item in asset.components]
        for busy in (False, True):
            model.draw(Layout([]), bpy.context, busy)
        assert before == [generation.fingerprint(item.low) for item in asset.components]
        # Preserve originals even when adopted/source and low refer to the same mesh.
        original_low = component.low
        component.low = component.source
        refuses(lambda: uv.build(bpy.context, asset, component), 'original/source')
        component.low = original_low
        uv.build(bpy.context, asset, component)
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / 'uv.blend')
            bpy.ops.wm.save_as_mainfile(filepath=path)
            assert component.uv_preview is None and second.uv_preview is None
            bpy.ops.wm.open_mainfile(filepath=path)
            settings = bpy.context.scene.mbt_assets
            asset = settings.assets[0]
            assert asset.components[0].uv_reference
            assert not any(obj.get('mbt_uv_proposal') for obj in bpy.data.objects)
        # Issue pointer survives rename; missing objects never reconnect by name.
        component = asset.components[0]
        for layer in list(component.low.data.uv_layers):
            component.low.data.uv_layers.remove(layer)
        validation.validate(bpy.context, asset)
        row = next(row for row in asset.issues if row.reason == 'Active UV map is missing.')
        affected = row.mesh
        affected.name = 'Renamed Working Low'
        assert row.mesh == affected
        bpy.data.objects.remove(affected, do_unlink=True)
        assert row.mesh is None
        # Removing records discards only disposable proposals, never the sources.
        asset.active_component = 1
        remaining = asset.components[1]
        remaining.texture_set_id = 'SeparateTestSet'
        uv.build(bpy.context, asset, remaining)
        assert remaining.uv_preview
        assert bpy.ops.mbt.asset_edit(action='REMOVE_COMPONENT') == {'FINISHED'}
        assert not any(obj.get('mbt_uv_proposal') for obj in bpy.data.objects)
        print('PASS: source/UV locks, proposals, stale/tamper guards, preserved seams/protected edges, joint packing, automatic/preserve modes, diagnostics, failure cleanup and lifecycle')
    finally:
        addon.unregister()


if __name__ == '__main__':
    main()