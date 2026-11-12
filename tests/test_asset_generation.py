"""Real DynaBool, preservation, bounded generation and FBX export in disposable Blender."""
import importlib
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))


def main():
    assert bpy.app.background
    addon = importlib.import_module(ROOT.name)
    addon.register()
    addon.feature_manager.sync(SimpleNamespace(enable_substance_painter=True))
    generation = importlib.import_module(ROOT.name + '.features.asset_processing.generation')
    exporter = importlib.import_module(ROOT.name + '.features.asset_processing.export')
    preview = importlib.import_module(ROOT.name + '.features.asset_processing.preview')
    try:
        bpy.ops.mesh.primitive_cube_add()
        source = bpy.context.object
        source.name = 'Original Housing'
        assert bpy.ops.mbt.asset_edit(action='CREATE') == {'FINISHED'}
        settings = bpy.context.scene.mbt_assets
        asset = settings.assets[0]
        component = asset.components[0]
        original = generation.fingerprint(source)
        assert component.remesh
        generation.generate(bpy.context, asset, component)
        low, high = component.low, component.generated_high
        assert low != source and high != source and low.data != source.data
        assert high.modifiers[0].node_group.name == 'DynaBool'
        assert high.mbt_bake_target == low
        assert generation.fingerprint(source) == original
        low.data.uv_layers.active.data[0].uv.x += 0.01
        artist_low = generation.fingerprint(low)
        counts = (len(bpy.data.objects), len(bpy.data.meshes))
        component.subdivision = 1
        generation.generate(bpy.context, asset, component)
        assert component.generated_high == high and component.low == low
        assert counts == (len(bpy.data.objects), len(bpy.data.meshes))
        assert generation.fingerprint(low) == artist_low
        assert generation.fingerprint(high) == component.high_signature
        configure = generation.configure
        def reject_commit(obj, item):
            if obj == high:
                raise RuntimeError('injected commit failure')
            configure(obj, item)
        before_commit = generation.fingerprint(high)
        with patch.object(generation, 'configure', reject_commit):
            try:
                generation.generate(bpy.context, asset, component)
                raise AssertionError('Commit should fail')
            except RuntimeError as error:
                assert str(error) == 'injected commit failure'
        assert generation.fingerprint(high) == before_commit
        assert counts == (len(bpy.data.objects), len(bpy.data.meshes))
        # Budget refusal must keep existing outputs and leave no snapshots.
        prior = generation.fingerprint(high)
        component.subdivision = 5
        component.max_faces = 100
        try:
            generation.generate(bpy.context, asset, component)
            raise AssertionError('Budget should refuse generation')
        except ValueError:
            pass
        assert generation.fingerprint(high) == prior
        assert counts == (len(bpy.data.objects), len(bpy.data.meshes))
        component.subdivision = 1
        component.max_faces = 1000000
        # Edited highs are protected.
        high.data.vertices[0].co.x += 0.1
        try:
            generation.generate(bpy.context, asset, component)
            raise AssertionError('Artist edit should be protected')
        except ValueError as error:
            assert 'edited' in str(error)
        high.data.vertices[0].co.x -= 0.1
        component.high_signature = generation.fingerprint(high)
        visibility = (source.hide_get(), low.hide_get(), high.hide_get())
        preview.show(bpy.context, component, 'HIGH')
        assert source.hide_get() and low.hide_get() and not high.hide_get()
        preview.restore()
        assert visibility == (source.hide_get(), low.hide_get(), high.hide_get())
        # Actual SDF path with coarse voxels.
        component.remesh = True
        component.voxel_size = 0.25
        generation.generate(bpy.context, asset, component)
        assert generation.fingerprint(source) == original
        with tempfile.TemporaryDirectory() as directory:
            bpy.context.scene.mbt_painter.output_dir = directory
            # Restore edited UV before strict export validation.
            low.data.uv_layers.active.data[0].uv.x -= 0.01
            exporter.export_asset(bpy.context, asset)
            first = Path(settings.last_export)
            assert (first / 'low.fbx').is_file() and (first / 'high.fbx').is_file()
            manifest = json.loads((first / 'asset.json').read_text())
            assert manifest['asset_id'] == asset.asset_id
            exporter.export_asset(bpy.context, asset)
            assert Path(settings.last_export) != first and first.is_dir()
            before_dirs = set(Path(directory).iterdir())
            def fail_export(*args, **kwargs):
                yield 'Injected failure'
                raise RuntimeError('injected')
            with patch.object(exporter.jobs.export_steps, '__wrapped__', fail_export):
                try:
                    exporter.export_asset(bpy.context, asset)
                    raise AssertionError('Injected failure was not propagated')
                except RuntimeError as error:
                    assert str(error) == 'injected'
            assert set(Path(directory).iterdir()) == before_dirs
            assert not any(scene.name.startswith('MBT_Painter_Export') for scene in bpy.data.scenes)
            # Custom mode never mutates high geometry; supports several highs.
            component.high_mode = 'CUSTOM'
            custom = source.copy()
            custom.data = source.data.copy()
            bpy.context.scene.collection.objects.link(custom)
            custom.name = 'Artist Floater'
            component.highs.add().mesh = custom
            custom_before = generation.fingerprint(custom)
            generation.generate(bpy.context, asset, component)
            exporter.export_asset(bpy.context, asset)
            assert generation.fingerprint(custom) == custom_before
            settings.export_high = False
            exporter.export_asset(bpy.context, asset)
            assert not (Path(settings.last_export) / 'high.fbx').exists()
            settings.export_high = True
            component.high_mode = 'DYNABOOL'
            # Save/load keeps high fingerprints valid across RNA pointer changes.
            path = str(Path(directory) / 'asset.blend')
            preview.show(bpy.context, component, 'HIGH')
            bpy.ops.wm.save_as_mainfile(filepath=path)
            assert not preview._state
            bpy.ops.wm.open_mainfile(filepath=path)
            asset = bpy.context.scene.mbt_assets.assets[0]
            component = asset.components[0]
            assert generation.fingerprint(component.generated_high) == component.high_signature
            generation.generate(bpy.context, asset, component)
        print('PASS: DynaBool/subdivision/SDF, source/UV preservation, stable refresh, edit/budget guards, preview restore, real FBX exports, cleanup and reload')
    finally:
        addon.unregister()


if __name__ == '__main__':
    main()