"""Non-destructive projection and clay shading shortcuts for concept meshes."""

import bpy

from ..core import gn
from ..core.registry import register_classes, unregister_classes

GROUP_NAME = 'MBT Triplanar UV'
MATERIAL_NAME = 'MBT Beveled Normal Grey'
UV_NAME = 'UVMap'
BEVEL_RADIUS = 0.001
REV = 1
OWNER_KEY = 'mbt_concepting'


def editable_meshes(context):
    return [obj for obj in context.selected_objects
            if obj.type == 'MESH' and obj.is_editable]


def _build_projection():
    group = bpy.data.node_groups.new(GROUP_NAME, 'GeometryNodeTree')
    try:
        group.is_modifier = True
        iface = group.interface
        gn.add_input(iface, 'Geometry', 'NodeSocketGeometry')
        gn.add_input(iface, 'Scale', 'NodeSocketFloat', 1.0, 0.000001, 10000.0)
        gn.add_input(iface, 'Rotation', 'NodeSocketVector', (0.0, 0.0, 0.0), subtype='EULER')
        gn.add_input(iface, 'Offset', 'NodeSocketVector', (0.0, 0.0, 0.0))
        gn.add_input(iface, 'UV Map Name', 'NodeSocketString', UV_NAME)
        gn.add_output(iface, 'Geometry', 'NodeSocketGeometry')
        nodes, links = group.nodes, group.links
        gi = gn.add_node(nodes, 'NodeGroupInput', -1200, 500)
        position = gn.add_node(nodes, 'GeometryNodeInputPosition', -1200, 150)
        normal = gn.add_node(nodes, 'GeometryNodeInputNormal', -1200, -200)
        face_normal = gn.add_node(nodes, 'GeometryNodeFieldOnDomain', -1000, -200,
                                  data_type='FLOAT_VECTOR', domain='FACE')
        links.new(normal.outputs['Normal'], face_normal.inputs['Value'])

        def rotate(source, y):
            node = gn.add_node(nodes, 'ShaderNodeVectorRotate', -780, y,
                               rotation_type='EULER_XYZ')
            links.new(source, node.inputs['Vector'])
            links.new(gi.outputs['Rotation'], node.inputs['Rotation'])
            return node.outputs['Vector']

        rotated_position = rotate(position.outputs['Position'], 200)
        rotated_normal = rotate(face_normal.outputs['Value'], -200)
        scale = gn.add_node(nodes, 'ShaderNodeVectorMath', -550, 250, operation='SCALE')
        links.new(rotated_position, scale.inputs[0])
        links.new(gi.outputs['Scale'], scale.inputs['Scale'])
        offset = gn.add_node(nodes, 'ShaderNodeVectorMath', -330, 250, operation='ADD')
        links.new(scale.outputs['Vector'], offset.inputs[0])
        links.new(gi.outputs['Offset'], offset.inputs[1])
        p = gn.add_node(nodes, 'ShaderNodeSeparateXYZ', -100, 300)
        n = gn.add_node(nodes, 'ShaderNodeSeparateXYZ', -550, -200)
        links.new(offset.outputs['Vector'], p.inputs[0])
        links.new(rotated_normal, n.inputs[0])

        def math_node(operation, a, b=None, x=0, y=0):
            node = gn.add_node(nodes, 'ShaderNodeMath', x, y, operation=operation)
            for index, value in enumerate((a, b)):
                if value is None:
                    continue
                if isinstance(value, (int, float)):
                    node.inputs[index].default_value = value
                else:
                    links.new(value, node.inputs[index])
            return node.outputs[0]

        absolute = [math_node('ABSOLUTE', n.outputs[axis], x=-320, y=-150-i*180)
                    for i, axis in enumerate('XYZ')]
        # Strict comparisons give deterministic ties: Z, then Y, then X.
        x_y = math_node('GREATER_THAN', absolute[0], absolute[1], x=-80, y=-150)
        x_z = math_node('GREATER_THAN', absolute[0], absolute[2], x=-80, y=-330)
        use_x = math_node('MULTIPLY', x_y, x_z, x=140, y=-180)
        use_y = math_node('GREATER_THAN', absolute[1], absolute[2], x=140, y=-420)
        uv_outputs = []
        for index, (axis, u, v, handedness) in enumerate((
                ('X', 'Y', 'Z', 1.0), ('Y', 'X', 'Z', -1.0), ('Z', 'X', 'Y', 1.0))):
            y = 550 + index * 300
            sign = math_node('SIGN', n.outputs[axis], x=140, y=y)
            oriented = math_node('MULTIPLY', sign, handedness, x=350, y=y)
            projected_u = math_node('MULTIPLY', p.outputs[u], oriented, x=560, y=y)
            combine = gn.add_node(nodes, 'ShaderNodeCombineXYZ', 780, y)
            links.new(projected_u, combine.inputs['X'])
            links.new(p.outputs[v], combine.inputs['Y'])
            uv_outputs.append(combine.outputs['Vector'])

        def switch(condition, false, true, x, y):
            node = gn.add_node(nodes, 'GeometryNodeSwitch', x, y, input_type='VECTOR')
            links.new(condition, node.inputs['Switch'])
            links.new(false, node.inputs['False'])
            links.new(true, node.inputs['True'])
            return node.outputs['Output']

        yz = switch(use_y, uv_outputs[2], uv_outputs[1], 1000, 500)
        uv = switch(use_x, yz, uv_outputs[0], 1230, 500)
        store = gn.add_node(nodes, 'GeometryNodeStoreNamedAttribute', 1470, 500,
                            data_type='FLOAT2', domain='CORNER')
        links.new(gi.outputs['Geometry'], store.inputs['Geometry'])
        links.new(gi.outputs['UV Map Name'], store.inputs['Name'])
        links.new(uv, store.inputs['Value'])
        output = gn.add_node(nodes, 'NodeGroupOutput', 1720, 500)
        links.new(store.outputs['Geometry'], output.inputs['Geometry'])
        group[OWNER_KEY] = 'TRIPLANAR_UV'
        group['mbt_rev'] = REV
        return group
    except Exception:
        bpy.data.node_groups.remove(group)
        raise


