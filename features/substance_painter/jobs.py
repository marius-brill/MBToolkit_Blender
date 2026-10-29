"""Non-destructive mesh snapshots and a versioned, Painter-independent job contract."""
import json
import math
from pathlib import Path
import re
import shutil
import tempfile
import uuid

import bpy
from .evaluation import bake_inputs, bake_steps, finish_steps

SCHEMA_VERSION = 1
CHANNELS = {'base_color': 'BaseColor', 'roughness': 'Roughness', 'metallic': 'Metallic',
            'normal': 'Normal', 'ao': 'AO'}


class PainterError(ValueError):
    pass


class ValidationIssues(PainterError):
    def __init__(self, issues):
        self.issues = issues
        self.blocking = any(issue['blocking'] for issue in issues)
        super().__init__('; '.join(f"{issue['object']}: {issue['reason']}" for issue in issues))


def safe_name(name):
    return re.sub(r'[^A-Za-z0-9_-]+', '_', name).strip('_')[:64] or 'Asset'


def meshes(collection):
    return sorted((obj for obj in collection.all_objects if obj.type == 'MESH'),
                  key=lambda obj: obj.name) if collection else []


def validate(context, ignore_warnings=False):
    return finish_steps(validate_steps(context, ignore_warnings=ignore_warnings))


@bake_steps
def validate_steps(context, ignore_warnings=False):
    settings = context.scene.mbt_painter
    if context.mode != 'OBJECT':
        raise PainterError('Switch to Object Mode before preparing a job')
    low, high = meshes(settings.low_collection), meshes(settings.high_collection)
    if not low or not high:
        raise PainterError('Choose non-empty low-poly and high-poly mesh collections')
    if set(low) & set(high):
        raise PainterError('Low and high collections must not share mesh objects (including children)')
    names = [safe_name(obj.name) for obj in low]
    if len(names) != len(set(names)):
        raise PainterError('Low-poly names collide after filename sanitization; rename the objects')
    issues = []
    def issue(obj, reason, blocking=True):
        issues.append({'object': obj.name, 'reason': reason, 'blocking': blocking})
    if not settings.bake_maps:
        raise PainterError('Select at least one bake map')
    if not settings.output_dir.strip():
        raise PainterError('Choose an output folder')
    if settings.output_dir.startswith('//') and not bpy.data.filepath:
        raise PainterError('Save the blend file or choose an absolute output folder')
    for obj in low + high:
        yield 'Validating mesh: ' + obj.name
        if obj.library or obj.data.library:
            issue(obj, 'linked data is not supported; make it local first')
        if not obj.data.polygons:
            issue(obj, 'mesh has no faces')
        if abs(obj.matrix_world.determinant()) < 1e-12:
            issue(obj, 'transform has zero scale')
        if obj in low:
            try:
                validate_uv(obj.data, obj.name, ignore_warnings=ignore_warnings)
            except ValidationIssues as error:
                issues.extend(error.issues)
        depsgraph = context.evaluated_depsgraph_get()
        evaluated = obj.evaluated_get(depsgraph)
        mesh = evaluated.to_mesh(preserve_all_data_layers=True, depsgraph=depsgraph)
        try:
            if not mesh or not mesh.polygons:
                issue(obj, 'evaluated mesh has no faces')
            elif obj in low:
                try:
                    validate_uv(mesh, obj.name, ignore_warnings=ignore_warnings)
                except ValidationIssues as error:
                    for entry in error.issues:
                        if entry not in issues:
                            issues.append(entry)
        finally:
            evaluated.to_mesh_clear()
    if issues:
        raise ValidationIssues(issues)
    if not settings.bake_maps:
        raise PainterError('Select at least one bake map')
    if not settings.output_dir.strip():
        raise PainterError('Choose an output folder')
    if settings.output_dir.startswith('//') and not bpy.data.filepath:
        raise PainterError('Save the blend file or choose an absolute output folder')
    return low, high


