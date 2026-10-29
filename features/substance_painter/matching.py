"""Conservative bake grouping; source names and geometry are never changed."""
import re
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from .evaluation import bake_steps, finish_steps


def stem(name):
    return re.split(r'[_.-](?:low|high)(?:[_.-]|$)', name, maxsplit=1, flags=re.I)[0]


def spatial_samples(mesh, matrix, limit=128):
    """Cover the vertex array, then choose spatially separated world-space samples."""
    count = len(mesh.vertices)
    pool_size = min(count, 1024)
    points = [matrix @ mesh.vertices[i * (count - 1) // max(pool_size - 1, 1)].co
              for i in range(pool_size)]
    if len(points) <= limit:
        return points
    selected = [points[0]]
    distances = [float('inf')] * len(points)
    for _ in range(limit - 1):
        last = selected[-1]
        distances = [min(distance, (point - last).length_squared)
                     for point, distance in zip(points, distances)]
        index = max(range(len(points)), key=distances.__getitem__)
        if distances[index] == 0:
            break
        selected.append(points[index])
    return selected


def resolve_sets(context):
    """Validate matches in the same texture-set scope used by job preparation."""
    from .jobs import meshes, ValidationIssues
    from .texture_sets import entries
    issues = []
    for entry in entries(context.scene.mbt_painter):
        try:
            resolve(context, meshes(entry.low_collection), meshes(entry.high_collection))
        except ValidationIssues as error:
            issues.extend(error.issues)
    if issues:
        raise ValidationIssues(issues)


def targets(value):
    return value if isinstance(value, tuple) else (value,)


def resolve(context, low, high):
    return finish_steps(resolve_steps(context, low, high))


@bake_steps
def resolve_steps(context, low, high):
    from .jobs import PainterError, ValidationIssues, safe_name
    keys = {obj: obj.mbt_bake_group.strip() or stem(obj.name) for obj in low}
    groups = {obj: 'MBTBake_' + safe_name(keys[obj]) for obj in low}
    if len(set(groups.values())) != len(set(keys.values())):
        raise PainterError('Bake group names collide after sanitization')
    result = {}
    surfaces = {}
    members_by_group = {group: tuple(obj for obj in low if groups[obj] == group)
                        for group in dict.fromkeys(groups.values())}
    issues = []

    def surface(obj, need_tree=True):
        cache_key = (obj, need_tree)
        if cache_key not in surfaces:
            depsgraph = context.evaluated_depsgraph_get()
            evaluated = obj.evaluated_get(depsgraph)
            mesh = evaluated.to_mesh()
            try:
                if not mesh.vertices or not mesh.polygons:
                    raise PainterError(f'{obj.name}: evaluated mesh has no surface for matching')
                if need_tree:
                    vertices = [evaluated.matrix_world @ v.co for v in mesh.vertices]
                    tree = BVHTree.FromPolygons(vertices, [list(p.vertices) for p in mesh.polygons])
                else:
                    tree = None
                    vertices = [evaluated.matrix_world @ Vector(corner) for corner in evaluated.bound_box]
                minimum = Vector(tuple(min(v[i] for v in vertices) for i in range(3)))
                maximum = Vector(tuple(max(v[i] for v in vertices) for i in range(3)))
                samples = spatial_samples(mesh, evaluated.matrix_world) if not need_tree else []
                surfaces[cache_key] = tree, minimum, maximum, samples
            finally:
                evaluated.to_mesh_clear()
        return surfaces[cache_key]

    for obj in high:
        yield 'Matching high mesh: ' + obj.name
        if obj.mbt_bake_group.strip():
            named = tuple(target for target in low if keys[target] == obj.mbt_bake_group.strip())
            if not named:
                raise PainterError(f'{obj.name}: Bake Group has no low meshes')
            result[obj] = named[0] if len(named) == 1 else named
            continue
        explicit = obj.mbt_bake_target
        if explicit is not None:
            if explicit not in groups:
                raise PainterError(f'{obj.name}: Bake Target is not in the low collection')
            members = tuple(target for target in low if groups[target] == groups[explicit])
            result[obj] = members[0] if len(members) == 1 else members
            continue
        named = [target for target in low if stem(target.name) == stem(obj.name)]
        if named:
            if len({groups[target] for target in named}) != 1:
                raise PainterError(f'{obj.name}: low name matches span different Bake Groups; set Bake Group explicitly')
            members = tuple(target for target in low if groups[target] == groups[named[0]])
            result[obj] = members[0] if len(members) == 1 else members
            continue
        _, hmin, hmax, samples = surface(obj, need_tree=False)
        scale = max((hmax - hmin).length, 1e-6)
        scores = []
        diagnostics = []
        for group, members in members_by_group.items():
            yield 'Surface matching: ' + obj.name + ' / ' + keys[members[0]]
            parts = []
            for target in members:
                yield 'Evaluating low surface: ' + target.name
                parts.append(surface(target))
            minimum = Vector(tuple(min(part[1][i] for part in parts) for i in range(3)))
            maximum = Vector(tuple(max(part[2][i] for part in parts) for i in range(3)))
            diagonal = (maximum - minimum).length
            tolerance = max(min(diagonal, scale) * 0.1, 1e-6)
            if any(hmax[i] < minimum[i] - tolerance or hmin[i] > maximum[i] + tolerance
                   for i in range(3)):
                diagnostics.append((0, keys[members[0]] + ': bounds too far apart'))
                continue
            distances = []
            for point in samples:
                nearest = [part[0].find_nearest(point)[3] for part in parts]
                nearest = [distance for distance in nearest if distance is not None]
                if nearest:
                    distances.append(min(nearest))
            if not distances or len(distances) != len(samples):
                continue
            coverage = sum(distance <= tolerance for distance in distances) / len(distances)
            diagnostics.append((coverage, f'{keys[members[0]]}: {coverage:.0%} surface coverage'))
            if coverage < 0.9:
                continue
            distances.sort()
            score = (distances[len(distances) // 2] + distances[int((len(distances) - 1) * 0.9)]) / (2 * scale)
            scores.append((score, group))
        scores.sort(key=lambda item: item[0])
        if not scores:
            detail = '; '.join(text for _, text in sorted(diagnostics, key=lambda item: item[0], reverse=True)[:3])
            reason = 'No nearby low group with sufficient surface coverage (requires 90%). ' + detail
        elif len(scores) > 1 and scores[1][0] <= scores[0][0] * 2 + 0.01:
            detail = ', '.join(f'{keys[members_by_group[group][0]]} (score {score:.4g})'
                               for score, group in scores[:3])
            reason = 'ambiguous low groups: ' + detail
        else:
            reason = ''
        if reason:
            issues.append({'object': obj.name, 'reason': reason + '. Set Bake Target or Bake Group.', 'blocking': True})
            continue
        members = members_by_group[scores[0][1]]
        result[obj] = members[0] if len(members) == 1 else members
    if issues:
        raise ValidationIssues(issues)
    missing = [obj.name for obj in low if not any(obj in targets(value) for value in result.values())]
    if missing:
        raise PainterError('No high mesh matched: ' + ', '.join(missing))
    names = {}
    for group in dict.fromkeys(groups.values()):
        for index, obj in enumerate(obj for obj in low if groups[obj] == group):
            names[obj] = group + '_low' + (f'_{index:03d}' if index else '')
        for index, obj in enumerate(obj for obj in high if groups[targets(result[obj])[0]] == group):
            names[obj] = group + '_high' + (f'_{index:03d}' if index else '')
    return names, result