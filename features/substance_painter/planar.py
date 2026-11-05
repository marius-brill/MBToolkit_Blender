"""Conservative world-space receiving patches. No geometry edits or bake claims."""
from math import cos, isfinite, radians

from mathutils import Vector


def receiving_patches(vertices, polygons, angle_degrees=.5, relative_tolerance=1e-5):
    """Group edge-connected coplanar polygons against a fixed seed plane.

    Geometric edges only: UV seams and triangulation diagonals do not split a
    patch. Open/hard/nonmanifold edges are protected. Returned polygon IDs refer
    to this exact snapshot, not necessarily the editable source mesh.
    """
    if not 0 <= angle_degrees < 30 or not isfinite(relative_tolerance) or relative_tolerance < 0:
        raise ValueError('Invalid planar patch tolerances')
    vertices = [Vector(co) for co in vertices]
    if any(not isfinite(component) for vertex in vertices for component in vertex):
        raise ValueError('Nonfinite receiving geometry')
    polygons = [tuple(face) for face in polygons]
    if not vertices:
        return {'patches': [], 'unassessed_faces': list(range(len(polygons)))}
    scale = (Vector(tuple(max(v[a] for v in vertices) for a in range(3))) -
             Vector(tuple(min(v[a] for v in vertices) for a in range(3)))).length
    tolerance = scale * relative_tolerance
    alignment = cos(radians(angle_degrees))
    faces, edges, invalid = {}, {}, set()
    for index, face in enumerate(polygons):
        if len(face) < 3 or len(set(face)) != len(face) or any(i < 0 or i >= len(vertices) for i in face):
            invalid.add(index)
            continue
        points = [vertices[i] for i in face]
        cross = sum(((points[i] - points[0]).cross(points[i + 1] - points[0])
                     for i in range(1, len(points) - 1)), Vector())
        if cross.length <= scale * scale * 1e-12:
            invalid.add(index)
            continue
        normal = cross.normalized()
        center = sum(points, Vector()) / len(points)
        if max(abs((point - center).dot(normal)) for point in points) > tolerance:
            invalid.add(index)
            continue
        faces[index] = (normal, center, cross.length / 2)
        for a, b in zip(face, face[1:] + face[:1]):
            edges.setdefault(tuple(sorted((a, b))), []).append(index)
    # Nonmanifold receiving faces are deliberately not candidates for correction.
    invalid.update(face for adjacent in edges.values() if len(adjacent) > 2 for face in adjacent)
    adjacency = {index: set() for index in faces if index not in invalid}
    for adjacent in edges.values():
        if len(adjacent) == 2 and all(face in adjacency for face in adjacent):
            a, b = adjacent
            adjacency[a].add(b)
            adjacency[b].add(a)
    remaining = set(adjacency)
    patches = []
    while remaining:
        seed = min(remaining)
        normal, origin, _ = faces[seed]
        pending, members = [seed], set()
        while pending:
            face = pending.pop()
            if face not in remaining:
                continue
            candidate_normal = faces[face][0]
            if face != seed and candidate_normal.dot(normal) < alignment:
                continue
            if max(abs((vertices[i] - origin).dot(normal)) for i in polygons[face]) > tolerance:
                continue
            remaining.remove(face)
            members.add(face)
            pending.extend(sorted(adjacency[face] - members, reverse=True))
        area = sum(faces[face][2] for face in members)
        fitted_normal = sum((faces[face][0] * faces[face][2] for face in members), Vector()).normalized()
        center = sum((faces[face][1] * faces[face][2] for face in members), Vector()) / area
        boundary = sorted(edge for edge, adjacent in edges.items()
                          if any(face in members for face in adjacent) and
                          (len(adjacent) != 2 or not all(face in members for face in adjacent)))
        patches.append({'faces': sorted(members), 'normal': tuple(fitted_normal), 'origin': tuple(center),
                        'area': area, 'boundary_edges': boundary,
                        'max_deviation': max(abs((vertices[i] - center).dot(fitted_normal))
                                             for face in members for i in polygons[face]),
                        'tolerance': tolerance})
    return {'patches': patches, 'unassessed_faces': sorted(invalid)}


def boundary_distance(point, vertices, boundary_edges):
    """World-space distance to a protected geometric segment; no UV dependency."""
    point = Vector(point)
    best = float('inf')
    for i, j in boundary_edges:
        a, b = Vector(vertices[i]), Vector(vertices[j])
        edge = b - a
        t = max(0.0, min(1.0, (point - a).dot(edge) / edge.length_squared)) if edge.length_squared else 0
        best = min(best, (point - (a + edge * t)).length)
    return best