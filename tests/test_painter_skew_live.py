"""Opt-in disposable Painter skew experiment; retains artifacts, never closes unrelated projects."""
import importlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import time
import traceback

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

sys.path.insert(0, str(Path(__file__).resolve().parent))
from skew_metrics import compare_masks, image_digest, normal_detail

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon = importlib.import_module(ROOT.name)
bridge = importlib.import_module(ROOT.name + '.features.substance_painter.bridge')
jobs = importlib.import_module(ROOT.name + '.features.substance_painter.jobs')
projection = importlib.import_module(ROOT.name + '.features.substance_painter.projection')


def footprint(path):
    image = bpy.data.images.load(str(path), check_existing=False)
    try:
        image.colorspace_settings.name = 'Non-Color'
        width, height = image.size
        data = list(image.pixels)
        points = []
        # Top face occupies .1-.9; avoid cube edge shading and UV padding.
        for y in range(int(height * .25), int(height * .75)):
            for x in range(int(width * .25), int(width * .85)):
                index = (y * width + x) * 4
                if (data[index] - .5) ** 2 + (data[index + 1] - .5) ** 2 > .12 ** 2:
                    points.append((x + .5, y + .5))
        if not points:
            raise AssertionError('No bolt normal footprint detected')
        return {'pixels': len(points), 'centroid': [sum(p[i] for p in points) / len(points) for i in (0, 1)],
                'bounds': [min(p[0] for p in points), min(p[1] for p in points),
                           max(p[0] for p in points), max(p[1] for p in points)],
                'resolution': [width, height]}
    finally:
        bpy.data.images.remove(image)


def read_normal(path):
    image = bpy.data.images.load(str(path), check_existing=False)
    try:
        image.colorspace_settings.name = 'Non-Color'
        return tuple(image.size), list(image.pixels)
    finally:
        bpy.data.images.remove(image)


def reference_masks(highs, resolution):
    """Independent orthographic reference on the known z=1 fixture receiver.

    This predicts thresholded normal detail, not all surface-hit coverage. The
    bolt's flat cap is intentionally not counted as normal detail.
    """
    vertices, triangles = [], []
    depsgraph = bpy.context.evaluated_depsgraph_get()
    for obj in highs:
        evaluated = obj.evaluated_get(depsgraph)
        mesh = evaluated.to_mesh()
        try:
            mesh.calc_loop_triangles()
            offset = len(vertices)
            vertices.extend(evaluated.matrix_world @ v.co for v in mesh.vertices)
            triangles.extend(tuple(offset + i for i in tri.vertices) for tri in mesh.loop_triangles)
        finally:
            evaluated.to_mesh_clear()
    tree = BVHTree.FromPolygons(vertices, triangles, all_triangles=True)
    expected, edge, detail = set(), set(), set()
    for y in range(resolution):
        v = (y + .5) / resolution
        for x in range(resolution):
            u = (x + .5) / resolution
            if not (.105 < u < .895 and .105 < v < .895):
                continue
            index = y * resolution + x
            if min(u - .1, .9 - u, v - .1, .9 - v) < .04:
                edge.add(index)
            else:
                detail.add(index)
            point = Vector(((u - .5) / .4, (v - .5) / .4, 3))
            hit, normal, _, _ = tree.ray_cast(point, Vector((0, 0, -1)), 2.2)
            if hit is not None and (normal.x ** 2 + normal.y ** 2) * .25 > .12 ** 2:
                expected.add(index)
    return expected, detail, edge


def reopen(client, job, mode):
    source = (f'assert _MBTPath(_mbt_project.file_path()).resolve() == _MBTPath({job["project_file"]!r}).resolve()\n'
              'assert not _mbt_project.is_busy()\n'
              '_mbt_project.save()\n_mbt_project.close()\n'
              f'_mbt_project.open({job["project_file"]!r})')
    client.execute(f'(exec({source!r}, globals()), _mbt_json.dumps({{"reopening": True}}))[1]')
    deadline = time.monotonic() + 60
    while True:
        persisted = client.execute('_mbt_projection_capabilities()')
        if persisted['state'] == 'DISCOVERED':
            break
        if time.monotonic() > deadline:
            raise RuntimeError('Test project reopen timed out')
        time.sleep(.5)
    assert persisted['texture_sets'][0]['properties']['SmoothNormals']['value'] == str(mode == 'AVERAGED')
    return persisted


