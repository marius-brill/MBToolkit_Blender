"""DynaBool: optional SDF remesh with automatic or manual local resolution."""

import bpy

from ...core import gn
from ...core.registry import register_classes, unregister_classes

GROUP_NAME = "DynaBool"
MODIFIER_NAME = "DynaBool"
REV = 7
# Revision-6 reference values only, retained for protected stock-group upgrades.
TARGET_TRIANGLES = 1500000
TRIANGLE_AREA_FACTOR = 2.25
FAILURE_ATTRIBUTE = 'mbt_dynabool_remesh_failed'
LIMIT_ATTRIBUTE = 'mbt_dynabool_resolution_limited'

DEFAULTS = {
    "Crease Angle": 50.0,
    "SubD Level": 2,
    "Remesh": True,
    "Voxel Size": 0.008,
    "Smooth Iterations": 0,
}


def _build(legacy=False, revision=REV):
    old = legacy or revision < 3
    ng = bpy.data.node_groups.new(GROUP_NAME, "GeometryNodeTree")
    iface = ng.interface
    gn.add_input(iface, "Geometry", "NodeSocketGeometry")
    gn.add_input(iface, "Crease Angle", "NodeSocketFloat", DEFAULTS["Crease Angle"], 0.0, 180.0)
    gn.add_input(iface, "SubD Level", "NodeSocketInt", DEFAULTS["SubD Level"], 0, 11)
    socket = gn.add_input(iface, "Remesh", "NodeSocketBool", DEFAULTS["Remesh"])
    socket.hide_in_modifier = revision == 3 and not old
    gn.add_input(iface, "Voxel Size", "NodeSocketFloat", DEFAULTS["Voxel Size"], min_value=0.0001 if old else 1e-8)
    gn.add_input(iface, "Smooth Iterations", "NodeSocketInt", 1 if old else DEFAULTS["Smooth Iterations"], min_value=0)
    if not legacy:
        socket = gn.add_input(iface, "Fallback on Failure", "NodeSocketBool", True)
        socket.description = 'Keep the subdivided mesh if remeshing is empty; check mbt_dynabool_remesh_failed'
        socket.hide_in_modifier = not old
    if not old:
        automatic_socket = gn.add_input(iface, 'Automatic Resolution', 'NodeSocketBool', True)
        automatic_socket.hide_in_modifier = revision == 4
        automatic_socket.description = 'Choose resolution from local dimensions; disable to use Voxel Size'
        if revision >= 4:
            socket = gn.add_input(iface, 'Resolved Voxel Size', 'NodeSocketFloat', 0.0, min_value=0.0)
            socket.hide_in_modifier = True
        if revision == 6:
            socket = gn.add_input(iface, 'Target Triangles', 'NodeSocketInt', TARGET_TRIANGLES, 1000, 10000000)
            socket.description = 'Approximate automatic remesh triangle count, not a hard cap; manual mode ignores this'
            automatic_socket.description = 'Estimate voxel size from subdivided surface area and Target Triangles; disable to use Voxel Size'
    gn.add_output(iface, "Geometry", "NodeSocketGeometry")

    nodes, links = ng.nodes, ng.links
    A = lambda idname, x, y, **kw: gn.add_node(nodes, idname, x, y, **kw)
    L = lambda *a, **k: gn.link(links, *a, **k)

    gi = A("NodeGroupInput", -800, 0)
    go = A("NodeGroupOutput", 2000, 200)

    # Crease / SubD
    edge_angle = A("GeometryNodeInputMeshEdgeAngle", -500, -250)
    to_deg = A("ShaderNodeMath", -300, -250, operation="DEGREES")
    cmp = A("FunctionNodeCompare", -100, -250, data_type="FLOAT", operation="GREATER_EQUAL")
    store = A("GeometryNodeStoreNamedAttribute", 150, 0, data_type="FLOAT", domain="EDGE")
    store.inputs["Name"].default_value = "crease_edge"
    store.inputs["Value"].default_value = 1.0
    clamp = A("ShaderNodeClamp", 150, -250, clamp_type="MINMAX")
    clamp.inputs["Min"].default_value = 0.0
    clamp.inputs["Max"].default_value = 11.0
    named = A("GeometryNodeInputNamedAttribute", 150, -450, data_type="FLOAT")
    named.inputs["Name"].default_value = "crease_edge"
    subd = A("GeometryNodeSubdivisionSurface", 450, 0)

    L(edge_angle, "Unsigned Angle", to_deg, "Value")
    links.new(to_deg.outputs[0], cmp.inputs[0])
    links.new(gi.outputs["Crease Angle"], cmp.inputs[1])
    links.new(cmp.outputs[0], store.inputs["Selection"])
    L(gi, "Geometry", store, "Geometry")
    links.new(gi.outputs["SubD Level"], clamp.inputs[0])
    L(store, "Geometry", subd, "Mesh")
    links.new(clamp.outputs[0], subd.inputs["Level"])
    links.new(named.outputs[0], subd.inputs["Edge Crease"])

    # Remesh
    to_sdf = A("GeometryNodeMeshToSDFGrid", 800, 100)
    gn.sock(to_sdf.inputs, "Band Width", 2).default_value = 3
    mean = A("GeometryNodeSDFGridMean", 1100, 200)
    gn.sock(mean.inputs, "Width", 1).default_value = 1
    to_mesh = A("GeometryNodeGridToMesh", 1400, 100)
    # SDF distances are in mesh units, not normalized density. A fixed nonzero
    # threshold falls outside the narrow band as voxel size is reduced.
    gn.sock(to_mesh.inputs, "Threshold", 1).default_value = 0.01 if legacy else 0.0
    gn.sock(to_mesh.inputs, "Adaptivity", 2).default_value = 0.0
    shade = A("GeometryNodeSetShadeSmooth", 1700, 100, domain="FACE")
    switch = A("GeometryNodeSwitch", 1850, 300, input_type="GEOMETRY")

    L(subd, "Mesh", to_sdf, "Mesh")
    if old:
        L(gi, "Voxel Size", to_sdf, "Voxel Size", in_i=1)
    else:
        bounds = A('GeometryNodeBoundBox', 100, -800)
        distance = A('ShaderNodeVectorMath', 300, -800, operation='DISTANCE')
        scale = A('ShaderNodeMath', 500, -800, operation='DIVIDE')
        scale.inputs[1].default_value = 36 if revision >= 5 else 144
        vertices = A('GeometryNodeInputMeshEdgeVertices', -100, -1100)
        length = A('ShaderNodeVectorMath', 100, -1100, operation='DISTANCE')
        links.new(vertices.outputs['Position 1'], length.inputs[0])
        links.new(vertices.outputs['Position 2'], length.inputs[1])
        statistic = A('GeometryNodeAttributeStatistic', 300, -1100, data_type='FLOAT', domain='EDGE')
        feature = A('ShaderNodeMath', 100, -1400, operation='GREATER_THAN')
        feature.inputs[1].default_value = 0.34906585
        links.new(edge_angle.outputs['Unsigned Angle'], feature.inputs[0])
        links.new(feature.outputs[0], statistic.inputs['Selection'])
        edge_scale = A('ShaderNodeMath', 500, -1100, operation='DIVIDE')
        edge_scale.inputs[1].default_value = 6
        minimum = A('ShaderNodeMath', 700, -800, operation='MINIMUM')
        safe = A('ShaderNodeMath', 900, -800, operation='MAXIMUM')
        safe.inputs[1].default_value = 1e-8
        automatic = A('GeometryNodeSwitch', 1100, -800, input_type='FLOAT')
        L(gi, 'Geometry', bounds, 'Geometry')
        links.new(bounds.outputs['Min'], distance.inputs[0])
        links.new(bounds.outputs['Max'], distance.inputs[1])
        links.new(distance.outputs['Value'], scale.inputs[0])
        L(gi, 'Geometry', statistic, 'Geometry')
        L(length, 'Value', statistic, 'Attribute')
        valid = A('ShaderNodeMath', 300, -1400, operation='GREATER_THAN')
        valid.inputs[1].default_value = 0
        links.new(statistic.outputs['Min'], valid.inputs[0])
        feature_size = A('GeometryNodeSwitch', 500, -1400, input_type='FLOAT')
        links.new(valid.outputs[0], feature_size.inputs['Switch'])
        links.new(distance.outputs['Value'], feature_size.inputs['False'])
        links.new(statistic.outputs['Min'], feature_size.inputs['True'])
        links.new(feature_size.outputs['Output'], edge_scale.inputs[0])
        links.new(scale.outputs[0], minimum.inputs[0])
        links.new(edge_scale.outputs[0], minimum.inputs[1])
        # Short edges are not a reliable global density target. Revision 5 uses
        # dimensions only, at four times the previous dimension-based voxel size.
        if revision >= 7:
            from . import resolution_nodes
            voxel, limited = resolution_nodes.build(ng, subd.outputs['Mesh'], gi.outputs['Crease Angle'])
            links.new(voxel, safe.inputs[0])
            adaptivity = A('GeometryNodeSwitch', 1200, -1900, input_type='FLOAT')
            L(gi, 'Automatic Resolution', adaptivity, 'Switch')
            adaptivity.inputs['True'].default_value = resolution_nodes.AUTOMATIC_ADAPTIVITY
            L(adaptivity, 'Output', to_mesh, 'Adaptivity')
            warning = A('GeometryNodeStoreNamedAttribute', 1800, 450, data_type='BOOLEAN', domain='POINT')
            warning.inputs['Name'].default_value = LIMIT_ATTRIBUTE
            live_limit = A('FunctionNodeBooleanMath', 450, -1900, operation='AND')
            no_override = A('ShaderNodeMath', 250, -1900, operation='LESS_THAN')
            L(gi, 'Resolved Voxel Size', no_override, 'Value')
            no_override.inputs[1].default_value = 1e-8
            links.new(limited, live_limit.inputs[0])
            links.new(no_override.outputs[0], live_limit.inputs[1])
            active_limit = A('FunctionNodeBooleanMath', 650, -1900, operation='AND')
            links.new(live_limit.outputs[0], active_limit.inputs[0])
            links.new(gi.outputs['Automatic Resolution'], active_limit.inputs[1])
            links.new(active_limit.outputs[0], warning.inputs['Value'])
            L(shade, 'Mesh', warning, 'Geometry')
        elif revision >= 6:
            face_area = A('GeometryNodeInputMeshFaceArea', 100, -1700)
            area_sum = A('GeometryNodeAttributeStatistic', 300, -1700, data_type='FLOAT', domain='FACE')
            weighted = A('ShaderNodeMath', 500, -1700, operation='MULTIPLY')
            weighted.inputs[1].default_value = TRIANGLE_AREA_FACTOR
            per_triangle = A('ShaderNodeMath', 700, -1700, operation='DIVIDE')
            root = A('ShaderNodeMath', 900, -1700, operation='SQRT')
            L(subd, 'Mesh', area_sum, 'Geometry')
            L(face_area, 'Area', area_sum, 'Attribute')
            links.new(area_sum.outputs['Sum'], weighted.inputs[0])
            links.new(weighted.outputs[0], per_triangle.inputs[0])
            links.new(gi.outputs['Target Triangles'], per_triangle.inputs[1])
            links.new(per_triangle.outputs[0], root.inputs[0])
            links.new(root.outputs[0], safe.inputs[0])
        else:
            links.new(scale.outputs[0] if revision >= 5 else minimum.outputs[0], safe.inputs[0])
        if revision == 4:
            automatic.inputs['Switch'].default_value = True
        else:
            L(gi, 'Automatic Resolution', automatic, 'Switch')
        L(gi, 'Voxel Size', automatic, 'False')
        links.new(safe.outputs[0], automatic.inputs['True'])
        if revision >= 4:
            resolved = A('GeometryNodeSwitch', 1300, -800, input_type='FLOAT')
            supplied = A('ShaderNodeMath', 1100, -1100, operation='GREATER_THAN')
            supplied.inputs[1].default_value = 0
            links.new(gi.outputs['Resolved Voxel Size'], supplied.inputs[0])
            links.new(supplied.outputs[0], resolved.inputs['Switch'])
            L(gi, 'Resolved Voxel Size', resolved, 'True')
            L(automatic, 'Output', resolved, 'False')
            if revision >= 5:
                manual = A('GeometryNodeSwitch', 1500, -800, input_type='FLOAT')
                L(gi, 'Automatic Resolution', manual, 'Switch')
                L(gi, 'Voxel Size', manual, 'False')
                L(resolved, 'Output', manual, 'True')
                L(manual, 'Output', to_sdf, 'Voxel Size')
            else:
                L(resolved, 'Output', to_sdf, 'Voxel Size')
        else:
            L(automatic, 'Output', to_sdf, 'Voxel Size')
    L(to_sdf, "SDF Grid", mean, "Grid")
    L(gi, "Smooth Iterations", mean, "Iterations", in_i=2)
    L(mean, "Grid", to_mesh, "Grid")
    L(to_mesh, "Mesh", shade, "Mesh")

    # Remesh toggle: False = subdivided mesh, True = remeshed
    L(gi, "Remesh", switch, "Switch")
    L(subd, "Mesh", switch, "False", in_i=1)
    if legacy:
        L(shade, "Mesh", switch, "True", in_i=2)
    elif old:
        size = A('GeometryNodeAttributeDomainSize', 1650, -300, component='MESH')
        empty = A('FunctionNodeCompare', 1850, -300, data_type='INT', operation='EQUAL')
        # Compare's integer sockets are distinct from its float A/B sockets.
        links.new(size.outputs['Face Count'], next(s for s in empty.inputs if s.name == 'A' and s.type == 'INT'))
        allowed = A('FunctionNodeBooleanMath', 2050, -300, operation='AND')
        failed = A('GeometryNodeStoreNamedAttribute', 1850, -550, data_type='BOOLEAN', domain='FACE')
        failed.inputs['Name'].default_value = FAILURE_ATTRIBUTE
        failed.inputs['Value'].default_value = True
        fallback = A('GeometryNodeSwitch', 2300, 100, input_type='GEOMETRY')
        L(shade, 'Mesh', size, 'Geometry')
        links.new(empty.outputs[0], allowed.inputs[0])
        links.new(gi.outputs['Fallback on Failure'], allowed.inputs[1])
        L(subd, 'Mesh', failed, 'Geometry')
        links.new(allowed.outputs[0], fallback.inputs['Switch'])
        L(shade, 'Mesh', fallback, 'False')
        L(failed, 'Geometry', fallback, 'True')
        L(fallback, 'Output', switch, 'True')
    else:
        if revision >= 7:
            L(warning, 'Geometry', switch, 'True')
        else:
            L(shade, 'Mesh', switch, 'True')
    if old or revision >= 4:
        L(switch, "Output", go, "Geometry")
    else:
        # Neither obsolete Remesh nor Fallback inputs can bypass the SDF.
        L(shade, 'Mesh', go, 'Geometry')
    return ng


