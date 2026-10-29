"""Blender-side Painter preparation and manual texture round-trip."""
from . import settings, operators


def register():
    settings.register()
    operators.register()


def unregister():
    operators.unregister()
    settings.unregister()


def draw(layout, context):
    from . import runtime
    from ...ui import section_icons
    props = context.scene.mbt_painter
    busy = runtime.busy()
    controls = layout.column()
    controls.enabled = not busy
    root = layout
    layout = controls
    layout.label(text='Substance Painter — Blender Setup')
    for role, attribute in (('LOW', 'low_collection'), ('HIGH', 'high_collection')):
        row = layout.row(align=True)
        row.prop(props, attribute)
        row.operator('mbt.painter_assign', text='', icon='ADD').role = role
    layout.prop(props, 'project_name')
    layout.prop(props, 'output_dir')
    layout.prop(props, 'resolution')
    box = layout.box()
    box.label(text='Requested Bake Maps')
    box.prop(props, 'bake_maps')
    box.label(text='Matching: By Mesh Name')
    active = context.active_object
    if active and active.type == 'MESH':
        box.prop(active, 'mbt_bake_group')
        box.label(text='Same group = shared low/high bake sources')
        box.prop(active, 'mbt_bake_target')
        if active.mbt_bake_target:
            box.label(text='Stored target; clear to auto-match', icon='INFO')
    box.label(text='Unassigned: automatic name / surface matching')
    layout.prop(props, 'bake_settings', icon='TRIA_DOWN' if props.bake_settings else 'TRIA_RIGHT', emboss=False)
    if props.bake_settings:
        options = layout.box()
        for attribute in ('front_distance', 'rear_distance', 'relative_distance', 'antialiasing',
                          'normal_format', 'project_template', 'replace_materials'):
            options.prop(props, attribute)
        if 'ID' in props.bake_maps:
            options.prop(props, 'id_source')
    layout = root
    actions = layout.row(align=True)
    actions.scale_y = 1.5
    connection = actions.row(align=True)
    connection.enabled = not busy
    connection.operator('mbt.painter_connect', text='Bake', **section_icons.icon_kwargs('substance_painter')).action = 'AUTO'
    cancel = actions.row(align=True)
    cancel.enabled = busy and runtime._cancel is not None and not runtime._cancel.is_set()
    cancel.operator('mbt.painter_cancel', text='', icon='X')
    if props.report:
        status = layout.box()
        status.label(text='Bake Status', **section_icons.icon_kwargs('bake_status'))
        import textwrap
        for line in textwrap.wrap(props.report, width=42):
            status.label(text=line)
        if 'Saved bake job.json is missing:' in props.report:
            recovery = status.row()
            recovery.enabled = not busy
            recovery.operator('mbt.painter_new_project', text='New Project Next Bake', icon='FILE_NEW')
    project = layout.row()
    project.enabled = not runtime.busy() and bool(props.project_file)
    project.operator('mbt.painter_connect', text='Open Painter Project', **section_icons.icon_kwargs('painter_app')).action = 'OPEN'
    layout.prop(props, 'advanced', icon='TRIA_DOWN' if props.advanced else 'TRIA_RIGHT', emboss=False)
    if props.advanced:
        advanced = layout.column()
        advanced.enabled = not runtime.busy()
        advanced.prop(props, 'export_config')
        advanced.operator('mbt.painter_connect', text='Update Textures (No Bake)', icon='IMPORT').action = 'EXPORT'
        advanced.operator('mbt.painter_new_project', text='New Project Next Bake', icon='FILE_NEW')
        row = advanced.row(align=True)
        row.operator('mbt.painter_connect', text='Test Connection').action = 'TEST'
        row.operator('mbt.painter_connect', text='Launch / Connect').action = 'CONNECT'
        advanced.operator('mbt.painter_action', text='Validate').action = 'VALIDATE'
        advanced.operator('mbt.painter_action', text='Retry Material Import').action = 'IMPORT'
        if props.preparation_timings:
            import json
            timings = json.loads(props.preparation_timings)
            diagnostics = advanced.box()
            diagnostics.label(text='Preparation: %.2fs active' % sum(item['seconds'] for item in timings))
            for item in sorted(timings, key=lambda item: item['seconds'], reverse=True)[:5]:
                diagnostics.label(text='%.3fs — %s' % (item['seconds'], item['stage']))