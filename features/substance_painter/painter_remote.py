"""Executed INSIDE Painter via the local remote endpoint, never imported by Blender."""
import json as _mbt_json
from pathlib import Path as _MBTPath
import substance_painter as _mbt_sp
import substance_painter.project as _mbt_project
import substance_painter.textureset as _mbt_textureset

if '_mbt_state' not in globals():
    _mbt_state = {'state': 'IDLE'}


def _mbt_probe():
    required = ('create', 'save_as', 'is_open', 'is_busy', 'is_in_edition_state',
                'execute_when_not_busy', 'Settings', 'NormalMapFormat')
    missing = [name for name in required if not hasattr(_mbt_project, name)]
    return _mbt_json.dumps({
        'version': str(getattr(_mbt_sp, '__version__', 'unknown')),
        'project_open': _mbt_project.is_open(), 'busy': _mbt_project.is_busy(),
        'missing': missing, 'can_create': not missing,
    })


def _mbt_guard_touch():
    import time
    globals()['_mbt_guard_deadline'] = time.monotonic() + 300


def _mbt_guard_release(show=False):
    state = globals().pop('_mbt_guard_window', None)
    timer = globals().pop('_mbt_guard_timer', None)
    if timer is not None:
        timer.stop()
        timer.deleteLater()
    if state is not None:
        window, enabled, visible = state
        window.setEnabled(enabled)
        if visible or show:
            window.show()
    if show:
        import substance_painter.ui as ui
        ui.show_main_window()
    return _mbt_json.dumps({'state': 'RELEASED'})


def _mbt_guard_acquire():
    """Disable/hide Painter during automation; watchdog recovers lost Blender clients."""
    if globals().get('_mbt_guard_window') is not None:
        return _mbt_json.dumps({'error': 'Painter is already reserved for an automated bake'})
    try:
        import time
        import substance_painter.ui as ui
        from PySide6.QtCore import QTimer
        window = ui.get_main_window()
        globals()['_mbt_guard_window'] = (window, window.isEnabled(), window.isVisible())
        _mbt_guard_touch()
        timer = QTimer(window)
        def watchdog():
            if time.monotonic() > globals().get('_mbt_guard_deadline', 0):
                _mbt_guard_release(show=True)
        timer.timeout.connect(watchdog)
        globals()['_mbt_guard_timer'] = timer
        timer.start(1000)
        window.setEnabled(False)
        window.hide()
        return _mbt_json.dumps({'state': 'RESERVED'})
    except Exception as error:
        _mbt_guard_release()
        return _mbt_json.dumps({'error': 'Cannot protect Painter UI: ' + str(error)})


def _mbt_open_project(project_file):
    try:
        if globals().get('_mbt_guard_window') is not None:
            raise RuntimeError('Painter is reserved for an automated bake')
        path = _MBTPath(project_file).resolve()
        if not path.is_file() or path.suffix.lower() != '.spp':
            raise RuntimeError('Associated Painter project does not exist yet; complete a bake first')
        if _mbt_project.is_busy():
            raise RuntimeError('Painter is busy')
        if _mbt_project.is_open():
            if _MBTPath(_mbt_project.file_path()).resolve() != path:
                raise RuntimeError('An unrelated Painter project is open. Save and close it first')
        else:
            _mbt_project.open(str(path))
        import substance_painter.ui as ui
        ui.show_main_window()
        return _mbt_json.dumps({'state': 'OPENED', 'project_file': str(path)})
    except Exception as error:
        return _mbt_json.dumps({'error': str(error)})


