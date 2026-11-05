"""Read-only, bounded projection-risk estimates; never a bake certification."""
from math import cos, radians

from mathutils import Vector
from mathutils.bvhtree import BVHTree

from .evaluation import bake_steps, finish_steps


def barycentric(point, a, b, c):
    u, v, p = b - a, c - a, point - a
    uu, uv, vv = u.dot(u), u.dot(v), v.dot(v)
    denominator = uu * vv - uv * uv
    if denominator <= max(uu * vv, 1e-30) * 1e-12:
        return None
    y = (vv * p.dot(u) - uv * p.dot(v)) / denominator
    z = (uu * p.dot(v) - uv * p.dot(u)) / denominator
    return 1 - y - z, y, z


def pixel_shift(height, direction, normal, vertices, uvs, resolution):
    """Map h*tan(theta) into the triangle's actual (possibly anisotropic) UVs."""
    alignment = direction.dot(normal)
    if alignment <= 1e-6:
        return None
    uv_a, uv_b = uvs[1] - uvs[0], uvs[2] - uvs[0]
    if abs(uv_a.x * uv_b.y - uv_a.y * uv_b.x) <= 1e-12:
        return None
    offset = (direction / alignment - normal) * height
    a, b, c = vertices
    weights = barycentric(a + offset, a, b, c)
    if weights is None:
        return None
    return ((uvs[1] - uvs[0]) * weights[1] +
            (uvs[2] - uvs[0]) * weights[2]).length * resolution


def snapshot(context, obj):
    """World-space geometric averaging plus evaluated corner normals for mesh mode."""
    evaluated = obj.evaluated_get(context.evaluated_depsgraph_get())
    mesh = evaluated.to_mesh(preserve_all_data_layers=True,
                             depsgraph=context.evaluated_depsgraph_get())
    try:
        mesh.calc_loop_triangles()
        vertices = [evaluated.matrix_world @ vertex.co for vertex in mesh.vertices]
        triangles = [tuple(triangle.vertices) for triangle in mesh.loop_triangles]
        normals = []
        averaged = [Vector() for _ in vertices]
        edges = {}
        # Accumulate each polygon once at each corner. Accumulating triangles
        # overweights a quad's diagonal endpoints and biases the estimated rays.
        for polygon in mesh.polygons:
            corners = [vertices[i] for i in polygon.vertices]
            cross = sum(((corners[i] - corners[0]).cross(corners[i + 1] - corners[0])
                         for i in range(1, len(corners) - 1)), Vector())
            for vertex in polygon.vertices:
                averaged[vertex] += cross
        for index, triangle in enumerate(triangles):
            a, b, c = (vertices[i] for i in triangle)
            cross = (b - a).cross(c - a)
            normals.append(cross.normalized())
            for a, b in zip(triangle, triangle[1:] + triangle[:1]):
                edges.setdefault(tuple(sorted((a, b))), []).append(index)
        # A gentle bend is not a flat panel. Hard corners delimit planar faces.
        curved = set()
        for neighbors in edges.values():
            if len(neighbors) == 2:
                a, b = neighbors
                alignment = normals[a].dot(normals[b])
                if cos(radians(30)) < alignment < cos(radians(1)):
                    curved.update(neighbors)
            elif len(neighbors) > 2:
                curved.update(neighbors)
        uv_layer = mesh.uv_layers.active
        normal_matrix = evaluated.matrix_world.to_3x3().inverted().transposed()
        shading = [tuple((normal_matrix @ mesh.corner_normals[loop].vector).normalized()
                         for loop in triangle.loops) for triangle in mesh.loop_triangles]
        uvs = ([tuple(uv_layer.data[loop].uv.copy() for loop in triangle.loops)
                for triangle in mesh.loop_triangles] if uv_layer else None)
        return {'vertices': vertices, 'triangles': triangles, 'normals': normals,
                'averaged': [normal.normalized() for normal in averaged], 'shading': shading,
                'curved': curved, 'uvs': uvs,
                'tree': BVHTree.FromPolygons(vertices, triangles, all_triangles=True)
                if triangles else None}
    finally:
        evaluated.to_mesh_clear()


