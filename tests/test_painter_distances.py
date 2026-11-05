"""Automatic distance estimation; disposable background Blender only, no Painter."""
import importlib
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

import bpy
from mathutils import Matrix

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon = importlib.import_module(ROOT.name)
jobs = importlib.import_module(ROOT.name + '.features.substance_painter.jobs')
distances = importlib.import_module(ROOT.name + '.features.substance_painter.distances')
evaluation = importlib.import_module(ROOT.name + '.features.substance_painter.evaluation')


def main():
    assert bpy.app.background
    addon.register()
    addon.feature_manager.sync(type('Preferences', (), {'enable_substance_painter': True})())
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    settings = bpy.context.scene.mbt_painter

    def plane(name, height, role):
        bpy.ops.mesh.primitive_plane_add(size=2, location=(0, 0, height))
        obj = bpy.context.object
        obj.name = name
        assert bpy.ops.mbt.painter_assign(role=role) == {'FINISHED'}
        return obj

    low = plane('Panel_low', 0, 'LOW')
    front = plane('Raised_high', .2, 'HIGH')
    rear = plane('Inset_high', -.1, 'HIGH')
    for obj in (low, front, rear):
        obj.mbt_bake_group = 'Panel'
    first = settings.texture_sets[0]
    assert first.auto_distances
    pairs = {front: low, rear: low}

    def estimate(entries=(first,), matches=pairs):
        bpy.context.view_layer.update()
        return evaluation.finish_steps(distances.estimate_steps(bpy.context, entries, matches))

    initial = estimate()[first.as_pointer()]
    assert 22 < initial['front_distance'] < 23, initial
    assert 11 < initial['rear_distance'] < 12, initial
    assert not initial['relative_distance']
    assert not initial['distance_estimate']['coverage_guaranteed']
    # Scene-unit conversion exactly matches Blender's bundled FBX exporter.
    units = bpy.context.scene.unit_settings
    units.system, units.scale_length = 'METRIC', .01
    centimeters = estimate()[first.as_pointer()]
    assert abs(centimeters['front_distance'] * 100 - initial['front_distance']) < 1e-5
    units.system, units.scale_length = 'NONE', 1
    # Shared rigid transforms plus nonuniform scale are evaluated in world space.
    transform = Matrix.Translation((4, -3, 7)) @ Matrix.Rotation(.6, 4, 'Y') @ Matrix.Diagonal((2, 1, 3, 1))
    originals = {obj: obj.matrix_world.copy() for obj in (low, front, rear)}
    for obj, matrix in originals.items():
        obj.matrix_world = transform @ matrix
    scaled = estimate()[first.as_pointer()]
    assert scaled['front_distance'] > initial['front_distance'] * 2.9
    assert scaled['rear_distance'] > initial['rear_distance'] * 2.9
    for obj, matrix in originals.items():
        obj.matrix_world = matrix
    # An evaluated modifier, rather than source coordinates, determines reach.
    modifier = front.modifiers.new('Raised thickness', 'SOLIDIFY')
    modifier.thickness, modifier.offset = .3, 1
    modified = estimate()[first.as_pointer()]
    assert modified['front_distance'] > initial['front_distance'] * 2
    front.modifiers.remove(modifier)
    # A second set far away must not influence the first set's receiver matching.
    bpy.ops.mbt.painter_texture_set(action='ADD')
    second = settings.texture_sets[1]
    other_low = plane('Other_low', 0, 'LOW')
    other_high = plane('Other_high', .8, 'HIGH')
    other_low.location.x = other_high.location.x = 100
    both = estimate((first, second), pairs | {other_high: other_low})
    assert abs(both[first.as_pointer()]['front_distance'] - initial['front_distance']) < 1e-5
    assert both[second.as_pointer()]['front_distance'] > 88
    first.auto_distances = False
    assert first.as_pointer() not in estimate((first, second), pairs | {other_high: other_low})
    first.auto_distances = True
    with TemporaryDirectory() as folder:
        settings.output_dir = folder
        jobs.prepare(bpy.context, automatic=True)
        job = jobs.read_job(settings.last_job)
        definitions = {item['set_id']: item for item in job['set_definitions']}
        assert abs(first.front_distance - initial['front_distance']) < 1e-5
        assert not first.relative_distance and not settings.relative_distance
        assert definitions[first.set_id]['baking']['distance_estimate']['coverage_guaranteed'] is False
        # Rebaking reuses estimates for the exported geometry, not live edits.
        front.location.z = 10
        jobs.update_bake_settings(settings.last_job, settings)
        rebake = jobs.read_job(settings.last_job)
        assert rebake['set_definitions'] == job['set_definitions']
    addon.unregister()
    print('PASS: automatic signed distances, units, transforms, modifiers, per-set scope, manual override, manifest and rebake')


if __name__ == '__main__':
    main()