def backend_probe(client, job, directory, low, cage_builder=None, after_bake=None):
    """Test-only adapter: production jobs remain distance-based and unchanged."""
    source = '''
import substance_painter.baking as baking
import substance_painter.resource as resource
params = baking.BakingParameters.from_texture_set(_mbt_textureset.all_texture_sets()[0])
discovery = {'common': {}, 'bakers': {}, 'modules': {}}
for name, prop in params.common().items():
    discovery['common'][name] = {'value': str(prop.value()), 'enums': prop.enum_values()}
for name in dir(_mbt_textureset.MeshMapUsage):
    usage = getattr(_mbt_textureset.MeshMapUsage, name)
    if isinstance(usage, _mbt_textureset.MeshMapUsage):
        try:
            discovery['bakers'][name] = list(params.baker(usage))
        except Exception as error:
            discovery['bakers'][name] = str(error)
for module in (baking, resource):
    discovery['modules'][module.__name__] = {
        name: str(getattr(module, name).__doc__)[:4000]
        for name in dir(module) if not name.startswith('_')}
'''
    guard = (f'assert _MBTPath(_mbt_project.file_path()).resolve() == _MBTPath({job["project_file"]!r}).resolve()\n'
             'assert not _mbt_project.is_busy()\n')
    discovery = client.execute(f'(exec({(guard + source)!r}, globals()), _mbt_json.dumps(discovery))[1]')
    (directory / 'backend_discovery.json').write_text(json.dumps(discovery, indent=2), encoding='utf-8')
    # Keep all production helpers intact. Only this isolated copy of _mbt_bake
    # switches cage mode; every other parameter and the event machinery is shared.
    remote = (ROOT / 'features/substance_painter/painter_remote.py').read_text(encoding='utf-8')
    start, end = remote.index('def _mbt_bake(job_path):'), remote.index('\ndef _mbt_save_baked(')
    adapter = remote[start:end].replace('def _mbt_bake(job_path):', 'def _mbt_cage_bake(job_path):')
    needle = "('CageMode', 'Distance-based')"
    assert adapter.count(needle) == 1
    adapter = adapter.replace(needle, "('CageMode', 'Custom file')")
    needle = 'baking.BakingParameters.set(changes)'
    assert adapter.count(needle) == 1
    adapter = adapter.replace(needle, "\n        for ts in texture_sets:\n"
                              "            common = baking.BakingParameters.from_texture_set(ts).common()\n"
                              "            changes[common['CageMesh']] = _mbt_test_cage\n        " + needle)
    client.execute(f'(exec({adapter!r}, globals()), _mbt_json.dumps({{"installed": True}}))[1]')
    outputs = {}
    try:
        for label in (('expanded', 'vertical_top', 'local') if cage_builder else ('expanded', 'vertical_top')):
            cage = low.copy()
            cage.data = low.data.copy()
            bpy.context.scene.collection.objects.link(cage)
            try:
                if cage_builder:
                    cage_builder(cage, label)
                else:
                    for vertex in cage.data.vertices:
                        if label == 'vertical_top' and vertex.co.z > 0:
                            vertex.co.z += .5
                        else:
                            vertex.co *= 1.5
                path = directory / (label + '_cage.fbx')
                jobs.export_meshes(bpy.context, [cage], path)
            finally:
                mesh = cage.data
                bpy.data.objects.remove(cage, do_unlink=True)
                bpy.data.meshes.remove(mesh)
            # The normal bake path is replaced only in the remote test namespace.
            source = (guard + f'_mbt_test_cage = {path.resolve().as_uri()!r}\n'
                      '_mbt_original_bake = _mbt_bake\n_mbt_bake = _mbt_cage_bake')
            client.execute(f'(exec({source!r}, globals()), _mbt_json.dumps({{"ready": True}}))[1]')
            try:
                result = bridge.bake(client, job['job_file'])
            finally:
                client.execute('(exec("_mbt_bake = _mbt_original_bake", globals()), _mbt_json.dumps({"restored": True}))[1]')
            output = directory / (label + '_cage.png')
            shutil.copy2(result['texture_sets'][0]['textures']['normal'], output)
            persisted = reopen(client, job, 'AVERAGED')
            props = persisted['texture_sets'][0]['properties']
            assert props['CageMode']['value'] == '2'
            assert props['CageMesh']['value'] == path.resolve().as_uri()
            outputs[label] = {'path': str(output), 'settings': persisted,
                              'save_reopen': 'PASS', 'vertex_count': len(low.data.vertices)}
            if after_bake:
                outputs[label].update(after_bake(label))
    finally:
        # Restore distance-based projection even when the experimental bake fails.
        source = guard + '''
import substance_painter.baking as baking
common = baking.BakingParameters.from_texture_set(_mbt_textureset.all_texture_sets()[0]).common()
baking.BakingParameters.set({common['CageMode']: common['CageMode'].enum_value('Distance-based'),
                             common['CageMesh']: ''})
'''
        client.execute(f'(exec({source!r}, globals()), _mbt_json.dumps({{"restored": True}}))[1]')
    return outputs