def validate_uv(mesh, name, ignore_warnings=False):
    uv = mesh.uv_layers.active
    if uv is None:
        raise ValidationIssues([{'object': name, 'reason': 'low-poly mesh needs an active UV map', 'blocking': True}])
    # Offset mirrored islands stay outside the bake tile; never wrap or normalize them.
    coords = [item.uv for item in uv.data]
    if any(not math.isfinite(v) for co in coords for v in co):
        raise ValidationIssues([{'object': name, 'reason': 'UVs must be finite', 'blocking': True}])
    warnings = set()
    mesh.calc_loop_triangles()
    for triangle in mesh.loop_triangles:
        a, b, c = (coords[index] for index in triangle.loops)
        if any(max(co[i] for co in (a, b, c)) <= 0 or min(co[i] for co in (a, b, c)) >= 1 for i in range(2)):
            continue
        if any(v < -1e-6 or v > 1 + 1e-6 for co in (a, b, c) for v in co):
            warnings.add('UV triangles cross the 0–1 bake-tile boundary')
        area = (b.x-a.x)*(c.y-a.y) - (b.y-a.y)*(c.x-a.x)
        if abs(area) < 1e-12:
            warnings.add('UVs contain collapsed triangles')
    if warnings and not ignore_warnings:
        raise ValidationIssues([{'object': name, 'reason': reason, 'blocking': False} for reason in sorted(warnings)])


def export_meshes(context, objects, filepath, low=False, names=None, material_names=None, ignore_warnings=False):
    return finish_steps(export_steps(context, objects, filepath, low=low, names=names,
                                    material_names=material_names, ignore_warnings=ignore_warnings))


@bake_steps
def export_steps(context, objects, filepath, low=False, names=None, material_names=None, ignore_warnings=False):
    """Export evaluated copies in a disposable scene; never select/change source objects."""
    scene = bpy.data.scenes.new('MBT_Painter_Export')
    scene.unit_settings.system = context.scene.unit_settings.system
    scene.unit_settings.scale_length = context.scene.unit_settings.scale_length
    temporary_objects, temporary_meshes, temporary_materials = [], [], []
    try:
        for index, source in enumerate(objects):
            yield 'Snapshot ' + ('low' if low else 'high') + ' mesh: ' + source.name
            depsgraph = context.evaluated_depsgraph_get()
            evaluated = source.evaluated_get(depsgraph)
            mesh = bpy.data.meshes.new_from_object(evaluated, preserve_all_data_layers=True,
                                                 depsgraph=depsgraph)
            temporary_meshes.append(mesh)
            if not mesh.polygons:
                raise PainterError(f'{source.name}: evaluated mesh has no faces')
            if low:
                validate_uv(mesh, source.name, ignore_warnings=ignore_warnings)
            # Unique material per low object gives deterministic Painter texture-set names.
            if low:
                mesh.materials.clear()
                material = bpy.data.materials.new(material_names[index] if material_names else 'MBT_' + safe_name(source.name))
                if material_names and material.name != material_names[index]:
                    temporary_materials.append(material)
                    raise PainterError('Texture-set material name is occupied; rename the conflicting material')
                temporary_materials.append(material)
                mesh.materials.append(material)
                for polygon in mesh.polygons:
                    polygon.material_index = 0
            expected = names[source] if names else safe_name(source.name) + ('_low' if low else '_high')
            obj = bpy.data.objects.new(expected, mesh)
            temporary_objects.append(obj)
            if names and obj.name != expected:
                # Source objects can already have the desired name. The FBX exporter
                # uses the temporary object's name; reserve it without touching sources.
                raise PainterError(f'Export name {expected} is occupied. Rename that source object (export names are reserved)')
            obj.matrix_world = evaluated.matrix_world.copy()
            scene.collection.objects.link(obj)
        yield 'Exporting ' + ('low-poly' if low else 'high-poly') + ' FBX'
        layer = scene.view_layers[0]
        layer.update()
        with context.temp_override(scene=scene, view_layer=layer):
            result = bpy.ops.export_scene.fbx(
                filepath=str(filepath), check_existing=False, use_selection=False,
                object_types={'MESH'}, use_mesh_modifiers=False, bake_anim=False,
                use_triangles=True, mesh_smooth_type='OFF', axis_forward='-Z', axis_up='Y',
                apply_unit_scale=True, add_leaf_bones=False)
        if result != {'FINISHED'} or not filepath.is_file():
            raise PainterError('FBX export did not finish')
        return [mat.name for mat in temporary_materials]
    finally:
        for obj in temporary_objects:
            bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.scenes.remove(scene)
        for mesh in temporary_meshes:
            bpy.data.meshes.remove(mesh)
        for material in temporary_materials:
            bpy.data.materials.remove(material)


