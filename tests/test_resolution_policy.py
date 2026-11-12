"""Source topology, edge hints and local feature preservation in Blender."""
import importlib
from pathlib import Path
import sys

import bpy
import bmesh

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
resolution = importlib.import_module(ROOT.name + '.features.geonodes.resolution')


def main():
    assert bpy.app.background
    # Face-split cube: all coincident seams may be welded on a disposable mesh.
    bpy.ops.mesh.primitive_cube_add()
    mesh = bpy.context.object.data
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bmesh.ops.split_edges(bm, edges=list(bm.edges))
    bm.to_mesh(mesh)
    bm.free()
    assert len(mesh.vertices) > 8
    resolution.prepare(mesh)
    assert len(mesh.vertices) == 8
    baseline = resolution.analyze(mesh)
    # A tiny extra sharp segment must not globally force microscopic voxels.
    bm = bmesh.new()
    bm.from_mesh(mesh)
    edge = next(iter(bm.edges))
    bmesh.utils.edge_split(edge, edge.verts[0], 0.00001)
    bm.to_mesh(mesh)
    bm.free()
    analysis = resolution.analyze(mesh)
    assert analysis['candidates']['sharp source edge'] < baseline['voxel'] / 100
    assert abs(analysis['voxel'] - baseline['voxel']) < 1e-8
    # An actual opening is neither capped nor mistaken for a repairable seam.
    bpy.ops.mesh.primitive_plane_add()
    plane = bpy.context.object.data
    resolution.prepare(plane)
    assert len(plane.polygons) == 1
    try:
        resolution.analyze(plane)
    except ValueError as exc:
        assert '1 boundary groups' in str(exc) and '4 edges' in str(exc)
    else:
        raise AssertionError('Open sheet accepted as a closed solid')
    # A tiny disconnected shell can be lost within global distance tolerance.
    # The per-shell acceptance limits must still reject its disappearance.
    bpy.ops.mesh.primitive_cube_add(size=2)
    large = bpy.context.object.data
    combined = large.copy()
    bm = bmesh.new()
    bm.from_mesh(combined)
    tiny = bmesh.ops.create_cube(bm, size=0.001)['verts']
    for vertex in tiny:
        vertex.co.x += 1.005
    bm.to_mesh(combined)
    bm.free()
    analysis = resolution.analyze(combined)
    accepted, error = resolution.quality(large, analysis)
    assert error < analysis['tolerance'], (error, analysis['tolerance'])
    assert not accepted, 'Small disconnected shell disappeared undetected'
    assert resolution.quality(combined, analysis)[0]
    # True thin walls generate tighter local limits, rather than forcing the
    # starting voxel to the smallest thickness/6 candidate.
    bpy.ops.mesh.primitive_cube_add(size=2)
    thin = bpy.context.object.data
    for vertex in thin.vertices:
        vertex.co.z *= 0.001
    thin.update()
    analysis = resolution.analyze(thin)
    assert analysis['voxel'] > analysis['candidates']['thickness/gap']
    assert min(limit for point, limit in analysis['local_samples']) < analysis['tolerance']
    assert resolution.quality(thin, analysis)[0]
    print('PASS conservative seam welding, genuine openings, tiny edge hints, missing shell and thin-wall constraints')


if __name__ == '__main__':
    main()