"""Opt-in ID coverage/local-cage experiment. Never operates on unrelated projects.

Run in disposable background Blender with -- --live [--joined] [--sparse]
[--edge-gap] [--replace-test SPP]. --edge-gap requires --sparse.
The dense low is a synthetic test input, NOT an automatic remesh of an artist asset.
"""
import json
import importlib
from pathlib import Path
import sys
import tempfile
import traceback

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_painter_skew_live as base
from skew_metrics import compare_masks, image_digest

import bmesh
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree


def guard(client, job):
    source = (f'assert _MBTPath(_mbt_project.file_path()).resolve() == _MBTPath({job["project_file"]!r}).resolve()\n'
              'assert not _mbt_project.is_busy()')
    client.execute(f'(exec({source!r}, globals()), _mbt_json.dumps({{"guarded": True}}))[1]')


def export_id(client, job, directory, label):
    guard(client, job)
    output = directory / (label + '_id')
    output.mkdir()
    config = {'exportShaderParams': False, 'exportPath': str(output),
              'defaultExportPreset': 'MBT_Coverage',
              'exportPresets': [{'name': 'MBT_Coverage', 'maps': [{
                  'fileName': '$textureSet_ID', 'channels': [
                      {'destChannel': c, 'srcChannel': c, 'srcMapType': 'meshMap', 'srcMapName': 'id'}
                      for c in 'RGB']}]}],
              'exportList': [{'rootPath': job['texture_sets'][0]['texture_set']}],
              'exportParameters': [{'parameters': {'fileFormat': 'png', 'bitDepth': '8',
                  'dithering': False, 'sizeLog2': 9, 'paddingAlgorithm': 'passthrough'}}]}
    source = ('import substance_painter.export as export\n'
              f'result = export.export_project_textures({config!r})\n'
              'assert result.status == export.ExportStatus.Success, result.message')
    client.execute(f'(exec({source!r}, globals()), _mbt_json.dumps({{"exported": True}}))[1]')
    path = output / (job['texture_sets'][0]['texture_set'] + '_ID.png')
    assert path.is_file()
    return path


def color_masks(pixels, region):
    # Dominant-channel classification tolerates ID antialiasing and color encoding.
    masks = {name: set() for name in ('red', 'green', 'blue')}
    for index in region:
        rgb = pixels[index * 4:index * 4 + 3]
        for channel, name in enumerate(masks):
            if rgb[channel] > .4 and rgb[channel] > max(rgb[(channel + 1) % 3], rgb[(channel + 2) % 3]) + .2:
                masks[name].add(index)
    return masks


def references(objects):
    vertices, triangles, colors = [], [], []
    for obj in objects:
        evaluated = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
        mesh = evaluated.to_mesh()
        try:
            mesh.calc_loop_triangles()
            offset = len(vertices)
            vertices.extend(evaluated.matrix_world @ vertex.co for vertex in mesh.vertices)
            for tri in mesh.loop_triangles:
                triangles.append(tuple(offset + i for i in tri.vertices))
                material = mesh.materials[tri.material_index]
                rgb = material.diffuse_color[:3]
                colors.append(('red', 'green', 'blue')[max(range(3), key=lambda c: rgb[c])]
                              if max(rgb) - min(rgb) > .5 else None)
        finally:
            evaluated.to_mesh_clear()
    tree = BVHTree.FromPolygons(vertices, triangles, all_triangles=True)
    masks = {name: set() for name in ('red', 'green', 'blue')}
    region = set()
    for y in range(512):
        for x in range(512):
            u, v = (x + .5) / 512, (y + .5) / 512
            if not (.102 < u < .898 and .102 < v < .898):
                continue
            index = y * 512 + x
            region.add(index)
            hit, _, face, _ = tree.ray_cast(Vector(((u - .5) / .4, (v - .5) / .4, 3)),
                                           Vector((0, 0, -1)), 2.2)
            if hit is not None and colors[face]:
                masks[colors[face]].add(index)
    return region, masks


CENTERS = ((-.35, .25, .18), (.40, .10, .36))


