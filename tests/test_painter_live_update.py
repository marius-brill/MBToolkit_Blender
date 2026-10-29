"""Opt-in custom-mapping and UI follow-up for a retained live-matrix blend.

Invoke a disposable GUI Blender with -- --live --blend <matrix/live_matrix.blend>.
Only the exact associated open Painter test project may be exported. No bake or
Painter save/close is requested. The blend and existing exports remain intact.
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


def main():
    if '--live' not in sys.argv or '--blend' not in sys.argv or bpy.app.background:
        raise RuntimeError('Requires disposable GUI Blender, -- --live --blend <matrix blend>')
    blend = Path(sys.argv[sys.argv.index('--blend') + 1]).resolve()
    if not blend.parent.name.startswith('MBToolkit_Painter_Matrix_') or blend.name != 'live_matrix.blend':
        raise RuntimeError('Refusing non-matrix blend')
    addon_utils.enable(ROOT.name, default_set=True)
    addon = importlib.import_module(ROOT.name)
    prefs = bpy.context.preferences.addons[ROOT.name].preferences
    prefs.enable_substance_painter = True
    addon.feature_manager.sync(prefs)
    feature = importlib.import_module(ROOT.name + '.features.substance_painter')
    jobs = importlib.import_module(ROOT.name + '.features.substance_painter.jobs')
    runtime = importlib.import_module(ROOT.name + '.features.substance_painter.runtime')
    bridge = importlib.import_module(ROOT.name + '.features.substance_painter.bridge')
    settings = bpy.context.scene.mbt_painter
    job = jobs.read_job(settings.last_job)
    assert Path(job['project_file']).resolve().is_relative_to(blend.parent)
    client, info = bridge.connect(60041)
    assert info['project_open'] and not info['busy']
    current = client.execute("__import__('json').dumps({'path': _mbt_project.file_path()})")['path']
    assert Path(current).resolve() == Path(job['project_file']).resolve()
    report = {'status': 'RUNNING', 'checks': []}
    destination = blend.parent / 'update_result.json'

    def remote(source, expression):
        return client.execute(f'(exec({source!r}, globals()), __import__("json").dumps({expression}))[1]')

    # Ask the installed preset for its actual filenames instead of guessing tokens.
    discovery = Path(tempfile.mkdtemp(prefix='custom_discovery_', dir=blend.parent))
    source = f'''import substance_painter.export as ex
presets = [p for p in ex.list_resource_export_presets() if p.resource_id.name == 'PBR Metallic Roughness']
assert len(presets) == 1
preset = presets[0].resource_id.url()
result = ex.export_project_textures({{'exportShaderParams': False, 'exportPath': {str(discovery)!r},
    'defaultExportPreset': preset,
    'exportList': [{{'rootPath': ts.name()}} for ts in _mbt_textureset.all_texture_sets()],
    'exportParameters': [{{'parameters': {{'fileFormat': 'png', 'sizeLog2': 9,
        'paddingAlgorithm': 'infinite', 'bitDepth': '8', 'dithering': False}}}}]}})
assert result.status in (ex.ExportStatus.Success, ex.ExportStatus.Warning), result.message
'''
    found = remote(source, "{'preset': preset, 'files': [str(path) for paths in result.textures.values() for path in paths]}")
    channels = {}
    for channel, suffix in (('base_color', 'BaseColor'), ('roughness', 'Roughness'),
                             ('metallic', 'Metallic'), ('normal', 'Normal')):
        entry = job['texture_sets'][0]
        matches = [Path(path).name for path in found['files']
                   if entry['texture_set'] + '_' + suffix in Path(path).name]
        assert len(matches) == 1, (channel, matches)
        channels[channel] = matches[0].replace(entry['texture_set'], '{texture_set}')
    mapping = {'preset': found['preset'], 'channels': channels}
    config = blend.parent / 'custom_mapping.json'
    config.write_text(json.dumps(mapping, indent=2), encoding='utf-8')
    settings.export_config = str(config)
    jobs.prepare(bpy.context, automatic=True)
    assert jobs.read_job(settings.last_job)['custom_export'] == mapping
    settings.advanced = True

    class MBT_PT_live_bake_smoke(bpy.types.Panel):
        bl_label = 'Live Bake UI smoke'
        bl_space_type = 'VIEW_3D'
        bl_region_type = 'UI'
        bl_category = 'MBT Live Test'
        draws = 0

        def draw(self, context):
            try:
                feature.draw(self.layout, context)
                type(self).draws += 1
            except Exception:
                report['draw_error'] = traceback.format_exc()

    bpy.utils.register_class(MBT_PT_live_bake_smoke)
    window = bpy.context.window_manager.windows[0]
    for area in window.screen.areas:
        if area.type == 'VIEW_3D':
            area.spaces.active.show_region_ui = True
            area.tag_redraw()
    def draw_popup(self, context):
        feature.draw(self.layout, context)
        report['popup_drawn'] = True

    with bpy.context.temp_override(window=window):
        bpy.context.window_manager.popup_menu(draw_popup, title='Live Bake UI smoke')
    started = time.monotonic()
    runtime.start(bpy.context, 'EXPORT')

    def tick():
        try:
            if runtime.busy():
                assert time.monotonic() - started < 180
                return 0.25
            assert settings.report.startswith('Exported from Painter.'), settings.report
            job = jobs.read_job(settings.last_job)
            for entry in job['texture_sets']:
                obj = next(obj for obj in bpy.context.scene.objects if obj.get('mbt_painter_id') == entry['object_id'])
                material = obj.data.materials[0]
                for channel, template in channels.items():
                    image = material.node_tree.nodes['MBT_' + channel].image
                    assert Path(image.filepath).name == template.replace('{texture_set}', entry['texture_set'])
                    assert tuple(image.size) == (512, 512)
                assert material.node_tree.nodes.get('MBT_ao') is None, 'Stale AO imported from previous export'
            report['checks'].append('Installed custom preset: preflight, real export, exact filenames, import, no stale AO')
            report.update(status='PASS', mapping=mapping, job=settings.last_job,
                          panel_draws=MBT_PT_live_bake_smoke.draws,
                          limitations=['Panel draw count may be zero unless its sidebar tab is selected',
                                       'No OS mouse/keyboard simulation or human visual review'])
            assert 'draw_error' not in report, report.get('draw_error')
            assert report.get('popup_drawn'), 'Real-layout Bake drawing did not execute'
        except Exception:
            report.update(status='FAIL', error=traceback.format_exc())
            traceback.print_exc()
        destination.write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(report['status'] + ': LIVE CUSTOM UPDATE ' + str(destination), flush=True)
        bpy.utils.unregister_class(MBT_PT_live_bake_smoke)
        bpy.ops.wm.quit_blender()
        return None

    bpy.app.timers.register(tick, first_interval=1)


if __name__ == '__main__':
    if '--live' not in sys.argv or '--blend' not in sys.argv or bpy.app.background:
        raise RuntimeError('Requires disposable GUI Blender, -- --live --blend <matrix blend>')
    blend = Path(sys.argv[sys.argv.index('--blend') + 1]).resolve()
    if not blend.parent.name.startswith('MBToolkit_Painter_Matrix_') or blend.name != 'live_matrix.blend':
        raise RuntimeError('Refusing non-matrix blend')
    bpy.ops.wm.open_mainfile(filepath=str(blend))

    def begin():
        try:
            main()
        except Exception:
            (blend.parent / 'update_result.json').write_text(json.dumps(
                {'status': 'FAIL', 'error': traceback.format_exc()}, indent=2), encoding='utf-8')
            traceback.print_exc()
            bpy.ops.wm.quit_blender()
        return None

    # File loading replaces windows/regions; wait until the GUI context is rebuilt.
    bpy.app.timers.register(begin, first_interval=1)