def get_group():
    return gn.ensure_group(GROUP_NAME, REV, _build, preserve_existing_name=True)


class MBT_OT_upgrade_dynabool(bpy.types.Operator):
    bl_idname = 'mbt.upgrade_dynabool'
    bl_label = 'Upgrade Selected DynaBool'
    bl_description = 'Upgrade stock legacy modifiers, preserving settings; regenerate processor-owned highs separately'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return gn.poll_mesh_selected(context)

    def execute(self, context):
        count, skipped = gn.upgrade_selected_groups(context, GROUP_NAME, 1, lambda: _build(legacy=True), get_group)
        second, protected = gn.upgrade_selected_groups(context, GROUP_NAME, 2, lambda: _build(revision=2), get_group)
        count += second
        skipped += protected
        third, protected = gn.upgrade_selected_groups(context, GROUP_NAME, 3, lambda: _build(revision=3), get_group)
        count += third
        skipped += protected
        fourth, protected = gn.upgrade_selected_groups(context, GROUP_NAME, 4, lambda: _build(revision=4), get_group)
        count += fourth
        skipped += protected
        fifth, protected = gn.upgrade_selected_groups(context, GROUP_NAME, 5, lambda: _build(revision=5), get_group)
        count += fifth
        skipped += protected
        sixth, protected = gn.upgrade_selected_groups(context, GROUP_NAME, 6, lambda: _build(revision=6), get_group)
        count += sixth
        skipped += protected
        self.report({'WARNING'} if skipped else {'INFO'},
                    f'Upgraded {count}; skipped {skipped} customized, animated, linked or processor-owned modifiers')
        return {'FINISHED'}