def get_projection_group():
    for group in bpy.data.node_groups:
        if (group.bl_idname == 'GeometryNodeTree'
                and group.get(OWNER_KEY) == 'TRIPLANAR_UV' and group.get('mbt_rev') == REV
                and group.is_editable):
            return group
    return _build_projection()


def get_beveled_material():
    for material in bpy.data.materials:
        if (material.get(OWNER_KEY) == 'BEVELED_NORMAL' and material.get('mbt_rev') == REV
                and material.is_editable):
            if material.node_tree is not None:
                for node in material.node_tree.nodes:
                    if node.bl_idname == 'ShaderNodeBevel' and node.samples == 4:
                        node.samples = 32
            if not material.get('mbt_small_bevel_default'):
                tree = material.node_tree
                if tree is not None and not material.animation_data and not tree.animation_data:
                    for node in tree.nodes:
                        if node.bl_idname == 'ShaderNodeBevel':
                            radius = node.inputs['Radius']
                            if not radius.is_linked and abs(radius.default_value - 0.01) < 1e-9:
                                radius.default_value = BEVEL_RADIUS
                # One-time migration; later artist edits must never be reset.
                material['mbt_small_bevel_default'] = True
            return material
    material = bpy.data.materials.new(MATERIAL_NAME)
    try:
        material.use_nodes = True
        material.diffuse_color = (0.3, 0.3, 0.3, 1.0)
        nodes, links = material.node_tree.nodes, material.node_tree.links
        nodes.clear()
        bevel = gn.add_node(nodes, 'ShaderNodeBevel', -300, 0, samples=32)
        bevel.label = 'Cycles only - shading, not geometry'
        bevel.inputs['Radius'].default_value = BEVEL_RADIUS
        shader = gn.add_node(nodes, 'ShaderNodeBsdfPrincipled', 0, 0)
        shader.inputs['Base Color'].default_value = material.diffuse_color
        shader.inputs['Roughness'].default_value = 0.45
        output = gn.add_node(nodes, 'ShaderNodeOutputMaterial', 350, 0)
        links.new(bevel.outputs['Normal'], shader.inputs['Normal'])
        links.new(shader.outputs['BSDF'], output.inputs['Surface'])
        material[OWNER_KEY] = 'BEVELED_NORMAL'
        material['mbt_rev'] = REV
        material['mbt_small_bevel_default'] = True
        return material
    except Exception:
        bpy.data.materials.remove(material)
        raise


