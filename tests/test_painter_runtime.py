"""AUTO orchestration and lifecycle tests; disposable background Blender only.

Painter/network, preparation and import boundaries are controlled. A real worker
thread and Blender timer exercise orchestration without launching Painter.
"""
import importlib
from pathlib import Path
import sys
import threading
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, patch

import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon = importlib.import_module(ROOT.name)
runtime = importlib.import_module(ROOT.name + '.features.substance_painter.runtime')
materials = importlib.import_module(ROOT.name + '.features.substance_painter.materials')


def main():
    assert bpy.app.background
    addon.register()
    addon.feature_manager.sync(SimpleNamespace(enable_substance_painter=True))
    main_thread = threading.get_ident()
    prefs = SimpleNamespace(painter_executable='', painter_port=60041)
    original_thread = threading.Thread
    with TemporaryDirectory() as folder:
        path = str(Path(folder) / 'job.json')
        scene = bpy.context.scene
        settings = scene.mbt_painter
        workers = []

        def thread(**kwargs):
            worker = original_thread(**kwargs)
            workers.append(worker)
            return worker

        def prepare(context, automatic=False):
            assert automatic and threading.get_ident() == main_thread
            context.scene.mbt_painter.last_job = path

        def connect(*args, **kwargs):
            assert threading.get_ident() != main_thread
            assert kwargs['allow_launch']
            kwargs['progress']('Controlled connection')
            return client, {'can_create': True}

        def record(*args):
            assert threading.get_ident() == main_thread
            calls.append('record')

        def import_maps(context):
            assert threading.get_ident() == main_thread
            assert context.scene == scene
            calls.append('import')
            return 'Materials updated'

        client = Mock()
        calls = []
        exported = {'state': 'EXPORTED', 'job_id': 'controlled'}
        with patch.object(runtime, 'get_prefs', return_value=prefs), \
                patch.object(runtime.bridge, 'detect_executable', return_value=''), \
                patch.object(runtime.jobs, 'prepare', side_effect=prepare) as prepared, \
                patch.object(runtime.bridge, 'connect', side_effect=connect), \
                patch.object(runtime.bridge, 'send', return_value={'project_file': 'asset.spp'}) as send, \
                patch.object(runtime.bridge, 'bake', return_value=exported) as bake, \
                patch.object(runtime.jobs, 'record_export', side_effect=record) as recorded, \
                patch.object(materials, 'import_maps', side_effect=import_maps) as imported, \
                patch.object(runtime.threading, 'Thread', side_effect=thread):

            def finish():
                workers[-1].join(timeout=5)
                assert not workers[-1].is_alive(), 'Controlled worker did not finish'
                timer = runtime._timer
                assert timer is not None and bpy.app.timers.is_registered(timer)
                # Calling a timer directly does not automatically unregister it.
                assert timer() is None
                if bpy.app.timers.is_registered(timer):
                    bpy.app.timers.unregister(timer)
                assert not runtime.busy() and runtime._cancel is None
                return settings.report

            runtime.start(bpy.context, 'AUTO')
            assert 'Materials updated' in finish()
            prepared.assert_called_once_with(bpy.context, automatic=True)
            assert send.call_args.kwargs['update']
            assert bake.call_args.args == (client, path)
            assert calls == ['record', 'import']

            calls.clear()
            send.side_effect = runtime.bridge.BridgeError('reload failed')
            bake.reset_mock()
            runtime.start(bpy.context, 'AUTO')
            assert 'reload failed' in finish()
            bake.assert_not_called()
            assert not calls
            send.side_effect = None

            def cancel_send(*args, **kwargs):
                runtime.cancel()
                return {'project_file': 'asset.spp'}

            send.side_effect = cancel_send
            runtime.start(bpy.context, 'AUTO')
            assert 'cancelled before baking' in finish()
            bake.assert_not_called()
            assert not calls
            send.side_effect = None

            def cancel_export(*args, **kwargs):
                kwargs['cancel'].set()
                return exported

            bake.side_effect = cancel_export
            runtime.start(bpy.context, 'AUTO')
            assert 'textures recorded but material import was skipped' in finish()
            assert calls == ['record']
            calls.clear()
            bake.side_effect = None

            runtime.start(bpy.context, 'AUTO')
            settings.last_job = str(Path(folder) / 'other.json')
            assert 'Active scene/job changed' in finish()
            assert not calls

            other = bpy.data.scenes.new('OtherRuntimeScene')
            runtime.start(bpy.context, 'AUTO')
            bpy.context.window.scene = other
            try:
                assert 'Active scene/job changed' in finish()
                assert not calls
            finally:
                bpy.context.window.scene = scene
                bpy.data.scenes.remove(other)

            bake.side_effect = runtime.bridge.BridgeError('bake failed')
            runtime.start(bpy.context, 'AUTO')
            assert 'bake failed' in finish()
            assert not calls
            bake.side_effect = None

            entered, release = threading.Event(), threading.Event()

            def blocked_connect(*args, **kwargs):
                entered.set()
                assert release.wait(timeout=5), 'Worker release timed out'
                return client, {'can_create': True}

            # Teardown must also cancel a worker still inside a remote request.
            calls.clear()
            send.reset_mock()
            bake.reset_mock()
            with patch.object(runtime.bridge, 'connect', side_effect=blocked_connect):
                runtime.start(bpy.context, 'AUTO')
                try:
                    assert entered.wait(timeout=5)
                    old_timer, cancellation = runtime._timer, runtime._cancel
                    assert old_timer() == 0.2 and runtime.busy()
                    runtime.unregister()
                    assert cancellation.is_set() and not runtime.busy()
                finally:
                    release.set()
                    workers[-1].join(timeout=5)
                assert not workers[-1].is_alive()
                assert old_timer() is None and not calls
                send.assert_not_called()
                bake.assert_not_called()
                runtime.register()

            # Retain a completed worker's result, then invalidate it before polling.
            runtime.start(bpy.context, 'AUTO')
            workers[-1].join(timeout=5)
            old_timer, cancellation = runtime._timer, runtime._cancel
            runtime.unregister()
            assert cancellation.is_set() and not runtime.busy()
            assert not bpy.app.timers.is_registered(old_timer)
            assert old_timer() is None and not calls
            assert runtime._load_pre not in bpy.app.handlers.load_pre
            runtime.register()
            runtime.register()
            assert bpy.app.handlers.load_pre.count(runtime._load_pre) == 1
            runtime.start(bpy.context, 'AUTO')
            assert 'Materials updated' in finish()

            # Startup failure must not leave a busy flag or registered timer.
            with patch.object(runtime.threading, 'Thread', side_effect=RuntimeError('thread failed')):
                try:
                    runtime.start(bpy.context, 'AUTO')
                except RuntimeError as error:
                    assert 'thread failed' in str(error)
                else:
                    raise AssertionError('Expected thread startup failure')
            assert not runtime.busy() and runtime._timer is None

            # A real file reload must clear the pending request before scenes vanish.
            blend = str(Path(folder) / 'runtime.blend')
            bpy.ops.wm.save_as_mainfile(filepath=blend)
            calls.clear()
            runtime.start(bpy.context, 'AUTO')
            workers[-1].join(timeout=5)
            old_timer, cancellation = runtime._timer, runtime._cancel
            bpy.ops.wm.open_mainfile(filepath=blend)
            assert cancellation.is_set() and not runtime.busy()
            assert runtime._timer is None and old_timer() is None
            assert not calls
    addon.unregister()
    assert runtime._load_pre not in bpy.app.handlers.load_pre
    print('PASS: AUTO worker/main-thread handoff, failures, cancellation, scene/job guards, teardown, restart and file reload', flush=True)


if __name__ == '__main__':
    main()