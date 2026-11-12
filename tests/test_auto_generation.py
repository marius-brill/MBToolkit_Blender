"""Disposable Blender: automatic remesh -> registered Bake inputs, no selections."""
import importlib
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
    jobs = importlib.import_module(ROOT.name + '.features.substance_painter.jobs')
    matching = importlib.import_module(ROOT.name + '.features.substance_painter.matching')
    dynabool = importlib.import_module(ROOT.name + '.features.geonodes.dynabool')
    gn = importlib.import_module(ROOT.name + '.core.gn')
    resolution = importlib.import_module(ROOT.name + '.features.geonodes.resolution')
    texture_sets = importlib.import_module(ROOT.name + '.features.substance_painter.texture_sets')
    try:
        bpy.ops.mesh.primitive_cube_add(size=0.1)
        source = bpy.context.object
        assert bpy.ops.mbt.asset_edit(action='CREATE') == {'FINISHED'}
        asset = bpy.context.scene.mbt_assets.assets[-1]
        component = asset.components[0]
        component.remesh = True
        component.voxel_size = 100  # Stored manual value must never control resolution.
        original = generation.fingerprint(source)
        bpy.ops.object.select_all(action='DESELECT')
        report = generation.generate(bpy.context, asset, component)
        print(report, flush=True)
        high, low = component.generated_high, component.low
        assert generation.fingerprint(source) == original
        settings = bpy.context.scene.mbt_painter
        assert len(settings.texture_sets) == 1
        entry = settings.texture_sets[0]
        assert component.texture_set_id == entry.set_id
        assert component.texture_collection == entry.collection
        assert list(entry.low_collection.objects) == [low]
        assert list(entry.high_collection.objects) == [high]
        assert source.name not in entry.collection.all_objects
        assert high.mbt_bake_target == low
        modifier = high.modifiers[0]
        assert modifier.node_group.get('mbt_rev') == dynabool.REV
        assert high['mbt_resolved_voxel'] < 0.002
        signature = generation.fingerprint(high)
        counts = len(bpy.data.objects), len(bpy.data.meshes), len(bpy.data.collections)
        generation.generate(bpy.context, asset, component)
        assert component.generated_high == high and component.low == low
        assert (len(bpy.data.objects), len(bpy.data.meshes), len(bpy.data.collections)) == counts
        assert len(settings.texture_sets) == 1
        assert generation.fingerprint(high) == signature
        # A fresh registration failure must remove temporary outputs, sets/children.
        bpy.ops.mesh.primitive_cube_add(size=0.1, location=(2, 0, 0))
        assert bpy.ops.mbt.asset_edit(action='CREATE') == {'FINISHED'}
        failed_asset = bpy.context.scene.mbt_assets.assets[-1]
        failed_component = failed_asset.components[0]
        before = len(bpy.data.objects), len(bpy.data.meshes), len(bpy.data.collections), len(settings.texture_sets)
        real_add = texture_sets.add_set
        def fail_registration(*args, **kwargs):
            real_add(*args, **kwargs)
            raise RuntimeError('injected registration failure')
        with patch.object(texture_sets, 'add_set', fail_registration):
            try:
                generation.generate(bpy.context, failed_asset, failed_component)
            except RuntimeError as error:
                assert 'registration failure' in str(error)
            else:
                raise AssertionError('Registration failure ignored')
        assert before == (len(bpy.data.objects), len(bpy.data.meshes), len(bpy.data.collections), len(settings.texture_sets))
        assert failed_component.low is None and failed_component.generated_high is None
        assert not failed_component.texture_set_id and failed_component.texture_collection is None
        with tempfile.TemporaryDirectory() as directory:
            settings.output_dir = directory
            lows, highs = jobs.validate(bpy.context, ignore_warnings=True)
            assert lows == [low] and highs == [high]
            names, pairs = matching.resolve(bpy.context, lows, highs)
            assert pairs[high] == low
            # Strict failure leaves both geometry and collection registration intact.
            bpy.ops.mesh.primitive_plane_add(size=0.1)
            plane = bpy.context.object
            component.source = plane
            before = len(bpy.data.objects), len(bpy.data.meshes), len(bpy.data.collections)
            try:
                generation.generate(bpy.context, asset, component)
            except ValueError as error:
                assert 'closed' in str(error)
            else:
                raise AssertionError('Open source was accepted')
            assert before == (len(bpy.data.objects), len(bpy.data.meshes), len(bpy.data.collections))
            assert generation.fingerprint(high) == signature
            component.source = source
            real_configure = generation.configure
            def fail_commit(obj, item):
                if obj == high:
                    raise RuntimeError('injected commit failure')
                return real_configure(obj, item)
            with patch.object(generation, 'configure', fail_commit):
                try:
                    generation.generate(bpy.context, asset, component)
                except RuntimeError as error:
                    assert str(error) == 'injected commit failure'
                else:
                    raise AssertionError('Commit failure ignored')
            assert before == (len(bpy.data.objects), len(bpy.data.meshes), len(bpy.data.collections))
            assert generation.fingerprint(high) == signature
            assert list(entry.high_collection.objects) == [high]
            # Multi-component generation reuses the asset's single texture set.
            bpy.ops.mesh.primitive_cube_add(size=0.1, location=(1, 0, 0))
            other = asset.components.add()
            other.component_id = 'other-component'
            other.name = 'Other'
            other.source = bpy.context.object
            generation.generate(bpy.context, asset, other)
            assert other.texture_set_id == component.texture_set_id
            assert len(settings.texture_sets) == 1
            assert len(entry.low_collection.objects) == len(entry.high_collection.objects) == 2
            jobs.validate(bpy.context, ignore_warnings=True)
            # Quality failure is bounded; never silently accept a coarse high.
            with patch.object(resolution, 'quality', return_value=(False, 1.0)):
                try:
                    generation.generate(bpy.context, asset, component)
                except ValueError as error:
                    assert any(stage in str(error) for stage in ('WORK ESTIMATE', 'QUALITY', 'FACES'))
                else:
                    raise AssertionError('Quality failure accepted')
            assert generation.fingerprint(high) == signature
            # Automatic resolution tracks actual dimensions, not an absolute default.
            small = source.data.copy()
            try:
                base = resolution.analyze(small)
                for vertex in small.vertices:
                    vertex.co *= 0.01
                small.update()
                scaled = resolution.analyze(small)
                assert abs(scaled['voxel'] / base['voxel'] - 0.01) < 1e-5
            finally:
                bpy.data.meshes.remove(small)
            # Thin solids must meet measured quality, not an unconditional
            # thickness/6 voxel rule; coarser accepted output is intentional.
            bpy.ops.mesh.primitive_cube_add(size=0.1, location=(3, 0, 0))
            thin = bpy.context.object
            for vertex in thin.data.vertices:
                vertex.co.z *= 0.1
            thin.data.update()
            thin_analysis = resolution.analyze(thin.data)
            assert thin_analysis['voxel'] <= 0.01 / 6
            thin_component = asset.components.add()
            thin_component.component_id = 'thin-component'
            thin_component.name = 'Thin'
            thin_component.source = thin
            generation.generate(bpy.context, asset, thin_component)
            thin_high = thin_component.generated_high
            assert 0 < thin_high['mbt_resolved_voxel'] <= thin_analysis['voxel'] * 4
            with generation.available(bpy.context, [thin_high]):
                evaluated = thin_high.evaluated_get(bpy.context.evaluated_depsgraph_get())
                mesh = evaluated.to_mesh()
                try:
                    assert resolution.quality(mesh, thin_analysis)[0]
                finally:
                    evaluated.to_mesh_clear()
            # Generated automatic settings and Bake links survive reload.
            path = str(Path(directory) / 'auto.blend')
            high_name = high.name
            bpy.ops.wm.save_as_mainfile(filepath=path)
            bpy.ops.wm.open_mainfile(filepath=path)
            assert bpy.data.objects[high_name].mbt_bake_target
            jobs.validate(bpy.context, ignore_warnings=True)
        # GN standalone manual mode uses the visible voxel size.
        bpy.ops.mesh.primitive_cube_add(size=0.1)
        obj = bpy.context.object
        mod = obj.modifiers.new('DynaBool', 'NODES')
        mod.node_group = dynabool.get_group()
        for socket in mod.node_group.interface.items_tree:
            if socket.name in {'Automatic Resolution', 'Fallback on Failure'}:
                gn.set_modifier_input(mod, socket.identifier, False)
            elif socket.name == 'Voxel Size':
                gn.set_modifier_input(mod, socket.identifier, 0.002)
        obj.update_tag()
        bpy.context.view_layer.update()
        evaluated = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
        mesh = evaluated.to_mesh()
        try:
            assert len(mesh.polygons) > 1000
        finally:
            evaluated.to_mesh_clear()
        print('PASS auto remesh, scale, strict failures, stable refresh, multi-component Bake registration/validation/matching and save/reload')
    finally:
        addon.unregister()


if __name__ == '__main__':
    main()