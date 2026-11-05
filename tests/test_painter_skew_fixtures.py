"""Disposable Blender checks for sparse topology and a genuine hard-edge ray gap.

No Painter connection or project changes. Live bakes remain separate acceptance.
"""
import sys
from pathlib import Path

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_painter_skew_coverage_live as coverage


def witness_tree(highs):
    vertices, triangles = [], []
    for obj in highs:
        evaluated = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
        mesh = evaluated.to_mesh()
        try:
            mesh.calc_loop_triangles()
            offset = len(vertices)
            vertices.extend(evaluated.matrix_world @ vertex.co for vertex in mesh.vertices)
            for triangle in mesh.loop_triangles:
                color = mesh.materials[triangle.material_index].diffuse_color
                if color[2] > .9 and color[0] < .1:
                    triangles.append(tuple(offset + i for i in triangle.vertices))
        finally:
            evaluated.to_mesh_clear()
    assert triangles, 'Missing colored gap witness'
    return BVHTree.FromPolygons(vertices, triangles, all_triangles=True)


def main():
    assert bpy.app.background, 'Run in a disposable background Blender process'
    base = coverage.base
    base.addon.register()
    try:
        base.addon.feature_manager.sync(type('P', (), {'enable_substance_painter': True})())
        for joined in (False, True):
            low, highs = coverage.fixture(joined, sparse=True, edge_gap=True)
            assert len(low.data.vertices) == 8 and len(low.data.polygons) == 6
            assert len(highs) == (1 if joined else 4)
            assert all(obj.mbt_bake_target == low for obj in highs)
            original = [tuple(v.co) for v in low.data.vertices]
            tree = witness_tree(highs)
            # Top and right-face perpendicular rays both miss this geometry.
            for i in range(21):
                x = i / 10 - 1
                assert tree.ray_cast(Vector((x, -.45, 2)), Vector((0, 0, -1)), 2)[0] is None
                assert tree.ray_cast(Vector((2, -.45, x)), Vector((-1, 0, 0)), 2)[0] is None
            # A tilted outward corner ray reaches the same nonempty witness.
            direction = Vector((.9, 0, 1)).normalized()
            origin = Vector((.9, -.45, 1)) + direction * .5
            assert tree.ray_cast(origin, -direction, .5)[0] is not None
            # A sparse local cage has no interior vertex to adjust independently.
            cage = low.copy()
            cage.data = low.data.copy()
            try:
                coverage.build_cage(cage, 'local')
                assert all((v.co - Vector(original[v.index]) * 1.5).length < 1e-6
                           for v in cage.data.vertices)
            finally:
                mesh = cage.data
                bpy.data.objects.remove(cage, do_unlink=True)
                bpy.data.meshes.remove(mesh)
            assert original == [tuple(v.co) for v in low.data.vertices]
        print('PASS: sparse topology, joined/separate highs, real perpendicular-ray gap, cage limitation, source preservation')
    finally:
        base.addon.unregister()


if __name__ == '__main__':
    main()