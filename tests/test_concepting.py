"""Run in a disposable Blender process with --background --factory-startup."""

import importlib
from math import pi
from pathlib import Path
import sys

import bpy
from mathutils import Euler, Vector

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
feature = importlib.import_module(ROOT.name + '.features.concepting')
gn = importlib.import_module(ROOT.name + '.core.gn')


def select(*objects):
    bpy.ops.object.select_all(action='DESELECT')
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objects[0] if objects else None


def check_projection(obj, scale=1.0, rotation=(0, 0, 0), offset=(0, 0, 0), name=None):
    bpy.context.view_layer.update()
    evaluated = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
    mesh = evaluated.to_mesh()
    try:
        target = name or (obj.data.uv_layers.active.name
                          if obj.data.uv_layers.active else feature.UV_NAME)
        attribute = mesh.attributes[target]
        assert attribute.domain == 'CORNER' and attribute.data_type == 'FLOAT2'
        assert len(mesh.vertices) == len(obj.data.vertices)
        matrix = Euler(rotation).to_matrix()
        for polygon in mesh.polygons:
            normal = matrix @ polygon.normal
            axis = max(range(3), key=lambda i: (abs(normal[i]), i))
            sign = 1 if normal[axis] >= 0 else -1
            for index in polygon.loop_indices:
                position = matrix @ mesh.vertices[mesh.loops[index].vertex_index].co
                position = position * scale + Vector(offset)
                expected = ((position.y * sign, position.z) if axis == 0 else
                            (-position.x * sign, position.z) if axis == 1 else
                            (position.x * sign, position.y))
                actual = attribute.data[index].vector
                assert all(abs(a-b) < 1e-5 for a, b in zip(actual, expected)), (actual[:], expected)
        expected_maps = set(obj.data.uv_layers.keys()) | {target}
        assert set(mesh.uv_layers.keys()) == expected_maps
        for layer in obj.data.uv_layers:
            if layer.name != target:
                assert [tuple(item.uv) for item in mesh.uv_layers[layer.name].data] == [
                    tuple(item.uv) for item in layer.data]
    finally:
        evaluated.to_mesh_clear()


