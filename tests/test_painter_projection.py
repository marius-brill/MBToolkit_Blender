"""Disposable Blender projection estimates and read-only Painter capability tests."""
import importlib
import json
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch

import bpy
from mathutils import Matrix, Vector

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon = importlib.import_module(ROOT.name)
projection = importlib.import_module(ROOT.name + '.features.substance_painter.projection')


def capability_tests():
    package = ModuleType('substance_painter')
    package.__version__ = 'controlled'
    project = ModuleType('substance_painter.project')
    textures = ModuleType('substance_painter.textureset')
    baking = ModuleType('substance_painter.baking')
    project.is_in_edition_state = lambda: True
    project.is_busy = lambda: False
    textures.all_texture_sets = lambda: [SimpleNamespace(name=lambda: 'Test')]
    prop = SimpleNamespace(value=lambda: 'Distance-based', enum_values=lambda: {'Distance-based': 0})
    baking.BakingParameters = Mock()
    baking.BakingParameters.from_texture_set.return_value.common.return_value = {
        'CageMode': prop, 'SkewMap': prop, 'OutputSize': prop}
    modules = {'substance_painter': package, 'substance_painter.project': project,
               'substance_painter.textureset': textures, 'substance_painter.baking': baking}
    with patch.dict(sys.modules, modules):
        namespace = {}
        exec(compile((ROOT / 'features/substance_painter/painter_remote.py').read_text(
            encoding='utf-8'), 'painter_remote.py', 'exec'), namespace)
        result = json.loads(namespace['_mbt_projection_capabilities']())
        assert result['state'] == 'DISCOVERED'
        assert not result['correction_verified']
        assert not result['automatic_correction_ready']
        assert not result['native_skew_candidates']
        assert not result['common_parameter_isolation_available']
        assert not result['texture_sets'][0]['custom_cage_available']
        assert result['texture_sets'][0]['native_skew_properties'] == ['SkewMap']
        assert set(result['texture_sets'][0]['properties']) == {'CageMode', 'SkewMap'}
        baking.BakingParameters.set.assert_not_called()
        project.is_busy = lambda: True
        assert json.loads(namespace['_mbt_projection_capabilities']())['state'] == 'NOT_READY'
        project.is_busy = lambda: False
        baking.unlink_all_common_parameters = Mock()
        baking.BakingParameters.from_texture_set.return_value.common.return_value = {
            'CageMode': SimpleNamespace(value=lambda: 0, enum_values=lambda: {'Custom file': 2}),
            'CageMesh': SimpleNamespace(value=lambda: '', enum_values=lambda: {})}
        result = json.loads(namespace['_mbt_projection_capabilities']())
        assert result['common_parameter_isolation_available']
        assert result['texture_sets'][0]['custom_cage_available']
        assert not result['correction_verified'], 'Available cage is not verified local correction'
        baking.unlink_all_common_parameters.assert_not_called()
        baking.BakingParameters.from_texture_set.side_effect = RuntimeError('unsupported')
        assert json.loads(namespace['_mbt_projection_capabilities']())['state'] == 'UNAVAILABLE'


