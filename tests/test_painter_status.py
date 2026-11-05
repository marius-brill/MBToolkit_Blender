"""Fixed-row status and independent clock regressions; disposable Blender only."""
import importlib
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch

import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon = importlib.import_module(ROOT.name)
painter = importlib.import_module(ROOT.name + '.features.substance_painter')
runtime = painter.operators.runtime


def main():
    assert bpy.app.background
    addon.register()
    addon.feature_manager.sync(SimpleNamespace(enable_substance_painter=True))
    for width in (8, 20, 36, 80):
        for report in ('Ready', 'Evaluating low surface: Object_003',
                       'Surface matching: ' + 'VeryLongMeshName' * 30,
                       'Preparation failed: ' + 'issue; ' * 500):
            lines = painter.status_lines(report, width)
            assert len(lines) == 2 and all(len(line) <= width for line in lines)
            assert not any('Elapsed:' in line for line in lines)
    with patch.object(runtime.time, 'monotonic', return_value=100) as clock:
        runtime.begin_clock()
        clock.return_value = 388
        assert runtime.elapsed_seconds() == 288
        bpy.context.scene.mbt_painter.report = 'Surface matching: ' + 'ChangingName' * 30
        assert runtime.elapsed_seconds() == 288
        runtime.finish_clock()
        clock.return_value = 1000
        assert runtime.elapsed_seconds() == 288
        runtime.begin_clock()
        assert runtime.elapsed_seconds() == 0
        clock.return_value = 1007
        runtime.cleanup()
        clock.return_value = 2000
        assert runtime.elapsed_seconds() == 7
    # Handoff preserves the same clock; long running phases never embed seconds.
    settings = bpy.context.scene.mbt_painter
    def steps(*args, **kwargs):
        yield 'Surface matching: ' + 'LongName' * 100
        yield 'Evaluating low surface: Object_003'
    with patch.object(runtime.preparation, 'signature', return_value=()), \
            patch.object(runtime.jobs, 'prepare_steps', side_effect=steps), \
            patch.object(runtime, 'start') as launch, \
            patch.object(runtime.time, 'monotonic', return_value=10) as clock:
        runtime.start_preparation(bpy.context, 'AUTO')
        timer = runtime._timer
        clock.return_value = 298
        assert timer() == 0.05
        assert runtime.elapsed_seconds() == 288
        assert settings.report.startswith('Surface matching:') and '(288s)' not in settings.report
        clock.return_value = 298.05
        previous = settings.report
        assert timer() == 0.05 and settings.report == previous  # throttle text, not work
        assert timer() is None
        launch.assert_called_once()
        assert runtime.elapsed_seconds() == 288.05
        if bpy.app.timers.is_registered(timer):
            bpy.app.timers.unregister(timer)
        runtime.cleanup()
    assert bpy.ops.mbt.painter_status_details(report_text='Full untruncated details') == {'FINISHED'}
    addon.unregister()
    print('PASS: bounded two-row status, independent monotonic clock, frozen completion/cancellation, details operator', flush=True)


if __name__ == '__main__':
    main()