class MBT_OT_check_dynabool(bpy.types.Operator):
    bl_idname = 'mbt.check_dynabool'
    bl_label = 'Check Selected DynaBool'
    bl_description = 'Evaluate selected meshes and report empty output or remesh fallback (may take time at high resolution)'

    @classmethod
    def poll(cls, context):
        return gn.poll_mesh_selected(context)

    def execute(self, context):
        issues = []
        limited = []
        for obj in context.selected_objects:
            if obj.type != 'MESH':
                continue
            evaluated = obj.evaluated_get(context.evaluated_depsgraph_get())
            mesh = evaluated.to_mesh()
            try:
                failed = mesh.attributes.get(FAILURE_ATTRIBUTE)
                if not mesh.polygons or (failed and any(v.value for v in failed.data)):
                    issues.append(obj.name)
                guard = mesh.attributes.get(LIMIT_ATTRIBUTE)
                if guard and any(v.value for v in guard.data):
                    limited.append(obj.name)
            finally:
                evaluated.to_mesh_clear()
        self.report({'WARNING'} if issues or limited else {'INFO'},
                    'Empty remesh/fallback: ' + ', '.join(issues) + '. Check closed geometry, thickness and voxel size.'
                    if issues else 'Automatic work limit reached: ' + ', '.join(limited) + '. Inspect tiny features; use manual resolution if needed.'
                    if limited else 'No empty output, fallback or automatic work limit detected; inspect thin features visually')
        return {'FINISHED'}


