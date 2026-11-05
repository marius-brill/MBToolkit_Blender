"""Blender-side Painter preparation and manual texture round-trip."""
from . import settings, operators


def status_lines(report, width=36):
    """Exactly two bounded rows; the full report is available in Details."""
    phase, separator, detail = ' '.join(report.split()).partition(': ')
    if not separator:
        phase, detail = 'Status', phase
    width = max(8, width)
    def clip(text):
        return text if len(text) <= width else text[:width - 1] + '…'
    return clip(phase), clip(detail)


def register():
    settings.register()
    operators.register()


def unregister():
    operators.unregister()
    settings.unregister()


def collection_row(layout, context, props, attribute, label, icon):
    """Identical field columns regardless of the number of action buttons."""
    from .texture_sets import draw_visibility
    if context.region is not None and not wide_layout(context):
        layout.label(text=label, icon=icon)
        layout.prop(props, attribute, text='')
        actions = layout.row(align=True)
        draw_visibility(actions, context, getattr(props, attribute))
        return actions
    row = layout.split(factor=0.72, align=True)
    field = row.split(factor=0.32, align=True)
    field.label(text=label, icon=icon)
    field.prop(props, attribute, text='')
    actions = row.row(align=True)
    draw_visibility(actions, context, getattr(props, attribute))
    return actions


def wide_layout(context):
    """Use view coordinates so sidebar zoom and UI scaling both affect wrapping."""
    region = context.region
    if region is None:
        return False
    view = region.view2d
    width = abs(view.region_to_view(region.width, 0)[0] - view.region_to_view(0, 0)[0])
    return width >= 420 * (context.preferences.system.ui_scale or 1.0)


def card(layout, title, icon='NONE', props=None, toggle=None, **kwargs):
    box = layout.box()
    header = box.row(align=True)
    if toggle:
        header.prop(props, toggle, text=title,
                    icon='TRIA_DOWN' if getattr(props, toggle) else 'TRIA_RIGHT', emboss=False)
        if not getattr(props, toggle):
            return None
    else:
        header.label(text=title, icon=icon, **kwargs)
    body = box.column()
    body.use_property_decorate = False
    return body


def action_rows(layout, context, count=2):
    """Paired actions become full-width buttons in narrow sidebars."""
    return layout.row(align=True) if wide_layout(context) and count > 1 else layout.column(align=True)


def draw_setup(layout, context, props):
    from .texture_sets import ROLE_COLORS
    layout = card(layout, 'Setup', 'TOOL_SETTINGS')
    row = collection_row(layout, context, props, 'texture_collection', 'Texture Set', 'OUTLINER_COLLECTION')
    row.operator('mbt.painter_texture_set', text='', icon='ADD').action = 'ADD'
    remove = row.row(align=True)
    remove.enabled = len(props.texture_sets) > 1
    remove.operator('mbt.painter_texture_set', text='', icon='REMOVE').action = 'REMOVE'
    for role, attribute in (('LOW', 'low_collection'), ('HIGH', 'high_collection')):
        row = collection_row(layout, context, props, attribute,
                             'Low Poly' if role == 'LOW' else 'High Poly',
                             'COLLECTION_' + ROLE_COLORS[attribute])
        row.operator('mbt.painter_assign', text='', icon='ADD').role = role
        row.label(text='', icon='BLANK1')


def draw_maps(layout, context, props):
    box = card(layout, 'Requested Bake Maps', 'RENDERLAYERS')
    if wide_layout(context):
        row = box.row(align=True)
        columns = [row.column(align=True), row.column(align=True)]
    else:
        columns = [box.column(align=True)]
    for index, (key, label) in enumerate(settings.BAKE_MAPS):
        column = columns[0 if len(columns) == 1 or index < 4 else 1]
        column.prop_enum(props, 'bake_maps', key, text=label)