def prepare(context, automatic=False, ignore_warnings=False):
    return finish_steps(prepare_steps(context, automatic=automatic, ignore_warnings=ignore_warnings))


def prepare_steps(context, automatic=False, ignore_warnings=False):
    yield 'Preparing mesh snapshots'
    settings = context.scene.mbt_painter
    previous = None
    # Resolve persisted project metadata before evaluating potentially huge meshes.
    # Never guess old texture-set identities or silently discard existing painting.
    if automatic and settings.project_file:
        if not settings.last_job:
            raise PainterError('Internal project data is missing. Use New Project in Advanced to reset safely')
        previous = read_job(settings.last_job)
        if Path(previous['project_file']).resolve() != Path(bpy.path.abspath(settings.project_file)).resolve():
            raise PainterError('Associated project identity differs from internal job')
        if previous['normal_format'] != settings.normal_format:
            raise PainterError('Normal format changed; use New Project in Advanced to apply it safely')
    names, pairs = None, {}
    custom = None
    from ...core.addon import get_prefs
    prefs = get_prefs(context)
    template_path = settings.project_template or (prefs.painter_project_template if prefs else '')
    template = bpy.path.abspath(template_path) if template_path else ''
    if template and not (automatic and settings.project_file) and (not Path(template).is_file() or Path(template).suffix.lower() != '.spt'):
        raise PainterError('Project Template must be an existing .spt file')
    if settings.export_config:
        custom = json.loads(Path(bpy.path.abspath(settings.export_config)).read_text(encoding='utf-8'))
        required = {'base_color', 'roughness', 'metallic', 'normal'}
        if (not isinstance(custom, dict) or not isinstance(custom.get('preset'), str)
                or not isinstance(custom.get('channels'), dict)
                or not required <= custom['channels'].keys() or not custom['channels'].keys() <= CHANNELS.keys()
                or any(not isinstance(value, str) or '{texture_set}' not in value
                       or '/' in value or '\\' in value or not value.endswith('.png')
                       for value in custom['channels'].values())
                or len(set(custom['channels'].values())) != len(custom['channels'])):
            raise PainterError('Export mapping needs preset URL and unpacked PNG channels containing {texture_set}')
    low, high = yield from validate_steps(context, ignore_warnings=ignore_warnings)
    if automatic:
        from .matching import resolve_steps
        names, pairs = yield from resolve_steps(context, low, high)
        from .materials import owned
        if not settings.replace_materials:
            protected = [obj.name for obj in low if any(slot.material and not owned(slot.material, obj)
                                                       for slot in obj.material_slots)]
            if protected:
                raise PainterError('Existing materials protected; enable Replace Existing Materials: ' + ', '.join(protected))
    # Stable IDs are assigned only after validation, and duplicates are repaired.
    ids = set()
    for obj in low:
        if not obj.get('mbt_painter_id') or obj['mbt_painter_id'] in ids:
            obj['mbt_painter_id'] = str(uuid.uuid4())
        ids.add(obj['mbt_painter_id'])
    material_names = None
    if previous:
        by_id = {entry.get('object_id'): entry for entry in previous['texture_sets']}
        if set(by_id) != ids:
            raise PainterError('Low mesh membership changed; use New Project in Advanced to protect existing painting')
        material_names = [by_id[obj['mbt_painter_id']]['texture_set'] for obj in low]
        if names:
            for target in low:
                entry = by_id[target['mbt_painter_id']]
                old_name = previous.get('mesh_names', {}).get(entry['object'])
                if old_name:
                    names[target] = old_name
            from .matching import targets
            for obj in high:
                prefixes = {re.sub(r'_low(?:_\d+)?$', '', names[target]) for target in targets(pairs[obj])}
                if len(prefixes) != 1:
                    raise PainterError('Bake group changed across existing texture sets; use New Project in Advanced')
                peers = [other for other in high if pairs[other] == pairs[obj]]
                index = peers.index(obj)
                names[obj] = prefixes.pop() + '_high' + (f'_{index:03d}' if index else '')
    if names and len(set(names.values())) != len(names):
        raise PainterError('Final bake mesh names collide after project-name reuse; use New Project in Advanced')
    if material_names and len(set(material_names)) != len(material_names):
        raise PainterError('Associated texture-set names collide; use New Project in Advanced')
    output = Path(bpy.path.abspath(settings.output_dir)).resolve()
    output.mkdir(parents=True, exist_ok=True)
    directory = Path(tempfile.mkdtemp(prefix=safe_name(settings.project_name) + '_', dir=output))
    try:
        sets = yield from export_steps(context, low, directory / 'low.fbx', low=True, names=names, material_names=material_names,
                                       ignore_warnings=ignore_warnings)
        yield from export_steps(context, high, directory / 'high.fbx', names=names)
        (directory / 'textures').mkdir()
        job = {
            'schema_version': SCHEMA_VERSION, 'job_id': str(uuid.uuid4()),
            'project_name': settings.project_name, 'blend_file': bpy.data.filepath,
            'status': 'prepared', 'low_mesh': str(directory / 'low.fbx'),
            'high_mesh': str(directory / 'high.fbx'),
            'project_file': previous['project_file'] if previous else str(directory / (safe_name(settings.project_name) + '.spp')),
            'project_template': template, 'custom_export': custom,
            'resolution': int(settings.resolution), 'bake_maps': sorted(settings.bake_maps),
            'normal_format': settings.normal_format, 'export_preset': settings.export_preset,
            'match_method': 'BY_NAME' if automatic else 'ALWAYS', 'apply_modifiers': True,
            'mesh_names': {obj.name: name for obj, name in (names or {}).items()},
            'baking': bake_settings(settings),
            'texture_sets': [
                {'object': obj.name, 'object_id': obj['mbt_painter_id'], 'texture_set': texture_set, 'uv_map': obj.data.uv_layers.active.name,
                 'textures': {channel: str(directory / 'textures' / f'{texture_set}_{suffix}.png')
                              for channel, suffix in CHANNELS.items()}}
                for obj, texture_set in zip(low, sets)],
        }
        path = directory / 'job.json'
        path.write_text(json.dumps(job, indent=2), encoding='utf-8')
    except BaseException:
        shutil.rmtree(directory, ignore_errors=True)
        raise
    settings.last_job = str(path)
    if automatic:
        settings.project_file = job['project_file']
        for obj, target in pairs.items():
            if not isinstance(target, tuple):
                obj.mbt_bake_target = target
    return f'Prepared {len(low)} low / {len(high)} high meshes. Painter has not been run.'


