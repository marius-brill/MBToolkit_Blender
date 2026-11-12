"""Destructive real-SDF regressions; disposable --background --factory-startup only."""
import importlib
import math
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

import bpy
import bmesh

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
dynabool = importlib.import_module(ROOT.name + '.features.geonodes.dynabool')
sdf = importlib.import_module(ROOT.name + '.features.geonodes.sdf_remesh')
gn = importlib.import_module(ROOT.name + '.core.gn')


def set_inputs(obj, modifier, **values):
    for socket in modifier.node_group.interface.items_tree:
        if getattr(socket, 'in_out', '') == 'INPUT' and socket.name in values:
            gn.set_modifier_input(modifier, socket.identifier, values[socket.name])
    obj.update_tag()
    bpy.context.view_layer.update()


def evaluate(obj, closed=False):
    evaluated = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
    mesh = evaluated.to_mesh()
    try:
        assert all(math.isfinite(c) for v in mesh.vertices for c in v.co)
        attribute = mesh.attributes.get(dynabool.FAILURE_ATTRIBUTE)
        fallback = bool(attribute and any(v.value for v in attribute.data))
        extent = tuple(max((v.co[i] for v in mesh.vertices), default=0)
                       - min((v.co[i] for v in mesh.vertices), default=0) for i in range(3))
        if closed:
            bm = bmesh.new()
            try:
                bm.from_mesh(mesh)
                assert bm.faces and all(e.is_manifold for e in bm.edges)
                assert all(f.calc_area() > 1e-15 for f in bm.faces)
                assert bm.calc_volume() > 0
            finally:
                bm.free()
        return len(mesh.polygons), extent, fallback
    finally:
        evaluated.to_mesh_clear()


def cube(group):
    bpy.ops.object.select_all(action='DESELECT')
    bpy.ops.mesh.primitive_cube_add(size=0.1)
    obj = bpy.context.object
    modifier = obj.modifiers.new('DynaBool', 'NODES')
    modifier.node_group = group
    return obj, modifier


def main():
    assert bpy.app.background
    dynabool.register()
    sdf.register()
    try:
        # Legacy graph reproduces empty output. Keep this exact reference for migration.
        legacy = dynabool._build(legacy=True)
        legacy['mbt_rev'] = 1
        obj, modifier = cube(legacy)
        original = tuple(tuple(v.co) for v in obj.data.vertices)
        set_inputs(obj, modifier, **{'Voxel Size': 0.001, 'Smooth Iterations': 0})
        assert evaluate(obj)[0] == 0
        assert bpy.ops.mbt.upgrade_dynabool() == {'FINISHED'}
        assert modifier.node_group != legacy and legacy.name == 'DynaBool'
        assert modifier.node_group == dynabool.get_group()
        # Fine-grid density assertions below exercise uniform manual extraction;
        # automatic extraction intentionally removes redundant planar polygons.
        set_inputs(obj, modifier, **{'Automatic Resolution': False})
        inputs = gn.modifier_inputs(modifier)
        voxel = next(s for s in modifier.node_group.interface.items_tree if s.name == 'Voxel Size')
        assert abs(getattr(inputs, voxel.identifier).value - 0.001) < 1e-8
        for smooth in (0, 1, 4):
            counts = []
            for size in (0.008, 0.004, 0.002, 0.001):
                set_inputs(obj, modifier, **{'Voxel Size': size, 'Resolved Voxel Size': size, 'Smooth Iterations': smooth})
                count, extent, fallback = evaluate(obj, closed=True)
                assert count > 100 and not fallback
                assert all(abs(length - 0.1) < size * 4 for length in extent), extent
                counts.append(count)
            assert counts == sorted(counts) and counts[-1] > 50000, counts
        assert original == tuple(tuple(v.co) for v in obj.data.vertices)
        obj.scale = (-2, 0.5, 3)
        obj.rotation_euler = (0.3, 0.1, 0.7)
        bpy.context.view_layer.update()
        assert evaluate(obj, closed=True)[0] == counts[-1]
        print('PASS: reproduced legacy disappearance; zero surface, density, manifoldness, bounds, source/transform preservation')

        # A flat surface has no volume. Mandatory remesh must not fake success.
        bpy.ops.mesh.primitive_plane_add(size=0.1)
        plane = bpy.context.object
        pm = plane.modifiers.new('DynaBool', 'NODES')
        pm.node_group = dynabool.get_group()
        set_inputs(plane, pm, **{'Resolved Voxel Size': 0.005, 'SubD Level': 1, 'Automatic Resolution': True, 'Smooth Iterations': 1})
        assert evaluate(plane)[0] == 0
        set_inputs(plane, pm, **{'Fallback on Failure': False})
        assert evaluate(plane)[0] == 0
        set_inputs(plane, pm, **{'Remesh': False})
        assert evaluate(plane)[0] == 4
        bpy.ops.mesh.primitive_cube_add(size=0.1)
        thin = bpy.context.object
        for vertex in thin.data.vertices:
            vertex.co.z *= 0.1
        tm = thin.modifiers.new('DynaBool', 'NODES')
        tm.node_group = dynabool.get_group()
        set_inputs(thin, tm, **{'Resolved Voxel Size': 0.001, 'Smooth Iterations': 0, 'Automatic Resolution': True})
        assert evaluate(thin, closed=True)[0] > 100 and not evaluate(thin)[2]
        # Disconnected shells and overlapping solids, including n-gon subdivision input.
        bm = bmesh.new()
        try:
            bmesh.ops.create_cube(bm, size=0.1)
            added = bmesh.ops.create_cube(bm, size=0.1)['verts']
            bmesh.ops.translate(bm, verts=added, vec=(0.2, 0, 0))
            bm.to_mesh(thin.data)
        finally:
            bm.free()
        thin.data.update()
        set_inputs(thin, tm, **{'Resolved Voxel Size': 0.004})
        assert evaluate(thin, closed=True)[0] > 100 and not evaluate(thin)[2]
        for vertex in thin.data.vertices:
            if vertex.co.x > 0.1:
                vertex.co.x -= 0.15
        thin.data.update()
        set_inputs(thin, tm, **{'Resolved Voxel Size': 0.003})
        assert evaluate(thin, closed=True)[0] > 100 and not evaluate(thin)[2]
        print('PASS: optional remesh without fallback, thin solid, disconnected and overlapping shells')

        # Customized graphs and processor-owned/animated objects must not be upgraded.
        custom = legacy.copy()
        next(n for n in custom.nodes if n.bl_idname == 'GeometryNodeGridToMesh').inputs['Threshold'].default_value = 0.02
        protected, protected_mod = cube(custom)
        assert bpy.ops.mbt.upgrade_dynabool() == {'FINISHED'}
        assert protected_mod.node_group == custom
        protected_mod.node_group = legacy
        protected['mbt_asset_role'] = 'HIGH'
        assert bpy.ops.mbt.upgrade_dynabool() == {'FINISHED'}
        assert protected_mod.node_group == legacy
        del protected['mbt_asset_role']
        protected.keyframe_insert(data_path='location', frame=1)
        assert bpy.ops.mbt.upgrade_dynabool() == {'FINISHED'}
        assert protected_mod.node_group == legacy
        # SDF standalone upgrade preserves values but removes its one-voxel inflation.
        old_sdf = sdf._build(legacy=True)
        old_sdf['mbt_rev'] = 2
        sobj, smod = cube(old_sdf)
        set_inputs(sobj, smod, **{'Density': 0.002, 'Smoothing Iterations': 0, 'Decimate Adaptivity': 0.0})
        before = evaluate(sobj)[1]
        assert bpy.ops.mbt.upgrade_sdf_remesh() == {'FINISHED'}
        assert smod.node_group == sdf.get_group() and smod.node_group != old_sdf
        count, after, fallback = evaluate(sobj, closed=True)
        assert count > 100 and all(abs(v - 0.1) < 0.001 for v in after), after
        assert all(a < b for a, b in zip(after, before)), (before, after)
        assert bpy.ops.mbt.check_dynabool() == {'FINISHED'}
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / 'dynabool.blend')
            name = obj.name
            bpy.ops.wm.save_as_mainfile(filepath=path)
            bpy.ops.wm.open_mainfile(filepath=path)
            restored = bpy.data.objects[name]
            assert restored.modifiers[0].node_group == dynabool.get_group()
            assert evaluate(restored, closed=True)[0] > 50000
        print('PASS: migration values, protected groups/objects, SDF zero-offset extraction and save/reload')
    finally:
        sdf.unregister()
        dynabool.unregister()


