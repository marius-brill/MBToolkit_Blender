"""Compact Model-tab UI; drawing only reads persistent scene data."""
from .settings import active_asset, active_component


def draw(layout, context, busy):
    from ..substance_painter import card, action_rows
    from ..substance_painter.issues import wrapped, text_width
    settings = context.scene.mbt_assets
    controls = layout.column()
    controls.enabled = not busy and getattr(context, 'mode', 'OBJECT') == 'OBJECT'
    assets = card(controls, 'Assets', 'OUTLINER_COLLECTION')
    actions = action_rows(assets, context)
    actions.operator('mbt.asset_edit', text='From Selection', icon='ADD').action = 'CREATE'
    actions.operator('mbt.asset_edit', text='Adopt Bake Setup', icon='LINKED').action = 'ADOPT'
    collection = card(assets, '', props=settings, toggle='show_collection')
    if collection is not None:
        collection.prop(settings, 'source_collection', text='Collection')
        collection.operator('mbt.asset_edit', text='Create from Collection').action = 'COLLECTION'
    if not settings.assets:
        wrapped(assets, 'Reference source meshes without changing geometry, UVs or bake settings.', text_width(context))
    else:
        assets.template_list('MBT_UL_assets', '', settings, 'assets', settings, 'active_asset', rows=3)
        asset = active_asset(settings)
        if asset:
            components = card(controls, 'Components', 'MESH_DATA')
            components.template_list('MBT_UL_asset_components', '', asset, 'components', asset, 'active_component', rows=4)
            actions = action_rows(components, context)
            actions.operator('mbt.asset_edit', text='Add Selected', icon='ADD').action = 'ADD'
            remove = actions.row()
            remove.enabled = controls.enabled and active_component(asset) is not None
            remove.operator('mbt.asset_edit', text='Remove Record', icon='REMOVE').action = 'REMOVE_COMPONENT'
            component = active_component(asset)
            if component:
                processing = card(controls, 'Processing', 'MOD_SUBSURF')
                processing.prop(component, 'high_mode')
                processing.label(text='Generation preserves existing low / UVs', icon='LOCKED')
                if component.high_mode == 'CUSTOM':
                    processing.operator('mbt.asset_process', text='Add Selected Highs').action = 'ASSIGN_HIGH'
                    processing.operator('mbt.asset_process', text='Clear High Links').action = 'CLEAR_HIGH'
                options = card(processing, '', props=settings, toggle='show_processing')
                if options is not None and component.high_mode == 'DYNABOOL':
                    options.prop(component, 'automatic_resolution')
                    if not component.automatic_resolution:
                        options.prop(component, 'voxel_size')
                    options.prop(component, 'remesh')
                    for field in ('subdivision', 'crease_angle', 'detail_tolerance', 'smoothing'):
                        options.prop(component, field)
                    options.prop(component, 'max_faces')
                    options.prop(component, 'max_work_gib')
                processing.operator('mbt.asset_process', text='Generate Component', icon='MOD_SUBSURF').action = 'GENERATE'
                processing.operator('mbt.asset_process', text='Generate Asset').action = 'GENERATE_ASSET'
                if component.generation_report:
                    wrapped(processing, component.generation_report, text_width(context))
                for item in asset.components:
                    if item.generation_state == 'Failed':
                        wrapped(processing, item.generation_report, text_width(context))
                if any(item.generation_state == 'Failed' for item in asset.components):
                    processing.operator('mbt.asset_process', text='Select Failed Sources', icon='RESTRICT_SELECT_OFF').action = 'SELECT_FAILED'
                uvs = card(controls, 'UV Preparation', 'GROUP_UVS')
                uvs.prop(component, 'uv_mode')
                uvs.prop(component, 'uv_locked')
                uvs.operator('mbt.asset_process', text='Validate UVs' if component.uv_mode == 'PRESERVE' else 'Prepare UVs', icon='GROUP_UVS').action = 'UV_PREPARE'
                uv_options = card(uvs, '', props=settings, toggle='show_uv')
                if uv_options is not None:
                    for field in ('uv_angle', 'uv_gap', 'uv_border', 'uv_allow_overlap'):
                        uv_options.prop(component, field)
                    uv_options.operator('mbt.asset_process', text='Acknowledge Reviewed UVs').action = 'UV_BASELINE'
                    wrapped(uv_options, 'Protected edges: Boolean edge attribute mbt_uv_protected. UVs pack jointly per texture set.', text_width(context))
                if component.uv_preview:
                    uvs.operator('mbt.asset_process', text='Show UV Proposal').action = 'UV_SHOW'
                    apply_row = uvs.row()
                    apply_row.enabled = controls.enabled and not component.uv_locked and component.uv_mode != 'PRESERVE'
                    apply_row.operator('mbt.asset_process', text='Apply UV Proposal', icon='CHECKMARK').action = 'UV_APPLY'
                    uvs.operator('mbt.asset_process', text='Discard Proposal', icon='CANCEL').action = 'UV_DISCARD'
                    wrapped(uvs, 'Inspect selected proposal in Edit Mode / UV Editor. Applying requires every shared member unlocked.', text_width(context))
                if component.uv_report:
                    wrapped(uvs, component.uv_report, text_width(context))
                inspector = card(controls, '', props=settings, toggle='show_inspector')
                if inspector is not None:
                    for action, label in (('SOURCE', 'Source'), ('LOW', 'Low'), ('HIGH', 'High'), ('RESTORE', 'Restore Visibility')):
                        inspector.operator('mbt.asset_process', text=label).action = action
                    wrapped(inspector, 'Visibility preview only; excluded collections remain excluded.', text_width(context))
            detail = card(controls, '', props=settings, toggle='show_component')
            component = active_component(asset)
            if detail is not None and component:
                detail.prop(component, 'source')
                detail.label(text='Low: ' + (component.low.name if component.low else 'Not generated'))
                detail.prop(component, 'uv_locked')
                for reference in component.highs:
                    detail.label(text='High: ' + (reference.mesh.name if reference.mesh else 'Missing'),
                                 icon='MESH_DATA' if reference.mesh else 'ERROR')
                if component.texture_collection:
                    detail.label(text='Set: ' + component.texture_collection.name)
                if not component.source:
                    wrapped(detail, 'Source was deleted. Assign a source or remove this record.', text_width(context))
            assets.operator('mbt.asset_edit', text='Remove Asset Record', icon='REMOVE').action = 'REMOVE_ASSET'
            draw_validation(controls, context, asset)
            status = card(controls, 'Dependency Status', 'TIME')
            status.operator('mbt.asset_process', text='Check Outdated', icon='FILE_REFRESH').action = 'CHECK_OUTDATED'
            wrapped(status, 'Explicit snapshots only. No automatic reprocessing.', text_width(context))
            for owner in ([component] if component else []) + [asset]:
                for stage in owner.stages:
                    status.label(text=stage.name + ': ' + stage.state.replace('_', ' ').title())
                    wrapped(status, stage.reason, text_width(context))
    if settings.report:
        wrapped(layout, settings.report, text_width(context))
    wrapped(layout, 'Sources are preserved. Protected UVs require explicit unlocking before changes.', text_width(context))
    if busy:
        layout.label(text='Bake in progress', icon='TIME')
        layout.operator('mbt.painter_cancel', text='Cancel Bake', icon='CANCEL')


