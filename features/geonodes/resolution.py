"""Bounded local-space feature analysis and sampled remesh acceptance checks."""
import math

import bmesh
from mathutils.bvhtree import BVHTree

from . import resolution_nodes


def shape_voxel(bm, surface, diagonal, crease_angle=50.0):
    """Mirror the live graph's weighted curvature/wall policy for checked jobs.

    No minimum-edge rule or triangle target. The floor is a maximum sampling-work
    allowance, so very small features may require explicit manual resolution.
    """
    epsilon = max(diagonal * 1e-6, 1e-10)
    area = sum(face.calc_area() for face in bm.faces)
    weight_sum = inverse_sum = 0.0
    for edge in bm.edges:
        if len(edge.link_faces) != 2:
            continue
        angle = edge.calc_face_angle(0)
        if not 0.01 < angle < math.radians(min(crease_angle, 60)):
            continue
        length = edge.calc_length()
        weight = length * angle
        transverse_area = sum(face.calc_area() for face in edge.link_faces) / 2
        radius = transverse_area / max(weight, 1e-20)
        weight_sum += weight
        inverse_sum += weight / max(radius, epsilon)
    baseline = diagonal / resolution_nodes.DIMENSION_SAMPLES
    curvature = weight_sum / max(inverse_sum, 1e-20) / resolution_nodes.CURVATURE_SAMPLES if weight_sum else baseline
    candidates = {'dimensions': baseline, 'curvature': curvature}
    for direction, label in ((-1, 'wall thickness'), (1, 'opposing gap')):
        selected_area = inverse_distance = 0.0
        for face in bm.faces:
            ray_direction = face.normal * direction
            hit, normal, index, distance = surface.ray_cast(
                face.calc_center_median() + ray_direction * epsilon, ray_direction, diagonal)
            if hit is not None and face.normal.dot(normal) < -0.5 and distance > epsilon * 10:
                face_area = face.calc_area()
                selected_area += face_area
                inverse_distance += face_area / max(distance + epsilon, epsilon)
        candidates[label] = selected_area / max(inverse_distance, 1e-20) / resolution_nodes.THICKNESS_SAMPLES if selected_area else baseline
    driver = min(candidates, key=candidates.get)
    floor = max(diagonal / 4096, math.sqrt(area / resolution_nodes.MAX_SURFACE_SAMPLES))
    limited = candidates[driver] < floor
    return max(candidates[driver], floor, 1e-8), driver, candidates, limited


def tree(mesh):
    return BVHTree.FromPolygons([v.co for v in mesh.vertices],
                               [tuple(p.vertices) for p in mesh.polygons])


def boundary_report(bm):
    """Describe boundary connected groups without assuming they are fillable loops."""
    remaining = {e for e in bm.edges if e.is_boundary}
    groups = []
    while remaining:
        seed = remaining.pop()
        edges, stack = {seed}, list(seed.verts)
        vertices = set(stack)
        while stack:
            vertex = stack.pop()
            for edge in vertex.link_edges:
                if edge in remaining:
                    remaining.remove(edge)
                    edges.add(edge)
                    for other in edge.verts:
                        if other not in vertices:
                            vertices.add(other)
                            stack.append(other)
        closed = all(sum(e in edges for e in v.link_edges) == 2 for v in vertices)
        extent = math.sqrt(sum((max(v.co[i] for v in vertices) -
                                min(v.co[i] for v in vertices)) ** 2 for i in range(3)))
        groups.append(f'{len(edges)} edges, extent {extent:.6g}, {"loop" if closed else "branched"}')
    return f'{len(groups)} boundary groups: ' + '; '.join(sorted(groups)[:8])


