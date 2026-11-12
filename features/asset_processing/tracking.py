"""Explicit-operation dependency checks; never regenerate outputs or scan on draw."""
import hashlib
import json

from . import generation, uv
from .identity import token
from ..substance_painter.evaluation import available

REVISION = 1
HIGH_FIELDS = ('high_mode', 'subdivision', 'crease_angle', 'remesh', 'automatic_resolution', 'voxel_size', 'detail_tolerance', 'smoothing', 'max_faces', 'max_work_gib')


def digest(value):
    return hashlib.sha256(repr(value).encode('utf-8')).hexdigest()


def baselines(owner):
    try:
        result = json.loads(owner.stage_baselines or '{}')
        return result if isinstance(result, dict) else {}
    except (ValueError, TypeError):
        return {}


def record(owner, stage, inputs):
    records = baselines(owner)
    records[stage] = {'revision': REVISION, 'inputs': inputs}
    owner.stage_baselines = json.dumps(records, sort_keys=True)


def mesh_input(context, obj, evaluated=False):
    if obj is None or obj.type != 'MESH' or obj.name not in context.scene.objects:
        raise ValueError('Referenced mesh is missing from this scene')
    if not evaluated:
        return digest((generation.fingerprint(obj), uv.layout_signature(obj.data)))
    with available(context, [obj]):
        snapshot = generation.snapshot(context, obj, 'MBT Dependency Check')
        try:
            return mesh_input(context, snapshot)
        finally:
            generation.discard(snapshot)


def source_input(context, component):
    return mesh_input(context, component.source, evaluated=True)


def high_input(context, component):
    return digest((source_input(context, component),
                   tuple(getattr(component, field) for field in HIGH_FIELDS)))


def uv_inputs(context, asset, component):
    members = uv.group(asset, component)
    return digest((uv.settings_signature(context, asset, members),
                   tuple((item.component_id, mesh_input(context, item.low),
                          mesh_input(context, item.low, True) if item.low and item.low.modifiers else None) for item in members),
                   context.scene.unit_settings.scale_length))


def export_inputs(context, asset):
    from .export import high_objects
    settings = context.scene.mbt_assets
    painter = context.scene.mbt_painter
    return digest((asset.asset_id, asset.name, settings.export_low, settings.export_high,
                   painter.output_dir, painter.normal_format,
                   tuple((item.component_id, item.name, token(context, item, asset), item.high_mode,
                          (item.low.name, mesh_input(context, item.low, True)) if settings.export_low and item.low else None,
                          tuple((obj.name, mesh_input(context, obj, True)) for obj in high_objects(item)) if settings.export_high else ())
                         for item in asset.components)))


def validation_inputs(context, asset):
    from .export import high_objects
    return digest((context.scene.mbt_painter.output_dir,
                   context.scene.mbt_assets.export_low, context.scene.mbt_assets.export_high,
                   tuple((item.component_id, source_input(context, item),
                          uv_inputs(context, asset, item), item.uv_allow_overlap, item.uv_locked,
                           item.uv_reference, item.high_mode, item.detail_tolerance,
                          tuple(mesh_input(context, obj, True) for obj in high_objects(item)))
                         for item in asset.components)))


def row(owner, stage, state, reason):
    item = owner.stages.add()
    item.name, item.state, item.reason = stage, state, reason


def compare(owner, stage, inputs, changed):
    baseline = baselines(owner).get(stage)
    if not isinstance(baseline, dict):
        row(owner, stage, 'UNKNOWN', 'No successful processing baseline; check does not adopt existing outputs.')
    elif baseline.get('revision') != REVISION:
        row(owner, stage, 'UNKNOWN', 'Processor signature revision changed; processing baseline needs renewal.')
    elif baseline.get('inputs') != inputs:
        row(owner, stage, 'OUTDATED', changed)
    else:
        row(owner, stage, 'CURRENT', 'Matches the last successful operation. Snapshot; check again after edits.')


def check(context, asset):
    """Publish status metadata only. Failed checks never update processing baselines."""
    from .export import high_objects
    for component in asset.components:
        component.stages.clear()
        try:
            if component.low is None:
                row(component, 'LOW', 'NOT_PROCESSED', 'No working low. Generate explicitly.')
            else:
                compare(component, 'LOW', source_input(context, component),
                        'Source changed since low creation. Existing low will NEVER be refreshed automatically.')
            if component.high_mode == 'DISABLED':
                row(component, 'HIGH', 'BLOCKED', 'High generation disabled by artist.')
            elif component.high_mode == 'CUSTOM':
                row(component, 'HIGH', 'BLOCKED', 'Custom highs are artist-owned inputs; never regenerated.' if high_objects(component)
                    else 'Assign custom high meshes first.')
            elif component.generated_high is None:
                row(component, 'HIGH', 'NOT_PROCESSED', 'No generated high.')
            elif (not generation.owned(component.generated_high, component, 'HIGH') or
                  component.generated_high.data.users != 1 or component.generated_high.library or
                  generation.fingerprint(component.generated_high) != component.high_signature):
                row(component, 'HIGH', 'BLOCKED', 'Generated high is edited, shared or foreign. Preserve as Custom High.')
            else:
                compare(component, 'HIGH', high_input(context, component), 'Evaluated source or DynaBool settings changed.')
            members = uv.group(asset, component)
            if component.low is None:
                row(component, 'UV', 'NOT_PROCESSED', 'Prepare a low first.')
            elif any(item.uv_locked or item.uv_mode == 'PRESERVE' for item in members):
                row(component, 'UV', 'BLOCKED', 'Texture-set member is protected or Preserve. Check never unlocks or applies UVs.')
            else:
                uv.check_scope(context, asset, members)
                uv.writable(context, members)
                compare(component, 'UV', uv_inputs(context, asset, component),
                        'Low geometry/layout, seams, pins, UV settings or shared texture-set dependencies changed.')
        except (ValueError, RuntimeError) as error:
            row(component, 'CHECK', 'UNKNOWN', str(error))
    asset.stages.clear()
    for stage, function, reason in (
            ('VALIDATION', validation_inputs, 'Validation inputs changed; validate again.'),
            ('EXPORT', export_inputs, 'Export inputs or settings changed; export explicitly to a fresh folder.')):
        try:
            compare(asset, stage, function(context, asset), reason)
        except (ValueError, RuntimeError) as error:
            row(asset, stage, 'UNKNOWN', str(error))
    row(asset, 'BAKE_HANDOFF', 'NOT_PROCESSED', 'Asset-to-Bake handoff is not implemented; existing Bake setup is unchanged.')
    asset.outdated_report = 'Checked dependency snapshots. No geometry, UVs, exports or Bake assignments changed.'
    return asset.outdated_report