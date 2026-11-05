"""Conservative bake grouping; source names and geometry are never changed."""
import re
from bisect import bisect_left
from math import sqrt
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from .evaluation import bake_steps, finish_steps


def stem(name):
    # Only a trailing role (plus Blender/numeric duplicate suffix) is structural.
    # An interior word such as vehicle_low_panel is part of the asset name.
    return re.sub(r'[_.-](?:low|high)(?:[_.-]\d+)*$', '', name, flags=re.I)


def group_name(key):
    """Avoid Painter interpreting interior _low/_high tokens as role delimiters."""
    from .jobs import safe_name
    return 'MBTBake_' + re.sub(r'_(low|high)(?=_|$)', r'-\1', safe_name(key), flags=re.I)


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


def surface_samples(mesh, matrix, limit=128):
    """Area-weighted triangle samples, independent of sculpt vertex density.

    Transform normals for non-uniform scale; the common determinant factor
    cancels when selecting triangles by relative world-space area.
    """
    mesh.calc_loop_triangles()
    normal_matrix = matrix.to_3x3().inverted().transposed()
    cumulative = []
    total = 0.0
    for triangle in mesh.loop_triangles:
        total += triangle.area * (normal_matrix @ triangle.normal).length
        cumulative.append(total)
    if total <= 0:
        return []
    points = []
    for index in range(limit):
        triangle = mesh.loop_triangles[bisect_left(cumulative, total * (index + 0.5) / limit)]
        a, b, c = (mesh.vertices[vertex].co for vertex in triangle.vertices)
        u = sqrt(((index + 0.5) * 0.7548776662466927) % 1)
        v = ((index + 0.5) * 0.5698402909980532) % 1
        points.append(matrix @ ((1 - u) * a + u * (1 - v) * b + u * v * c))
    return points


