"""Conservative bake grouping; source names and geometry are never changed."""
import re
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from .evaluation import bake_steps, finish_steps


def stem(name):
    return re.split(r'_(?:low|high)(?:_|\.|$)', name, maxsplit=1, flags=re.I)[0]


def targets(value):
    return value if isinstance(value, tuple) else (value,)


def resolve(context, low, high):
    return finish_steps(resolve_steps(context, low, high))


@bake_steps
def resolve_steps(context, low, high):
    from .jobs import PainterError, safe_name
    keys = {obj: obj.mbt_bake_group.strip() or stem(obj.name) for obj in low}
    groups = {obj: 'MBTBake_' + safe_name(keys[obj]) for obj in low}
    if len(set(groups.values())) != len(set(keys.values())):
        raise PainterError('Bake group names collide after sanitization')
    result = {}
    surfaces = {}

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
                step = max(1, len(mesh.vertices) // 128)
                samples = [evaluated.matrix_world @ mesh.vertices[i].co
                           for i in range(0, len(mesh.vertices), step)][:128]
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
        scores = []
        for target in low:
            yield 'Surface matching: ' + obj.name + ' / ' + target.name
            tree, minimum, maximum, _ = surface(target)
            diagonal = (maximum - minimum).length
            tolerance = max(diagonal * 0.1, 1e-6)
            if any(hmax[i] < minimum[i] - tolerance or hmin[i] > maximum[i] + tolerance
                   for i in range(3)):
                continue
            distances = [tree.find_nearest(point)[3] for point in samples]
            if not distances or any(distance is None for distance in distances):
                continue
            if sum(distance <= tolerance for distance in distances) / len(distances) < 0.9:
                continue
            scores.append((sum(distances) / len(distances) / max(diagonal, 1e-6), target))
        scores.sort(key=lambda item: item[0])
        if not scores or (len(scores) > 1 and scores[1][0] <= scores[0][0] * 2 + 0.01):
            raise PainterError(f'{obj.name}: ambiguous or missing low match. Select this high mesh and set Bake Target')
        members = tuple(target for target in low if groups[target] == groups[scores[0][1]])
        result[obj] = members[0] if len(members) == 1 else members
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