class MBT_OT_add_dynabool(bpy.types.Operator):
    bl_idname = "mbt.add_dynabool"
    bl_label = "DynaBool"
    bl_description = "Add the DynaBool modifier (crease by angle, subdivision, SDF remesh) to the selected meshes"
    bl_options = {"REGISTER", "UNDO"}

    automatic_resolution: bpy.props.BoolProperty(name='Automatic Resolution', default=True)

    @classmethod
    def poll(cls, context):
        return gn.poll_mesh_selected(context)

    def execute(self, context):
        from . import resolution
        added = 0
        errors = []
        for obj in context.selected_objects:
            if obj.type != 'MESH' or MODIFIER_NAME in obj.modifiers:
                continue
            try:
                evaluated = obj.evaluated_get(context.evaluated_depsgraph_get())
                mesh = evaluated.to_mesh()
                try:
                    work = mesh.copy()
                finally:
                    evaluated.to_mesh_clear()
                try:
                    resolution.prepare(work)
                    analysis = resolution.analyze(work)
                    voxel = analysis['voxel'] if self.automatic_resolution else DEFAULTS['Voxel Size']
                    resolution.budget(analysis, voxel, 1000000)
                finally:
                    bpy.data.meshes.remove(work)
                modifier = obj.modifiers.new(MODIFIER_NAME, 'NODES')
                modifier.node_group = get_group()
                for socket in modifier.node_group.interface.items_tree:
                    if socket.name == 'Automatic Resolution':
                        gn.set_modifier_input(modifier, socket.identifier, self.automatic_resolution)
                obj.update_tag()
                added += 1
            except (ValueError, RuntimeError) as error:
                errors.append(f'{obj.name}: {error}')
        self.report({'WARNING'} if errors else {'INFO'}, f'{added} added, {len(errors)} failed. ' + '; '.join(errors))
        return {'FINISHED'} if added else {'CANCELLED'}


