"""Matching and UV diagnostics regressions in a disposable background Blender."""
import importlib
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon = importlib.import_module(ROOT.name)
matching = importlib.import_module(ROOT.name + '.features.substance_painter.matching')
jobs = importlib.import_module(ROOT.name + '.features.substance_painter.jobs')


def main():
    assert bpy.app.background
    addon.register()
    addon.feature_manager.sync(type('Settings', (), {'enable_substance_painter': True})())
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    ctx = bpy.context

    def cube(name, role, x=0):
        bpy.ops.mesh.primitive_cube_add(location=(x, 0, 0))
        obj = ctx.object
        obj.name = name
        bpy.ops.mbt.painter_assign(role=role)
        return obj

    a = cube('PieceA', 'LOW')
    b = cube('PieceB', 'LOW')
    high = cube('Sculpt', 'HIGH')
    a.mbt_bake_group = b.mbt_bake_group = 'Shared'
    _, pairs = matching.resolve(ctx, [a, b], [high])
    assert set(matching.targets(pairs[high])) == {a, b}
    # One high spans disconnected low pieces; distances must use the group union.
    b.location.x = 4
    ctx.view_layer.update()
    mesh = high.data
    mesh.clear_geometry()
    vertices = [tuple(obj.matrix_world @ vertex.co) for obj in (a, b) for vertex in obj.data.vertices]
    faces = [tuple(index + offset for index in face.vertices)
             for offset, obj in ((0, a), (8, b)) for face in obj.data.polygons]
    mesh.from_pydata(vertices, [], faces)
    ctx.view_layer.update()
    _, pairs = matching.resolve(ctx, [a, b], [high])
    assert set(matching.targets(pairs[high])) == {a, b}
    # Distinct identical groups really are ambiguous, and all highs are reported.
    a.mbt_bake_group = 'A'
    b.mbt_bake_group = 'B'
    b.location.x = 0
    high.data = a.data.copy()
    second = cube('AnotherSculpt', 'HIGH')
    ctx.view_layer.update()
    try:
        matching.resolve(ctx, [a, b], [high, second])
    except jobs.ValidationIssues as error:
        assert error.blocking and len(error.issues) == 2
        assert all('ambiguous low groups' in issue['reason'] for issue in error.issues)
    else:
        raise AssertionError('Distinct overlapping groups must remain ambiguous')
    second.location.x = 100
    ctx.view_layer.update()
    try:
        matching.resolve(ctx, [a], [second])
    except jobs.ValidationIssues as error:
        assert 'bounds too far apart' in str(error)
    else:
        raise AssertionError('Distant surfaces must not match')
    # Bake uses best-effort assignments while explicit diagnostics stay strict.
    warnings = []
    names, pairs = matching.resolve(ctx, [a, b], [high, second], warnings=warnings)
    assert set(names) == {a, b, high, second} and set(pairs) == {high, second}
    assert warnings and all(not issue['blocking'] for issue in warnings)
    assert any('Best-effort assignment' in issue['reason'] for issue in warnings)
    assert any('No high mesh matched' in issue['reason'] for issue in warnings)
    with TemporaryDirectory() as folder:
        settings = ctx.scene.mbt_painter
        settings.output_dir = folder
        jobs.prepare(ctx, automatic=True)
        job = jobs.read_job(settings.last_job)
        assert job['matching_issues'] and settings.matching_report
        assert all(obj.name in job['mesh_names'] for obj in (a, b, high, second))
        assert high.mbt_bake_target is None and second.mbt_bake_target is None
        assert Path(job['low_mesh']).is_file() and Path(job['high_mesh']).is_file()
        # Best-effort assignments must remain usable on a subsequent preparation.
        jobs.prepare(ctx, automatic=True)
        assert jobs.read_job(settings.last_job)['matching_issues']
        bpy.ops.mbt.painter_new_project()
        assert not settings.matching_report
    high.mbt_bake_group = 'MissingGroup'
    high.mbt_bake_target = second
    warnings = []
    _, pairs = matching.resolve(ctx, [a], [high], warnings=warnings)
    assert pairs[high] == a
    assert any('Bake Group has no low' in issue['reason'] for issue in warnings)
    assert any('Bake Target is not in' in issue['reason'] for issue in warnings)
    high.mbt_bake_group = ''
    high.mbt_bake_target = None
    # A tenfold winner and the reported 0.002/0.01223 pair are not ambiguous.
    assert not matching.ambiguous_scores(0.0007579, 0.008244)
    assert not matching.ambiguous_scores(0.002, 0.01223)
    assert matching.ambiguous_scores(0, 0)
    assert matching.ambiguous_scores(0.01, 0.011)
    # Minority raised details must not impose a 90% vertex-coverage gate.
    assert matching.distance_score([0.001] * 82 + [0.3] * 18, 0.1, 1) is not None
    assert matching.distance_score([0.3] * 82 + [0.001] * 18, 0.1, 1) is None
    # Equal-sized parallel surfaces have different distances. The old ambiguity
    # floor rejected this clear best candidate even though it was five times closer.
    a.mbt_bake_group = 'A'
    b.mbt_bake_group = 'B'
    b.location.x = 0.08
    high.location.x = 0.01
    second.data = a.data.copy()
    second.location.x = 0.08
    second.mbt_bake_target = b
    ctx.view_layer.update()
    _, pairs = matching.resolve(ctx, [a, b], [high, second])
    assert pairs[high] == a and pairs[second] == b
    # A densely tessellated, tiny remote detail must not dominate sampling.
    detail_mesh = bpy.data.meshes.new('AreaSamples')
    vertices = [(0, 0, 0), (10, 0, 0), (0, 10, 0)]
    faces = [(0, 1, 2)]
    for index in range(200):
        offset = len(vertices)
        vertices.extend([(100, index * 0.0001, 0), (100.0001, index * 0.0001, 0),
                         (100, index * 0.0001 + 0.0001, 0)])
        faces.append((offset, offset + 1, offset + 2))
    detail_mesh.from_pydata(vertices, [], faces)
    assert all(point.x < 11 for point in matching.surface_samples(detail_mesh, a.matrix_world))
    # Actual surface matching accepts a cube with one raised face (4/8 vertices
    # beyond the old tolerance), rather than diagnosing a bakeability failure.
    raised = cube('RaisedDetail', 'HIGH')
    for vertex in raised.data.vertices:
        if vertex.co.z > 0:
            vertex.co.z += 0.5
    ctx.view_layer.update()
    assert matching.resolve(ctx, [a], [raised])[1][raised] == a
    assert matching.stem('Part.007-low') == matching.stem('Part.007-high') == 'Part.007'
    # 255 vertices used to sample only the first 128; retain the remote endpoint.
    sample_mesh = bpy.data.meshes.new('SampleOrder')
    sample_mesh.from_pydata([(0, 0, 0)] * 254 + [(100, 0, 0)], [], [])
    assert any(point.x == 100 for point in matching.spatial_samples(sample_mesh, a.matrix_world))
    # Precise diagnostics distinguish valid 3D faces from zero-area geometry.
    uv_mesh = bpy.data.meshes.new('Diagnostics')
    uv_mesh.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0), (2, 0, 0)], [], [(0, 1, 2), (0, 1, 3)])
    layer = uv_mesh.uv_layers.new(name='BakeUV')
    for item in layer.data:
        item.uv = (0.5, 0.5)
    try:
        jobs.validate_uv(uv_mesh, 'Example')
    except jobs.ValidationIssues as error:
        assert len(error.issues) == 2 and not error.blocking
        assert all(issue['uv_map'] == 'BakeUV' and issue['triangle_count'] == 1 for issue in error.issues)
        assert {tuple(issue['faces']) for issue in error.issues} == {(0,), (1,)}
    else:
        raise AssertionError('Collapsed faces must be diagnosed')
    jobs.validate_uv(uv_mesh, 'Example', ignore_warnings=True)
    # Original collapsed geometry removed by a modifier must not warn at bake time.
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    low = cube('Filtered_low', 'LOW')
    cube('Filtered_high', 'HIGH')
    original_uvs = [tuple(item.uv) for item in low.data.uv_layers.active.data]
    vertices = [tuple(vertex.co) for vertex in low.data.vertices] + [(3, 0, 0), (4, 0, 0), (3, 1, 0)]
    faces = [tuple(face.vertices) for face in low.data.polygons] + [(8, 9, 10)]
    low.data.clear_geometry()
    low.data.from_pydata(vertices, [], faces)
    layer = low.data.uv_layers.active or low.data.uv_layers.new()
    for index, item in enumerate(layer.data):
        item.uv = original_uvs[index] if index < len(original_uvs) else (0.5, 0.5)
    keep = low.vertex_groups.new(name='ExportedVertices')
    keep.add(list(range(8)), 1.0, 'REPLACE')
    mask = low.modifiers.new('Remove unused collapsed face', 'MASK')
    mask.vertex_group = keep.name
    try:
        jobs.validate_uv(low.data, low.name)
    except jobs.ValidationIssues as error:
        assert not error.blocking
    else:
        raise AssertionError('Source mesh should contain a collapsed face')
    with TemporaryDirectory() as folder:
        ctx.scene.mbt_painter.output_dir = folder
        ctx.view_layer.update()
        jobs.validate(ctx)
        assert bpy.ops.mbt.painter_action(action='VALIDATE') == {'FINISHED'}
        # Identical surfaces across sets are not competing candidates in Validate.
        low.name = 'FirstRetopo'
        first_high = jobs.meshes(ctx.scene.mbt_painter.high_collection)[0]
        first_high.name = 'FirstSculpt'
        bpy.ops.mbt.painter_texture_set(action='ADD')
        cube('SecondRetopo', 'LOW')
        cube('SecondSculpt', 'HIGH')
        assert bpy.ops.mbt.painter_action(action='VALIDATE') == {'FINISHED'}
    addon.unregister()
    print('PASS: group union, robust detail matching, clear winners, true ambiguity, distance rejection, area sampling and UV diagnostics', flush=True)


if __name__ == '__main__':
    main()