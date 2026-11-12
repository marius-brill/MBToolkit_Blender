"""Disposable Blender regression for editable DynaBool resolution and density."""
import importlib
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
dynabool = importlib.import_module(ROOT.name + '.features.geonodes.dynabool')
gn = importlib.import_module(ROOT.name + '.core.gn')


def inputs(obj, modifier, **values):
    for socket in modifier.node_group.interface.items_tree:
        if getattr(socket, 'in_out', '') == 'INPUT' and socket.name in values:
            gn.set_modifier_input(modifier, socket.identifier, values[socket.name])
    obj.update_tag()
    bpy.context.view_layer.update()


def triangles(obj):
    evaluated = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
    mesh = evaluated.to_mesh()
    try:
        mesh.calc_loop_triangles()
        return len(mesh.loop_triangles)
    finally:
        evaluated.to_mesh_clear()


def main():
    assert bpy.app.background
    addon = importlib.import_module(ROOT.name)
    addon.register()
    from types import SimpleNamespace
    addon.feature_manager.sync(SimpleNamespace(enable_substance_painter=True, enable_geonodes=True))
    generation = importlib.import_module(ROOT.name + '.features.asset_processing.generation')
    try:
        bpy.ops.object.select_all(action='DESELECT')
        bpy.ops.mesh.primitive_cube_add(size=0.1)
        obj = bpy.context.object
        old = dynabool._build(revision=6)
        old['mbt_rev'] = 6
        modifier = obj.modifiers.new('DynaBool', 'NODES')
        modifier.node_group = old
        assert bpy.ops.mbt.upgrade_dynabool() == {'FINISHED'}
        assert modifier.node_group == dynabool.get_group() and modifier.node_group != old
        automatic = next(s for s in modifier.node_group.interface.items_tree if s.name == 'Automatic Resolution')
        assert not automatic.hide_in_modifier
        new_count = triangles(obj)
        assert 100 < new_count < 100000, new_count
        assert not any(s.name == 'Target Triangles' for s in modifier.node_group.interface.items_tree)
        print(f'PASS shape-driven cube: {new_count:,} triangles; no target socket')
        inputs(obj, modifier, **{'Automatic Resolution': False, 'Voxel Size': 0.004,
                                 'Resolved Voxel Size': 0.0005})
        coarse = triangles(obj)
        inputs(obj, modifier, **{'Resolved Voxel Size': 0.001})
        assert triangles(obj) == coarse, 'Internal resolution overrode manual input'
        inputs(obj, modifier, **{'Voxel Size': 0.002})
        fine = triangles(obj)
        assert fine > coarse * 2
        inputs(obj, modifier, **{'Automatic Resolution': True, 'Resolved Voxel Size': 0.0})
        assert triangles(obj) == new_count
        inputs(obj, modifier, **{'Automatic Resolution': False})
        with tempfile.TemporaryDirectory() as directory:
            name = obj.name
            path = str(Path(directory) / 'resolution.blend')
            bpy.ops.wm.save_as_mainfile(filepath=path)
            bpy.ops.wm.open_mainfile(filepath=path)
            obj = bpy.data.objects[name]
            assert triangles(obj) == fine
        print('PASS modifier toggle, manual voxel edits, internal override bypass, save/reload and rev6 upgrade')
        bpy.ops.object.select_all(action='DESELECT')
        bpy.ops.mesh.primitive_cube_add(size=0.1)
        source = bpy.context.object
        assert bpy.ops.mbt.asset_edit(action='CREATE') == {'FINISHED'}
        asset = bpy.context.scene.mbt_assets.assets[-1]
        component = asset.components[0]
        component.automatic_resolution = False
        component.voxel_size = 0.001
        generation.generate(bpy.context, asset, component)
        high = component.generated_high
        assert abs(high['mbt_resolved_voxel'] - component.voxel_size) < 1e-10
        modifier = high.modifiers[0]
        stored = gn.modifier_inputs(modifier)
        socket = next(s for s in modifier.node_group.interface.items_tree if s.name == 'Automatic Resolution')
        assert not getattr(stored, socket.identifier).value
        signature = generation.fingerprint(high)
        component.voxel_size = 0.05
        try:
            with patch.object(generation.resolution, 'quality', return_value=(False, 0.01)):
                generation.generate(bpy.context, asset, component)
        except ValueError as error:
            assert 'manual voxel' in str(error) or 'REMESH:' in str(error), str(error)
        else:
            raise AssertionError('Coarse manual voxel silently refined')
        assert generation.fingerprint(high) == signature
        component.automatic_resolution = True
        generation.generate(bpy.context, asset, component)
        assert component.generated_high == high
        print('PASS manual asset generation, strict failure rollback and switching back to automatic')
    finally:
        addon.unregister()


if __name__ == '__main__':
    main()