def draw_matching(layout, context, props):
    matching = card(layout, 'Mesh Matching', 'LINKED')
    matching.label(text='Automatic: names / surfaces', icon='INFO')
    active = context.active_object
    if active and active.type == 'MESH':
        matching.label(text=active.name, icon='MESH_DATA')
        matching.prop(active, 'mbt_bake_group')
        matching.prop(active, 'mbt_bake_target')
        if active.mbt_bake_target:
            matching.label(text='Auto suggestion; rechecked each bake' if active.mbt_bake_auto_target == active.mbt_bake_target
                      else 'Manual target; clear to auto-match', icon='INFO')
    else:
        matching.label(text='Select a mesh to edit its assignment')


def draw_settings(layout, context, props):
    if props.bake_settings:
        options = card(layout, 'Bake Settings', 'PREFERENCES')
        options.prop(props, 'auto_distances')
        if props.auto_distances:
            options.label(text='Estimated at preparation; absolute centimeters.', icon='INFO')
            options.label(text='Approximation, not guaranteed ray coverage.')
        distances = options.column()
        distances.enabled = not props.auto_distances
        for attribute in ('front_distance', 'rear_distance', 'relative_distance'):
            distances.prop(props, attribute)
        for attribute in ('projection_normals', 'antialiasing',
                          'normal_format', 'project_template', 'replace_materials'):
            options.prop(props, attribute)
        if props.projection_normals == 'FACE':
            options.label(text='Mesh normals can skew or miss hard edges', icon='ERROR')
        if 'ID' in props.bake_maps:
            options.prop(props, 'id_source')
        options.separator()
        options.prop(props, 'projection_threshold')
        options.operator('mbt.painter_action', text='Analyze Projection', icon='VIEWZOOM').action = 'PROJECTION'
        options.label(text='Estimate only — no correction applied', icon='INFO')
        if props.projection_report:
            options.operator('mbt.painter_status_details', text='Projection Details', icon='TEXT').report_text = props.projection_report


def draw_actions(layout, context, props, busy):
    from . import runtime
    from ...ui import section_icons
    layout = card(layout, 'Bake', 'RENDER_STILL')
    actions = action_rows(layout, context)
    actions.scale_y = 1.5
    connection = actions.row(align=True)
    connection.enabled = not busy
    connection.operator('mbt.painter_connect', text='Bake', **section_icons.icon_kwargs('substance_painter')).action = 'AUTO'
    cancel = actions.row(align=True)
    cancel.enabled = busy and runtime._cancel is not None and not runtime._cancel.is_set()
    cancel.operator('mbt.painter_cancel', text='Cancel Bake', icon='X')
    layout.prop(props, 'bake_settings', text='Bake Settings', icon='PREFERENCES', toggle=True)


def draw_status(layout, context, props, busy):
    from . import runtime
    from ...ui import section_icons
    if props.report:
        status = layout.box()
        header = status.row(align=True)
        header.label(text='Bake Status', **section_icons.icon_kwargs('bake_status'))
        header.operator('mbt.painter_status_details', text='', icon='TEXT').report_text = props.report
        # Keep text within the sidebar, including UI scale and sidebar zoom.
        region = context.region
        width = 36
        if region is not None:
            unit = 20 * (context.preferences.system.ui_scale or 1.0)
            view = region.view2d
            left = view.region_to_view(0, 0)[0]
            right = view.region_to_view(region.width, 0)[0]
            width = max(8, min(80, int(abs(right - left) / unit * 2) - 6))
        for line in status_lines(props.report, width):
            status.label(text=line)
        status.label(text=f'Elapsed: {int(runtime.elapsed_seconds())} s')
        if props.issue_rows:
            blocking = sum(item.blocking for item in props.issue_rows)
            status.label(text=f'{blocking} blocking / {len(props.issue_rows) - blocking} warnings', icon='ERROR')
        if not busy and props.matching_report:
            issues = status.row(align=True)
            issues.label(text='Matching issues — inspect bake results', icon='ERROR')
            issues.operator('mbt.painter_status_details', text='Details', icon='TEXT').report_text = props.matching_report
        if 'Saved bake job.json is missing:' in props.report:
            recovery = status.row()
            recovery.enabled = not busy
            recovery.operator('mbt.painter_new_project', text='New Project Next Bake', icon='FILE_NEW')