@bake_steps
def analyze_steps(context, threshold=1.0, sample_limit=256):
    """Use assigned highs, not guessed bolt identities; bounded samples can miss detail."""
    from .jobs import PainterError, meshes, singular_transform
    from .matching import resolve_steps, surface_samples, targets
    from .texture_sets import entries

    if context.mode != 'OBJECT':
        raise PainterError('Switch to Object Mode before analyzing projection')
    if threshold <= 0 or sample_limit < 1:
        raise PainterError('Projection threshold and sample limit must be positive')
    issues, checked, raised, skipped = [], 0, 0, 0
    for entry in entries(context.scene.mbt_painter):
        lows, highs = meshes(entry.low_collection), meshes(entry.high_collection)
        if not lows or not highs:
            raise PainterError('Choose non-empty low/high collections for projection analysis')
        for obj in lows + highs:
            if singular_transform(obj.matrix_world):
                raise PainterError(obj.name + ': singular transform')
        warnings = []
        _, pairs = yield from resolve_steps(context, lows, highs, warnings=warnings)
        issues.extend(warnings)
        surfaces = {}
        for low in lows:
            yield 'Analyzing receiving surface: ' + low.name
            surfaces[low] = snapshot(context, low)
        mode = getattr(entry, 'projection_normals', 'AVERAGED')
        for high in highs:
            yield 'Sampling projection detail: ' + high.name
            evaluated = high.evaluated_get(context.evaluated_depsgraph_get())
            mesh = evaluated.to_mesh()
            try:
                points = surface_samples(mesh, evaluated.matrix_world, limit=sample_limit)
            finally:
                evaluated.to_mesh_clear()
            maximum, affected, ambiguous = 0.0, 0, 0
            skipped_before = skipped
            for index, point in enumerate(points):
                if index % 64 == 0:
                    yield 'Estimating projection: ' + high.name
                candidates = []
                for low in targets(pairs[high]):
                    surface = surfaces[low]
                    if surface['tree'] is not None:
                        hit, _, triangle, distance = surface['tree'].find_nearest(point)
                        if hit is not None:
                            candidates.append((distance, low, surface, hit, triangle))
                candidates.sort(key=lambda item: item[0])
                if not candidates:
                    skipped += 1
                    continue
                distance, low, surface, hit, triangle = candidates[0]
                if len(candidates) > 1 and candidates[1][0] <= distance * 1.05 + 1e-8:
                    ambiguous += 1
                    skipped += 1
                    continue
                if triangle in surface['curved'] or surface['uvs'] is None:
                    skipped += 1
                    continue
                indices = surface['triangles'][triangle]
                vertices = tuple(surface['vertices'][i] for i in indices)
                weights = barycentric(point, *vertices)
                # Nearest-edge hits do not establish a perpendicular receiving surface.
                if weights is None or min(weights) < -1e-5:
                    skipped += 1
                    continue
                normal = surface['normals'][triangle]
                height = (point - hit).dot(normal)
                if height <= 1e-6 * max(1e-12, (vertices[1] - vertices[0]).length,
                                       (vertices[2] - vertices[0]).length):
                    checked += 1
                    continue
                raised += 1
                corner_normals = (surface['shading'][triangle] if mode == 'FACE' else
                                  tuple(surface['averaged'][i] for i in indices))
                direction = sum((value * weight for value, weight in zip(corner_normals, weights)), Vector()).normalized()
                shift = pixel_shift(height, direction, normal, vertices,
                                    surface['uvs'][triangle], int(entry.resolution))
                if shift is None:
                    skipped += 1
                    continue
                checked += 1
                maximum = max(maximum, shift)
                affected += shift > threshold
            unassessed = skipped - skipped_before
            if affected or unassessed:
                reason = (f'Estimated {"mesh" if mode == "FACE" else "averaged"}-normal skew up to {maximum:.2f} px; '
                          f'{affected}/{len(points)} samples above {threshold:g} px. '
                          'Approximation, not Painter ray verification; no correction applied.')
                if ambiguous:
                    reason += f' {ambiguous} samples have ambiguous receiving surfaces.'
                if unassessed:
                    reason += (f' {unassessed} samples unassessed (curvature, missing UVs, '
                               'boundary/ambiguous hits or invalid projection); not certified safe.')
                issues.append({'object': high.name, 'reason': reason, 'blocking': False,
                               'kind': 'PROJECTION_ESTIMATE', 'max_pixels': maximum, 'projection_normals': mode,
                               'affected_samples': affected, 'ambiguous_samples': ambiguous,
                               'unassessed_samples': unassessed,
                               'targets': [low.name for low in targets(pairs[high])]})
    return {'issues': issues, 'checked_samples': checked, 'raised_samples': raised,
            'skipped_samples': skipped, 'threshold_pixels': threshold,
            'model': 'area-weighted polygon averaging or evaluated corner mesh normals; bounded high surface samples',
            'correction_applied': False}


def analyze(context, threshold=1.0, sample_limit=256):
    return finish_steps(analyze_steps(context, threshold, sample_limit))