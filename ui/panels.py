"""Selection-driven, fixed section cards in the MBToolkit viewport sidebar."""

from importlib import import_module

import bpy
from bpy.props import BoolProperty, StringProperty

from ..core.addon import ADDON_ID, get_prefs
from ..core.registry import register_classes, unregister_classes
from ..core import feature_manager
from ..core.section_data import SECTIONS, SECTION_BY_KEY, decode_selection, select_section
from . import section_icons


SELECTOR_SCALE = 2.0


def selector_columns(context, count):
    """Wrap rather than squeeze doubled buttons in a narrow sidebar."""
    region = getattr(context, 'region', None)
    if region is None:
        return max(1, count)
    ui_scale = context.preferences.system.ui_scale or 1.0
    available = max(1, region.width - 32 * ui_scale)
    return max(1, min(count, int(available / (20 * SELECTOR_SCALE * ui_scale))))


def visible_sections(prefs):
    return [key for key in decode_selection(prefs.sidebar_sections)
            if key != 'substance_painter' and feature_manager.is_enabled(key)]


def redraw(context):
    for window in context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()


class MBT_OT_select_section(bpy.types.Operator):
    bl_idname = 'mbt.select_section'
    bl_label = 'Select Toolkit Section'
    bl_options = {'INTERNAL'}

    section: StringProperty(options={'SKIP_SAVE'})
    extend: BoolProperty(options={'SKIP_SAVE'})

    @classmethod
    def description(cls, context, properties):
        entry = SECTION_BY_KEY.get(properties.section)
        return entry[1] if entry else 'Section'

    def invoke(self, context, event):
        self.extend = event.shift
        return self.execute(context)

    def execute(self, context):
        prefs = get_prefs(context)
        if prefs is None or self.section not in SECTION_BY_KEY:
            return {'CANCELLED'}
        if not feature_manager.is_enabled(self.section):
            return {'CANCELLED'}
        if self.section == 'substance_painter':
            return {'CANCELLED'}  # Baking now has its own sidebar category.
        prefs.sidebar_sections = select_section(prefs.sidebar_sections, self.section, self.extend)
        context.preferences.is_dirty = True
        redraw(context)
        return {'FINISHED'}


def draw_section(layout, context, key):
    entry = SECTION_BY_KEY[key]
    card = layout.box()
    card.use_property_decorate = False
    header = card.row()
    header.label(text=entry[1], **section_icons.icon_kwargs(key))
    card.separator(factor=0.35)
    body = card.column()
    body.use_property_decorate = False
    for index, path in enumerate(entry[4]):
        if index:
            body.separator()
        if key == 'tools':
            body.label(text='Incremental Rename' if index == 0 else 'Clean Up')
        module = import_module(f'{ADDON_ID}.features.{path}')
        module.draw(body, context)


class MBT_PT_main(bpy.types.Panel):
    bl_idname = 'MBT_PT_main'
    bl_label = 'MBToolkit'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'MBToolkit'

    def draw_header_preset(self, context):
        self.layout.operator('mbt.open_prefs', text='', icon='PREFERENCES')

    def draw(self, context):
        # Use Blender's existing panel backdrop, not a second encompassing box.
        # Native layout sizing handles added/removed sections and scrolling.
        layout = self.layout
        layout.use_property_decorate = False
        prefs = get_prefs(context)
        if prefs is None:
            layout.label(text='Initializing MBToolkit…', icon='INFO')
            return
        selected = visible_sections(prefs)
        available = [entry for entry in SECTIONS
                     if entry[0] != 'substance_painter' and feature_manager.is_enabled(entry[0])]
        columns = selector_columns(context, len(available))
        for start in range(0, len(available), columns):
            toolbar = layout.row(align=True)
            toolbar.alignment = 'LEFT'
            toolbar.scale_x = SELECTOR_SCALE
            toolbar.scale_y = SELECTOR_SCALE
            toolbar.emboss = 'NORMAL'
            toolbar.operator_context = 'INVOKE_DEFAULT'
            for key, label, icon, color, modules in available[start:start + columns]:
                op = toolbar.operator('mbt.select_section', text='', emboss=True,
                                      depress=key in selected, **section_icons.icon_kwargs(key))
                op.section = key
        layout.separator(factor=0.5)
        if not selected:
            layout.label(text='Choose a section above', icon='INFO')
            layout.label(text='Shift-click to show multiple sections')
            if not any(feature_manager.is_enabled(entry[0]) for entry in SECTIONS):
                layout.label(text='Enable features in Preferences')
        for key in selected:
            draw_section(layout, context, key)


class MBT_PT_baking(bpy.types.Panel):
    bl_idname = 'MBT_PT_baking'
    bl_label = 'MBToolkit Baking'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'MBT Baking'

    @classmethod
    def poll(cls, context):
        return feature_manager.is_enabled('substance_painter') and hasattr(context.scene, 'mbt_painter')

    def draw_header_preset(self, context):
        self.layout.operator('mbt.open_prefs', text='', icon='PREFERENCES')

    def draw(self, context):
        self.layout.use_property_decorate = False
        module = import_module(f'{ADDON_ID}.features.substance_painter')
        module.draw(self.layout, context)


classes = (MBT_OT_select_section, MBT_PT_main, MBT_PT_baking)
# Kept as panels-only bookkeeping for feature lifecycle callers/tests.
_registered = []
_running = False


def refresh():
    # Visibility is drawn from the active feature registry; no RNA churn needed.
    if _running:
        redraw(bpy.context)


def register():
    global _running
    section_icons.register()
    try:
        register_classes(classes)
    except Exception:
        for cls in reversed(classes):
            if cls.is_registered:
                unregister_classes((cls,))
        section_icons.unregister()
        raise
    _registered.extend((MBT_PT_main, MBT_PT_baking))
    _running = True


def unregister():
    global _running
    _running = False
    unregister_classes(classes)
    _registered.clear()
    section_icons.unregister()
