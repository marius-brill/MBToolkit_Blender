"""Input handling regressions; run in disposable background Blender."""
import importlib
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon = importlib.import_module(ROOT.name)
jobs = importlib.import_module(ROOT.name + '.features.substance_painter.jobs')
matching = importlib.import_module(ROOT.name + '.features.substance_painter.matching')
evaluation = importlib.import_module(ROOT.name + '.features.substance_painter.evaluation')


def main():
    assert bpy.app.background
    addon.register()
    addon.feature_manager.sync(type('Settings', (), {'enable_substance_painter': True})())
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    ctx = bpy.context
    settings = ctx.scene.mbt_painter
    lows, highs = [], []
    for role, count, objects in (('LOW', 2, lows), ('HIGH', 2, highs)):
        for index in range(count):
            bpy.ops.mesh.primitive_cube_add()
            obj = ctx.object
            obj.name = f'body_{role.lower()}_{index}'
            bpy.ops.mbt.painter_assign(role=role)
            objects.append(obj)
    with TemporaryDirectory() as folder:
        settings.output_dir = folder
        # One high -> several lows, several highs -> one low, and shared groups.
        names, pairs = matching.resolve(ctx, lows, highs[:1])
        assert set(matching.targets(pairs[highs[0]])) == set(lows)
        assert len(set(names.values())) == 3
        names, pairs = matching.resolve(ctx, lows[:1], highs)
        assert all(pairs[obj] == lows[0] for obj in highs)
        for obj in lows + highs:
            obj.mbt_bake_group = 'Shared'
        names, pairs = matching.resolve(ctx, lows, highs)
        assert len(set(names.values())) == 4
        assert all(set(matching.targets(value)) == set(lows) for value in pairs.values())
        # Offset mirrored islands remain unchanged, including negative offsets.
        for item in lows[0].data.uv_layers.active.data:
            item.uv.x += 2
        for item in lows[1].data.uv_layers.active.data:
            item.uv.x -= 2
        original = [[tuple(item.uv) for item in obj.data.uv_layers.active.data] for obj in lows]
        jobs.validate(ctx)
        # Hidden collection ancestors, view-layer exclusion, object hide and locks.
        parent = bpy.data.collections.new('HiddenParent')
        ctx.scene.collection.children.link(parent)
        parent.children.link(settings.low_collection)
        settings.texture_collection.children.unlink(settings.low_collection)
        settings.texture_collection.children.link(parent)
        parent.hide_viewport = True
        parent.hide_select = True
        layer = ctx.view_layer.layer_collection.children[parent.name]
        layer.exclude = True
        highs[0].hide_set(True)
        highs[1].hide_viewport = True
        jobs.prepare(ctx, automatic=True)
        layer = ctx.view_layer.layer_collection.children[parent.name]
        assert layer.exclude and parent.hide_viewport and parent.hide_select, (layer.exclude, parent.hide_viewport, parent.hide_select)
        assert highs[0].hide_get() and highs[1].hide_viewport
        assert original == [[tuple(item.uv) for item in obj.data.uv_layers.active.data] for obj in lows]
        jobs.prepare(ctx, automatic=True)
        assert len(jobs.read_job(settings.last_job)['texture_sets']) == 2
        layer = ctx.view_layer.layer_collection.children[parent.name]
        with patch.object(jobs, 'export_steps', side_effect=RuntimeError('export failure')):
            try:
                jobs.prepare(ctx, automatic=True)
            except RuntimeError:
                pass
            else:
                raise AssertionError('Expected failed export')
        layer = ctx.view_layer.layer_collection.children[parent.name]
        assert layer.exclude and parent.hide_viewport and highs[0].hide_get()
        # All issue meshes collected at once; hard failures cannot be ignored.
        for obj in lows:
            obj.data.uv_layers.remove(obj.data.uv_layers.active)
        try:
            jobs.validate(ctx, ignore_warnings=True)
        except jobs.ValidationIssues as error:
            assert error.blocking and {entry['object'] for entry in error.issues} == {obj.name for obj in lows}
        else:
            raise AssertionError('Missing UVs must block')
        for obj in lows:
            uv = obj.data.uv_layers.new()
            for item in uv.data:
                item.uv = (0.5, 0.5)
        try:
            jobs.validate(ctx)
        except jobs.ValidationIssues as error:
            assert not error.blocking and len(error.issues) == 2
            entries = error.issues
        else:
            raise AssertionError('Collapsed triangles must warn')
        jobs.validate(ctx, ignore_warnings=True)
        # Popup branches without invoking GUI in this background test process.
        assert bpy.ops.mbt.painter_issues(issues=json.dumps(entries), action='PREPARE',
                                         connect=False, choice='IGNORE') == {'FINISHED'}
        assert bpy.ops.mbt.painter_issues(issues=json.dumps(entries), action='PREPARE',
                                         connect=False, choice='SELECT') == {'FINISHED'}
        assert set(ctx.selected_objects) == set(lows)
        layer = ctx.view_layer.layer_collection.children[parent.name]
        assert not layer.exclude and not parent.hide_viewport
    addon.unregister()
    print('PASS: grouped matching, offset UVs, hidden/excluded inputs, failure restoration, aggregated validation and popup actions', flush=True)


if __name__ == '__main__':
    main()