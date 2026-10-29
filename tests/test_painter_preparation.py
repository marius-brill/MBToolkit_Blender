"""Disposable background checks for staged preparation and early cancellation."""
import importlib
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon = importlib.import_module(ROOT.name)
jobs = importlib.import_module(ROOT.name + '.features.substance_painter.jobs')
runtime = importlib.import_module(ROOT.name + '.features.substance_painter.runtime')


def counts():
    return tuple(len(data) for data in (bpy.data.objects, bpy.data.meshes,
                                      bpy.data.materials, bpy.data.scenes))


def main():
    assert bpy.app.background
    addon.register()
    addon.feature_manager.sync(SimpleNamespace(enable_substance_painter=True))
    settings = bpy.context.scene.mbt_painter
    bpy.ops.mesh.primitive_cube_add()
    low = bpy.context.object
    low.name = 'Preparation_low'
    bpy.ops.mbt.painter_assign(role='LOW')
    bpy.ops.mesh.primitive_cube_add()
    high = bpy.context.object
    high.name = 'Preparation_high'
    bpy.ops.mbt.painter_assign(role='HIGH')
    high.hide_set(True)
    high.hide_select = True
    original = counts()
    with TemporaryDirectory() as folder:
        settings.output_dir = folder
        settings.last_job = str(Path(folder) / 'removed_bake' / 'job.json')
        settings.project_file = str(Path(folder) / 'painting.spp')
        stored_job, stored_project = settings.last_job, settings.project_file
        with patch.object(jobs, 'validate_steps') as validate:
            try:
                jobs.prepare(bpy.context, automatic=True)
            except jobs.PainterError as error:
                assert 'Saved bake job.json is missing:' in str(error)
                assert 'New Project Next Bake' in str(error)
            else:
                raise AssertionError('Missing persisted job must not silently reset painting')
            validate.assert_not_called()
        assert settings.last_job == stored_job and settings.project_file == stored_project
        assert not list(Path(folder).iterdir())
        settings.last_job = ''
        settings.project_file = ''
        # Close at every published stage, including after snapshots/low FBX exist.
        stages = []
        for stop in range(1, 30):
            steps = jobs.prepare_steps(bpy.context, automatic=True)
            complete = False
            try:
                for _ in range(stop):
                    message = next(steps)
                    if message not in stages:
                        stages.append(message)
            except StopIteration:
                complete = True
            finally:
                steps.close()
            assert counts() == original
            assert high.hide_get() and high.hide_select
            if complete:
                break
            assert not list(Path(folder).iterdir()), list(Path(folder).iterdir())
            assert not settings.last_job and not settings.project_file
        else:
            raise AssertionError('Preparation did not complete within step budget')
        assert any('Validating' in stage for stage in stages)
        assert any('Matching' in stage for stage in stages)
        assert 'Exporting high-poly FBX' in stages
        assert Path(settings.last_job).is_file()

        settings.last_job = ''
        settings.project_file = ''
        with patch.object(runtime.bridge, 'connect') as connect:
            runtime.start_preparation(bpy.context, 'AUTO')
            timer = runtime._timer
            assert runtime.busy() and runtime._cancel is not None
            assert timer() == 0.05
            runtime.cancel()
            assert 'Cancellation requested' in settings.report
            assert timer() is None
            assert not runtime.busy() and runtime._preparation is None
            assert 'cancelled during preparation' in settings.report
            connect.assert_not_called()
        assert counts() == original and high.hide_get()
        assert json.loads(settings.preparation_timings)
        # Exercise all staged ticks through the prepared-to-worker handoff without network.
        with patch.object(runtime, 'start') as launch:
            runtime.start_preparation(bpy.context, 'AUTO')
            timer = runtime._timer
            for _ in range(40):
                if timer() is None:
                    break
            else:
                raise AssertionError('Staged timer did not reach handoff')
            if bpy.app.timers.is_registered(timer):
                bpy.app.timers.unregister(timer)
            launch.assert_called_once_with(bpy.context, 'AUTO', ignore_warnings=False, _prepared=True)
            assert not runtime.busy()
            runtime.cleanup()
        # A user edit between ticks must prevent Painter launch and release state.
        with patch.object(runtime.bridge, 'connect') as connect:
            runtime.start_preparation(bpy.context, 'AUTO')
            timer = runtime._timer
            assert timer() == 0.05
            high.name = 'RenamedDuringPreparation'
            assert timer() is None
            assert 'inputs or settings changed' in settings.report
            assert not runtime.busy() and runtime._scene is None
            connect.assert_not_called()
        # Restore surviving state even after an input is deleted and collection renamed.
        evaluation = importlib.import_module(ROOT.name + '.features.substance_painter.evaluation')
        collection = settings.high_collection
        with evaluation.available(bpy.context, [low, high]):
            collection.name = 'RenamedCollection'
            bpy.data.objects.remove(high, do_unlink=True)
            low.select_set(True)
        assert collection.name == 'RenamedCollection'
        assert runtime._scene is None
    addon.unregister()
    print('PASS: staged preparation, snapshot/output cleanup, hidden-state restoration, early runtime cancellation', flush=True)


if __name__ == '__main__':
    main()