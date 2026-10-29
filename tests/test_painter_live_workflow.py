"""Opt-in live Blender/Painter matrix. Run in a disposable Blender process.

Requires -- --live. Launches/connects Painter, refuses an existing project, and
retains its own temporary artifacts. Closes only its exact test project when
switching normal conventions. Leaves the final test project open. No GUI input
simulation or production-asset certification is implied.
"""
import importlib
import json
from pathlib import Path
import sys
import tempfile
import time
import traceback

import addon_utils
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
bridge = importlib.import_module(ROOT.name + '.features.substance_painter.bridge')
runtime = importlib.import_module(ROOT.name + '.features.substance_painter.runtime')
jobs = importlib.import_module(ROOT.name + '.features.substance_painter.jobs')


def main():
    if '--live' not in sys.argv:
        raise RuntimeError('Explicit -- --live required; use a disposable Blender process')
    directory = Path(tempfile.mkdtemp(prefix='MBToolkit_Painter_Matrix_'))
    print('LIVE_DIRECTORY=' + str(directory), flush=True)
    report = {'directory': str(directory), 'blender': bpy.app.version_string,
              'checks': [], 'status': 'RUNNING'}

    def write():
        (directory / 'result.json').write_text(json.dumps(report, indent=2), encoding='utf-8')

    write()
    client, info = bridge.connect(60041, bridge.detect_executable(), allow_launch=True,
                                  progress=lambda message: print(message, flush=True))
    if info['project_open'] or info['busy']:
        report.update(status='SKIPPED', reason='Painter already has an open project or is busy; untouched')
        write()
        print(report['reason'], flush=True)
        bpy.ops.wm.quit_blender()
        return
    addon_utils.enable(ROOT.name, default_set=True)
    addon = importlib.import_module(ROOT.name)
    prefs = bpy.context.preferences.addons[ROOT.name].preferences
    prefs.enable_substance_painter = True
    addon.feature_manager.sync(prefs)
    settings = bpy.context.scene.mbt_painter
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    lows, highs = [], []
    for group, width, color in (('Wide', 0.18, (0.8, 0.05, 0.02, 1)),
                                ('Narrow', 0.04, (0.02, 0.15, 0.8, 1))):
        # Deliberately coincident groups: isolation depends on BY_NAME, not spacing.
        bpy.ops.mesh.primitive_cube_add()
        low = bpy.context.object
        low.name = group + '_low'
        bpy.ops.mbt.painter_assign(role='LOW')
        lows.append(low)
        for index, scale in enumerate((1.0, 0.98)):
            bpy.ops.mesh.primitive_cube_add()
            high = bpy.context.object
            high.name = group + '_high' + (f'_{index:03d}' if index else '')
            high.scale = (scale,) * 3
            modifier = high.modifiers.new('Live bevel', 'BEVEL')
            modifier.width, modifier.segments = width, 3
            material = bpy.data.materials.new(group + '_ID_' + str(index))
            material.diffuse_color = color
            high.data.materials.append(material)
            attribute = high.data.color_attributes.new(name='Color', type='BYTE_COLOR', domain='CORNER')
            for item in attribute.data:
                item.color = color
            bpy.ops.mbt.painter_assign(role='HIGH')
            highs.append(high)
    settings.output_dir = str(directory)
    settings.project_name = 'LiveMatrixOpenGL'
    settings.resolution = '512'
    settings.bake_maps = {key for key, _ in importlib.import_module(
        ROOT.name + '.features.substance_painter.settings').BAKE_MAPS}
    settings.front_distance = settings.rear_distance = 0.15
    settings.antialiasing = 'None'
    settings.id_source = 'Material Color'
    bpy.context.view_layer.update()
    bpy.ops.wm.save_as_mainfile(filepath=str(directory / 'live_matrix.blend'))
    phase = 0
    started = time.monotonic()
    previous_report = ''
    original = None
    layer_names = None

    def remote(source, expression):
        return client.execute(f'(exec({source!r}, globals()), __import__("json").dumps({expression}))[1]')

    def check_export(label):
        assert settings.report.startswith('Exported from Painter.'), settings.report
        job = jobs.read_job(settings.last_job)
        assert job['status'] == 'exported' and len(job['texture_sets']) == 2
        stats = {}
        normals = {}
        for entry in job['texture_sets']:
            obj = next(obj for obj in lows if obj['mbt_painter_id'] == entry['object_id'])
            material = obj.data.materials[0]
            assert material['mbt_painter_job'] == job['job_id']
            assert material['mbt_painter_object_id'] == entry['object_id']
            stats[entry['texture_set']] = {}
            for channel in ('base_color', 'roughness', 'metallic', 'normal', 'ao'):
                path = Path(entry['textures'][channel])
                assert path.is_file(), str(path)
                node = material.node_tree.nodes['MBT_' + channel]
                image = node.image
                assert tuple(image.size) == (512, 512), (path, tuple(image.size))
                assert image.colorspace_settings.name == ('sRGB' if channel == 'base_color' else 'Non-Color')
                values = list(image.pixels[:])
                assert values and all(0 <= value <= 1 for value in values)
                # Sample RGB only, excluding alpha.
                rgb = [values[i] for i in range(0, len(values), 4)]
                stats[entry['texture_set']][channel] = {'bytes': path.stat().st_size,
                    'red_min': min(rgb), 'red_max': max(rgb)}
                if channel == 'normal':
                    normals[entry['texture_set']] = values[::16]
                    assert max(rgb) - min(rgb) > 0.05, 'Normal export is unexpectedly flat'
            if job['normal_format'] == 'DIRECTX':
                assert any(node.bl_idname == 'ShaderNodeMath' and node.operation == 'SUBTRACT'
                           for node in material.node_tree.nodes), 'Missing DirectX green inversion'
        keys = sorted(normals)
        difference = sum(abs(a-b) for a, b in zip(normals[keys[0]], normals[keys[1]])) / len(normals[keys[0]])
        assert difference > 0.001, 'Overlapping groups unexpectedly have identical normal maps'
        report['checks'].append({'stage': label, 'job': settings.last_job,
                                 'normal_group_difference': difference, 'textures': stats})
        write()
        return job

    def start(action='AUTO'):
        nonlocal started
        started = time.monotonic()
        runtime.start(bpy.context, action)

    def tick():
        nonlocal phase, previous_report, original, layer_names
        try:
            if settings.report != previous_report:
                print('LIVE:', settings.report, flush=True)
                previous_report = settings.report
            if time.monotonic() - started > 600:
                raise RuntimeError('Live stage exceeded 10 minutes; Painter left untouched')
            if runtime.busy():
                return 0.25
            if phase == 0:
                original = check_export('OpenGL, all maps, material ID, AA None, two lows/four highs')
                marker_source = '''import substance_painter.layerstack as ls
import substance_painter.colormanagement as cm
for ts in _mbt_textureset.all_texture_sets():
    stack = ts.get_stack()
    layer = ls.insert_fill(ls.InsertPosition.from_textureset_stack(stack))
    layer.set_name('MBT_LIVE_RETAIN_' + ts.name())
    layer.set_source(ls.ChannelType.BaseColor, cm.Color(0.12, 0.42, 0.18))
    paint = ls.insert_paint(ls.InsertPosition.from_textureset_stack(stack))
    paint.set_name('MBT_LIVE_PAINT_' + ts.name())
_mbt_project.save()
'''
                layer_names = remote(marker_source,
                    "{ts.name(): [node.get_name() for node in ls.get_root_layer_nodes(ts.get_stack())] for ts in _mbt_textureset.all_texture_sets()}")
                report['layer_markers'] = layer_names
                lows[0].name = 'RenamedWideLow'
                highs[0].modifiers['Live bevel'].width = 0.12
                settings.id_source = 'Vertex Color'
                settings.antialiasing = 'Supersampling 4x'
                bpy.context.view_layer.update()
                phase = 1
                start()
            elif phase == 1:
                job = check_export('Reuse after rename/geometry change, vertex ID, AA 4x')
                assert job['project_file'] == original['project_file']
                assert {e['texture_set'] for e in job['texture_sets']} == {e['texture_set'] for e in original['texture_sets']}
                actual = remote('import substance_painter.layerstack as ls',
                    "{ts.name(): [node.get_name() for node in ls.get_root_layer_nodes(ts.get_stack())] for ts in _mbt_textureset.all_texture_sets()}")
                assert actual == layer_names, (actual, layer_names)
                assert all(abs(maps['base_color']['red_min'] - 0.12) < 0.02
                           for maps in report['checks'][-1]['textures'].values()), 'Fill color was not retained after mesh reload'
                settings.antialiasing = 'Supersampling 16x'
                phase = 2
                start()
            elif phase == 2:
                check_export('Reuse with AA 16x')
                phase = 3
                start('EXPORT')
            elif phase == 3:
                check_export('Painting-only texture update, no bake')
                job = jobs.read_job(settings.last_job)
                assert Path(job['project_file']).resolve().is_relative_to(directory)
                # Exact-path guard: only close the project created by this test.
                remote(f"assert _MBTPath(_mbt_project.file_path()).resolve() == _MBTPath({job['project_file']!r}).resolve()\n_mbt_project.save()\n_mbt_project.close()",
                       "{'closed': not _mbt_project.is_open()}")
                bpy.ops.mbt.painter_new_project()
                settings.project_name = 'LiveMatrixDirectX'
                settings.normal_format = 'DIRECTX'
                settings.antialiasing = 'None'
                phase = 4
                start()
            elif phase == 4:
                check_export('DirectX, all maps, vertex ID, green inversion')
                bpy.ops.wm.save_as_mainfile(filepath=str(directory / 'live_matrix.blend'))
                report.update(status='PASS', limitations=[
                    'Synthetic beveled meshes, not production assets',
                    'Layer-stack retention verified; empty paint layer has no brush strokes',
                    'Pixel statistics are not a human visual quality review',
                    'Custom export mapping and OS input smoke tests not yet exercised'])
                write()
                print('PASS: LIVE WORKFLOW MATRIX ' + str(directory), flush=True)
                bpy.ops.wm.quit_blender()
                return None
            return 0.25
        except Exception:
            runtime.cancel()
            report.update(status='FAIL', phase=phase, error=traceback.format_exc(), last_result=settings.report)
            write()
            traceback.print_exc()
            print('FAIL: LIVE WORKFLOW MATRIX ' + str(directory), flush=True)
            bpy.ops.wm.quit_blender()
            return None

    start()
    bpy.app.timers.register(tick, first_interval=0.25)
    if bpy.app.background:
        # Background Blender exits after the script, so service both timers here.
        while report['status'] == 'RUNNING':
            if runtime._timer is not None:
                timer = runtime._timer
                result = timer()
                if result is None and bpy.app.timers.is_registered(timer):
                    bpy.app.timers.unregister(timer)
            tick()
            time.sleep(0.25)


if __name__ == '__main__':
    main()