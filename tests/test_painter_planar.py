"""Disposable Blender tests for conservative planar receiving patches."""
import importlib
from pathlib import Path
import sys

import bpy
from mathutils import Matrix, Vector

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
planar = importlib.import_module(ROOT.name + '.features.substance_painter.planar')


def main():
    assert bpy.app.background
    vertices = [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)]
    triangles = [(0, 1, 2), (0, 2, 3)]
    result = planar.receiving_patches(vertices, triangles)
    assert not result['unassessed_faces'] and len(result['patches']) == 1
    patch = result['patches'][0]
    assert patch['faces'] == [0, 1] and len(patch['boundary_edges']) == 4
    assert (0, 2) not in patch['boundary_edges']
    assert abs(planar.boundary_distance((.5, .5, 0), vertices, patch['boundary_edges']) - .5) < 1e-6
    assert abs(patch['area'] - 1) < 1e-6
    for scale in (1e-4, 1, 1e4):
        matrix = Matrix.Translation((3, -2, 4)) @ Matrix.Rotation(.7, 4, 'Y') @ Matrix.Scale(scale, 4)
        transformed = [matrix @ Vector(v) for v in vertices]
        assert len(planar.receiving_patches(transformed, triangles)['patches']) == 1
    # A hard corner splits patches; disconnected coplanar islands stay separate.
    extra = vertices + [(0, 0, 1), (0, 1, 1), (3, 0, 0), (4, 0, 0), (3, 1, 0)]
    result = planar.receiving_patches(extra, triangles + [(0, 3, 5, 4), (6, 7, 8)])
    assert len(result['patches']) == 3
    # Gentle curvature is never absorbed by chaining neighbor angle tolerances.
    bent = vertices + [(2, 0, .01), (2, 1, .01)]
    result = planar.receiving_patches(bent, [(0, 1, 2, 3), (1, 4, 5, 2)])
    assert len(result['patches']) == 2
    assert planar.receiving_patches(vertices, [(0, 1, 1)])['unassessed_faces'] == [0]
    nonmanifold = planar.receiving_patches(extra, [(0, 1, 2), (1, 0, 3), (0, 1, 4)])
    assert nonmanifold['unassessed_faces'] == [0, 1, 2]
    assert not nonmanifold['patches']
    assert len(planar.receiving_patches(vertices, triangles, angle_degrees=0)['patches']) == 1
    assert planar.receiving_patches([], []) == {'patches': [], 'unassessed_faces': []}
    for invalid in (float('nan'), float('inf')):
        try:
            planar.receiving_patches([(invalid, 0, 0)], [])
        except ValueError:
            pass
        else:
            raise AssertionError('Nonfinite geometry was accepted')
    print('PASS: planar grouping, diagonal/boundary protection, transforms, curvature, invalid and nonmanifold rejection')


if __name__ == '__main__':
    main()