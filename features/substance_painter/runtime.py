"""Network work off the UI thread; Blender state touched only by a main-thread timer."""
import queue
import threading
import time
import bpy
from bpy.app.handlers import persistent
from ...core.addon import get_prefs
from . import bridge, jobs
from . import preparation

_pending = None
_generation = 0
_cancel = None
_timer = None
_preparation = None
_scene = None


def cancel():
    if _cancel is not None:
        _cancel.set()
        # Worker callbacks only signal the event; RNA is main-thread-only.
        if threading.current_thread() is threading.main_thread() and _scene is not None:
            try:
                _scene.mbt_painter.report = 'Cancellation requested…'
            except (ReferenceError, AttributeError):
                pass
            redraw()


def busy():
    return _pending is not None


def redraw():
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            area.tag_redraw()


def start_preparation(context, action, ignore_warnings=False):
    """Advance one main-thread preparation step per UI tick; close unwinds snapshots."""
    global _pending, _cancel, _timer, _preparation, _scene
    scene = context.scene
    window = context.window
    if busy():
        raise jobs.PainterError('A Painter request is already running')
    initial_signature = preparation.signature(context)
    generation = _generation
    cancellation = threading.Event()
    _scene = scene
    _pending = queue.Queue()
    _cancel = cancellation
    _preparation = preparation.measured_steps(context, jobs.prepare_steps(
        context, automatic=action == 'AUTO', ignore_warnings=ignore_warnings))
    scene.mbt_painter.report = 'Preparing mesh snapshots'
    started = time.monotonic()

    def advance():
        global _pending, _cancel, _timer, _preparation
        if generation != _generation:
            return None
        try:
            if cancellation.is_set():
                cleanup()
                scene.mbt_painter.report = 'Bake cancelled during preparation; Painter was not started.'
                redraw()
                return None
            if bpy.context.scene != scene or bpy.context.mode != 'OBJECT':
                raise jobs.PainterError('Scene or mode changed during preparation; bake stopped')
            if window is not None and window not in tuple(bpy.context.window_manager.windows):
                raise jobs.PainterError('Preparation window was closed; bake stopped')
            if preparation.signature(bpy.context) != initial_signature:
                raise jobs.PainterError('Bake inputs or settings changed during preparation; bake stopped. Retry Bake.')
            # UI timers do not inherit an operator context. Retain the initiating window.
            with bpy.context.temp_override(window=window, scene=scene):
                message = next(_preparation)
            scene.mbt_painter.report = f'{message} ({int(time.monotonic() - started)}s)'
            redraw()
            return 0.05
        except StopIteration:
            _preparation = None
            _pending = None
            _cancel = None
            _timer = None
            try:
                start(bpy.context, action, ignore_warnings=ignore_warnings, _prepared=True)
            except Exception as error:
                cleanup()
                scene.mbt_painter.report = 'Painter startup failed: ' + str(error)
                redraw()
            return None
        except Exception as error:
            cleanup()
            try:
                scene.mbt_painter.report = 'Preparation failed: ' + str(error)
            except (ReferenceError, AttributeError):
                pass
            if isinstance(error, jobs.ValidationIssues):
                from .operators import show_issues
                show_issues(bpy.context, error, action, connect=True)
            redraw()
            return None

    _timer = advance
    try:
        bpy.app.timers.register(advance, first_interval=0.05)
        redraw()
    except Exception:
        cleanup()
        raise