def prepare(mesh):
    """Clean only the disposable high snapshot; never close artist boundaries."""
    if any(not math.isfinite(c) for v in mesh.vertices for c in v.co):
        raise ValueError('SOURCE: non-finite vertex coordinates')
    bm = bmesh.new()
    try:
        bm.from_mesh(mesh)
        scale = math.sqrt(sum((max((v.co[i] for v in bm.verts), default=0) -
                               min((v.co[i] for v in bm.verts), default=0)) ** 2 for i in range(3)))
        bmesh.ops.dissolve_degenerate(bm, dist=max(scale * 1e-10, 1e-12), edges=list(bm.edges))
        loose = [e for e in bm.edges if not e.link_faces]
        if loose:
            bmesh.ops.delete(bm, geom=loose, context='EDGES')
        unused = [v for v in bm.verts if not v.link_faces]
        if unused:
            bmesh.ops.delete(bm, geom=unused, context='VERTS')
        # Accept a conservative boundary-only weld only if it closes ALL openings
        # without producing nonmanifold edges. Never partially stitch a real hole.
        trial = bm.copy()
        try:
            bmesh.ops.remove_doubles(trial, verts=[v for v in trial.verts if v.is_boundary],
                                    dist=max(scale * 1e-7, 1e-12))
            if len(trial.verts) < len(bm.verts) and all(e.is_manifold for e in trial.edges):
                bm.free()
                bm = trial
                trial = None
        finally:
            if trial is not None:
                trial.free()
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        bm.to_mesh(mesh)
        mesh.update()
    finally:
        bm.free()