def _mbt_status():
    _mbt_guard_touch()
    if _mbt_state.get('state') in {'OPENING', 'RELOADED'} and not _mbt_project.is_busy() and _mbt_project.is_in_edition_state():
        if _mbt_state['state'] == 'OPENING':
            return _mbt_update(_mbt_state['job_path'])
        job = _mbt_json.loads(_MBTPath(_mbt_state['job_path']).read_text(encoding='utf-8'))
        if sorted(ts.name() for ts in _mbt_textureset.all_texture_sets()) != sorted(e['texture_set'] for e in job['texture_sets']):
            _mbt_state.update(state='FAILED', error='Texture sets changed during mesh reload; baking stopped')
        else:
            _mbt_state.update(state='COMPLETE', project_file=job['project_file'],
                              texture_sets=sorted(e['texture_set'] for e in job['texture_sets']))
    if (_mbt_state.get('state') == 'CREATING' and _mbt_project.is_in_edition_state()
            and not _mbt_project.is_busy()):
        _mbt_finish()
    return _mbt_json.dumps(_mbt_state)


def _mbt_create(job_path):
    global _mbt_state, _mbt_finish
    try:
        if _mbt_state.get('state') == 'CREATING':
            raise RuntimeError('An MBToolkit project request is already running')
        if _mbt_project.is_open() or _mbt_project.is_busy():
            raise RuntimeError('Painter has an open project or is busy. Save and close it yourself before sending.')
        path = _MBTPath(job_path)
        job = _mbt_json.loads(path.read_text(encoding='utf-8'))
        if job.get('schema_version') != 1:
            raise RuntimeError('Unsupported job schema')
        if not _MBTPath(job['low_mesh']).is_file():
            raise RuntimeError('Low FBX not found')
        if _MBTPath(job['project_file']).exists():
            raise RuntimeError('Refusing to overwrite an existing Painter project')
        settings = _mbt_project.Settings(
            normal_map_format=(_mbt_project.NormalMapFormat.OpenGL if job['normal_format'] == 'OPENGL'
                               else _mbt_project.NormalMapFormat.DirectX),
            default_texture_resolution=job['resolution'], import_cameras=False)
        _mbt_state = {'state': 'CREATING', 'job_id': job['job_id']}
        arguments = {'mesh_file_path': job['low_mesh'], 'settings': settings}
        if job.get('project_template'):
            arguments['template_file_path'] = job['project_template']
        _mbt_project.create(**arguments)

        def finish():
            global _mbt_state
            try:
                if not _mbt_project.is_in_edition_state():
                    raise RuntimeError('Painter project did not enter edition state')
                actual = sorted(item.name() for item in _mbt_textureset.all_texture_sets())
                expected = sorted(item['texture_set'] for item in job['texture_sets'])
                if actual != expected:
                    raise RuntimeError(f'Texture sets differ: expected {expected}, got {actual}')
                if _MBTPath(job['project_file']).exists():
                    raise RuntimeError('Project file already exists; refusing overwrite')
                _mbt_project.save_as(job['project_file'])
                _mbt_state = {'state': 'COMPLETE', 'project_file': job['project_file'],
                              'texture_sets': actual, 'job_id': job['job_id']}
            except Exception as error:
                _mbt_state = {'state': 'FAILED', 'error': str(error)}

        # Not-busy alone can occur before edition state is entered. Status polling
        # waits for both conditions rather than invoking the save callback too early.
        _mbt_finish = finish
    except Exception as error:
        if _mbt_state.get('job_id') == locals().get('job', {}).get('job_id'):
            _mbt_state = {'state': 'FAILED', 'error': str(error)}
        return _mbt_json.dumps({'state': 'FAILED', 'error': str(error)})
    return _mbt_status()