def build_cage(cage, label):
    """Blend only interior test vertices. Boundary displacement stays identical.

    Expanded field deliberately recreates tilted rays even on a dense receiver.
    This is an authored test cage, not a prediction of Painter's averaged field.
    """
    original_normals = [polygon.normal.copy() for polygon in cage.data.polygons]
    for vertex in cage.data.vertices:
        co = vertex.co.copy()
        expanded = co * 1.5
        if co.z > .999 and max(abs(co.x), abs(co.y)) < .999:
            weight = 1.0 if label == 'vertical_top' else 0.0
            if label == 'local':
                distance = min(((co.x - x) ** 2 + (co.y - y) ** 2) ** .5 for x, y, _ in CENTERS)
                t = max(0.0, min(1.0, (.44 - distance) / .16))
                weight = t * t * (3 - 2 * t)
            vertical = co + Vector((0, 0, .5))
            vertex.co = expanded.lerp(vertical, weight)
        else:
            vertex.co = expanded
    cage.data.update()
    # A local blend must not fold any triangles, even when image metrics pass.
    cage.data.calc_loop_triangles()
    for triangle in cage.data.loop_triangles:
        a, b, c = (cage.data.vertices[i].co for i in triangle.vertices)
        normal = original_normals[triangle.polygon_index]
        assert (b - a).cross(c - a).dot(normal) > 1e-10, 'Collapsed/folded cage triangle'


def fixture(joined, sparse=False, edge_gap=False):
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    bpy.ops.mesh.primitive_cube_add(size=2)
    low = bpy.context.object
    low.name = 'Coverage_low'
    if not sparse:
        bm = bmesh.new()
        try:
            bm.from_mesh(low.data)
            bmesh.ops.subdivide_edges(bm, edges=list(bm.edges), cuts=15, use_grid_fill=True)
            bm.to_mesh(low.data)
        finally:
            bm.free()
    low.data.update()
    uv = low.data.uv_layers.active
    # Six separate square islands; top keeps the historical .1-.9 mapping.
    for polygon in low.data.polygons:
        axis = max(range(3), key=lambda a: abs(polygon.normal[a]))
        axes = [a for a in range(3) if a != axis]
        side = {(0, -1): 0, (0, 1): 1, (1, -1): 2, (1, 1): 3, (2, -1): 4}.get(
            (axis, 1 if polygon.normal[axis] > 0 else -1))
        for loop in polygon.loop_indices:
            co = low.data.vertices[low.data.loops[loop].vertex_index].co
            uv.data[loop].uv = ((.5 + .4 * co.x, .5 + .4 * co.y) if side is None else
                                (.02 + .18 * side + .07 * (co[axes[0]] + 1),
                                 .01 + .035 * (co[axes[1]] + 1)))
    bpy.ops.mbt.painter_assign(role='LOW')
    materials = []
    for name, color in (('Panel', (.12, .12, .12, 1)), ('Red', (1, 0, 0, 1)),
                        ('Green', (0, 1, 0, 1)), ('Blue', (0, 0, 1, 1))):
        material = bpy.data.materials.new('Coverage_' + name)
        material.diffuse_color = color
        material.use_nodes = True
        material.node_tree.nodes.get('Principled BSDF').inputs['Base Color'].default_value = color
        materials.append(material)
    high = low.copy()
    high.data = low.data.copy()
    bpy.context.scene.collection.objects.link(high)
    high.name = 'Coverage_high'
    high.data.materials.clear()
    high.data.materials.append(materials[0])
    lows = [low]
    highs = [high]
    for index, (x, y, height) in enumerate((*CENTERS, (1.04, -.45, .18))):
        if edge_gap and index == 2:
            # The whole witness lies outside BOTH adjacent low face extents.
            # Face-perpendicular rays cannot reach it; angled corner rays can.
            mesh = bpy.data.meshes.new('CornerGap')
            mesh.from_pydata([(1.01, -.7, 1.19), (1.19, -.7, 1.01),
                              (1.19, -.2, 1.01), (1.01, -.2, 1.19)], [], [(0, 1, 2, 3)])
            mesh.update()
            witness = bpy.data.objects.new('CornerGap_high', mesh)
            bpy.context.scene.collection.objects.link(witness)
            witness.data.materials.append(materials[3])
            highs.append(witness)
            continue
        bpy.ops.mesh.primitive_cylinder_add(vertices=12, radius=.14 if index < 2 else .12,
                                          depth=height, location=(x, y, 1 + height / 2))
        bolt = bpy.context.object
        bolt.name = 'CoverageDetail_high_' + str(index)
        bolt.data.materials.append(materials[index + 1])
        bevel = bolt.modifiers.new('Coverage bevel', 'BEVEL')
        bevel.width, bevel.segments = .02, 2
        highs.append(bolt)
    if joined:
        # Apply evaluated modifiers before join so the geometric reference matches FBX.
        for obj in highs:
            mesh = bpy.data.meshes.new_from_object(obj.evaluated_get(bpy.context.evaluated_depsgraph_get()))
            old = obj.data
            obj.modifiers.clear()
            obj.data = mesh
            if not old.users:
                bpy.data.meshes.remove(old)
        bpy.ops.object.select_all(action='DESELECT')
        for obj in highs:
            obj.select_set(True)
        bpy.context.view_layer.objects.active = high
        bpy.ops.object.join()
        highs = [high]
    bpy.ops.object.select_all(action='DESELECT')
    for obj in highs:
        obj.select_set(True)
        obj.mbt_bake_target = low
    bpy.context.view_layer.objects.active = highs[0]
    bpy.ops.mbt.painter_assign(role='HIGH')
    return low, highs