def main():
    assert bpy.app.background
    feature.register()
    try:
        bpy.ops.mesh.primitive_cube_add()
        first = bpy.context.object
        uv = first.data.uv_layers.new(name='ArtistUV')
        for item in uv.data:
            item.uv = (0.25, 0.75)
        first.data.uv_layers.active = uv
        second = first.copy()
        second.data = first.data.copy()
        second.data.uv_layers.active.name = 'SecondActiveUV'
        bpy.context.collection.objects.link(second)
        empty = bpy.data.objects.new('Ignored Empty', None)
        bpy.context.collection.objects.link(empty)
        select(first, second, empty)
        assert bpy.ops.mbt.triplanar_uv() == {'FINISHED'}
        group = first.modifiers[-1].node_group
        assert second.modifiers[-1].node_group == group
        assert feature.get_projection_group() == group
        assert bpy.ops.mbt.triplanar_uv() == {'CANCELLED'}
        assert len(first.modifiers) == len(second.modifiers) == 1
        assert not empty.modifiers
        check_projection(first)
        check_projection(second)
        assert all(tuple(item.uv) == (0.25, 0.75)
                   for item in first.data.uv_layers['ArtistUV'].data)
        # Existing group defaults (including legacy map names) must not win over
        # per-object active maps. Repeated invocation must preserve manual targets.
        map_socket = next(s for s in group.interface.items_tree
                          if s.item_type == 'SOCKET' and s.in_out == 'INPUT'
                          and s.name == 'UV Map Name')
        group_default = map_socket.default_value
        map_socket.default_value = 'MBT_TriplanarUV'
        bpy.ops.mesh.primitive_cube_add()
        no_uv = bpy.context.object
        for layer in list(no_uv.data.uv_layers):
            no_uv.data.uv_layers.remove(layer)
        select(no_uv)
        assert bpy.ops.mbt.triplanar_uv() == {'FINISHED'}
        check_projection(no_uv)
        assert not no_uv.data.uv_layers
        map_socket.default_value = group_default
        # All six box faces, plus rotated face normals and corner positions.
        rotation = (0.2, 0.3, pi / 2)
        values = {'Scale': 2.5, 'Rotation': rotation, 'Offset': (0.3, -0.4, 0.7),
                  'UV Map Name': 'CustomProjection'}
        for socket in group.interface.items_tree:
            if socket.item_type == 'SOCKET' and socket.in_out == 'INPUT' and socket.name in values:
                gn.set_modifier_input(first.modifiers[-1], socket.identifier, values[socket.name])
        first.update_tag()
        check_projection(first, 2.5, rotation, (0.3, -0.4, 0.7), 'CustomProjection')
        select(first)
        assert bpy.ops.mbt.triplanar_uv() == {'CANCELLED'}
        check_projection(first, 2.5, rotation, (0.3, -0.4, 0.7), 'CustomProjection')
        print('PASS projection: six axes, transforms, UV preservation, reuse and repeat prevention')

        original = bpy.data.materials.new('Artist Material')
        other = bpy.data.materials.new('Other Artist Material')
        first.data.materials.append(original)
        first.data.materials.append(other)
        for polygon in first.data.polygons:
            polygon.material_index = polygon.index % 2
        witness = first.copy()
        witness.data = first.data
        bpy.context.collection.objects.link(witness)
        indices = tuple(p.material_index for p in first.data.polygons)
        select(first, second, empty)
        assert bpy.ops.mbt.beveled_normal_material() == {'FINISHED'}
        material = feature.get_beveled_material()
        bevel = next(node for node in material.node_tree.nodes
                     if node.bl_idname == 'ShaderNodeBevel')
        assert bevel.samples == 32
        bevel.samples = 4
        assert feature.get_beveled_material() == material
        assert bevel.samples == 32
        assert abs(bevel.inputs['Radius'].default_value - 0.001) < 1e-9
        # Only migrate legacy stock values, once; keep artist changes intact.
        del material['mbt_small_bevel_default']
        bevel.inputs['Radius'].default_value = 0.01
        assert feature.get_beveled_material() == material
        assert abs(bevel.inputs['Radius'].default_value - 0.001) < 1e-9
        bevel.inputs['Radius'].default_value = 0.01
        feature.get_beveled_material()
        assert abs(bevel.inputs['Radius'].default_value - 0.01) < 1e-9
        del material['mbt_small_bevel_default']
        bevel.inputs['Radius'].default_value = 0.003
        feature.get_beveled_material()
        assert abs(bevel.inputs['Radius'].default_value - 0.003) < 1e-9
        assert all(slot.material == material and slot.link == 'OBJECT' for slot in first.material_slots)
        assert second.material_slots[0].material == material
        assert [slot.material for slot in witness.material_slots] == [original, other]
        assert tuple(p.material_index for p in first.data.polygons) == indices
        assert first.data.materials[0] == original
        assert any(link.from_node.bl_idname == 'ShaderNodeBevel'
                   and link.to_socket.name == 'Normal' for link in material.node_tree.links)
        assert bpy.ops.mbt.beveled_normal_material() == {'FINISHED'}
        assert feature.get_beveled_material() == material
        # Empty shared mesh material slots must not appear on unselected users.
        bpy.ops.mesh.primitive_cube_add()
        bare = bpy.context.object
        bare_witness = bare.copy()
        bare_witness.data = bare.data
        bpy.context.collection.objects.link(bare_witness)
        select(bare)
        assert bpy.ops.mbt.beveled_normal_material() == {'FINISHED'}
        assert not bare_witness.material_slots and bare.data != bare_witness.data
        assert bare.material_slots[0].material == material
        select(empty)
        assert not bpy.ops.mbt.triplanar_uv.poll()
        assert not bpy.ops.mbt.beveled_normal_material.poll()
        print('PASS materials: all slots, graph wiring, reuse, shared data isolation and poll')
    finally:
        feature.unregister()
    feature.register()
    feature.unregister()
    print('ALL CONCEPTING CHECKS PASSED')


if __name__ == '__main__':
    main()