def main():
    if '--live' not in sys.argv:
        raise RuntimeError('Explicit -- --live required in a disposable Blender process')
    directory = Path(tempfile.mkdtemp(prefix='MBToolkit_Painter_Skew_'))
    report = {'status': 'RUNNING', 'directory': str(directory), 'checks': {}}
    print('SKEW_DIRECTORY=' + str(directory), flush=True)
    def write():
        (directory / 'result.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    write()
    client, info = bridge.connect(60041)
    if '--replace-test' in sys.argv and info['project_open'] and not info['busy']:
        expected = Path(sys.argv[sys.argv.index('--replace-test') + 1]).resolve()
        if not expected.parent.parent.name.startswith('MBToolkit_Painter_Skew_') or not expected.is_file():
            raise RuntimeError('Replacement requires an exact retained skew-test project path')
        source = (f'assert _MBTPath(_mbt_project.file_path()).resolve() == _MBTPath({str(expected)!r}).resolve()\n'
                  '_mbt_project.save()\n_mbt_project.close()')
        client.execute(f'(exec({source!r}, globals()), _mbt_json.dumps({{"closed": True}}))[1]')
        info = client.install()
    if info['project_open'] or info['busy']:
        report.update(status='SKIPPED', reason='Existing project/busy Painter left untouched')
        write()
        return
    addon.register()
    addon.feature_manager.sync(type('Preferences', (), {'enable_substance_painter': True})())
    try:
        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.delete(use_global=False)
        bpy.ops.mesh.primitive_cube_add(size=2)
        low = bpy.context.object
        low.name = 'Panel_low'
        uv = low.data.uv_layers.active
        side = 0
        for polygon in low.data.polygons:
            for loop in polygon.loop_indices:
                co = low.data.vertices[low.data.loops[loop].vertex_index].co
                axes = [axis for axis in range(3) if abs(polygon.normal[axis]) < .5]
                uv.data[loop].uv = ((.5 + .4 * co.x, .5 + .4 * co.y) if polygon.normal.z > .9
                                    else (.02 + .18 * side + .07 * (co[axes[0]] + 1),
                                          .01 + .035 * (co[axes[1]] + 1)))
            if polygon.normal.z < .9:
                side += 1
        bpy.ops.mbt.painter_assign(role='LOW')
        high = low.copy()
        high.data = low.data.copy()
        bpy.context.scene.collection.objects.link(high)
        high.name = 'Panel_high'
        if '--edge-fixture' in sys.argv:
            bevel = high.modifiers.new('Coverage witness bevel', 'BEVEL')
            bevel.width, bevel.segments = .08, 3
        bpy.context.view_layer.objects.active = high
        low.select_set(False)
        high.select_set(True)
        bpy.ops.mbt.painter_assign(role='HIGH')
        bpy.ops.mesh.primitive_cylinder_add(vertices=6, radius=.22, depth=.30, location=(.45, .15, 1.15))
        bolt = bpy.context.object
        bolt.name = 'Bolt_high'
        bolt.mbt_bake_target = low
        bevel = bolt.modifiers.new('Bolt bevel', 'BEVEL')
        bevel.width, bevel.segments = .035, 3
        bpy.ops.mbt.painter_assign(role='HIGH')
        settings = bpy.context.scene.mbt_painter
        settings.output_dir = str(directory)
        settings.project_name = 'SkewExperiment'
        settings.resolution = '512'
        settings.bake_maps = {'NORMAL'}
        settings.front_distance = .25
        settings.rear_distance = .02
        settings.antialiasing = 'Supersampling 4x'
        bpy.context.view_layer.update()
        report['estimate'] = projection.analyze(bpy.context)
        expected, detail_region, edge_region = reference_masks([high, bolt], 512)
        assert expected & detail_region, 'Independent reference contains no normal detail'
        report['edge_fixture'] = '--edge-fixture' in sys.argv
        report['expected_edge_detail_pixels'] = len(expected & edge_region)
        if report['edge_fixture']:
            assert expected & edge_region, 'Edge coverage witness must not be empty'
        jobs.prepare(bpy.context, automatic=True, ignore_warnings=False)
        bridge.send(client, settings.last_job)
        job = jobs.read_job(settings.last_job)
        job['job_file'] = settings.last_job
        report['job'] = settings.last_job
        report['capabilities'] = client.execute('_mbt_projection_capabilities()')
        # Exact-path guard before every write to the disposable Painter project.
        for label, mode in (('averaged', 'AVERAGED'), ('perpendicular_reference', 'FACE'),
                            ('averaged_repeat', 'AVERAGED')):
            settings.projection_normals = mode
            jobs.update_bake_settings(settings.last_job, settings)
            report.setdefault('mode_estimates', {})[mode] = projection.analyze(bpy.context)
            result = bridge.bake(client, settings.last_job, progress=lambda message: print(message, flush=True))
            actual = client.execute('_mbt_projection_capabilities()')
            assert actual['texture_sets'][0]['properties']['SmoothNormals']['value'] == str(mode == 'AVERAGED')
            normal = Path(result['texture_sets'][0]['textures']['normal'])
            output = directory / (label + '.png')
            shutil.copy2(normal, output)
            report['checks'][label] = footprint(output)
            size, pixels = read_normal(output)
            assert size == (512, 512)
            mask = normal_detail(pixels, size[0], detail_region)
            report['checks'][label]['reference'] = compare_masks(mask, expected & detail_region, size[0])
            report['checks'][label]['image_digest'] = image_digest(pixels)
            report['checks'][label]['edge_detail_pixels'] = len(normal_detail(pixels, size[0], edge_region))
            report['checks'][label]['edge_reference'] = compare_masks(
                normal_detail(pixels, size[0], edge_region), expected & edge_region, size[0])
            report.setdefault('persistence', {})[label] = reopen(client, job, mode)
            write()
        a = report['checks']['averaged']['centroid']
        b = report['checks']['perpendicular_reference']['centroid']
        report['centroid_shift_pixels'] = sum((x-y)**2 for x,y in zip(a,b)) ** .5
        assert report['centroid_shift_pixels'] > 1, report
        assert any(issue.get('max_pixels', 0) > 1 for issue in report['estimate']['issues'])
        assert not any(issue.get('max_pixels', 0) > 1 for issue in report['mode_estimates']['FACE']['issues'])
        repeat = report['checks']['averaged_repeat']
        assert repeat == report['checks']['averaged'], 'Projection setting leaked across rebakes'
        reference = report['checks']['perpendicular_reference']['reference']
        assert reference['centroid_error_pixels'] < 1, reference
        assert reference['detail_recall'] > .9 and reference['intersection_over_union'] > .85, reference
        report['projection_setting_save_reopen'] = 'PASS'
        if '--cage-probe' in sys.argv:
            report['cage_probe'] = backend_probe(client, job, directory, low)
            for label, entry in report['cage_probe'].items():
                size, pixels = read_normal(entry['path'])
                entry['reference'] = compare_masks(normal_detail(pixels, size[0], detail_region),
                                                   expected & detail_region, size[0])
                entry['image_digest'] = image_digest(pixels)
                entry['edge_detail_pixels'] = len(normal_detail(pixels, size[0], edge_region))
                entry['edge_reference'] = compare_masks(normal_detail(pixels, size[0], edge_region),
                                                        expected & edge_region, size[0])
            report['cage_direction_control'] = (
                report['cage_probe']['expanded']['image_digest'] !=
                report['cage_probe']['vertical_top']['image_digest'])
            assert report['cage_direction_control'], 'Cage settings accepted but output unchanged'
            vertical = report['cage_probe']['vertical_top']
            assert vertical['reference']['centroid_error_pixels'] < 1
            assert vertical['reference']['detail_recall'] > .9
            assert vertical['reference']['intersection_over_union'] > .85
            if report['edge_fixture']:
                baseline = report['checks']['averaged']['edge_reference']['detail_recall']
                assert baseline > .9, 'Baseline edge witness is not reliable enough'
                assert vertical['edge_reference']['detail_recall'] >= baseline - .01
                report['edge_witness_nonregression'] = 'PASS'
            report['backend_verdict'] = ('CUSTOM_CAGE_DIRECTION_PROVEN_ON_SYNTHETIC_FIXTURE; '
                                         'LOCAL_EDGE_PROTECTION_NOT_PROVEN')
            # Save the restored production mode rather than retaining the cage.
            reopen(client, job, 'AVERAGED')
        bpy.ops.wm.save_as_mainfile(filepath=str(directory / 'fixture.blend'))
        report.update(status='PASS', limitations=['Synthetic fixture, not production certification',
                      'Face-normal reference is not a general edge-safe correction',
                      'Normal footprint centroid is not exact per-ray correspondence',
                      'Normal-detail recall does not measure all high-surface hit coverage',
                      'Sparse cage changes an entire face, not an arbitrary local bolt region',
                      'Beveled edge witness did not distinguish projection modes'])
    except Exception:
        report.update(status='FAIL', error=traceback.format_exc())
        raise
    finally:
        write()
        addon.unregister()
    print(json.dumps(report, indent=2), flush=True)


if __name__ == '__main__':
    main()