def draw_export(layout, context, busy):
    from ..substance_painter import card
    from ..substance_painter.issues import wrapped, text_width
    settings = context.scene.mbt_assets
    controls = layout.column()
    controls.enabled = not busy and getattr(context, 'mode', 'OBJECT') == 'OBJECT'
    output = card(controls, 'Painter-ready Export', 'EXPORT')
    asset = active_asset(settings)
    output.label(text='Asset: ' + (asset.name if asset else 'Choose in Model'))
    output.prop(context.scene.mbt_painter, 'output_dir')
    output.prop(settings, 'export_low')
    output.prop(settings, 'export_high')
    output.operator('mbt.asset_process', text='Export Active Asset', icon='EXPORT').action = 'EXPORT'
    wrapped(output, 'New folder per export. Writes FBX and asset.json; does not launch Painter or modify projects.', text_width(context))
    if settings.report:
        wrapped(layout, settings.report, text_width(context))
    if busy:
        layout.operator('mbt.painter_cancel', text='Cancel Bake', icon='CANCEL')


def draw_validation(layout, context, asset):
    from ..substance_painter import card
    from ..substance_painter.issues import wrapped, text_width
    settings = context.scene.mbt_assets
    box = card(layout, '', props=settings, toggle='show_validation')
    if box is None:
        return
    box.operator('mbt.asset_process', text='Validate Asset', icon='CHECKMARK').action = 'VALIDATE'
    if asset.validation_report:
        wrapped(box, asset.validation_report, text_width(context))
    if asset.issues:
        box.template_list('MBT_UL_asset_issues', '', asset, 'issues', asset, 'issue_index', rows=3)
        if 0 <= asset.issue_index < len(asset.issues):
            issue = asset.issues[asset.issue_index]
            wrapped(box, issue.reason, text_width(context))
            wrapped(box, 'Action: ' + issue.action, text_width(context))
            row = box.row()
            row.enabled = layout.enabled and issue.mesh is not None
            row.operator('mbt.asset_process', text='Select Mesh').action = 'ISSUE_SELECT'
            row.operator('mbt.asset_process', text='Frame').action = 'ISSUE_FRAME'