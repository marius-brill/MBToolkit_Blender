"""Disposable shape/fidelity/performance regressions. Optional exported user fixture."""
import bpy
import bmesh
import importlib
import math
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
dynabool = importlib.import_module(ROOT.name + '.features.geonodes.dynabool')
gn = importlib.import_module(ROOT.name + '.core.gn')
resolution = importlib.import_module(ROOT.name + '.features.geonodes.resolution')
resolution_nodes = importlib.import_module(ROOT.name + '.features.geonodes.resolution_nodes')


def live_policy(mesh):
    """Read back scalar live-node measurements, independently of SDF meshing."""
    obj = bpy.data.objects.new('Policy parity', mesh)
    bpy.context.scene.collection.objects.link(obj)
    group = bpy.data.node_groups.new('Policy parity', 'GeometryNodeTree')
    gn.add_input(group.interface, 'Geometry', 'NodeSocketGeometry')
    gn.add_output(group.interface, 'Geometry', 'NodeSocketGeometry')
    gi = group.nodes.new('NodeGroupInput')
    go = group.nodes.new('NodeGroupOutput')
    angle = group.nodes.new('ShaderNodeValue')
    angle.outputs[0].default_value = 50
    voxel, limited = resolution_nodes.build(group, gi.outputs['Geometry'], angle.outputs[0])
    store = group.nodes.new('GeometryNodeStoreNamedAttribute')
    store.data_type, store.domain = 'FLOAT', 'POINT'
    store.inputs['Name'].default_value = 'policy_voxel'
    group.links.new(gi.outputs['Geometry'], store.inputs['Geometry'])
    group.links.new(voxel, store.inputs['Value'])
    flag = group.nodes.new('GeometryNodeStoreNamedAttribute')
    flag.data_type, flag.domain = 'BOOLEAN', 'POINT'
    flag.inputs['Name'].default_value = 'policy_limited'
    group.links.new(store.outputs['Geometry'], flag.inputs['Geometry'])
    group.links.new(limited, flag.inputs['Value'])
    group.links.new(flag.outputs['Geometry'], go.inputs['Geometry'])
    modifier = obj.modifiers.new('Policy parity', 'NODES')
    modifier.node_group = group
    result = snapshot(obj)
    try:
        return (result.attributes['policy_voxel'].data[0].value,
                result.attributes['policy_limited'].data[0].value)
    finally:
        bpy.data.meshes.remove(result)
        bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.node_groups.remove(group)


def set_inputs(obj, modifier, **values):
    for s in modifier.node_group.interface.items_tree:
        if getattr(s, 'in_out', '') == 'INPUT' and s.name in values:
            gn.set_modifier_input(modifier, s.identifier, values[s.name])
    obj.update_tag()
    bpy.context.view_layer.update()


def snapshot(obj):
    evaluated = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
    mesh = evaluated.to_mesh()
    try:
        return mesh.copy()
    finally:
        evaluated.to_mesh_clear()


def check(obj, subdivision=2):
    modifier = next((m for m in obj.modifiers if m.type == 'NODES'
                     and m.node_group and m.node_group.name.startswith('DynaBool')), None)
    if modifier is None:
        modifier = obj.modifiers.new('DynaBool', 'NODES')
    modifier.node_group = dynabool.get_group()
    set_inputs(obj, modifier, **{'SubD Level': subdivision, 'Remesh': False})
    reference = snapshot(obj)
    try:
        analysis = resolution.analyze(reference)
        bm = bmesh.new()
        bm.from_mesh(reference)
        bm.normal_update()
        try:
            python_voxel, _, _, _ = resolution.shape_voxel(bm, resolution.tree(reference), analysis['diagonal'])
        finally:
            bm.free()
        node_voxel, unused = live_policy(reference)
        assert abs(node_voxel / python_voxel - 1) < 0.05, (obj.name, node_voxel, python_voxel)
        start = time.perf_counter()
        set_inputs(obj, modifier, **{'Remesh': True})
        result = snapshot(obj)
        try:
            seconds = time.perf_counter() - start
            result.calc_loop_triangles()
            triangles = len(result.loop_triangles)
            accepted, error = resolution.quality(result, analysis)
            print(f'{obj.name}: {triangles:,} tris, {seconds:.4f}s; '
                  f'voxel {analysis["voxel"]:.6g}, {analysis["driver"]}; '
                  f'error {error:.6g}/{analysis["tolerance"]:.6g}; accepted {accepted}', flush=True)
            assert accepted, analysis.get('quality_reason')
            assert 0 < triangles < 500000
            if obj.type == 'MESH' and obj.name.startswith('Sphere'):
                # Smooth normals alone must not hide a badly faceted silhouette.
                angles = []
                for face in result.polygons:
                    nearest = analysis['surface'].find_nearest(face.center)
                    if nearest[0] is not None:
                        angles.append(face.normal.angle(nearest[1]))
                angles.sort()
                normal_p95 = math.degrees(angles[int(len(angles) * 0.95)])
                print(f'Sphere face-normal p95: {normal_p95:.3f} degrees', flush=True)
                assert normal_p95 < 12
            # A uniformly scaled input must not change local sampling density.
            for vertex in obj.data.vertices:
                vertex.co *= 0.1
            widths = [(m, m.width) for m in obj.modifiers if m.type == 'BEVEL']
            for m, width in widths:
                m.width = width * 0.1
            obj.data.update()
            obj.update_tag()
            bpy.context.view_layer.update()
            scaled = snapshot(obj)
            try:
                scaled.calc_loop_triangles()
                assert abs(len(scaled.loop_triangles) / triangles - 1) < 0.08
            finally:
                bpy.data.meshes.remove(scaled)
                for vertex in obj.data.vertices:
                    vertex.co *= 10
                for m, width in widths:
                    m.width = width
                obj.data.update()
        finally:
            bpy.data.meshes.remove(result)
    finally:
        bpy.data.meshes.remove(reference)


