"""Automation-first UV suite; original implementation, no vendored sources."""
from . import settings, operators
from ...core.registry import register_modules, unregister_modules


def register():
    register_modules((settings, operators))


def unregister():
    unregister_modules((settings, operators))


def section(layout, settings, property_name):
    box = layout.box()
    row = box.row()
    row.use_property_split = False
    row.prop(settings, property_name, icon='TRIA_DOWN' if getattr(settings, property_name) else 'TRIA_RIGHT', emboss=False)
    return box if getattr(settings, property_name) else None


def buttons(layout, pairs):
    for pair in pairs:
        row = layout.row(align=True)
        for action, text in pair:
            row.operator('mbt.uv_action', text=text).action = action


def draw(layout, context):
    is_uv = context.area is not None and context.area.type == 'IMAGE_EDITOR'
    settings = context.scene.mbt_uv
    layout.use_property_split = True
    layout.use_property_decorate = False
    layout.prop(settings, 'preset')
    row = layout.row()
    row.scale_y = 1.5
    row.operator('mbt.uv_action', text='Auto UV: Seams / Unwrap / Pack', icon='GROUP_UVS').action = 'AUTO'
    layout.operator('mbt.uv_action', text='Unwrap Existing Seams').action = 'UNWRAP'
    box = section(layout, settings, 'show_auto')
    if box:
        row = box.row(align=True)
        row.use_property_split = False
        row.use_property_decorate = False
        row.prop(settings, 'width')
        row.prop(settings, 'height')
        for name in ('gap', 'border', 'method', 'unwrap_search', 'auto_shape'):
            box.prop(settings, name)
    if not is_uv:
        box = layout.box()
        box.label(text='Seam Management')
        box.prop(settings, 'seams')
        box.prop(settings, 'angle')
        buttons(box, ((('SEAMS', 'Smart Seams'), ('REPAIR_SEAMS', 'Complete Regions')),
                      (('MARK_SELECTED', 'Mark Selected'), ('CLEAR_SELECTED', 'Clear Selected')),
                      (('COMPLETE_SEAM', 'Complete Selected Loop'),),
                      (('SEAMS_UV', 'From UV Borders'), ('CLEAR_SEAMS', 'Clear Target Seams'))))
        box = section(layout, settings, 'show_seam_options')
        if box:
            for name in ('material_seams', 'region_angle'):
                box.prop(settings, name)
        draw_report(layout, settings)
        return
    buttons(layout, ((('INPLACE', 'Unwrap In Place'), ('IMPROVE', 'Improve Existing')),))
    box = layout.box()
    box.label(text='Shape & Repair')
    buttons(box, ((('STRAIGHTEN', 'Smart Straighten'), ('CHAIN', 'Edge Chain')),
                  (('QUADRIFY', 'Quadrify'), ('RECTIFY', 'Rectify')),
                  (('RELAX', 'Flatten / Relax'), ('CIRCLE', 'Circle')),
                  (('ORIENT', 'Orient'), ('ROTATE', 'Rotate 90°'))))
    box = section(layout, settings, 'show_shape')
    if box:
        for name in ('axis', 'spacing', 'iterations', 'max_stretch'):
            box.prop(settings, name)
    layout.operator('mbt.pack_uvs', text='Smart Pack')
    box = section(layout, settings, 'show_layout')
    if box:
        for name in ('rotation', 'effort', 'pack_backend', 'pack_scale', 'preserve_stacks', 'tile_start', 'tile_count'):
            box.prop(settings, name)
        buttons(box, ((('PIN', 'Lock Islands'), ('UNPIN', 'Unlock Islands')),))
    box = layout.box()
    box.label(text='Texel Density (whole islands)')
    box.prop(settings, 'density_unit', expand=True)
    box.prop(settings, 'density_display', text='Density (' + ('px/cm' if settings.density_unit == 'CM' else 'px/m') + ')')
    row = box.row(align=True)
    for action, text in (('MEASURE', 'Get'), ('DENSITY', 'Set'), ('NORMALIZE', 'Normalize')):
        row.operator('mbt.uv_action', text=text).action = action
    box.operator('mbt.uv_action', text='Match Active Island').action = 'MATCH_DENSITY'
    box.prop(settings, 'density_tolerance')
    box = section(layout, settings, 'show_diagnostics')
    if box:
        buttons(box, ((('INSPECT', 'Inspect UVs'), ('COUNT', 'Count Islands')),
                      (('SELECT_ISLANDS', 'Islands'), ('SELECT_SIMILAR', 'Similar Topology')),
                      (('SELECT_OVERLAP', 'Overlaps'), ('SELECT_DEGENERATE', 'Collapsed')),
                      (('SELECT_OUTSIDE', 'Outside Tiles'), ('SELECT_FLIPPED', 'Negative Winding')),
                      (('SELECT_DENSITY', 'Density Deviations'),)))
    box = layout.box()
    box.label(text='Connectivity & Transforms')
    for pair in ((('WELD', 'Weld'), ('SPLIT', 'Split Faces')),
                 (('ALIGN_U', 'Align U'), ('ALIGN_V', 'Align V')),
                 (('DISTRIBUTE_U', 'Distribute U'), ('DISTRIBUTE_V', 'Distribute V')),
                 (('MATCH_SIZE', 'Match Dimensions'), ('FIT', 'Fit Proportionally'))):
        row = box.row(align=True)
        for action, text in pair:
            row.operator('mbt.uv_action', text=text).action = action
    box = section(layout, settings, 'show_maps')
    if box:
        box.prop(settings, 'map_name')
        buttons(box, ((('MAP_NEW', 'New'), ('MAP_COPY', 'Copy')),
                      (('MAP_RENAME', 'Rename'), ('MAP_ACTIVE', 'Activate')),
                      (('CHECKER', 'Show Checker Image'),)))
    draw_report(layout, settings)


def draw_report(layout, settings):
    if settings.report:
        import textwrap
        for line in textwrap.wrap(settings.report, width=46):
            layout.label(text=line)
    if settings.details:
        box = section(layout, settings, 'show_details')
        if box:
            import textwrap
            for reason in settings.details.splitlines():
                for line in textwrap.wrap(reason, width=46):
                    box.label(text=line)