def draw_advanced(layout, context, props, busy):
    advanced = card(layout, 'Advanced / Troubleshooting', props=props, toggle='advanced')
    if advanced is not None:
        advanced.enabled = not busy
        advanced.label(text='Connection / Diagnostics', icon='TOOL_SETTINGS')
        row = action_rows(advanced, context)
        row.operator('mbt.painter_connect', text='Test Connection').action = 'TEST'
        row.operator('mbt.painter_connect', text='Launch / Connect').action = 'CONNECT'
        advanced.operator('mbt.painter_connect', text='Inspect Projection Capabilities').action = 'CAPABILITIES'
        advanced.operator('mbt.painter_action', text='Validate').action = 'VALIDATE'
        if props.preparation_timings:
            import json
            from .issues import text_width, wrapped
            timings = json.loads(props.preparation_timings)
            diagnostics = advanced.box()
            diagnostics.label(text='Preparation: %.2fs active' % sum(item['seconds'] for item in timings))
            for item in sorted(timings, key=lambda item: item['seconds'], reverse=True)[:5]:
                wrapped(diagnostics, '%.3fs — %s' % (item['seconds'], item['stage']), text_width(context))


def draw_export(layout, context, props, busy):
    from ...ui import section_icons
    output = card(layout, 'Project / Output', 'FILE')
    output.enabled = not busy
    output.prop(props, 'project_name')
    output.prop(props, 'output_dir')
    project = output.row()
    project.enabled = not busy and bool(props.project_file)
    project.operator('mbt.painter_connect', text='Open Painter Project', **section_icons.icon_kwargs('painter_app')).action = 'OPEN'
    output.operator('mbt.painter_new_project', text='New Project Next Bake', icon='FILE_NEW')
    textures = card(layout, 'Textures / Materials', 'IMPORT')
    textures.enabled = not busy
    textures.prop(props, 'export_config')
    textures.operator('mbt.painter_connect', text='Update Textures (No Bake)', icon='IMPORT').action = 'EXPORT'
    textures.operator('mbt.painter_action', text='Retry Material Import', icon='MATERIAL').action = 'IMPORT'


def draw(layout, context):
    from . import runtime
    from .issues import draw as draw_issues
    props = context.scene.mbt_painter
    busy = runtime.busy()
    tabs = layout.row(align=True)
    tabs.scale_y = 1.25
    tabs.prop(props, 'ui_tab', expand=True)
    layout.separator(factor=0.5)
    controls = layout.column()
    controls.enabled = not busy
    if props.ui_tab == 'MODEL':
        draw_setup(controls, context, props)
        draw_matching(controls, context, props)
        controls.operator('mbt.painter_action', text='Validate Setup', icon='CHECKMARK').action = 'VALIDATE'
    elif props.ui_tab == 'BAKE':
        controls.prop(props, 'resolution')
        draw_maps(controls, context, props)
        draw_actions(layout, context, props, busy)
        options = layout.column()
        options.enabled = not busy
        draw_settings(options, context, props)
    else:
        draw_export(layout, context, props, busy)
    if busy and props.ui_tab != 'BAKE':
        cancel = layout.row()
        cancel.enabled = runtime._cancel is not None and not runtime._cancel.is_set()
        cancel.operator('mbt.painter_cancel', text='Cancel Bake', icon='X')
    draw_status(layout, context, props, busy)
    if props.ui_tab in {'MODEL', 'BAKE'}:
        draw_issues(layout, context)
    if props.ui_tab == 'BAKE':
        draw_advanced(layout, context, props, busy)