def distance_score(distances, tolerance, scale):
    """Rank correspondence, not bakeability; tolerate minority sculpt details."""
    if not distances:
        return None
    distances = sorted(distances)
    median = distances[len(distances) // 2]
    upper = distances[int((len(distances) - 1) * 0.75)]
    if median > tolerance or upper > tolerance * 2:
        return None
    return (median + upper) / (2 * scale)


def ambiguous_scores(best, second):
    # The former +0.01 floor overwhelmed small scores, even a tenfold winner.
    return second <= best * 1.25 + 1e-5


def targets(value):
    return value if isinstance(value, tuple) else (value,)


def resolve(context, low, high, warnings=None):
    return finish_steps(resolve_steps(context, low, high, warnings=warnings))


@bake_steps
def resolve_steps(context, low, high, warnings=None):
    from .jobs import PainterError, ValidationIssues
    keys = {obj: obj.mbt_bake_group.strip() or stem(obj.name) for obj in low}
    groups = {obj: group_name(keys[obj]) for obj in low}
    if len(set(groups.values())) != len(set(keys.values())):
        raise PainterError('Bake group names collide after sanitization')
    result = {}
    surfaces = {}
    members_by_group = {group: tuple(obj for obj in low if groups[obj] == group)
                        for group in dict.fromkeys(groups.values())}
    issues = []

    def warn(obj, reason, **details):
        entry = {'object': obj.name, 'reason': reason, 'blocking': False, **details}
        if warnings is not None:
            warnings.append(entry)

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
                    mesh.calc_loop_triangles()
                    tree = BVHTree.FromPolygons(vertices, [tuple(t.vertices) for t in mesh.loop_triangles], all_triangles=True)
                else:
                    tree = None
                    vertices = [evaluated.matrix_world @ Vector(corner) for corner in evaluated.bound_box]
                minimum = Vector(tuple(min(v[i] for v in vertices) for i in range(3)))
                maximum = Vector(tuple(max(v[i] for v in vertices) for i in range(3)))
                samples = surface_samples(mesh, evaluated.matrix_world) if not need_tree else []
                probes = spatial_samples(mesh, evaluated.matrix_world, limit=16) if not need_tree else []
                surfaces[cache_key] = tree, minimum, maximum, samples, probes
            finally:
                evaluated.to_mesh_clear()
        return surfaces[cache_key]

    for obj in high:
        yield 'Matching high mesh: ' + obj.name
        if obj.mbt_bake_group.strip():
            named = tuple(target for target in low if keys[target] == obj.mbt_bake_group.strip())
            if not named:
                if warnings is None:
                    raise PainterError(f'{obj.name}: Bake Group has no low meshes')
                warn(obj, 'Bake Group has no low meshes; using automatic matching.')
            else:
                result[obj] = named[0] if len(named) == 1 else named
                continue
        explicit = obj.mbt_bake_target
        # Auto suggestions are not manual overrides. Keep the visible pointer for
        # compatibility, but recompute it after geometry/name changes on each bake.
        if explicit is not None and explicit == obj.mbt_bake_auto_target:
            explicit = None
        if explicit is not None:
            if explicit not in groups:
                if warnings is None:
                    raise PainterError(f'{obj.name}: Bake Target is not in the low collection')
                warn(obj, 'Bake Target is not in the low collection; using automatic matching.')
            else:
                members = tuple(target for target in low if groups[target] == groups[explicit])
                result[obj] = members[0] if len(members) == 1 else members
                continue
        named = [target for target in low if stem(target.name) == stem(obj.name)]
        if named:
            if len({groups[target] for target in named}) != 1:
                if warnings is None:
                    raise PainterError(f'{obj.name}: low name matches span different Bake Groups; set Bake Group explicitly')
                warn(obj, 'Low name matches span different Bake Groups; using surface matching.')
            else:
                members = tuple(target for target in low if groups[target] == groups[named[0]])
                result[obj] = members[0] if len(members) == 1 else members
                continue
        _, hmin, hmax, samples, probes = surface(obj, need_tree=False)
        scale = max((hmax - hmin).length, 1e-6)
        scores = []
        diagnostics = []
        fallback = []
        evidence = {}
        for group, members in members_by_group.items():
            yield 'Surface matching: ' + obj.name + ' / ' + keys[members[0]]
            parts = []
            for target in members:
                if (target, True) not in surfaces:
                    yield 'Evaluating low surface: ' + target.name
                parts.append(surface(target))
            minimum = Vector(tuple(min(part[1][i] for part in parts) for i in range(3)))
            maximum = Vector(tuple(max(part[2][i] for part in parts) for i in range(3)))
            diagonal = (maximum - minimum).length
            tolerance = max(min(diagonal, scale) * 0.1, 1e-6)
            distances = []
            for point in samples:
                nearest = [part[0].find_nearest(point)[3] for part in parts]
                nearest = [distance for distance in nearest if distance is not None]
                if nearest:
                    distances.append(min(nearest))
            # Even a distant fallback uses surface evidence, not box centers.
            if distances:
                ordered = sorted(distances)
                fallback.append((ordered[len(ordered) // 2], group))
                coverage = sum(distance <= tolerance for distance in distances) / len(distances)
                evidence[group] = {'coverage': coverage, 'tolerance': tolerance,
                                   'sample_count': len(distances)}
            if any(hmax[i] < minimum[i] - tolerance or hmin[i] > maximum[i] + tolerance
                   for i in range(3)):
                diagnostics.append((0, keys[members[0]] + ': bounds too far apart'))
                continue
            if not distances or len(distances) != len(samples):
                continue
            coverage = sum(distance <= tolerance for distance in distances) / len(distances)
            diagnostics.append((coverage, f'{keys[members[0]]}: {coverage:.0%} surface coverage'))
            score = distance_score(distances, tolerance, scale)
            if score is not None:
                scores.append((score, group))
        scores.sort(key=lambda item: item[0])
        # Resolve close decisions with more area samples before declaring a tie.
        if len(scores) > 1 and ambiguous_scores(scores[0][0], scores[1][0]):
            yield 'Refining ambiguous surface match: ' + obj.name
            evaluated = obj.evaluated_get(context.evaluated_depsgraph_get())
            mesh = evaluated.to_mesh()
            try:
                refined = surface_samples(mesh, evaluated.matrix_world, limit=512)
            finally:
                evaluated.to_mesh_clear()
            rescored = []
            for _, group in scores:
                parts = [surface(target) for target in members_by_group[group]]
                distances = [min(part[0].find_nearest(point)[3] for part in parts) for point in refined]
                tolerance = evidence[group]['tolerance']
                score = distance_score(distances, tolerance, scale)
                if score is not None:
                    rescored.append((score, group))
                evidence[group].update(coverage=sum(d <= tolerance for d in distances) / max(1, len(distances)),
                                       sample_count=len(distances))
            scores = sorted(rescored, key=lambda item: item[0])
        candidates = [{'group': keys[members_by_group[group][0]],
                       'targets': [target.name for target in members_by_group[group]],
                       'score': score, **evidence[group]} for score, group in scores[:3]]
        if not scores:
            detail = '; '.join(text for _, text in sorted(diagnostics, key=lambda item: item[0], reverse=True)[:3])
            reason = 'Automatic assignment unresolved (not a bakeability test). ' + detail
        elif len(scores) > 1 and ambiguous_scores(scores[0][0], scores[1][0]):
            detail = ', '.join(f'{keys[members_by_group[group][0]]} (score {score:.4g})'
                               for score, group in scores[:3])
            reason = 'ambiguous low groups: ' + detail
        else:
            reason = ''
        if reason:
            if warnings is None:
                issues.append({'object': obj.name, 'reason': reason + '. Set Bake Target or Bake Group.',
                               'blocking': True, 'candidates': candidates,
                               'targets': [target for candidate in candidates for target in candidate['targets']]})
                continue
            if not scores and not fallback:
                raise PainterError(f'{obj.name}: evaluated mesh has no usable surface samples')
            chosen = scores[0][1] if scores else min(fallback, key=lambda item: item[0])[1]
            members = members_by_group[chosen]
            warn(obj, reason + '. Best-effort assignment: ' + ', '.join(target.name for target in members) +
                 '. Inspect the bake; set Bake Target or Bake Group to correct it.',
                 assignment='FALLBACK', targets=[target.name for target in members], candidates=candidates)
            result[obj] = members[0] if len(members) == 1 else members
            continue
        members = members_by_group[scores[0][1]]
        result[obj] = members[0] if len(members) == 1 else members
        chosen = scores[0][1]
        parts = [surface(target) for target in members]
        tolerance = evidence[chosen]['tolerance']
        distant = sum(min(part[0].find_nearest(point)[3] for part in parts) > tolerance * 2 for point in probes)
        if evidence[chosen]['coverage'] < 0.9 or distant:
            warn(obj, 'Surface assignment has unmatched detail or spatial regions. This is not a bakeability test; '
                 'inspect projection distances and the assigned group.', assignment='SURFACE',
                 targets=[target.name for target in members], candidates=candidates,
                 distant_probes=distant, **evidence[chosen])
    if issues:
        raise ValidationIssues(issues)
    missing = [obj.name for obj in low if not any(obj in targets(value) for value in result.values())]
    if missing:
        if warnings is None:
            raise ValidationIssues([{'object': name, 'reason': 'No high mesh matched; set Bake Target or Bake Group.',
                                     'blocking': True} for name in missing])
        for name in missing:
            warnings.append({'object': name, 'reason': 'No high mesh matched; this low may bake without high-poly detail.',
                             'blocking': False})
    names = {}
    for group in dict.fromkeys(groups.values()):
        for index, obj in enumerate(obj for obj in low if groups[obj] == group):
            names[obj] = group + '_low' + (f'_{index:03d}' if index else '')
        for index, obj in enumerate(obj for obj in high if groups[targets(result[obj])[0]] == group):
            names[obj] = group + '_high' + (f'_{index:03d}' if index else '')
    return names, result