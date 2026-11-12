"""Read-only stage diagnostics. Findings are snapshots, not artifact guarantees."""
from collections import defaultdict
from types import SimpleNamespace
import math
import bmesh

from ..substance_painter import jobs
from ..uv_suite import geometry
from . import uv
from .export import high_objects, plan


def validate(context, asset):
    findings = []
    def issue(component, stage, severity, reason, action, obj=None):
        findings.append((component, stage, severity, reason, action, obj))
    groups = defaultdict(list)
    for component in asset.components:
        groups[uv.set_key(component, asset)].append(component)
        source = component.source
        if source is None or source.name not in context.scene.objects:
            issue(component, 'ANALYZE', 'ERROR', 'Source mesh is missing from this scene.', 'Assign the source or remove this component.', source)
        low = component.low
        if low is None:
            issue(component, 'GENERATE', 'ERROR', 'Working low is missing.', 'Generate the component before preparing UVs or exporting.')
        if component.high_mode != 'DISABLED' and not high_objects(component):
            issue(component, 'GENERATE', 'ERROR', 'High-poly input is missing.', 'Generate DynaBool or assign a custom high mesh.')
        for obj in dict.fromkeys(obj for obj in [source, low] + high_objects(component) if obj):
            if obj.type != 'MESH':
                issue(component, 'GEOMETRY', 'ERROR', 'Referenced object is not a mesh.', 'Assign a mesh object.', obj)
                continue
            if obj.modifiers:
                issue(component, 'GEOMETRY', 'INFO', 'Topology findings inspect base mesh only; evaluated modifier output is not fully validated.',
                      'Inspect evaluated high geometry; dependency checks are not quality validation.', obj)
            if jobs.singular_transform(obj.matrix_world):
                issue(component, 'GEOMETRY', 'ERROR', 'Object transform is singular.', 'Correct zero scale before processing.', obj)
            elif obj.matrix_world.determinant() < 0:
                issue(component, 'GEOMETRY', 'WARNING', 'Object has a mirrored transform.', 'Inspect normals and tangent-space shading; do not blindly apply source transforms.', obj)
            elif any(abs(abs(value) - 1) > 1e-5 for value in obj.matrix_world.to_scale()):
                issue(component, 'GEOMETRY', 'INFO', 'Object scale is not unit scale.', 'Review scale-sensitive voxel and projection settings.', obj)
            if any(not math.isfinite(value) for vertex in obj.data.vertices for value in vertex.co):
                issue(component, 'GEOMETRY', 'ERROR', 'Mesh contains non-finite coordinates.', 'Repair the mesh before processing.', obj)
                continue
            if len(obj.data.polygons) > 50000:
                issue(component, 'GEOMETRY', 'INFO', 'Detailed topology validation skipped above 50,000 faces.', 'Inspect this mesh manually or validate a smaller mesh.', obj)
                continue
            bm = bmesh.new()
            try:
                bm.from_mesh(obj.data)
                if not bm.faces:
                    issue(component, 'GEOMETRY', 'ERROR', 'Mesh has no faces.', 'Assign a nonempty mesh.', obj)
                degenerate = sum(face.calc_area() <= 1e-12 for face in bm.faces)
                if degenerate:
                    issue(component, 'GEOMETRY', 'WARNING', f'{degenerate} near-zero-area faces.', 'Inspect and repair degenerate faces; threshold is mesh-local.', obj)
                nonmanifold = sum(not edge.is_manifold for edge in bm.edges)
                if nonmanifold:
                    issue(component, 'GEOMETRY', 'WARNING', f'{nonmanifold} boundary/non-manifold edges.', 'Open meshes can be intentional; inspect before voxel fusion.', obj)
            finally:
                bm.free()
        if low and component.uv_locked and component.uv_reference and uv.layout_signature(low.data) != component.uv_reference:
            issue(component, 'UV', 'WARNING', 'Protected UV layout changed since the last approved baseline.', 'Review texture alignment; acknowledge the layout only after checking it.', low)
        if component.high_mode == 'DYNABOOL' and component.remesh:
            issue(component, 'GENERATE', 'INFO', 'Automatic remesh uses sampled, not exhaustive, feature checks.', 'Inspect thin walls, holes and sharp-edge silhouettes.', component.generated_high)
    for members in groups.values():
        states, meshes = [], []
        try:
            for component in members:
                low = component.low
                if low is None or low.type != 'MESH':
                    continue
                if low.data.uv_layers.active is None:
                    issue(component, 'UV', 'ERROR', 'Active UV map is missing.', 'Prepare UVs on a derived low or create a UV map manually.', low)
                    continue
                if len(low.data.polygons) > 50000:
                    issue(component, 'UV', 'WARNING', 'UV validation skipped above 50,000 faces.', 'Validate a smaller layout; no UV readiness claim is made.', low)
                    continue
                bm = bmesh.new()
                meshes.append(bm)
                bm.from_mesh(low.data)
                states.append(SimpleNamespace(bm=bm, layer=bm.loops.layers.uv.active, targets=set(bm.faces), obj=low))
            if states:
                settings = uv.options(context, members)
                report = geometry.inspect(SimpleNamespace(states=states), settings, padding=True)
                checks = (
                    ('degenerate', 'ERROR', 'collapsed UV triangles', 'Unwrap or repair collapsed UVs.'),
                    ('outside', 'WARNING', 'UV triangles outside tile 1001', 'Review intentional offsets; processor packing currently targets tile 1001.'),
                    ('gap_violations', 'WARNING', 'island gap pairs below the requested padding', 'Repack the full texture set or adjust padding.'),
                    ('border_violations', 'WARNING', 'triangles inside the requested tile border', 'Review border padding before baking.'))
                for key, severity, label, action in checks:
                    if report[key]:
                        for component in members:
                            issue(component, 'UV', severity, f'Texture-set total: {report[key]} {label}.', action, component.low)
                if report['overlaps'] and not all(item.uv_allow_overlap for item in members):
                    for component in members:
                        issue(component, 'UV', 'WARNING', f'Texture-set total: {report["overlaps"]} overlapping triangle pairs.', 'Review intentional stacks or jointly repack; enable Allow UV Overlap for every member only when intended.', component.low)
                densities = []
                for state in states:
                    for island in geometry.islands(state):
                        try:
                            densities.append(geometry.density(state, island, settings.width, settings.height, context.scene.unit_settings.scale_length))
                        except RuntimeError:
                            pass
                if densities and max(densities) > min(densities) * 1.25:
                    for component in members:
                        issue(component, 'UV', 'INFO', 'Island texel densities vary by more than 25% across this texture set.', 'Review whether intentional density allocation is appropriate.', component.low)
        except (ValueError, RuntimeError) as error:
            for component in members:
                issue(component, 'UV', 'WARNING', 'UV validation incomplete: ' + str(error), 'Correct invalid UVs or reduce layout complexity and validate again.', component.low)
        finally:
            for bm in meshes:
                bm.free()
    if not context.scene.mbt_painter.output_dir.strip():
        issue(None, 'EXPORT', 'ERROR', 'Output folder is empty.', 'Choose an output folder in Export.')
    try:
        settings = context.scene.mbt_assets
        plan(context, asset, settings.export_low, settings.export_high)
    except ValueError as error:
        issue(None, 'EXPORT', 'ERROR', str(error), 'Resolve the input assignments before exporting.')
    asset.issues.clear()
    for component, stage, severity, reason, action, obj in findings:
        row = asset.issues.add()
        row.component_id = component.component_id if component else ''
        row.component_name = component.name if component else asset.name
        row.mesh = obj
        row.stage = stage
        row.severity = severity
        row.reason = reason
        row.action = action
    asset.issue_index = 0
    errors = sum(row.severity == 'ERROR' for row in asset.issues)
    warnings = sum(row.severity == 'WARNING' for row in asset.issues)
    asset.validation_report = f'{errors} errors, {warnings} warnings, {len(asset.issues) - errors - warnings} info. Snapshot; revalidate after edits.'
    from . import tracking
    try:
        if any('skipped above' in row.reason or 'validation incomplete' in row.reason for row in asset.issues):
            raise ValueError('Validation coverage is incomplete')
        tracking.record(asset, 'VALIDATION', tracking.validation_inputs(context, asset))
    except (ValueError, RuntimeError):
        # Incomplete checks must not bless a previous report as current.
        records = tracking.baselines(asset)
        records.pop('VALIDATION', None)
        import json
        asset.stage_baselines = json.dumps(records)
    return asset.validation_report