classes = (MBT_OT_add_dynabool, MBT_OT_upgrade_dynabool, MBT_OT_check_dynabool)


def draw(layout, context):
    layout.prop(context.scene, 'mbt_dynabool_auto_resolution')
    obj = context.object
    if obj:
        for modifier in obj.modifiers:
            group = modifier.node_group if modifier.type == 'NODES' else None
            if group and group.get('mbt_rev') == REV and group.name.startswith(GROUP_NAME):
                socket = next(s for s in group.interface.items_tree if s.name == 'Automatic Resolution')
                inputs = gn.modifier_inputs(modifier)
                if inputs is not None:
                    layout.prop(getattr(inputs, socket.identifier), 'value', text='Active Modifier: Automatic Resolution')
                else:
                    layout.prop(modifier, f'["{socket.identifier}"]', text='Active Modifier: Automatic Resolution')
                break
    operator = layout.operator("mbt.add_dynabool", icon="MOD_SUBSURF")
    operator.automatic_resolution = context.scene.mbt_dynabool_auto_resolution
    layout.operator('mbt.upgrade_dynabool', icon='FILE_REFRESH')
    layout.operator('mbt.check_dynabool', icon='CHECKMARK')


def register():
    register_classes(classes)
    bpy.types.Scene.mbt_dynabool_auto_resolution = bpy.props.BoolProperty(
        name='Automatic Resolution', default=True,
        description='Default for new DynaBool modifiers; existing modifiers have their own toggle')


def unregister():
    if hasattr(bpy.types.Scene, 'mbt_dynabool_auto_resolution'):
        del bpy.types.Scene.mbt_dynabool_auto_resolution
    unregister_classes(classes)
