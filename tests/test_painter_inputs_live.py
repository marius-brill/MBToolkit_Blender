"""Opt-in real bake for grouped lows and offset mirrored UVs; disposable Blender."""
import importlib
import json
from pathlib import Path
import sys
import tempfile
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))


def main():
    assert bpy.app.background and '--live' in sys.argv
    addon = importlib.import_module(ROOT.name)
    bridge = importlib.import_module(ROOT.name + '.features.substance_painter.bridge')
    jobs = importlib.import_module(ROOT.name + '.features.substance_painter.jobs')
    client, info = bridge.connect(60041, bridge.detect_executable(), allow_launch=True)
    if info['project_open'] or info['busy']:
        print('SKIPPED: existing Painter project/busy; untouched', flush=True)
        return
    directory = Path(tempfile.mkdtemp(prefix='MBToolkit_Painter_Inputs_Live_'))
    print('LIVE_DIRECTORY=' + str(directory), flush=True)
    addon.register()
    addon.feature_manager.sync(type('Settings', (), {'enable_substance_painter': True})())
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    settings = bpy.context.scene.mbt_painter
    lows = []
    for index in range(2):
        bpy.ops.mesh.primitive_cube_add()
        obj = bpy.context.object
        obj.name = f'body_low_{index}'
        obj.mbt_bake_group = 'Body'
        bpy.ops.mbt.painter_assign(role='LOW')
        # Offset a whole face/island, not individual corners, like a mirrored shell.
        for loop in obj.data.polygons[0].loop_indices:
            obj.data.uv_layers.active.data[loop].uv.x += 1 if index == 0 else -1
        lows.append(obj)
    bpy.ops.mesh.primitive_cube_add()
    high = bpy.context.object
    high.name = 'body_high'
    high.mbt_bake_group = 'Body'
    bevel = high.modifiers.new('Bake detail', 'BEVEL')
    bevel.width, bevel.segments = 0.04, 3
    bpy.ops.mbt.painter_assign(role='HIGH')
    settings.output_dir = str(directory)
    settings.resolution = '512'
    settings.bake_maps = {'NORMAL', 'AO'}
    settings.antialiasing = 'None'
    settings.low_collection.hide_viewport = True
    jobs.prepare(bpy.context, automatic=True)
    job = jobs.read_job(settings.last_job)
    guarded = False
    try:
        client.execute('_mbt_guard_acquire()')
        guarded = True
        bridge.send(client, settings.last_job, update=True, progress=lambda message: print(message, flush=True))
        result = bridge.bake(client, settings.last_job, progress=lambda message: print(message, flush=True))
        assert result['state'] == 'EXPORTED'
        assert len(result['texture_sets']) == 2
        jobs.record_export(settings.last_job, result)
        materials = importlib.import_module(ROOT.name + '.features.substance_painter.materials')
        materials.import_maps(bpy.context)
        assert all(obj.data.materials for obj in lows)
        assert settings.low_collection.hide_viewport
        (directory / 'result.json').write_text(json.dumps({'status': 'PASS', 'job': settings.last_job,
            'checks': ['two lows to one high', 'positive/negative offset islands', 'hidden low collection',
                       'protected Painter window', 'bake/save/export/import']}, indent=2))
        print('PASS LIVE: two lows/one high, offset islands, hidden collection, protected bake/save/export/import', flush=True)
    finally:
        if guarded:
            client.execute('_mbt_guard_release()')
        # Close only our exact disposable project; retained files are available for inspection.
        client.execute(f'(__import__("substance_painter.project", fromlist=["project"]).close() '
                       f'if _mbt_project.is_open() and str(_MBTPath(_mbt_project.file_path()).resolve()) == '
                       f'{str(Path(job["project_file"]).resolve())!r} and not _mbt_project.is_busy() else None, '
                       f'__import__("json").dumps({{"closed_test_only": True}}))[1]')
    addon.unregister()


if __name__ == '__main__':
    main()