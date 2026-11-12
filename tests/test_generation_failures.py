"""Disposable Blender mixed-source processing and accurate per-object failures."""
import importlib
from pathlib import Path
import sys
from types import SimpleNamespace

import bpy
import bmesh

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))


def main():
    assert bpy.app.background
    addon = importlib.import_module(ROOT.name)
    addon.register()
    addon.feature_manager.sync(SimpleNamespace(enable_substance_painter=True))
    generation = importlib.import_module(ROOT.name + '.features.asset_processing.generation')
    resolution = importlib.import_module(ROOT.name + '.features.geonodes.resolution')
    gn = importlib.import_module(ROOT.name + '.core.gn')
    try:
        bpy.ops.mesh.primitive_cube_add(size=1)
        bpy.ops.mbt.asset_edit(action='CREATE')
        asset = bpy.context.scene.mbt_assets.assets[0]
        cube = asset.components[0]
        cube.source.name = 'SolidWithLooseGeometry'
        bm = bmesh.new()
        bm.from_mesh(cube.source.data)
        a = bm.verts.new((3, 0, 0))
        b = bm.verts.new((4, 0, 0))
        bm.edges.new((a, b))
        bm.to_mesh(cube.source.data)
        bm.free()
        original = generation.fingerprint(cube.source)
        bpy.ops.mesh.primitive_plane_add()
        plane = asset.components.add()
        plane.component_id = 'plane'
        plane.name = 'Plane'
        plane.source = bpy.context.object
        plane.source.name = 'OpenPanel'
        bpy.ops.mesh.primitive_uv_sphere_add(segments=12, ring_count=8)
        sphere = asset.components.add()
        sphere.component_id = 'sphere'
        sphere.source = bpy.context.object
        sphere.name = 'Curved'
        assert bpy.ops.mbt.asset_process(action='GENERATE_ASSET') == {'FINISHED'}
        assert cube.generation_state == 'Succeeded', cube.generation_report
        assert sphere.generation_state == 'Succeeded', sphere.generation_report
        assert plane.generation_state == 'Failed', plane.generation_report
        assert 'OpenPanel' in plane.generation_report and 'boundary edges' in plane.generation_report
        assert '2 succeeded, 1 failed' in bpy.context.scene.mbt_assets.report
        assert plane.generated_high is None
        assert bpy.ops.mbt.asset_process(action='SELECT_FAILED') == {'FINISHED'}
        assert plane.source in bpy.context.selected_objects
        assert generation.fingerprint(cube.source) == original
        # Remesh off bypasses SDF restrictions, not high generation or Bake setup.
        plane.remesh = False
        generation.generate(bpy.context, asset, plane)
        assert plane.generation_state == 'Succeeded'
        assert 'Remesh disabled' in plane.generation_report
        mod = plane.generated_high.modifiers[0]
        inputs = gn.modifier_inputs(mod)
        sockets = {s.name: s.identifier for s in mod.node_group.interface.items_tree if s.item_type == 'SOCKET'}
        assert getattr(inputs, sockets['Automatic Resolution']).value
        assert not getattr(inputs, sockets['Remesh']).value
        # New sparse work estimate must not reject a large empty bounding box.
        resolution.budget({'extents': (1000000, 1000000, 1000000), 'area': 1}, 0.01, 10000000)
        # Reproduce the screenshot's 6.50-GiB estimate without allocating that RAM.
        work = {'area': 6.5 * 1024 ** 3 / (6 * 96)}
        assert abs(resolution.budget(work, 1, 10000000) - 6.5) < 1e-6
        try:
            resolution.budget(work, 1, 10000000, 2)
        except ValueError as error:
            assert 'configured Work Allowance 2' in str(error)
            assert 'not measured RAM' in str(error)
        else:
            raise AssertionError('Explicit user work allowance was ignored')
        assert resolution.budget(work, 1, 10000000, 0) == 6.5
        # Subdivision changes target topology, not the source feature resolution.
        initial_voxel = cube.generated_high['mbt_resolved_voxel']
        cube.subdivision = 3
        generation.generate(bpy.context, asset, cube)
        assert abs(cube.generated_high['mbt_resolved_voxel'] - initial_voxel) < 1e-8
        assert 'source driver:' in cube.generation_report
        assert 'Initial attempt' in cube.generation_report or 'Refinement' in cube.generation_report
        assert 'work estimate' in cube.generation_report
        # Measured face failures carry the real limit, not a generic memory message.
        cube.max_faces = 100
        try:
            generation.generate(bpy.context, asset, cube)
        except ValueError:
            pass
        else:
            raise AssertionError('Expected face refusal')
        assert cube.generation_state == 'Failed'
        assert 'face budget' in cube.generation_report.lower() or 'FACES' in cube.generation_report
        assert cube.generated_high is not None
        # Standalone selection is best-effort: an open object cannot cancel solids.
        dynabool = importlib.import_module(ROOT.name + '.features.geonodes.dynabool')
        dynabool.register()
        try:
            bpy.ops.object.select_all(action='DESELECT')
            cube.source.select_set(True)
            plane.source.select_set(True)
            assert bpy.ops.mbt.add_dynabool() == {'FINISHED'}
            assert 'DynaBool' in cube.source.modifiers
            assert 'DynaBool' not in plane.source.modifiers
        finally:
            dynabool.unregister()
        print('PASS mixed solids/loose geometry/open surface/curved source, optional remesh, named errors, automatic-on and sparse work bounds')
    finally:
        addon.unregister()


if __name__ == '__main__':
    main()