def _mbt_update(job_path):
    """Open only the associated project, then refresh geometry without closing anything."""
    global _mbt_state
    _mbt_guard_touch()
    try:
        job = _mbt_json.loads(_MBTPath(job_path).read_text(encoding='utf-8'))
        if _mbt_project.is_busy():
            raise RuntimeError('Painter is busy')
        if not _mbt_project.is_open():
            if not _MBTPath(job['project_file']).is_file():
                return _mbt_create(job_path)
            _mbt_state = {'state': 'OPENING', 'job_path': job_path, 'job_id': job['job_id']}
            _mbt_project.open(job['project_file'])
            return _mbt_json.dumps(_mbt_state)
        if _MBTPath(_mbt_project.file_path()).resolve() != _MBTPath(job['project_file']).resolve():
            raise RuntimeError('An unrelated Painter project is open. Save and close it before baking')
        if not _mbt_project.is_in_edition_state():
            raise RuntimeError('Painter project is not ready')
        _mbt_state = {'state': 'RELOADING', 'job_path': job_path, 'job_id': job['job_id']}
        def finished(status):
            if status == _mbt_project.ReloadMeshStatus.SUCCESS:
                _mbt_state['state'] = 'RELOADED'
            else:
                _mbt_state.update(state='FAILED', error='Mesh reload failed; baking stopped')
        _mbt_project.reload_mesh(job['low_mesh'],
            _mbt_project.MeshReloadingSettings(import_cameras=False, preserve_strokes=True), finished)
        return _mbt_json.dumps(_mbt_state)
    except Exception as error:
        _mbt_state = {'state': 'FAILED', 'error': str(error)}
        return _mbt_json.dumps(_mbt_state)


def _mbt_export(job_path):
    """Export only the saved project belonging to this manifest; never bake or save it."""
    try:
        _mbt_guard_touch()
        import substance_painter.export as export
        import math
        import tempfile
        job = _mbt_json.loads(_MBTPath(job_path).read_text(encoding='utf-8'))
        if job.get('schema_version') != 1 or job.get('export_preset') != 'MBT_PBR':
            raise RuntimeError('Unsupported job schema or texture layout')
        if not _mbt_project.is_open() or not _mbt_project.is_in_edition_state() or _mbt_project.is_busy():
            raise RuntimeError('Painter needs an open, ready project before export')
        current = _mbt_project.file_path()
        if not current or _MBTPath(current).resolve() != _MBTPath(job['project_file']).resolve():
            raise RuntimeError('Open Painter project does not match the Blender setup. Open the associated project before updating textures.')
        actual = sorted(item.name() for item in _mbt_textureset.all_texture_sets())
        if actual != sorted(item['texture_set'] for item in job['texture_sets']):
            raise RuntimeError('Painter texture sets do not match the active job')
        # Unique directory avoids mistaking stale files for a successful export.
        parent = _MBTPath(job_path).resolve().parent / 'textures'
        parent.mkdir(exist_ok=True)
        directory = _MBTPath(tempfile.mkdtemp(prefix='export_', dir=str(parent)))
        definitions = (
            ('base_color', 'BaseColor', 'documentMap', 'baseColor', 'RGB'),
            ('roughness', 'Roughness', 'documentMap', 'roughness', 'L'),
            ('metallic', 'Metallic', 'documentMap', 'metallic', 'L'),
            ('normal', 'Normal', 'virtualMap',
             'Normal_OpenGL' if job['normal_format'] == 'OPENGL' else 'Normal_DirectX', 'RGB'),
            ('ao', 'AO', 'virtualMap', 'AO_Mixed', 'L'))
        maps = []
        for channel, suffix, source_type, source_name, components in definitions:
            maps.append({'fileName': '$textureSet_' + suffix,
                         'channels': [{'destChannel': component, 'srcChannel': component,
                                       'srcMapType': source_type, 'srcMapName': source_name}
                                      for component in components]})
        config = {'exportShaderParams': False, 'exportPath': str(directory),
                  'defaultExportPreset': 'MBToolkitPBR',
                  'exportPresets': [{'name': 'MBToolkitPBR', 'maps': maps}],
                  'exportList': [{'rootPath': name} for name in actual],
                  'exportParameters': [{'parameters': {'fileFormat': 'png', 'bitDepth': '8',
                      'dithering': False, 'sizeLog2': int(math.log2(job['resolution'])),
                      'paddingAlgorithm': 'infinite'}}]}
        custom = job.get('custom_export')
        if custom:
            config['defaultExportPreset'] = custom['preset']
            del config['exportPresets']
        result = export.export_project_textures(config)
        if result.status not in (export.ExportStatus.Success, export.ExportStatus.Warning):
            raise RuntimeError('Painter export failed: ' + result.message)
        returned = {_MBTPath(path).resolve() for paths in result.textures.values() for path in paths}
        entries = []
        for entry in job['texture_sets']:
            paths = {}
            expected_files = {channel: entry['texture_set'] + '_' + suffix + '.png'
                              for channel, suffix, *_ in definitions}
            if custom:
                expected_files = {channel: filename.replace('{texture_set}', entry['texture_set'])
                                  for channel, filename in custom['channels'].items()}
            for channel, filename in expected_files.items():
                matches = [path for path in returned
                           if path.name == filename
                           and path.parent == directory.resolve() and path.is_file()]
                if len(matches) == 1:
                    paths[channel] = str(matches[0])
            if not {'base_color', 'roughness', 'metallic', 'normal'} <= paths.keys():
                raise RuntimeError('Export missing required PBR textures for ' + entry['texture_set']
                                   + ': ' + result.message)
            entries.append({'object': entry['object'], 'textures': paths})
        return _mbt_json.dumps({'state': 'EXPORTED', 'job_id': job['job_id'],
                               'texture_sets': entries, 'message': result.message})
    except Exception as error:
        return _mbt_json.dumps({'state': 'FAILED', 'error': str(error)})