def main():
    assert bpy.app.background and '--live' in sys.argv, 'Requires disposable background Blender and -- --live'
    if '--edge-gap' in sys.argv and '--sparse' not in sys.argv:
        raise ValueError('--edge-gap requires --sparse; dense local edge-gap acceptance is not implemented')
    directory = Path(tempfile.mkdtemp(prefix='MBToolkit_Painter_Skew_'))
    report = {'status': 'RUNNING', 'directory': str(directory), 'joined': '--joined' in sys.argv,
              'sparse': '--sparse' in sys.argv, 'edge_gap': '--edge-gap' in sys.argv}
    print('SKEW_DIRECTORY=' + str(directory), flush=True)
    base.addon.register()
    try:
        base.addon.feature_manager.sync(type('P', (), {'enable_substance_painter': True})())
        client = base.bridge.Client(timeout=30)
        client.check_endpoint()
        probe = client.install()
        if '--replace-test' in sys.argv and probe['project_open']:
            replacement = Path(sys.argv[sys.argv.index('--replace-test') + 1]).resolve()
            assert replacement.is_file() and any(p.name.startswith('MBToolkit_Painter_Skew_') for p in replacement.parents)
            source = (f'assert _MBTPath(_mbt_project.file_path()).resolve() == _MBTPath({str(replacement)!r}).resolve()\n'
                      'assert not _mbt_project.is_busy()\n_mbt_project.save()\n_mbt_project.close()')
            client.execute(f'(exec({source!r}, globals()), _mbt_json.dumps({{"closed": True}}))[1]')
            probe = client.install()
        assert not probe['project_open'] and not probe['busy'], 'Refusing unrelated/open/busy project'
        low, highs = fixture(report['joined'], report['sparse'], report['edge_gap'])
        report['low_vertex_count'] = len(low.data.vertices)
        planar = importlib.import_module(base.ROOT.name + '.features.substance_painter.planar')
        report['receiving_patches'] = planar.receiving_patches(
            [v.co for v in low.data.vertices], [p.vertices for p in low.data.polygons])
        assert len(report['receiving_patches']['patches']) == 6
        assert not report['receiving_patches']['unassessed_faces']
        original = [tuple(v.co) for v in low.data.vertices]
        region, expected = references(highs)
        assert all(expected[name] for name in ('red', 'green')), 'Interior reference witnesses must be nonempty'
        if not report['edge_gap']:
            assert expected['blue'], 'Boundary reference must be nonempty'
        settings = bpy.context.scene.mbt_painter
        settings.output_dir, settings.project_name = str(directory), 'SkewCoverage'
        settings.resolution, settings.bake_maps = '512', {'NORMAL', 'ID'}
        settings.front_distance, settings.rear_distance = .3, .02
        base.jobs.prepare(bpy.context, automatic=True, ignore_warnings=False)
        job = base.jobs.read_job(settings.last_job)
        job['job_file'] = settings.last_job
        report['job'] = settings.last_job
        base.bridge.send(client, settings.last_job)
        measurements = {}

        def measure(label):
            path = export_id(client, job, directory, label)
            size, pixels = base.read_normal(path)
            assert size == (512, 512)
            masks = color_masks(pixels, region)
            measurements[label] = masks
            return {'id_path': str(path), 'id_digest': image_digest(pixels),
                    'witness_pixels': {name: len(mask) for name, mask in masks.items()}, 'coverage': {
                name: compare_masks(masks[name], expected[name], 512) for name in expected}}

        report['modes'] = {}
        for mode in ('AVERAGED', 'FACE'):
            for definition in job['set_definitions']:
                definition['baking']['projection_normals'] = mode
            Path(settings.last_job).write_text(json.dumps(job, indent=2), encoding='utf-8')
            guard(client, job)
            base.bridge.bake(client, settings.last_job)
            report['modes'][mode] = measure(mode)
        for definition in job['set_definitions']:
            definition['baking']['projection_normals'] = 'AVERAGED'
        Path(settings.last_job).write_text(json.dumps(job, indent=2), encoding='utf-8')
        if report['sparse']:
            # No local cage is claimed: this low has no interior control vertices.
            report['sparse_local_cage_representable'] = False
            report['automatic_correction_ready'] = False
            if report['edge_gap']:
                averaged = len(measurements['AVERAGED']['blue'])
                mesh = len(measurements['FACE']['blue'])
                report['hard_edge_gap'] = {'averaged_pixels': averaged, 'mesh_normal_pixels': mesh,
                    'loss_demonstrated': averaged > 20 and mesh < averaged * .1}
                assert report['hard_edge_gap']['loss_demonstrated'], report['hard_edge_gap']
            report['status'] = 'PASS'
            report['limitations'] = ['Backend/coverage prerequisite only; no automatic correction implemented',
                                    'Sparse cage cannot represent independent interior and boundary directions']
            base.reopen(client, job, 'AVERAGED')
            bpy.ops.wm.save_as_mainfile(filepath=str(directory / 'fixture.blend'))
            return
        report['cages'] = base.backend_probe(client, job, directory, low, build_cage, measure)
        assert original == [tuple(v.co) for v in low.data.vertices], 'Source low changed'
        report['source_unchanged'] = True
        report['expected_pixels'] = {name: len(mask) for name, mask in expected.items()}
        report['edge_retention'] = compare_masks(measurements['local']['blue'], measurements['expanded']['blue'], 512)
        assert measurements['expanded']['blue'] and measurements['local']['blue'], 'Empty edge witness is not preservation'
        report['edge_mode_difference'] = compare_masks(measurements['FACE']['blue'], measurements['expanded']['blue'], 512)
        report['local_vs_expanded_digest_differs'] = report['cages']['local']['id_digest'] != report['cages']['expanded']['id_digest']
        report['locality_proven'] = (report['local_vs_expanded_digest_differs'] and
                                    report['edge_retention']['intersection_over_union'] > .98)
        report['acceptance'] = {}
        for name in ('red', 'green'):
            metric = report['cages']['local']['coverage'][name]
            report['acceptance'][name] = (metric['detail_recall'] is not None and metric['detail_recall'] > .9 and
                                         metric['intersection_over_union'] > .85 and
                                         metric['centroid_error_pixels'] is not None and metric['centroid_error_pixels'] < 1)
        report['automatic_correction_ready'] = False
        report['limitations'] = [
            'Synthetic dense low input; no artist geometry is remeshed',
            'Expanded cage is authored, not the Painter averaged-normal field',
            'Blue witness measures preservation of baseline angled rays, not edge correctness',
            'ID masks include caps but do not measure texture/normal fidelity',
            'Local field uses known bolt locations, not automatic detection',
            'Not yet a hard-edge coverage-loss certification']
        report['status'] = 'PASS' if report['locality_proven'] and all(report['acceptance'].values()) else 'EXPERIMENT_INCOMPLETE'
        base.reopen(client, job, 'AVERAGED')
        bpy.ops.wm.save_as_mainfile(filepath=str(directory / 'fixture.blend'))
    except Exception:
        report.update(status='FAIL', error=traceback.format_exc())
        raise
    finally:
        (directory / 'result.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        base.addon.unregister()
    print(json.dumps(report, indent=2), flush=True)
    if report['status'] != 'PASS':
        raise RuntimeError('Experiment did not meet local correction acceptance gates; inspect result.json')


if __name__ == '__main__':
    main()