def analyze(mesh, detail=0.01, crease_angle=50.0):
    if not mesh.polygons or any(not math.isfinite(c) for v in mesh.vertices for c in v.co):
        raise ValueError('Source has empty or non-finite geometry')
    coords = [v.co.copy() for v in mesh.vertices]
    extents = [max(v[i] for v in coords) - min(v[i] for v in coords) for i in range(3)]
    diagonal = math.sqrt(sum(v * v for v in extents))
    if diagonal <= 0:
        raise ValueError('Source has no spatial extent')
    bm = bmesh.new()
    try:
        bm.from_mesh(mesh)
        boundaries = sum(e.is_boundary for e in bm.edges)
        invalid = sum(not e.is_manifold and not e.is_boundary for e in bm.edges)
        if boundaries or invalid:
            raise ValueError(f'SOURCE: {boundaries} boundary edges, {invalid} nonmanifold edges; '
                             f'{boundary_report(bm)}. Remesh requires closed solids. '
                             'Repair deliberate holes, explicitly add thickness for sheets, or disable Remesh; no automatic capping was applied')
        # Consistent normals on the disposable analysis mesh, never the artist source.
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        samples = [v.co.copy() for v in bm.verts]
        sharp = [e for e in bm.edges if e.calc_face_angle(0) > math.radians(20)]
        for edge in sharp:
            a, b = (v.co for v in edge.verts)
            samples.extend(a.lerp(b, t) for t in (0.25, 0.5, 0.75))
        lengths = [e.calc_length() for e in sharp if e.calc_length() > diagonal * 1e-7]
        surface = BVHTree.FromBMesh(bm)
        thickness = diagonal
        local_samples = []
        # A small disconnected shell must not disappear merely because it fits
        # inside the whole-object tolerance. Local per-shell bounds remain sampled.
        remaining = set(bm.verts)
        while remaining:
            seed = remaining.pop()
            shell, stack = [seed], [seed]
            while stack:
                vertex = stack.pop()
                for edge in vertex.link_edges:
                    other = edge.other_vert(vertex)
                    if other in remaining:
                        remaining.remove(other)
                        shell.append(other)
                        stack.append(other)
            shell_diagonal = math.sqrt(sum((max(v.co[i] for v in shell) -
                                            min(v.co[i] for v in shell)) ** 2 for i in range(3)))
            limit = min(diagonal * detail, shell_diagonal * detail)
            local_samples.extend((v.co.copy(), limit) for v in shell)
        # Bounded deterministic rays estimate opposing walls/gaps. This is not an
        # exhaustive medial-axis computation; the acceptance test is also sampled.
        faces = list(bm.faces)
        bm.faces.index_update()
        stride = max(1, len(faces) // 2048)
        epsilon = diagonal * 1e-6
        for face in faces[::stride]:
            center = face.calc_center_median()
            nearest, normal, source_index, unused = surface.find_nearest(center)
            if nearest is None:
                continue
            samples.append(nearest.copy())
            for direction in (normal, -normal):
                hit, hit_normal, index, distance = surface.ray_cast(nearest + direction * epsilon, direction, diagonal)
                # Opposing wall/gap only: reject adjacent faces and oblique local
                # self-hits. Keep these as acceptance constraints, not a global
                # demand for six voxels across the single smallest ray distance.
                if (hit is not None and index != source_index and distance > epsilon * 100
                        and normal.dot(hit_normal) < -0.8
                        and not set(faces[source_index].verts).intersection(faces[index].verts)):
                    thickness = min(thickness, distance)
                    limit = min(diagonal * detail, distance / 4)
                    local_samples.extend(((nearest.copy(), limit), (hit.copy(), limit)))
        tolerance = diagonal * detail
        voxel, driver, candidates, limited = shape_voxel(bm, surface, diagonal, crease_angle)
        candidates.update({'detail tolerance': tolerance / 1.5,
                           'thickness/gap': thickness / 6,
                           'sharp source edge': min(lengths, default=diagonal) / 6})
        if tolerance / 1.5 < voxel:
            voxel, driver = tolerance / 1.5, 'detail tolerance'
        return {'voxel': voxel, 'tolerance': tolerance, 'samples': samples,
                'driver': driver, 'candidates': candidates,
                'work_limited': limited,
                'local_samples': local_samples,
                'extents': extents, 'diagonal': diagonal, 'surface': surface,
                'area': sum(f.calc_area() for f in bm.faces)}
    finally:
        bm.free()


def budget(analysis, voxel, max_faces, max_work_gib=8.0):
    """Return a heuristic work estimate, not measured RAM or a face prediction.

    max_faces remains in the signature for callers; only actual evaluated face
    counts enforce that independent limit. Zero work allowance disables this guard.
    """
    if not math.isfinite(voxel) or voxel <= 0:
        raise ValueError('Automatic resolution is invalid; repair degenerate source features')
    faces = analysis['area'] / voxel ** 2
    # Estimate the sparse surface band rather than a dense box (which unfairly
    # rejects disconnected/thin meshes with large empty space between them).
    estimated_bytes = faces * 6 * 96
    estimated_gib = estimated_bytes / 1024 ** 3
    if max_work_gib > 0 and estimated_gib > max_work_gib:
        raise ValueError(f'WORK ESTIMATE: {estimated_gib:.2f} GiB exceeds configured Work Allowance {max_work_gib:g} GiB; this is not measured RAM. Raise Work Allowance if appropriate, split the source or relax detail tolerance (not Face Budget)')
    return estimated_gib


def quality(mesh, analysis):
    analysis['quality_reason'] = ''
    if not mesh.polygons:
        return False, float('inf')
    if any(not math.isfinite(c) for v in mesh.vertices for c in v.co):
        return False, float('inf')
    bm = bmesh.new()
    try:
        bm.from_mesh(mesh)
        if any(not e.is_manifold for e in bm.edges) or any(f.calc_area() <= 0 for f in bm.faces):
            return False, float('inf')
    finally:
        bm.free()
    output = tree(mesh)
    error = 0.0
    preserved = True
    worst_ratio = 0.0
    for point, limit in analysis.get('local_samples', ()):
        hit = output.find_nearest(point)
        distance = hit[3] if hit[0] is not None else float('inf')
        error = max(error, distance)
        preserved = preserved and distance <= limit
        if limit > 0 and distance / limit > worst_ratio:
            worst_ratio = distance / limit
            analysis['quality_reason'] = f'local shell/thin-feature deviation {distance:.6g}, limit {limit:.6g}'
    for point in analysis['samples']:
        hit = output.find_nearest(point)
        error = max(error, hit[3] if hit[0] is not None else float('inf'))
    # Reverse samples catch added bridges/outward distortion, not just source loss.
    stride = max(1, len(mesh.vertices) // 10000)
    for index in range(0, len(mesh.vertices), stride):
        vertex = mesh.vertices[index]
        hit = analysis['surface'].find_nearest(vertex.co)
        error = max(error, hit[3] if hit[0] is not None else float('inf'))
    if preserved:
        analysis['quality_reason'] = f'global deviation {error:.6g}, limit {analysis["tolerance"]:.6g}'
    return preserved and error <= analysis['tolerance'], error