def start(context, action, ignore_warnings=False, _prepared=False):
    global _pending, _cancel, _timer, _scene
    if busy():
        raise jobs.PainterError('A Painter connection/send request is already running')
    prefs = get_prefs(context)
    if prefs is None:
        raise jobs.PainterError('Enable MBToolkit to access Painter preferences')
    if action in {'SEND', 'BAKE_NEW', 'AUTO'} and not _prepared and not bpy.app.background:
        start_preparation(context, action, ignore_warnings=ignore_warnings)
        return
    executable = bpy.path.abspath(prefs.painter_executable) if prefs.painter_executable else bridge.detect_executable()
    port = prefs.painter_port
    job_path = ''
    project_file = bpy.path.abspath(context.scene.mbt_painter.project_file)
    if action == 'OPEN':
        from pathlib import Path
        if not project_file or not Path(project_file).is_file():
            raise jobs.PainterError('Associated Painter project does not exist yet; complete a bake first')
    if action in {'SEND', 'BAKE_NEW', 'AUTO'}:
        if not _prepared:
            context.scene.mbt_painter.report = 'Preparing mesh snapshots'
            if ignore_warnings:
                jobs.prepare(context, automatic=action == 'AUTO', ignore_warnings=True)
            else:
                jobs.prepare(context, automatic=action == 'AUTO')
        job_path = context.scene.mbt_painter.last_job
    elif action in {'EXPORT', 'BAKE'}:
        if context.mode != 'OBJECT':
            raise jobs.PainterError('Switch to Object Mode before export/import')
        job_path = bpy.path.abspath(context.scene.mbt_painter.last_job)
        jobs.read_job(job_path)
        if action == 'BAKE':
            jobs.update_bake_settings(job_path, context.scene.mbt_painter)
    scene = context.scene
    _scene = scene
    scene.mbt_painter.report = 'Connecting to Painter...'
    started = time.monotonic()
    stage = 'Connecting to Painter'
    results = queue.Queue()
    generation = _generation
    _pending = results
    cancellation = threading.Event()
    _cancel = cancellation if action in {'BAKE', 'BAKE_NEW', 'AUTO'} else None

    def progress(message):
        results.put((False, message))

    def work():
        client = None
        protected = False
        completion = 'Painter request did not complete'
        try:
            client, info = bridge.connect(port, executable, allow_launch=action in {'OPEN', 'SEND', 'CONNECT', 'BAKE_NEW', 'AUTO'}, progress=progress)
            if action == 'OPEN':
                client.execute(f'_mbt_open_project({project_file!r})')
                completion = 'Opened Painter project: ' + project_file
                return
            if not info.get('can_create'):
                raise bridge.BridgeError('Painter is missing required APIs: ' + ', '.join(info.get('missing', [])))
            if cancellation.is_set():
                raise bridge.BridgeError('Workflow cancelled before project creation/baking')
            if action in {'BAKE', 'BAKE_NEW', 'AUTO'}:
                client.execute('_mbt_guard_acquire()')
                protected = True
            if action in {'SEND', 'BAKE_NEW', 'AUTO'}:
                result = bridge.send(client, job_path, progress=progress, update=action == 'AUTO')
                message = 'Painter project saved: ' + result['project_file'] + '. Baking has not been run.'
            if action in {'BAKE', 'BAKE_NEW', 'AUTO'}:
                if cancellation.is_set():
                    raise bridge.BridgeError('Workflow cancelled before baking')
                result = bridge.bake(client, job_path, cancel=cancellation, progress=progress)
                completion = result
                return
            elif action == 'EXPORT':
                progress('Exporting PBR textures from Painter')
                result = bridge.export_maps(client, job_path)
                completion = result
                return
            elif action != 'SEND':
                message = f"Connected to Painter (Python API {info['version']}); project open: {info['project_open']}; busy: {info['busy']}"
            completion = message
        except Exception as error:
            completion = 'Failed — Painter: ' + str(error)
        finally:
            if protected:
                try:
                    client.execute('_mbt_guard_release()')
                except Exception as error:
                    # The Painter-side watchdog also restores input after lost connections.
                    completion = 'Painter UI restore pending watchdog; check Painter before retrying: ' + str(error)
            results.put((True, completion))

    def poll():
        global _pending, _cancel, _timer, _scene
        nonlocal stage
        if generation != _generation:
            return None
        done = False
        while True:
            try:
                done, stage = results.get_nowait()
            except queue.Empty:
                break
            if done:
                break
        message = stage if done else f'{stage} ({int(time.monotonic() - started)}s)'
        if done:
            _pending = None
            _cancel = None
            _timer = None
            _scene = None
        try:
            if scene.name in bpy.data.scenes:
                if done and isinstance(message, dict):
                    try:
                        if scene != bpy.context.scene or bpy.path.abspath(scene.mbt_painter.last_job) != job_path:
                            raise jobs.PainterError('Active scene/job changed during export; import was skipped')
                        jobs.record_export(job_path, message)
                        if cancellation.is_set():
                            raise jobs.PainterError('Workflow cancelled during export; textures recorded but material import was skipped')
                        from . import materials
                        message = 'Exported from Painter. ' + materials.import_maps(bpy.context)
                    except Exception as error:
                        message = 'Export/import failed: ' + str(error)
                scene.mbt_painter.report = message
        except ReferenceError:
            pass  # File reload/deleted scene while the remote request was running.
        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                area.tag_redraw()
        return None if done else 0.2

    _timer = poll
    try:
        bpy.app.timers.register(poll, first_interval=0.2)
        threading.Thread(target=work, daemon=True).start()
    except Exception:
        cleanup()
        raise


def cleanup():
    global _pending, _generation, _cancel, _timer, _preparation, _scene
    cancel()
    _generation += 1
    _pending = None
    _cancel = None
    if _timer is not None and bpy.app.timers.is_registered(_timer):
        bpy.app.timers.unregister(_timer)
    _timer = None
    if _preparation is not None:
        steps, _preparation = _preparation, None
        try:
            steps.close()
        except (ReferenceError, RuntimeError, AttributeError) as error:
            print('Painter preparation cleanup warning:', error)
        finally:
            _scene = None
    else:
        _scene = None


@persistent
def _load_pre(_):
    # Non-persistent timers disappear on file load; invalidate their queued results
    # before Blender replaces the scene, and ask the old worker to stop cooperatively.
    cleanup()


def register():
    if _load_pre not in bpy.app.handlers.load_pre:
        bpy.app.handlers.load_pre.append(_load_pre)


def unregister():
    cleanup()
    if _load_pre in bpy.app.handlers.load_pre:
        bpy.app.handlers.load_pre.remove(_load_pre)