def processor_cases():
    addon = importlib.import_module(ROOT.name)
    addon.register()
    addon.feature_manager.sync(SimpleNamespace(enable_substance_painter=True))
    generation = importlib.import_module(ROOT.name + '.features.asset_processing.generation')
    try:
        bpy.ops.object.select_all(action='DESELECT')
        bpy.ops.mesh.primitive_cube_add(size=0.1)
        source = bpy.context.object
        assert bpy.ops.mbt.asset_edit(action='CREATE') == {'FINISHED'}
        asset = bpy.context.scene.mbt_assets.assets[-1]
        component = asset.components[0]
        component.remesh = True
        component.voxel_size = 0.002
        legacy = dynabool._build(revision=2)
        legacy['mbt_rev'] = 2
        # Generate a valid legacy high at coarse resolution before upgrading.
        component.voxel_size = 0.008
        generation.generate(bpy.context, asset, component)
        generated = component.generated_high
        generated.modifiers[0].node_group = legacy
        component.high_signature = generation.fingerprint(generated)
        high, low = component.generated_high, component.low
        prior = generation.fingerprint(high)
        group_name = legacy.name
        dynabool.get_group()
        assert legacy.name == group_name and generation.fingerprint(high) == prior
        component.voxel_size = 0.002
        generation.generate(bpy.context, asset, component)
        assert component.generated_high == high and component.low == low
        assert high.modifiers[0].node_group.get('mbt_rev') == dynabool.REV
        # Adaptive automatic extraction should not be required to retain the
        # old uniform-grid polygon count; closed, finite output is the invariant.
        assert evaluate(high, closed=True)[0] > 100
        # Strict processor must reject an open surface without replacing the high.
        bpy.ops.mesh.primitive_plane_add(size=0.1)
        component.source = bpy.context.object
        counts = len(bpy.data.objects), len(bpy.data.meshes)
        prior = generation.fingerprint(high)
        try:
            generation.generate(bpy.context, asset, component)
        except ValueError as error:
            assert 'closed' in str(error), str(error)
        else:
            raise AssertionError('Processor accepted a failed remesh')
        assert (len(bpy.data.objects), len(bpy.data.meshes)) == counts
        assert component.generated_high == high and generation.fingerprint(high) == prior
        component.source = source
        component.detail_tolerance = 0.0001
        try:
            generation.generate(bpy.context, asset, component)
        except ValueError as error:
            assert 'WORK ESTIMATE' in str(error), str(error)
        else:
            raise AssertionError('Processor accepted an excessive voxel estimate')
        assert (len(bpy.data.objects), len(bpy.data.meshes)) == counts
        assert generation.fingerprint(high) == prior
        print('PASS: processor legacy fingerprint/stable refresh, strict empty rejection, voxel budget and rollback cleanup')
    finally:
        addon.unregister()


if __name__ == '__main__':
    main()
    processor_cases()