class MBT_OT_triplanar_uv(bpy.types.Operator):
    bl_idname = 'mbt.triplanar_uv'
    bl_label = 'Triplanar UV'
    bl_description = ('Add per-face box projection to each mesh\'s active UV map '
                      '(UVMap if none exists; hard seams, not blended triplanar)')
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and bool(editable_meshes(context))

    def execute(self, context):
        added = 0
        group = None
        for obj in editable_meshes(context):
            if any(mod.type == 'NODES' and mod.node_group
                   and mod.node_group.get(OWNER_KEY) == 'TRIPLANAR_UV' for mod in obj.modifiers):
                continue
            group = group or get_projection_group()
            modifier = obj.modifiers.new('Triplanar UV', 'NODES')
            modifier.node_group = group
            active_uv = obj.data.uv_layers.active
            uv_name = active_uv.name if active_uv is not None else UV_NAME
            socket = next(s for s in group.interface.items_tree
                          if s.item_type == 'SOCKET' and s.in_out == 'INPUT'
                          and s.name == 'UV Map Name')
            gn.set_modifier_input(modifier, socket.identifier, uv_name)
            obj.update_tag()
            added += 1
        if not added:
            self.report({'WARNING'}, 'Selected meshes already have Triplanar UV')
            return {'CANCELLED'}
        self.report({'INFO'}, f'Added Triplanar UV to {added} mesh(es), targeting their active UV maps')
        return {'FINISHED'}


class MBT_OT_beveled_normal_material(bpy.types.Operator):
    bl_idname = 'mbt.beveled_normal_material'
    bl_label = 'Beveled Normal Material'
    bl_description = ('Assign grey clay with Bevel normals to every material slot on selected '
                      'meshes; bevel shading requires Cycles Rendered view')
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and bool(editable_meshes(context))

    def execute(self, context):
        material = get_beveled_material()
        objects = editable_meshes(context)
        for obj in objects:
            if not obj.material_slots:
                # Adding a slot changes mesh data: isolate shared/linked data first.
                if obj.data.users > 1 or not obj.data.is_editable:
                    obj.data = obj.data.copy()
                obj.data.materials.append(None)
            for slot in obj.material_slots:
                slot.link = 'OBJECT'
                slot.material = material
            obj.update_tag()
        message = f'Assigned beveled grey to {len(objects)} mesh(es)'
        if context.scene.render.engine != 'CYCLES':
            self.report({'WARNING'}, message + '; bevel normals require Cycles Rendered view')
        else:
            self.report({'INFO'}, message + '; view in Cycles Rendered mode')
        return {'FINISHED'}


classes = (MBT_OT_triplanar_uv, MBT_OT_beveled_normal_material)


def draw(layout, context):
    layout.operator('mbt.triplanar_uv', icon='GROUP_UVS')
    layout.operator('mbt.beveled_normal_material', icon='MATERIAL')
    layout.label(text='Beveled normals: Cycles Rendered view', icon='INFO')


def register():
    register_classes(classes)


def unregister():
    unregister_classes(classes)