def _mbt_bake_status():
    _mbt_guard_touch()
    return _mbt_json.dumps(globals().get('_mbt_bake_state', {'state': 'IDLE'}))


def _mbt_cancel_bake():
    if globals().get('_mbt_bake_state', {}).get('state') == 'BAKING':
        accepted = _mbt_stop.request_stop()
        return _mbt_json.dumps({'cancel_requested': bool(accepted)})
    return _mbt_json.dumps({'cancel_requested': False})


def _mbt_bake(job_path):
    global _mbt_bake_state, _mbt_stop
    _mbt_guard_touch()
    try:
        import math
        import substance_painter.baking as baking
        import substance_painter.event as event
        job = _mbt_json.loads(_MBTPath(job_path).read_text(encoding='utf-8'))
        if globals().get('_mbt_bake_state', {}).get('state') == 'BAKING':
            raise RuntimeError('An MBToolkit bake is already running')
        if not _mbt_project.is_in_edition_state() or _mbt_project.is_busy():
            raise RuntimeError('Painter project is not ready for baking')
        if _MBTPath(_mbt_project.file_path()).resolve() != _MBTPath(job['project_file']).resolve():
            raise RuntimeError('Open Painter project does not match the active job')
        high = _MBTPath(job['high_mesh'])
        if not high.is_file():
            raise RuntimeError('High-poly FBX is missing')
        mapping = {'NORMAL': 'Normal', 'AO': 'AO', 'CURVATURE': 'Curvature',
                   'POSITION': 'Position', 'THICKNESS': 'Thickness',
                   'WORLD_SPACE_NORMAL': 'WorldSpaceNormal', 'ID': 'ID'}
        requested = job['bake_maps']
        if not requested or any(name not in mapping for name in requested):
            raise RuntimeError('Invalid bake-map selection')
        texture_sets = _mbt_textureset.all_texture_sets()
        if sorted(ts.name() for ts in texture_sets) != sorted(e['texture_set'] for e in job['texture_sets']):
            raise RuntimeError('Painter texture sets do not match job')
        options = job['baking']
        changes = {}
        plans = []
        for ts in texture_sets:
            params = baking.BakingParameters.from_texture_set(ts)
            common = params.common()
            values = {'OutputSize': (int(math.log2(job['resolution'])),) * 2,
                      'HipolyMesh': high.resolve().as_uri(),
                      'LowAsHigh': False,
                      'MaxHeight': options['front_distance'],
                      'MaxDepth': options['rear_distance'],
                      'RelativeScale': options['relative_distance']}
            if job.get('match_method') == 'BY_NAME':
                values.update(LowpolySuffix='_low', HipolySuffix='_high')
            for key, value in values.items():
                if key not in common:
                    raise RuntimeError('Unsupported Painter bake parameter ' + key + '; available: ' + str(list(common)))
                changes[common[key]] = value
            for key, label in (('SubSampling', options['antialiasing']),
                               ('FilterMethod', 'By Mesh Name' if job.get('match_method') == 'BY_NAME' else 'Always'),
                               ('CageMode', 'Distance-based')):
                if key not in common:
                    raise RuntimeError('Unsupported Painter bake parameter: ' + key)
                prop = common[key]
                if label not in prop.enum_values():
                    raise RuntimeError(f'Unsupported {key} option {label}; available: {prop.enum_values()}')
                changes[prop] = prop.enum_value(label)
            usages = {name: getattr(_mbt_textureset.MeshMapUsage, usage) for name, usage in mapping.items()}
            if 'ID' in requested:
                prop = params.baker(usages['ID'])['ColorSource']
                changes[prop] = prop.enum_value(options['id_source'])
            plans.append((params, usages))
        baking.BakingParameters.set(changes)
        for params, usages in plans:
            params.set_textureset_enabled(True)
            selected = {usages[name] for name in requested}
            for usage in (getattr(_mbt_textureset.MeshMapUsage, name)
                          for name in dir(_mbt_textureset.MeshMapUsage)
                          if isinstance(getattr(_mbt_textureset.MeshMapUsage, name), _mbt_textureset.MeshMapUsage)):
                params.set_baker_enabled(usage, usage in selected)
            if 'CURVATURE' in requested:
                params.set_curvature_method(baking.CurvatureMethod.FromMesh)
        _mbt_bake_state = {'state': 'BAKING', 'progress': 0, 'job_id': job['job_id']}

        def progress(evt):
            _mbt_bake_state['progress'] = evt.progress

        def ended(evt):
            global _mbt_bake_state
            event.DISPATCHER.disconnect(event.BakingProcessProgress, progress)
            event.DISPATCHER.disconnect(event.BakingProcessEnded, ended)
            if evt.status == baking.BakingStatus.Success:
                _mbt_bake_state['state'] = 'BAKED'
            elif evt.status == baking.BakingStatus.Cancel:
                _mbt_bake_state['state'] = 'CANCELLED'
            else:
                _mbt_bake_state = {'state': 'FAILED', 'error': 'Painter baking failed; inspect Painter log'}

        event.DISPATCHER.connect_strong(event.BakingProcessProgress, progress)
        event.DISPATCHER.connect_strong(event.BakingProcessEnded, ended)
        try:
            _mbt_stop = baking.bake_selected_textures_async()
        except Exception:
            event.DISPATCHER.disconnect(event.BakingProcessProgress, progress)
            event.DISPATCHER.disconnect(event.BakingProcessEnded, ended)
            _mbt_bake_state = {'state': 'FAILED', 'error': 'Painter could not start baking'}
            _mbt_stop = None
            raise
        return _mbt_bake_status()
    except Exception as error:
        return _mbt_json.dumps({'state': 'FAILED', 'error': str(error)})


def _mbt_save_baked(job_path):
    _mbt_guard_touch()
    try:
        job = _mbt_json.loads(_MBTPath(job_path).read_text(encoding='utf-8'))
        if globals().get('_mbt_bake_state', {}).get('state') != 'BAKED':
            raise RuntimeError('No confirmed successful bake')
        if _mbt_bake_state['job_id'] != job['job_id']:
            raise RuntimeError('Bake job identity mismatch')
        if _mbt_project.is_busy() or not _mbt_project.is_in_edition_state():
            return _mbt_json.dumps({'state': 'WAITING'})
        if _MBTPath(_mbt_project.file_path()).resolve() != _MBTPath(job['project_file']).resolve():
            raise RuntimeError('Open project changed after bake')
        _mbt_project.save()
        return _mbt_json.dumps({'state': 'SAVED'})
    except Exception as error:
        return _mbt_json.dumps({'error': str(error)})