"""Clickable diagnostics and matching safety; disposable Blender only."""
import importlib
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace

import bpy
from mathutils import Matrix

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon = importlib.import_module(ROOT.name)
issues = importlib.import_module(ROOT.name + '.features.substance_painter.issues')
matching = importlib.import_module(ROOT.name + '.features.substance_painter.matching')
jobs = importlib.import_module(ROOT.name + '.features.substance_painter.jobs')
preparation = importlib.import_module(ROOT.name + '.features.substance_painter.preparation')


def main():
    assert bpy.app.background
    addon.register()
    addon.feature_manager.sync(type('Settings', (), {'enable_substance_painter': True})())
    context = bpy.context
    settings = context.scene.mbt_painter

    def cube(name, role, x=0):
        bpy.ops.mesh.primitive_cube_add(location=(x, 0, 0))
        obj = context.object
        obj.name = name
        bpy.ops.mbt.painter_assign(role=role)
        return obj

    low = cube('vehicle_low_panel_low', 'LOW')
    high = cube('vehicle_low_panel_high', 'HIGH')
    assert matching.stem(low.name) == matching.stem(high.name) == 'vehicle_low_panel'
    assert matching.stem('vehicle_low_door_high') != matching.stem(high.name)
    assert matching.stem('body_low_001') == matching.stem('body-high.001') == 'body'
    assert not jobs.singular_transform(Matrix.Diagonal((1e-5, 1e-5, 1e-5, 1)))
    assert not jobs.singular_transform(Matrix.Diagonal((-2, 3, 4, 1)))
    assert jobs.singular_transform(Matrix.Diagonal((0, 1, 1, 1)))
    names, pairs = matching.resolve(context, [low], [high])
    assert pairs[high] == low and names[low].count('_low') == 1
    issues.publish(context, [{'object': high.name, 'reason': 'Ambiguous candidates', 'blocking': False,
                              'targets': [low.name]},
                             {'object': low.name, 'reason': 'Missing UV', 'blocking': True}])
    high.hide_set(True)
    high.hide_select = True
    high.name = 'RenamedIssueMesh'
    assert bpy.ops.mbt.painter_issue_select(index=0) == {'FINISHED'}
    assert context.view_layer.objects.active == high and set(context.selected_objects) == {high}
    assert not high.hide_get() and not high.hide_select
    assert bpy.ops.mbt.painter_issue_select(index=0, candidates=True) == {'FINISHED'}
    assert context.view_layer.objects.active == low
    # Compact diagnostics never repeat assignment fields or candidate metrics.
    sys.path.insert(0, str(ROOT / 'tests'))
    import test_sidebar_sections as sidebar_tests
    sidebar_tests.bpy = bpy

    class IssueLayout(sidebar_tests.Layout):
        def row(self, **kwargs): return IssueLayout(self.records)
        def column(self, **kwargs): return IssueLayout(self.records)
        def box(self): return IssueLayout(self.records)
        def template_list(self, *args, **kwargs): pass
        def prop(self, obj, name, **kwargs):
            self.records.append(('property', name))

    records = []
    issues.draw(IssueLayout(records), context)
    assert ('property', 'mbt_bake_group') not in records
    assert ('property', 'mbt_bake_target') not in records
    assert any(kind == 'mbt.painter_issue_details' for kind, _ in records)
    assert issues.summary('Surface assignment has unmatched detail or spatial regions.')[0] == 'Surface mismatch'
    settings.issue_rows[0].payload = json.dumps({'candidates': [
        {'group': 'Panel', 'score': 0.03472, 'coverage': 0.83, 'sample_count': 128, 'targets': [low.name]}]})
    detail = issues.details_text(settings.issue_rows[0])
    assert '83%' in detail and '128 samples' in detail and '0.03472' in detail
    detail_records = []
    issues.MBT_OT_painter_issue_details.draw(SimpleNamespace(
        layout=IssueLayout(detail_records), report_text=detail), context)
    assert any(kind == 'label' and 'Candidate: Panel' in kw['text'] for kind, kw in detail_records)
    assert bpy.ops.mbt.painter_issue_select(all_meshes=True) == {'FINISHED'}
    assert set(context.selected_objects) == {low, high}
    # Exercise the actual filter method with a small non-RNA receiver.
    dummy = type('Filter', (), {'filter_name': 'missing uv', 'bitflag_filter_item': 1})()
    flags, _ = issues.MBT_UL_painter_issues.filter_items(dummy, context, settings, 'issue_rows')
    assert flags == [0, 1]
    old_name = high.name
    for obj in context.selected_objects:
        obj.select_set(False)
    context.view_layer.objects.active = low
    bpy.data.objects.remove(high, do_unlink=True)
    replacement = cube(old_name, 'HIGH')
    replacement.select_set(False)
    context.view_layer.objects.active = low
    assert settings.issue_rows[0].mesh is None
    assert bpy.ops.mbt.painter_issue_select(index=0) == {'CANCELLED'}
    assert not replacement.select_get() and context.view_layer.objects.active == low
    assert settings.issue_rows[0].mesh is None  # Never rebound by name.
    issues.publish(context, [])
    replacement.name = 'vehicle_low_panel_high'
    with TemporaryDirectory() as folder:
        settings.output_dir = folder
        jobs.prepare(context, automatic=True)
        assert replacement.mbt_bake_target == low == replacement.mbt_bake_auto_target
        issues.publish(context, [{'object': replacement.name, 'reason': 'Persisted candidate', 'blocking': False,
                                  'targets': [low.name]}])
        blend = str(Path(folder) / 'issues.blend')
        bpy.ops.wm.save_as_mainfile(filepath=blend)
        bpy.ops.wm.open_mainfile(filepath=blend)
        settings = context.scene.mbt_painter
        low = settings.issue_rows[0].targets[0].mesh
        replacement = settings.issue_rows[0].mesh
        assert replacement.mbt_bake_auto_target == low
        assert bpy.ops.mbt.painter_issue_select(index=0, candidates=True) == {'FINISHED'}
        assert context.view_layer.objects.active == low
        replacement.name = 'Sculpt'
        replacement.location.x = 100
        context.view_layer.update()
        warnings = []
        matching.resolve(context, [low], [replacement], warnings=warnings)
        assert any(entry.get('assignment') == 'FALLBACK' for entry in warnings)
        replacement.mbt_bake_target = low
        assert replacement.mbt_bake_auto_target is None
        assert matching.resolve(context, [low], [replacement])[1][replacement] == low
        replacement.mbt_bake_target = None
        replacement.location.x = 0
        context.view_layer.update()
        # Unmatched spatial extrema are reported without rejecting the assignment.
        replacement.data.vertices[0].co.x -= 20
        context.view_layer.update()
        warnings = []
        matching.resolve(context, [low], [replacement], warnings=warnings)
        assert warnings
        # Collapsed UVs can navigate to faces, but never through changed topology.
        for uv in low.data.uv_layers.active.data:
            uv.uv = (0.5, 0.5)
        try:
            jobs.validate_uv(low.data, low.name, stage='evaluated/export mesh')
        except jobs.ValidationIssues as error:
            issues.publish(context, error.issues)
        assert bpy.ops.mbt.painter_issue_faces() == {'FINISHED'}
        bpy.ops.object.mode_set(mode='OBJECT')
        assert all(face.select for face in low.data.polygons)
        subdivision = low.modifiers.new('Changed topology', 'SUBSURF')
        context.view_layer.update()
        assert bpy.ops.mbt.painter_issue_faces() == {'CANCELLED'}
        low.modifiers.remove(subdivision)
        # Deterministic surface-based fallback prefers the closer surface even
        # when the competing object's bounding-box center is closer.
        fallback_low = cube('Fallback_low', 'LOW', x=0)
        fallback_low.scale = (99, 99, 99)
        low.location.x = 5
        replacement.location.x = 0
        replacement.data = low.data.copy()
        replacement.mbt_bake_target = None
        context.view_layer.update()
        warnings = []
        _, pairs = matching.resolve(context, [low, fallback_low], [replacement], warnings=warnings)
        assert pairs[replacement] == low
        assert any(entry.get('assignment') == 'FALLBACK' for entry in warnings)
        bpy.ops.mbt.painter_texture_set(action='ADD')
        second_low = cube('Second_low', 'LOW')
        cube('Second_high', 'HIGH')
        settings.active_texture_set = 0
        before = preparation.signature(context)
        second_low.location.y += 1
        context.view_layer.update()
        assert preparation.signature(context) != before
    addon.unregister()
    assert not hasattr(bpy.types.Object, 'mbt_bake_auto_target')
    print('PASS: clickable selection, rename/delete identity, candidates, filtering, role parsing, tiny scale, auto/manual provenance and all-set guards', flush=True)


if __name__ == '__main__':
    main()