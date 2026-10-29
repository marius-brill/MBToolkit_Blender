"""Synthetic preparation benchmark; disposable background process, no Painter."""
import importlib
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace

import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon = importlib.import_module(ROOT.name)
jobs = importlib.import_module(ROOT.name + '.features.substance_painter.jobs')
preparation = importlib.import_module(ROOT.name + '.features.substance_painter.preparation')
evaluation = importlib.import_module(ROOT.name + '.features.substance_painter.evaluation')


def main():
    assert bpy.app.background
    addon.register()
    addon.feature_manager.sync(SimpleNamespace(enable_substance_painter=True))
    bpy.ops.mesh.primitive_cube_add()
    low = bpy.context.object
    low.name = 'Benchmark_low'
    bpy.ops.mbt.painter_assign(role='LOW')
    bpy.ops.mesh.primitive_uv_sphere_add(segments=256, ring_count=128)
    high = bpy.context.object
    high.name = 'Benchmark_high'
    subdivision = high.modifiers.new('Benchmark subdivision', 'SUBSURF')
    subdivision.levels = 2
    bpy.ops.mbt.painter_assign(role='HIGH')
    settings = bpy.context.scene.mbt_painter
    with tempfile.TemporaryDirectory(prefix='mbt_benchmark_') as folder:
        settings.output_dir = folder
        evaluation.finish_steps(preparation.measured_steps(
            bpy.context, jobs.prepare_steps(bpy.context, automatic=True)))
        records = json.loads(settings.preparation_timings)
        assert any('high-poly FBX' in item['stage'] for item in records)
        assert all(item['seconds'] >= 0 for item in records)
        result = {'blender': bpy.app.version_string, 'fixture': '256x128 sphere, subdivision 2',
                  'high_base_faces': len(high.data.polygons), 'steps': records,
                  'active_seconds': sum(item['seconds'] for item in records)}
        destination = Path(tempfile.gettempdir()) / 'mbt_painter_performance.json'
        destination.write_text(json.dumps(result, indent=2))
        print('PASS: synthetic preparation benchmark:', destination, flush=True)
    addon.unregister()


if __name__ == '__main__':
    main()