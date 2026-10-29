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
    from .texture_sets import entries
    groups = entries(settings)
    low, high = [], []
    for entry in groups:
        lows, highs = meshes(entry.low_collection), meshes(entry.high_collection)
        if not lows or not highs:
            raise PainterError('Choose non-empty low-poly and high-poly mesh collections for every texture set')
        if set(lows + highs) & set(low + high):
            raise PainterError('Mesh objects must not belong to multiple texture sets')
        if not entry.bake_maps:
            raise PainterError('Select at least one bake map for every texture set')
        if hasattr(entry, 'collection'):
            parent = entry.collection
            if parent is None or any(child not in parent.children_recursive for child in
                                     (entry.low_collection, entry.high_collection)):
                raise PainterError('Each texture set must contain its low/high child collections')
        low.extend(lows)
        high.extend(highs)
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
                # Quality warnings describe the exported surface, not faces removed by modifiers.
                validate_uv(obj.data, obj.name, ignore_warnings=True)
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
                    validate_uv(mesh, obj.name, ignore_warnings=ignore_warnings, stage='evaluated/export mesh')
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


def validate_uv(mesh, name, ignore_warnings=False, stage='mesh'):
    uv = mesh.uv_layers.active
    if uv is None:
        raise ValidationIssues([{'object': name, 'reason': 'low-poly mesh needs an active UV map', 'blocking': True}])
    # Offset mirrored islands stay outside the bake tile; never wrap or normalize them.
    coords = [item.uv for item in uv.data]
    if any(not math.isfinite(v) for co in coords for v in co):
        raise ValidationIssues([{'object': name, 'reason': 'UVs must be finite', 'blocking': True}])
    if ignore_warnings:
        return
    warnings = {}
    def warn(reason, triangle):
        entry = warnings.setdefault(reason, {'count': 0, 'faces': set()})
        entry['count'] += 1
        entry['faces'].add(triangle.polygon_index)
    mesh.calc_loop_triangles()
    for triangle in mesh.loop_triangles:
        a, b, c = (coords[index] for index in triangle.loops)
        if any(max(co[i] for co in (a, b, c)) <= 0 or min(co[i] for co in (a, b, c)) >= 1 for i in range(2)):
            continue
        if any(v < -1e-6 or v > 1 + 1e-6 for co in (a, b, c) for v in co):
            warn('UV triangles cross the 0–1 bake-tile boundary', triangle)
        area = (b.x-a.x)*(c.y-a.y) - (b.y-a.y)*(c.x-a.x)
        if abs(area) < 1e-12:
            points = [mesh.vertices[index].co for index in triangle.vertices]
            edge_a, edge_b = points[1] - points[0], points[2] - points[0]
            geometric_scale = max(edge_a.length_squared, edge_b.length_squared)
            degenerate = edge_a.cross(edge_b).length_squared <= geometric_scale ** 2 * 1e-24
            reason = ('Zero-area geometry triangles also have collapsed UVs' if degenerate
                      else 'UVs contain collapsed triangles on nonzero-area geometry')
            warn(reason, triangle)
    if warnings and not ignore_warnings:
        issues = []
        for reason, entry in sorted(warnings.items()):
            faces = sorted(entry['faces'])
            preview = ', '.join(str(index + 1) for index in faces[:12])
            if len(faces) > 12:
                preview += ', …'
            issues.append({'object': name, 'blocking': False, 'uv_map': uv.name,
                           'stage': stage, 'faces': faces, 'triangle_count': entry['count'],
                           'reason': f"{reason}: {entry['count']} triangle(s), UV map '{uv.name}', {stage}; "
                                     f'faces (1-based): {preview}'})
        raise ValidationIssues(issues)


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
    shared_materials, exported_sets = {}, []
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
                validate_uv(mesh, source.name, ignore_warnings=ignore_warnings, stage='evaluated/export mesh')
            # One temporary material per collection-backed set, shared by its low meshes.
            if low:
                mesh.materials.clear()
                expected_material = material_names[index] if material_names else 'MBT_Default'
                material = shared_materials.get(expected_material)
                if material is None:
                    material = bpy.data.materials.new(expected_material)
                    temporary_materials.append(material)
                    if material.name != expected_material:
                        raise PainterError('Texture-set material name is occupied; rename the conflicting material')
                    shared_materials[expected_material] = material
                exported_sets.append(material.name)
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
        return exported_sets
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
    from .texture_sets import entries, ensure_default
    ensure_default(context)
    groups = entries(settings)
    owners = {obj: entry for entry in groups for obj in meshes(entry.low_collection)}
    group_names = {entry.as_pointer(): 'MBT_' + safe_name(entry.collection.name if hasattr(entry, 'collection') else 'Default')
                   for entry in groups}
    if len(set(group_names.values())) != len(group_names):
        raise PainterError('Texture-set collection names collide after sanitization')
    if automatic:
        from .matching import resolve_steps
        names, pairs = {}, {}
        matching_issues = []
        for index, entry in enumerate(groups):
            try:
                scoped_names, scoped_pairs = yield from resolve_steps(context, meshes(entry.low_collection), meshes(entry.high_collection))
            except ValidationIssues as error:
                matching_issues.extend(error.issues)
                continue
            if len(groups) > 1:
                scoped_names = {obj: f'MBTSet_{index:03d}_' + name for obj, name in scoped_names.items()}
            names.update(scoped_names)
            pairs.update(scoped_pairs)
        if matching_issues:
            raise ValidationIssues(matching_issues)
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
    material_names = [group_names[owners[obj].as_pointer()] for obj in low]
    if previous:
        by_id = {entry.get('object_id'): entry for entry in previous['texture_sets']}
        if set(by_id) != ids:
            raise PainterError('Low mesh membership changed; use New Project in Advanced to protect existing painting')
        definitions = previous.get('set_definitions')
        current_membership = {obj['mbt_painter_id']: getattr(owners[obj], 'set_id', 'default') for obj in low}
        previous_membership = {entry['object_id']: entry.get('set_id', 'default') for entry in previous['texture_sets']}
        if not definitions or current_membership != previous_membership:
            raise PainterError('Texture-set membership changed; use New Project in Advanced to protect existing painting')
        defined_names = {entry['set_id']: entry['texture_set'] for entry in definitions}
        if (len(set(defined_names.values())) != len(groups) or any(
                entry['texture_set'] != defined_names.get(entry.get('set_id'))
                for entry in previous['texture_sets'])):
            raise PainterError('Associated texture-set names collide or differ; use New Project in Advanced')
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
    if previous and len(set(material_names)) != len(groups):
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
            'set_definitions': [
                {'set_id': getattr(entry, 'set_id', 'default'),
                 'texture_set': material_names[low.index(meshes(entry.low_collection)[0])],
                 'resolution': int(entry.resolution), 'bake_maps': sorted(entry.bake_maps),
                 'baking': bake_settings(entry)} for entry in groups],
            'texture_sets': [
                {'object': obj.name, 'object_id': obj['mbt_painter_id'],
                 'set_id': getattr(owners[obj], 'set_id', 'default'),
                 'texture_set': texture_set, 'uv_map': obj.data.uv_layers.active.name,
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
    if 'set_definitions' in job:
        definitions = job['set_definitions']
        if not isinstance(definitions, list) or not definitions:
            raise PainterError('Invalid texture-set definitions')
        identities, names = set(), set()
        for definition in definitions:
            if (not isinstance(definition, dict)
                    or not isinstance(definition.get('set_id'), str) or not definition['set_id']
                    or not isinstance(definition.get('texture_set'), str) or not definition['texture_set']
                    or definition.get('resolution') not in (512, 1024, 2048, 4096, 8192)
                    or not isinstance(definition.get('bake_maps'), list) or not definition['bake_maps']
                    or not isinstance(definition.get('baking'), dict)):
                raise PainterError('Invalid texture-set definition')
            if definition['set_id'] in identities or definition['texture_set'] in names:
                raise PainterError('Duplicate texture-set definition')
            identities.add(definition['set_id'])
            names.add(definition['texture_set'])
        by_id = {definition['set_id']: definition['texture_set'] for definition in definitions}
        if (any(entry.get('set_id') not in by_id or by_id[entry['set_id']] != entry['texture_set']
                for entry in job['texture_sets'])
                or {entry['texture_set'] for entry in job['texture_sets']} != names):
            raise PainterError('Texture-set membership differs from definitions')
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
    if job.get('set_definitions'):
        from .texture_sets import entries
        by_id = {getattr(entry, 'set_id', 'default'): entry for entry in entries(settings)}
        if set(by_id) != {entry['set_id'] for entry in job['set_definitions']}:
            raise PainterError('Texture sets changed; prepare a new bake first')
        for definition in job['set_definitions']:
            entry = by_id[definition['set_id']]
            if not entry.bake_maps:
                raise PainterError('Select at least one bake map for every texture set')
            definition.update(resolution=int(entry.resolution), bake_maps=sorted(entry.bake_maps),
                              baking=bake_settings(entry))
    destination = Path(bpy.path.abspath(path))
    temporary = destination.with_suffix('.json.tmp')
    try:
        temporary.write_text(json.dumps(job, indent=2), encoding='utf-8')
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)