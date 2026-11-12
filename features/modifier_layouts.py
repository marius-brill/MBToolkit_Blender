# SPDX-FileCopyrightText: 2026 MBToolkit contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Selected-instance native-style layouts, backed by versioned Blender UI data.

No native panel pointer manipulation, copied objects, or stack mutation during draw.
Source metadata is generated offline; runtime uses only Blender's supported RNA/UI.
"""

import bpy

from .modifier_layout_data import LAYOUTS

# Runtime-only expansion state shared by Properties and the viewport popup.
# Do not store UI choices in modifier IDProperties or create undo entries.
_section_open = {}
ARRAY_SECTIONS = (
    ('Relative Offset', 'use_relative_offset', (('relative_offset_displace', {'text': 'Factor'}),)),
    ('Constant Offset', 'use_constant_offset', (('constant_offset_displace', {'text': 'Distance'}),)),
    ('Object Offset', 'use_object_offset', (('offset_object', {'text': 'Object'}),)),
    ('Merge', 'use_merge_vertices', (('merge_threshold', {'text': 'Distance'}),
                                     ('use_merge_vertices_cap', {'text': 'First and Last Copies'}))),
    ('UVs', None, (('offset_u', {'text': 'Offset U'}), ('offset_v', {'text': 'V'}))),
    ('Caps', None, (('start_cap', {'text': 'Cap Start'}), ('end_cap', {'text': 'End'}))),
)


PHYSICS = {'CLOTH', 'COLLISION', 'DYNAMIC_PAINT', 'FLUID', 'SOFT_BODY', 'SURFACE'}
SEARCH = {'vertex_group': 'vertex_groups', 'vertex_group_name': 'vertex_groups',
          'vertex_group_a': 'vertex_groups', 'vertex_group_b': 'vertex_groups'}
INFLUENCE = {
    'draw_layer_filter_settings': ('layer_filter', 'invert_layer_filter',
        'use_layer_pass_filter', 'layer_pass_filter', 'invert_layer_pass_filter'),
    'draw_material_filter_settings': ('material_filter', 'invert_material_filter',
        'use_material_pass_filter', 'material_pass_filter', 'invert_material_pass_filter'),
    'draw_vertex_group_settings': ('vertex_group_name', 'invert_vertex_group'),
    'draw_custom_curve_settings': ('use_custom_curve', 'custom_curve'),
}


def visible(md, name):
    """Conditional branches that RNA alone cannot describe."""
    kind = md.type
    if kind in {'ARRAY', 'GREASE_PENCIL_ARRAY'}:
        if name in {'count', 'fit_length', 'curve'} and hasattr(md, 'fit_type'):
            return md.fit_type == {'count': 'FIXED_COUNT', 'fit_length': 'FIT_LENGTH', 'curve': 'FIT_CURVE'}[name]
    if kind == 'BEVEL':
        if name in {'width', 'width_pct'}:
            return (name == 'width_pct') == (md.offset_type == 'PERCENT')
        if name in {'angle_limit', 'vertex_group', 'invert_vertex_group', 'edge_weight', 'vertex_weight'}:
            method = {'angle_limit': 'ANGLE', 'vertex_group': 'VGROUP', 'invert_vertex_group': 'VGROUP',
                      'edge_weight': 'WEIGHT', 'vertex_weight': 'WEIGHT'}[name]
            return md.limit_method == method
        if name == 'custom_profile':
            return md.profile_type == 'CUSTOM'
        if name == 'spread':
            return md.miter_inner == 'MITER_ARC'
    if kind == 'BOOLEAN':
        if name in {'object', 'collection'}:
            return md.operand_type == name.upper()
        if name in {'use_self', 'use_hole_tolerant'}:
            return md.solver == 'EXACT'
        if name == 'double_threshold':
            return md.solver == 'FAST'
        if name == 'debug_options':
            return bpy.app.debug
    if kind == 'DECIMATE':
        fields = {'ratio': 'COLLAPSE', 'use_collapse_triangulate': 'COLLAPSE',
                  'use_symmetry': 'COLLAPSE', 'symmetry_axis': 'COLLAPSE',
                  'vertex_group': 'COLLAPSE', 'invert_vertex_group': 'COLLAPSE',
                  'vertex_group_factor': 'COLLAPSE', 'iterations': 'UNSUBDIV',
                  'angle_limit': 'DISSOLVE', 'use_dissolve_boundaries': 'DISSOLVE', 'delimit': 'DISSOLVE'}
        if name in fields:
            return md.decimate_type == fields[name]
    if kind == 'REMESH':
        if name in {'voxel_size', 'adaptivity'}:
            return md.mode == 'VOXEL'
        if name in {'octree_depth', 'scale', 'use_remove_disconnected', 'threshold'}:
            return md.mode != 'VOXEL'
        if name == 'sharpness':
            return md.mode == 'SHARP'
    if kind == 'MASK' and name in {'armature', 'vertex_group', 'invert_vertex_group'}:
        return (name == 'armature') == (md.mode == 'ARMATURE')
    if kind in {'SHRINKWRAP', 'GREASE_PENCIL_SHRINKWRAP'}:
        if name in {'use_project_x', 'use_project_y', 'use_project_z', 'use_negative_direction',
                    'use_positive_direction', 'project_limit', 'subsurf_levels', 'cull_face',
                    'use_invert_cull', 'auxiliary_target'}:
            return md.wrap_method == 'PROJECT'
    if name == 'custom_curve' and hasattr(md, 'use_custom_curve'):
        return md.use_custom_curve
    return True


def enabled(md, name):
    toggles = {
        'constant_offset_displace': 'use_constant_offset',
        'relative_offset_displace': 'use_relative_offset', 'offset_object': 'use_object_offset',
        'merge_threshold': 'use_merge_vertices', 'use_merge_vertices_cap': 'use_merge_vertices',
        'seed': 'use_random_order', 'split_angle': 'use_edge_angle',
        'layer_pass_filter': 'use_layer_pass_filter', 'material_pass_filter': 'use_material_pass_filter',
    }
    toggle = toggles.get(name)
    return toggle is None or not hasattr(md, toggle) or bool(getattr(md, toggle))


def property_ui(layout, obj, md, name, options, drawn):
    if name.startswith('@'):
        for field in INFLUENCE.get(name[1:], ()):
            property_ui(layout, obj, md, field, {}, drawn)
        return
    prop = md.bl_rna.properties.get(name)
    if prop is None or prop.is_hidden or name in drawn or not visible(md, name):
        return
    drawn.add(name)
    row = layout.row(align=True)
    options = dict(options)
    widget = options.pop('widget', None)
    value = getattr(md, name)
    # Read-only struct pointers can still own editable values (curve mappings,
    # ramps and bevel profiles); only the pointer assignment itself is read-only.
    embedded = prop.type == 'POINTER' and value is not None and not isinstance(value, bpy.types.ID)
    row.enabled = obj.is_editable and enabled(md, name) and (embedded or not md.is_property_readonly(name))
    if widget == 'curve_profile':
        row.template_curveprofile(md, name)
    elif widget == 'curve_mapping' or isinstance(value, bpy.types.CurveMapping):
        row.template_curve_mapping(md, name)
    elif isinstance(value, bpy.types.ColorRamp):
        row.template_color_ramp(md, name, expand=True)
    elif name in SEARCH:
        row.prop_search(md, name, obj, SEARCH[name], **options)
    elif prop.type not in {'COLLECTION', 'POINTER'} or value is None or isinstance(value, bpy.types.ID):
        row.prop(md, name, **options)
    else:
        # Nested structured settings are kept together, never flattened into the
        # modifier's main property list. Do not follow ID links or owner cycles.
        box = row.box()
        box.label(text=prop.name)
        for field in value.bl_rna.properties:
            if field.identifier != 'rna_type' and not field.is_hidden and not field.is_readonly and field.type not in {'POINTER', 'COLLECTION'}:
                box.prop(value, field.identifier)


def section_key(md, title):
    return f'{md.id_data.session_uid}:{md.persistent_uid}:{title}'


def section(layout, md, title, state, popup, *, toggle=None):
    # panel() is not supported in operator popups. Use the same native-looking
    # disclosure rows in BOTH views rather than two independent UI implementations.
    key = section_key(md, title)
    native_state = state if state and state in md.bl_rna.properties else None
    opened = bool(getattr(md, native_state)) if native_state else _section_open.get(key, bool(toggle))
    header = layout.row(align=True)
    header.use_property_split = False
    header.use_property_decorate = False
    op = header.operator('mbt.modifier_section', text='' if toggle else title,
                         icon='TRIA_DOWN' if opened else 'TRIA_RIGHT', emboss=False)
    op.key = key
    op.object_name = md.id_data.name
    op.object_uid = str(md.id_data.session_uid)
    op.uid = md.persistent_uid
    op.state = native_state or ''
    op.opened = opened
    if toggle:
        header.prop(md, toggle, text=title)
    if not opened:
        return None
    body = layout.column(align=True)
    body.use_property_split = True
    body.use_property_decorate = True
    body.context_pointer_set('mbt_modifier_settings', md)
    if toggle:
        body.enabled = md.id_data.is_editable and bool(getattr(md, toggle))
    return body


def operator_ui(layout, md, idname, text, **values):
    op = layout.operator(idname, text=text)
    category, identifier = idname.split('.')
    if 'modifier' in getattr(getattr(bpy.ops, category), identifier).get_rna_type().properties:
        op.modifier = md.name
    for name, value in values.items():
        setattr(op, name, value)


def actions(layout, md):
    """Native modifier-specific operations, explicitly bound to this instance."""
    kind = md.type
    if kind in {'MESH_DEFORM', 'SURFACE_DEFORM', 'CORRECTIVE_SMOOTH', 'LAPLACIANDEFORM'}:
        names = {'MESH_DEFORM': ('meshdeform_bind', 'is_bound'),
                 'SURFACE_DEFORM': ('surfacedeform_bind', 'is_bound'),
                 'CORRECTIVE_SMOOTH': ('correctivesmooth_bind', 'is_bind'),
                 'LAPLACIANDEFORM': ('laplaciandeform_bind', 'is_bind')}
        op, state = names[kind]
        operator_ui(layout, md, 'object.' + op, 'Unbind' if getattr(md, state, False) else 'Bind')
    elif kind == 'MULTIRES':
        for op, label in (('multires_subdivide', 'Subdivide'), ('multires_unsubdivide', 'Unsubdivide'),
                          ('multires_higher_levels_delete', 'Delete Higher'), ('multires_reshape', 'Reshape'),
                          ('multires_base_apply', 'Apply Base')):
            operator_ui(layout, md, 'object.' + op, label)
    elif kind == 'SKIN':
        for op, label in (('skin_armature_create', 'Create Armature'), ('skin_loose_mark_clear', 'Mark Loose'),
                          ('skin_root_mark', 'Mark Root'), ('skin_radii_equalize', 'Equalize Radii')):
            operator_ui(layout, md, 'object.' + op, label)
    elif kind == 'OCEAN':
        operator_ui(layout, md, 'object.ocean_bake', 'Free Bake' if md.is_cached else 'Bake', free=md.is_cached)
    elif kind == 'EXPLODE':
        operator_ui(layout, md, 'object.explode_refresh', 'Refresh')


def collections(layout, md):
    if md.type == 'UV_PROJECT':
        for index, projector in enumerate(md.projectors):
            layout.prop(projector, 'object', text=f'Projector {index + 1}')
    if md.type not in {'GREASE_PENCIL_DASH', 'GREASE_PENCIL_TIME'}:
        return
    if md.type == 'GREASE_PENCIL_TIME' and md.mode != 'CHAIN':
        return
    prefix = 'grease_pencil_dash' if md.type == 'GREASE_PENCIL_DASH' else 'grease_pencil_time'
    row = layout.row()
    row.template_list('MOD_UL_' + prefix + '_modifier_segments', '', md, 'segments', md, 'segment_active_index', rows=3)
    controls = row.column(align=True)
    for suffix, icon in (('add', 'ADD'), ('remove', 'REMOVE')):
        op = controls.operator('object.' + prefix + '_modifier_segment_' + suffix, text='', icon=icon)
        op.modifier = md.name
    for direction, icon in (('UP', 'TRIA_UP'), ('DOWN', 'TRIA_DOWN')):
        op = controls.operator('object.' + prefix + '_modifier_segment_move', text='', icon=icon)
        op.modifier = md.name
        op.type = direction
    if 0 <= md.segment_active_index < len(md.segments):
        segment = md.segments[md.segment_active_index]
        for prop in segment.bl_rna.properties:
            if prop.identifier != 'rna_type' and not prop.is_readonly and prop.type not in {'POINTER', 'COLLECTION'}:
                layout.prop(segment, prop.identifier)


def draw(layout, context, md, *, popup=False):
    """Draw one modifier without touching selection, expansion, or stack contents."""
    obj = context.object
    layout.context_pointer_set('modifier', md)
    layout.use_property_split = True
    layout.use_property_decorate = True
    from .modifier_list import draw_settings_header
    draw_settings_header(layout, context, md)
    if md.type in PHYSICS or md.type == 'PARTICLE_SYSTEM':
        layout.label(text='Settings are inside the ' + ('Particles' if md.type == 'PARTICLE_SYSTEM' else 'Physics') + ' tab', icon='INFO')
        return
    if md.type not in LAYOUTS:
        layout.label(text='New modifier type: use Native Stack for its settings', icon='INFO')
        return
    if md.type == 'NODES':
        layout.template_ID(md, 'node_group', new='node.new_geometry_node_group_assign')
        from .modifier_list import _draw_node_inputs
        _draw_node_inputs(layout, md)
        return
    if md.type == 'ARRAY':
        drawn = set()
        property_ui(layout, obj, md, 'fit_type', {}, drawn)
        field = {'FIXED_COUNT': 'count', 'FIT_LENGTH': 'fit_length', 'FIT_CURVE': 'curve'}[md.fit_type]
        property_ui(layout, obj, md, field, {}, drawn)
        for title, toggle, props in ARRAY_SECTIONS:
            body = section(layout, md, title, None, popup, toggle=toggle)
            if body is not None:
                for name, options in props:
                    property_ui(body, obj, md, name, options, drawn)
        return
    drawn = set()
    for title, props, state in LAYOUTS[md.type][1]:
        body = layout if title == 'Settings' else section(layout, md, title, state, popup)
        if body is None:
            # Remember closed panels' properties so they do not leak elsewhere.
            for name, _ in props:
                if name.startswith('@'):
                    drawn.update(INFLUENCE.get(name[1:], ()))
                else:
                    drawn.add(name)
            continue
        body.context_pointer_set('mbt_modifier_settings', md)
        for name, options in props:
            property_ui(body, obj, md, name, options, drawn)
        if title == 'Settings':
            if md.type == 'BEVEL' and md.limit_method == 'WEIGHT':
                property_ui(body, obj, md, 'vertex_weight' if md.affect == 'VERTICES' else 'edge_weight', {}, drawn)
            collections(body, md)
            controls = body.column(align=True)
            controls.enabled = obj.is_editable
            actions(controls, md)
    # Source helpers/dynamic properties not represented by literal native prop()
    # calls remain accessible in a separate, explicitly named advanced section.
    base = set(bpy.types.Modifier.bl_rna.properties.keys())
    remaining = [(p.identifier, {}) for p in md.bl_rna.properties
                 if p.identifier not in drawn | base and not p.is_hidden and not p.is_readonly
                 and p.type != 'COLLECTION' and not p.identifier.startswith('open_')
                 and visible(md, p.identifier)]
    if remaining:
        body = section(layout, md, 'Additional Settings', None, popup)
        if body is not None:
            for name, options in remaining:
                property_ui(body, obj, md, name, options, drawn)