def read_job(path):
    if not path:
        raise PainterError('Prepare a job or choose a job.json first')
    resolved = Path(bpy.path.abspath(path))
    try:
        job = json.loads(resolved.read_text(encoding='utf-8'))
    except FileNotFoundError as error:
        raise PainterError(
            f'Saved bake job.json is missing: {resolved}. Restore the original bake folder to keep '
            'the associated painting, or choose New Project Next Bake to start fresh. '
            'Existing Painter files will not be deleted.') from error
    if not isinstance(job, dict) or job.get('schema_version') != SCHEMA_VERSION:
        raise PainterError('Unsupported Painter job schema')
    if (not isinstance(job.get('job_id'), str) or not job['job_id']
            or job.get('normal_format') not in {'OPENGL', 'DIRECTX'}
            or job.get('export_preset') != 'MBT_PBR'
            or not isinstance(job.get('texture_sets'), list) or not job['texture_sets']):
        raise PainterError('Invalid Painter job manifest')
    seen = set()
    for entry in job['texture_sets']:
        if (not isinstance(entry, dict) or not isinstance(entry.get('object'), str)
                or not isinstance(entry.get('texture_set'), str)
                or not isinstance(entry.get('uv_map'), str)
                or not isinstance(entry.get('textures'), dict)
                or set(entry['textures']) != set(CHANNELS)
                or any(not isinstance(p, str) or not Path(p).is_absolute()
                       for p in entry['textures'].values())):
            raise PainterError('Invalid texture-set entry in job manifest')
        if entry['object'] in seen:
            raise PainterError('Duplicate object in job manifest')
        seen.add(entry['object'])
    return job