def main():
    assert bpy.app.background
    bpy.ops.mesh.primitive_cube_add(size=0.1)
    check(bpy.context.object)
    bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16, radius=0.05)
    check(bpy.context.object, subdivision=0)
    bpy.ops.mesh.primitive_cylinder_add(vertices=48, radius=0.02, depth=0.15)
    check(bpy.context.object, subdivision=0)
    bpy.ops.mesh.primitive_cube_add(size=0.1)
    thin = bpy.context.object
    for v in thin.data.vertices:
        v.co.z *= 0.025
    check(thin, subdivision=0)
    bpy.ops.mesh.primitive_cube_add(size=0.1)
    beveled = bpy.context.object
    bevel = beveled.modifiers.new('Bevel', 'BEVEL')
    bevel.width = 0.002
    bevel.segments = 4
    check(beveled, subdivision=0)
    bpy.ops.mesh.primitive_cube_add(size=0.1)
    segmented = bpy.context.object
    bm = bmesh.new()
    bm.from_mesh(segmented.data)
    edge = next(iter(bm.edges))
    bmesh.utils.edge_split(edge, edge.verts[0], 1e-5)
    bm.to_mesh(segmented.data)
    bm.free()
    check(segmented, subdivision=0)
    # Opposing gap must not fuse two separate closed components.
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=0.1)
    other = bmesh.ops.create_cube(bm, size=0.1)['verts']
    bmesh.ops.translate(bm, verts=other, vec=(0.102, 0, 0))
    mesh = bpy.data.meshes.new('Gap reference')
    bm.to_mesh(mesh)
    bm.free()
    gap = bpy.data.objects.new('Gap', mesh)
    bpy.context.scene.collection.objects.link(gap)
    check(gap, subdivision=0)
    output = snapshot(gap)
    bm = bmesh.new()
    bm.from_mesh(output)
    remaining = set(bm.verts)
    shells = 0
    while remaining:
        shells += 1
        stack = [remaining.pop()]
        while stack:
            vertex = stack.pop()
            for edge in vertex.link_edges:
                other = edge.other_vert(vertex)
                if other in remaining:
                    remaining.remove(other)
                    stack.append(other)
    bm.free()
    bpy.data.meshes.remove(output)
    assert shells == 2, shells
    # The work safeguard is observable, not a silently enforced triangle target.
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=0.1)
    for vertex in bm.verts:
        vertex.co.z *= 0.0001
    pathological = bpy.data.meshes.new('Very thin work-limit probe')
    bm.to_mesh(pathological)
    bm.free()
    voxel, limited = live_policy(pathological)
    assert limited and voxel > 0
    bpy.data.meshes.remove(pathological)
    # Many-object smoke: bounded total output and report time, not a flaky time threshold.
    start = time.perf_counter()
    total = 0
    for index in range(12):
        bpy.ops.mesh.primitive_cube_add(size=0.1, location=(index, 0, 0))
        obj = bpy.context.object
        modifier = obj.modifiers.new('DynaBool', 'NODES')
        modifier.node_group = dynabool.get_group()
        obj.update_tag()
        mesh = snapshot(obj)
        try:
            mesh.calc_loop_triangles()
            total += len(mesh.loop_triangles)
        finally:
            bpy.data.meshes.remove(mesh)
    assert total < 1000000, total
    print(f'12-object smoke: {total:,} tris, {time.perf_counter()-start:.3f}s', flush=True)
    if '--fixture' in sys.argv:
        path = sys.argv[sys.argv.index('--fixture') + 1]
        with bpy.data.libraries.load(path) as (source, target):
            target.objects = ['Cube.029']
        obj = target.objects[0]
        assert obj
        bpy.context.scene.collection.objects.link(obj)
        # Check without scaling: upstream bevel widths are absolute local units.
        modifier = obj.modifiers['DynaBool']
        modifier.node_group = dynabool.get_group()
        set_inputs(obj, modifier, **{'Remesh': False})
        reference = snapshot(obj)
        analysis = resolution.analyze(reference)
        set_inputs(obj, modifier, **{'Remesh': True})
        mesh = snapshot(obj)
        try:
            mesh.calc_loop_triangles()
            accepted, error = resolution.quality(mesh, analysis)
            print(f'Cube.029: {len(mesh.loop_triangles):,} triangles; error {error:.6g}; '
                  f'quality {accepted}; {analysis["quality_reason"]}', flush=True)
            assert accepted
            assert 10000 < len(mesh.loop_triangles) < 500000
        finally:
            bpy.data.meshes.remove(mesh)
            bpy.data.meshes.remove(reference)
    print('PASS shape quality, scale stability, bounded many-object output')


if __name__ == '__main__':
    main()