def main():
    assert bpy.app.background
    capability_tests()
    vertices = tuple(Vector(v) for v in ((0, 0, 0), (1, 0, 0), (0, 1, 0)))
    uvs = tuple(Vector(v) for v in ((0, 0), (1, 0), (0, 1)))
    normal = Vector((0, 0, 1))
    direction = Vector((1, 0, 1)).normalized()
    assert abs(projection.pixel_shift(0.1, direction, normal, vertices, uvs, 100) - 10) < 1e-5
    assert projection.pixel_shift(1, normal, normal, vertices, uvs, 100) == 0
    assert projection.pixel_shift(1, -normal, normal, vertices, uvs, 100) is None
    addon.register()
    addon.feature_manager.sync(SimpleNamespace(enable_substance_painter=True))
    try:
        bpy.ops.mesh.primitive_plane_add(size=2)
        low = bpy.context.object
        low.name = 'Panel_low'
        bpy.ops.mbt.painter_assign(role='LOW')
        bpy.ops.mesh.primitive_cylinder_add(vertices=12, radius=0.2, depth=0.2, location=(0.5, 0, 0.12))
        high = bpy.context.object
        high.name = 'Panel_high'
        bpy.ops.mbt.painter_assign(role='HIGH')
        original = tuple(vertex.co.copy() for vertex in low.data.vertices)
        high.hide_set(True)
        high.hide_select = True
        count = len(bpy.data.meshes)
        result = projection.analyze(bpy.context)
        assert not result['issues'], result
        assert result['raised_samples'] > 0
        assert not result['correction_applied']
        assert high.hide_get() and high.hide_select
        assert len(bpy.data.meshes) == count
        assert tuple(vertex.co for vertex in low.data.vertices) == original
        # Cancellation at a generator yield restores hidden inputs.
        steps = projection.analyze_steps(bpy.context)
        next(steps)
        steps.close()
        assert high.hide_get() and high.hide_select
        # A box has averaged geometric normals which tilt across a flat face.
        collection = bpy.context.scene.mbt_painter.low_collection
        collection.objects.unlink(low)
        bpy.ops.mesh.primitive_cube_add(size=2)
        box = bpy.context.object
        box.name = 'Panel_low'
        collection.objects.link(box)
        for other in tuple(box.users_collection):
            if other != collection:
                other.objects.unlink(box)
        high.location.z = 1.12
        bpy.context.view_layer.update()
        snapshot = projection.snapshot(bpy.context, box)
        for normal in snapshot['averaged']:
            assert max(abs(abs(component) - 3 ** -.5) for component in normal) < 1e-5
        result = projection.analyze(bpy.context)
        assert any(issue.get('max_pixels', 0) > 1 for issue in result['issues']), result
        before = max(issue.get('max_pixels', 0) for issue in result['issues'])
        transform = Matrix.Translation((3, -2, 4)) @ Matrix.Rotation(0.7, 4, 'Y')
        box.matrix_world = transform @ box.matrix_world
        high.matrix_world = transform @ high.matrix_world
        bpy.context.view_layer.update()
        transformed = projection.analyze(bpy.context)
        after = max(issue.get('max_pixels', 0) for issue in transformed['issues'])
        assert abs(before - after) < 0.01, (before, after)
        settings = bpy.context.scene.mbt_painter
        settings.projection_normals = 'FACE'
        face = projection.analyze(bpy.context)
        assert not any(issue.get('max_pixels', 0) > 1 for issue in face['issues'])
        settings.projection_normals = 'AVERAGED'
        # No averaging follows shading normals, not geometric face normals.
        for polygon in box.data.polygons:
            polygon.use_smooth = True
        box.data.update()
        box.update_tag(refresh={'DATA'})
        bpy.context.view_layer.update()
        settings.projection_normals = 'FACE'
        smooth = projection.analyze(bpy.context)
        assert any(issue.get('max_pixels', 0) > 1 for issue in smooth['issues']), smooth
        for polygon in box.data.polygons:
            polygon.use_smooth = False
        box.data.update()
        box.update_tag(refresh={'DATA'})
        bpy.context.view_layer.update()
        settings.projection_normals = 'AVERAGED'
        assert bpy.ops.mbt.painter_action(action='PROJECTION') == {'FINISHED'}
        assert bpy.context.scene.mbt_painter.issue_rows
        assert json.loads(bpy.context.scene.mbt_painter.projection_report)['checked_samples']
        # Missing UVs are skipped, not certified as safe.
        box.data.uv_layers.remove(box.data.uv_layers.active)
        box.data.update()
        box.update_tag(refresh={'DATA'})
        bpy.context.view_layer.update()
        result = projection.analyze(bpy.context)
        assert result['skipped_samples'] > 0 and result['checked_samples'] == 0, result
        assert result['issues'][0]['unassessed_samples'] > 0
        box.scale.x = 0
        bpy.context.view_layer.update()
        try:
            projection.analyze(bpy.context)
        except ValueError as error:
            assert 'singular' in str(error)
        else:
            raise AssertionError('Singular transform accepted')
        bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16)
        sphere = projection.snapshot(bpy.context, bpy.context.object)
        assert sphere['curved'], 'Curved shell must not be treated as a planar receiver'
    finally:
        addon.unregister()
    print('PASS: projection math, planar baseline, box skew, hidden-state cleanup, UV skips, capability gating')


if __name__ == '__main__':
    main()