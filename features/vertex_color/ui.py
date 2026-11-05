"""Compact native sidebar controls; no writes or scans while drawing."""

from . import mesh, preview


def action(layout, operator, text, value, icon='NONE'):
    props = layout.operator(operator, text=text, icon=icon)
    props.action = value
    return props


def draw(layout, context):
    obj = context.active_object
    if obj is None or obj.type != 'MESH':
        layout.label(text='Select a mesh to edit vertex colors', icon='INFO')
        return
    settings = context.scene.mbt_vertex_color
    attributes = obj.data.color_attributes
    attribute = attributes.active_color
    layout.operator_context = 'INVOKE_DEFAULT'
    if not obj.data.is_editable:
        layout.label(text='Mesh data is read-only', icon='LOCKED')
        return
    row = layout.row(align=True)
    layout.label(text='Attribute')
    row.prop_search(attributes, 'active_color_name', obj.data, 'color_attributes', text='')
    add = row.row(align=True)
    add.enabled = context.mode == 'OBJECT'
    action(add, 'mbt.vertex_color_attribute', '', 'CREATE', 'ADD')
    if attribute is None:
        create = layout.column()
        create.enabled = context.mode == 'OBJECT'
        action(create, 'mbt.vertex_color_attribute', 'Create Color Attribute', 'CREATE', 'GROUP_VCOL')
        if context.mode != 'OBJECT':
            layout.label(text='Use Object Mode to create an attribute', icon='INFO')
        return
    layout.label(text=('Face Corner' if attribute.domain == 'CORNER' else 'Vertex') + ' · ' +
                 ('Byte Color' if attribute.data_type == 'BYTE_COLOR' else 'Float Color'))
    layout.prop(settings, 'target')
    layout.prop(settings, 'affect')
    if obj.data.users > 1:
        layout.label(text=f'Shared mesh: affects {obj.data.users} users', icon='ERROR')
    if settings.affect == 'SELECTED' and attribute.domain == 'POINT':
        layout.label(text='Vertex values are shared by adjacent faces', icon='INFO')
    layout.prop(settings, 'color', text='Fill Color')
    row = layout.row(align=True)
    row.operator('mbt.vertex_color_edit', text='Edit Color…', icon='COLOR')
    action(row, 'mbt.vertex_color_apply', 'Fill', 'FILL', 'BRUSH_DATA')
    row = layout.row(align=True)
    row.label(text='Write')
    for index, channel in enumerate('RGBA'):
        row.prop(settings, 'write_mask', index=index, text=channel, toggle=True)
    layout.label(text='Preview')
    row = layout.row(align=True)
    for component in ('OFF', 'RGB', 'R', 'G', 'B', 'A'):
        row.operator('mbt.vertex_color_preview', text='Off' if component == 'OFF' else component,
                     depress=preview.mode(context) == component).component = component
    if preview.mode(context) != 'OFF':
        layout.prop(settings, 'space', text='Values')
        layout.label(text='Solid shading only', icon='INFO')
        if preview.mode(context) == 'RGB':
            layout.label(text='RGB preview ignores alpha')
    layout.prop(settings, 'tools', icon='TRIA_DOWN' if settings.tools else 'TRIA_RIGHT', emboss=False)
    if settings.tools:
        column = layout.column(align=True)
        column.prop(settings, 'space')
        column.prop(settings, 'channel')
        column.prop(settings, 'value')
        row = column.row(align=True)
        action(row, 'mbt.vertex_color_apply', 'Set', 'SET')
        action(row, 'mbt.vertex_color_apply', 'Invert', 'INVERT')
        column.prop(settings, 'destination')
        row = column.row(align=True)
        action(row, 'mbt.vertex_color_apply', 'Copy', 'COPY')
        action(row, 'mbt.vertex_color_apply', 'Swap', 'SWAP')
        action(column, 'mbt.vertex_color_apply', 'Sample First Affected', 'SAMPLE', 'EYEDROPPER')
        action(column, 'mbt.vertex_color_apply', 'Use Material Base Color', 'MATERIAL', 'MATERIAL')
        action(column, 'mbt.vertex_color_apply', 'Inspect Values / Min–Max', 'INSPECT', 'VIEWZOOM')
        if settings.status:
            # Keep each channel on its own bounded row in narrow sidebars.
            for text in settings.status.split(' | '):
                column.label(text=text)
    layout.prop(settings, 'attributes', icon='TRIA_DOWN' if settings.attributes else 'TRIA_RIGHT', emboss=False)
    if settings.attributes:
        column = layout.column(align=True)
        column.enabled = context.mode == 'OBJECT'
        row = column.row(align=True)
        action(row, 'mbt.vertex_color_attribute', 'Rename', 'RENAME')
        action(row, 'mbt.vertex_color_attribute', 'Duplicate', 'DUPLICATE')
        action(column, 'mbt.vertex_color_attribute', 'Set Render Default', 'RENDER', 'RENDER_STILL')
        action(column, 'mbt.vertex_color_attribute', 'Create Missing on Targets', 'MISSING', 'ADD')
        action(column, 'mbt.vertex_color_attribute', 'Convert Domain / Storage…', 'CONVERT')
        action(column, 'mbt.vertex_color_attribute', 'Make Single User', 'SINGLE', 'DUPLICATE')
        action(column, 'mbt.vertex_color_attribute', 'Delete Attribute…', 'DELETE', 'TRASH')
        if context.mode != 'OBJECT':
            layout.label(text='Attribute management requires Object Mode', icon='INFO')