def record_export(path, result):
    """Validate returned files before atomically updating this job's import paths."""
    job = read_job(path)
    if result.get('job_id') != job['job_id'] or result.get('state') != 'EXPORTED':
        raise PainterError('Export response does not match the active job')
    entries = result.get('texture_sets', [])
    if (not isinstance(entries, list) or len(entries) != len(job['texture_sets'])
            or any(not isinstance(entry, dict) for entry in entries)):
        raise PainterError('Invalid exported texture-set response')
    by_object = {entry.get('object'): entry.get('textures') for entry in entries}
    if len(by_object) != len(entries) or set(by_object) != {entry['object'] for entry in job['texture_sets']}:
        raise PainterError('Exported targets do not match job targets')
    root = Path(bpy.path.abspath(path)).resolve().parent / 'textures'
    for entry in job['texture_sets']:
        textures = by_object[entry['object']]
        if (not isinstance(textures, dict) or not set(textures) <= set(CHANNELS)
                or not {'base_color', 'roughness', 'metallic', 'normal'} <= textures.keys()):
            raise PainterError('Export response is missing required shader channels')
        for channel, filename in textures.items():
            file = Path(filename).resolve()
            if not file.is_relative_to(root) or file.suffix.lower() != '.png' or not file.is_file():
                raise PainterError(f'Invalid or missing exported file: {file}')
            entry['textures'][channel] = str(file)
        if 'ao' not in textures:
            # Do not silently import AO left over from an earlier export.
            entry['textures']['ao'] = str(Path(textures['base_color']).parent /
                                         (entry['texture_set'] + '_AO.png'))
    job['status'] = 'exported'
    destination = Path(bpy.path.abspath(path))
    temporary = destination.with_suffix('.json.tmp')
    try:
        temporary.write_text(json.dumps(job, indent=2), encoding='utf-8')
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return job


def bake_settings(settings):
    return {'front_distance': settings.front_distance, 'rear_distance': settings.rear_distance,
            'relative_distance': settings.relative_distance, 'antialiasing': settings.antialiasing,
            'id_source': settings.id_source}


def update_bake_settings(path, settings):
    job = read_job(path)
    if not settings.bake_maps:
        raise PainterError('Select at least one bake map')
    job.update(baking=bake_settings(settings), bake_maps=sorted(settings.bake_maps),
               resolution=int(settings.resolution))
    destination = Path(bpy.path.abspath(path))
    temporary = destination.with_suffix('.json.tmp')
    try:
        temporary.write_text(json.dumps(job, indent=2), encoding='utf-8')
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)