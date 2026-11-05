"""Conservative signed surface-reach estimates, not a ray-coverage guarantee."""
from math import isfinite

from mathutils import Vector
from mathutils.bvhtree import BVHTree

from .evaluation import bake_steps


@bake_steps
def estimate_steps(context, entries, pairs):
    from .jobs import PainterError, meshes
    from .matching import targets

    results = {}
    for entry in entries:
        if not entry.auto_distances:
            continue
        lows = meshes(entry.low_collection)
        surfaces = {}
        bounds = []
        for obj in lows:
            yield 'Measuring cage receiver: ' + obj.name
            evaluated = obj.evaluated_get(context.evaluated_depsgraph_get())
            mesh = evaluated.to_mesh()
            try:
                vertices = [evaluated.matrix_world @ vertex.co for vertex in mesh.vertices]
                mesh.calc_loop_triangles()
                triangles = [tuple(triangle.vertices) for triangle in mesh.loop_triangles]
                if not vertices or not triangles or any(not isfinite(c) for v in vertices for c in v):
                    raise PainterError(obj.name + ': invalid surface for automatic cage distances')
                surfaces[obj] = BVHTree.FromPolygons(vertices, triangles, all_triangles=True)
                bounds.extend((Vector(tuple(min(v[i] for v in vertices) for i in range(3))),
                               Vector(tuple(max(v[i] for v in vertices) for i in range(3)))))
            finally:
                evaluated.to_mesh_clear()
        front = rear = 0.0
        ambiguous = 0
        for obj in meshes(entry.high_collection):
            yield 'Measuring cage detail: ' + obj.name
            receivers = targets(pairs[obj]) if obj in pairs else tuple(lows)
            evaluated = obj.evaluated_get(context.evaluated_depsgraph_get())
            mesh = evaluated.to_mesh()
            try:
                # All vertices preserve thin protrusions that bounded sampling can miss.
                # Triangle centers additionally probe interiors of large/highly concave faces.
                mesh.calc_loop_triangles()
                def points():
                    for vertex in mesh.vertices:
                        yield evaluated.matrix_world @ vertex.co
                    for triangle in mesh.loop_triangles:
                        yield evaluated.matrix_world @ (sum(
                            (mesh.vertices[i].co for i in triangle.vertices), Vector()) / 3)

                for index, point in enumerate(points()):
                    if index and index % 8192 == 0:
                        yield 'Measuring cage detail: ' + obj.name + f' ({index} samples)'
                    if not all(isfinite(c) for c in point):
                        raise PainterError(obj.name + ': nonfinite geometry in cage estimate')
                    hits = [surfaces[low].find_nearest(point) for low in receivers]
                    hits = sorted((hit for hit in hits if hit[0] is not None), key=lambda hit: hit[3])
                    if not hits:
                        raise PainterError(obj.name + ': no receiving surface for cage estimate')
                    location, normal, _, distance = hits[0]
                    if len(hits) > 1 and hits[1][3] <= distance * 1.05 + 1e-9:
                        ambiguous += 1
                        front, rear = max(front, distance), max(rear, distance)
                    elif (point - location).dot(normal) >= 0:
                        front = max(front, distance)
                    else:
                        rear = max(rear, distance)
            finally:
                evaluated.to_mesh_clear()
        minimum = Vector(tuple(min(v[i] for v in bounds) for i in range(3)))
        maximum = Vector(tuple(max(v[i] for v in bounds) for i in range(3)))
        margin = max((maximum - minimum).length * 0.001, 1e-8)
        # FBX exporter applies Blender scene units as centimeters, including NONE.
        scale = 100 * (context.scene.unit_settings.scale_length
                       if context.scene.unit_settings.system != 'NONE' else 1)
        results[entry.as_pointer()] = {
            'front_distance': (front * 1.1 + margin) * scale,
            'rear_distance': (rear * 1.1 + margin) * scale,
            'relative_distance': False,
            'distance_estimate': {'method': 'signed nearest surface; vertices and triangle centers',
                                  'ambiguous_samples': ambiguous,
                                  'coverage_guaranteed': False},
        }
    return results


def apply_results(settings, entries, results):
    """Publish only after preparation succeeds, outside staged input guards."""
    from . import settings as properties
    properties._syncing = True
    try:
        for entry in entries:
            values = results.get(entry.as_pointer())
            if values:
                for field in ('front_distance', 'rear_distance', 'relative_distance'):
                    setattr(entry, field, values[field])
        if settings.texture_sets:
            active = settings.texture_sets[settings.active_texture_set]
            for field in ('front_distance', 'rear_distance', 'relative_distance'):
                setattr(settings, field, getattr(active, field))
    finally:
        properties._syncing = False