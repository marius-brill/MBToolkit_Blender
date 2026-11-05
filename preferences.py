import bpy
from bpy.props import BoolProperty, CollectionProperty, EnumProperty, IntProperty, FloatProperty, StringProperty
from .core.pie_data import KEY_ITEMS, MBT_PieMenu
from .core.script_data import MBT_ScriptFavorite

from .core.registry import register_classes, unregister_classes
from .core.addon import get_prefs
from .core import preferences_ui, feature_manager, sidebar_data
from .core.section_data import DEFAULT_SELECTION


def _drag_favorite(self, value):
    if value and not preferences_ui._drag_sessions:
        bpy.ops.mbt.reorder_favorites('INVOKE_DEFAULT', key=self.key)


class MBT_ModifierFavorite(bpy.types.PropertyGroup):
    key: StringProperty()
    label: StringProperty()
    drag: BoolProperty(name='Drag to reorder',
        description='Drag to move this favorite; release to finish, Escape to cancel',
        get=lambda self: preferences_ui.favorite_dragged(self.key), set=_drag_favorite,
        options={'SKIP_SAVE'})


class MBT_OT_modifier_favorite(bpy.types.Operator):
    bl_idname = 'mbt.modifier_favorite'
    bl_label = 'Edit Modifier Favorites'
    key: StringProperty()
    label: StringProperty()
    action: EnumProperty(items=[(x, x.title(), '') for x in ('TOGGLE', 'UP', 'DOWN', 'REMOVE')])
    index: IntProperty()

    def execute(self, context):
        prefs = get_prefs(context)
        if prefs is None:
            return {'CANCELLED'}
        favorites = prefs.modifier_favorites
        if self.action == 'TOGGLE':
            index = next((i for i, f in enumerate(favorites) if f.key == self.key), None)
            if index is None:
                item = favorites.add()
                item.key, item.label = self.key, self.label
            else:
                favorites.remove(index)
        elif 0 <= self.index < len(favorites):
            if self.action == 'REMOVE':
                favorites.remove(self.index)
            else:
                target = self.index + (-1 if self.action == 'UP' else 1)
                if 0 <= target < len(favorites):
                    favorites.move(self.index, target)
        context.preferences.is_dirty = True
        for window in context.window_manager.windows:
            for area in window.screen.areas:
                area.tag_redraw()
        return {'FINISHED'}


def _modifier_hotkey_changed(self, context):
    if feature_manager.is_enabled('modifier_list'):
        from .features.modifier_list import rebuild_keymap
        rebuild_keymap()


def draw_modifier_preferences(layout, prefs):
    from .features.modifier_list import catalog, entry_key, CATEGORIES
    layout.label(text='Viewport modifier popup shortcut:')
    preferences_ui.draw_shortcut(layout, prefs)
    entries = {}
    for obj_type in ('MESH', 'CURVE', 'VOLUME', 'GREASEPENCIL', 'POINTCLOUD', 'LATTICE'):
        for entry in catalog(obj_type):
            entries[entry_key(entry)] = entry
    preview = layout.box()
    preview.label(text='Favorites')
    preferences_ui.draw_favorite_tiles(preview, prefs, entries)
    if not prefs.modifier_favorites:
        preview.label(text='Choose favorites below to build your toolbar', icon='ADD')
    layout.label(text='Available modifiers')
    favorites = {f.key for f in prefs.modifier_favorites}
    row = layout.row()
    for category in CATEGORIES:
        col = row.column(align=True)
        col.label(text=category)
        for key, entry in entries.items():
            if entry['category'] == category:
                op = col.operator('mbt.modifier_favorite', text=entry['label'],
                                  icon=entry['icon'], depress=key in favorites)
                op.key, op.label, op.action = key, entry['label'], 'TOGGLE'


class MBT_Preferences(bpy.types.AddonPreferences):
    bl_idname = __package__  # root package = add-on id

    # UV tools settings
    uv_angle_threshold: FloatProperty(
        name="UV Angle Threshold",
        description="Angle threshold for marking seams in UV tools (degrees)",
        default=70.0,
        min=0.0,
        max=180.0,
        step=1.0
    )

    pies: CollectionProperty(type=MBT_PieMenu)
    modifier_favorites: CollectionProperty(type=MBT_ModifierFavorite)
    script_favorites: CollectionProperty(type=MBT_ScriptFavorite)
    script_favorite_index: IntProperty(default=0, min=0, options={'SKIP_SAVE'})
    n_panel_tabs: CollectionProperty(type=sidebar_data.MBT_NPanelTab)
    sidebar_sections: StringProperty(name='Visible Toolkit Sections', default=DEFAULT_SELECTION,
        description='Selected MBToolkit sections in click order; independent of whole sidebar tabs')
    n_panel_enabled: BoolProperty(name='Enable Sidebar Tab Management', default=True,
        description='Apply saved sidebar visibility and order', update=sidebar_data.changed)
    modifier_popup_key: EnumProperty(name='Key', items=KEY_ITEMS, default='W', update=_modifier_hotkey_changed)
    modifier_popup_shift: BoolProperty(name='Shift', default=True, update=_modifier_hotkey_changed)
    modifier_popup_ctrl: BoolProperty(name='Ctrl', default=False, update=_modifier_hotkey_changed)
    modifier_popup_alt: BoolProperty(name='Alt', default=False, update=_modifier_hotkey_changed)
    modifier_popup_oskey: BoolProperty(name='OS Key', default=False, update=_modifier_hotkey_changed)
    pie_index: IntProperty()
    stats_timings: BoolProperty(name='Native Modifier Timings', default=True,
        description='Read last-evaluation modifier timings, not frame time')
    stats_tri_budget: IntProperty(name='Triangle Budget', default=1000000, min=1)
    stats_ms_budget: FloatProperty(name='Modifier Budget (ms)', default=16.0, min=0.01)
    painter_executable: StringProperty(name='Painter Executable', subtype='FILE_PATH',
        description='Leave empty to detect the standard Adobe/Steam installation')
    painter_project_template: StringProperty(name='Default Project Template', subtype='FILE_PATH',
        description='Optional .spt template for new projects; scene template overrides this')
    painter_port: IntProperty(name='Local Port', default=60041, min=1024, max=65535,
        description='IPv4/IPv6 loopback only; automatic launch uses the default port 60041')
    tab: EnumProperty(
        items=(("GENERAL", "General", "", 7),
               ("MODIFIERS", "Modifiers", "", 0), ("PIES", "Pie Menus", "", 1),
               ("PERFORMANCE", "Scene Performance", "", 2), ("UV", "UV", "", 3),
               ("N_PANEL", "N-Panel", "Manage whole 3D Viewport sidebar tabs", 4),
               ("PAINTER", "Painter", "Substance Painter connection", 5), ("ABOUT", "About", "", 6)),
        default="GENERAL",
    )

    def draw(self, context):
        layout = self.layout
        layout.row().prop(self, "tab", expand=True)
        
        if self.tab == 'GENERAL':
            layout.label(text='Enable only the features you use.', icon='PREFERENCES')
            for key, label, default, paths in feature_manager.FEATURES:
                layout.prop(self, 'enable_' + key)
                if feature_manager.error(key):
                    layout.label(text=feature_manager.error(key), icon='ERROR')
            layout.separator()
            layout.label(text='Changes apply immediately. Disabled features are skipped at startup.')
            layout.label(text='Save Preferences to retain these choices across restarts.')
            layout.operator('wm.save_userpref', text='Save Preferences', icon='FILE_TICK')
            return
        feature = {'MODIFIERS': 'modifier_list', 'PIES': 'pie_menus',
                   'PERFORMANCE': 'scene_stats', 'UV': 'uv_tools',
                   'N_PANEL': 'n_panel', 'PAINTER': 'substance_painter'}.get(self.tab)
        if feature and not feature_manager.is_enabled(feature):
            layout.label(text='This feature is disabled. Enable it in General.', icon='INFO')
            layout.prop(self, 'enable_' + feature)
            return
        if self.tab == 'MODIFIERS':
            draw_modifier_preferences(layout, self)
        elif self.tab == 'N_PANEL':
            from .features import n_panel
            n_panel.draw_preferences(layout, self)
        elif self.tab == 'PERFORMANCE':
            layout.prop(self, 'stats_timings')
            layout.prop(self, 'stats_tri_budget')
            layout.prop(self, 'stats_ms_budget')
        elif self.tab == "PIES":
            from .features.pie_menus import ui as pie_ui
            pie_ui.draw_prefs(layout, self)
        elif self.tab == 'UV':
            layout.label(text='UV Tools')
            layout.prop(self, 'uv_angle_threshold')
        elif self.tab == 'PAINTER':
            layout.prop(self, 'painter_executable')
            layout.prop(self, 'painter_project_template')
            layout.prop(self, 'painter_port')
            row = layout.row(align=True)
            row.operator('mbt.painter_connect', text='Detect').action = 'DETECT'
            row.operator('mbt.painter_connect', text='Test Connection').action = 'TEST'
            row.operator('mbt.painter_connect', text='Launch / Connect').action = 'CONNECT'
            layout.label(text='Remote scripting executes code. Use only on a trusted machine.', icon='ERROR')
            layout.label(text='Client uses 127.0.0.1 / ::1 only. Keep the Painter port firewalled.')
            if context.scene and hasattr(context.scene, 'mbt_painter'):
                layout.label(text=context.scene.mbt_painter.report)
        else:
            layout.label(text="MBToolkit - personal hard surface workflow toolkit")
            if feature_manager.is_enabled('pie_menus'):
                layout.operator("mbt.rebuild_hotkeys", icon="FILE_REFRESH")
            



for _key, _label, _default, _paths in feature_manager.FEATURES:
    MBT_Preferences.__annotations__['enable_' + _key] = BoolProperty(
        name=_label, default=_default, update=feature_manager.changed,
        description=f'Load {_label}; disabled features are skipped on the next startup')


classes = (MBT_ModifierFavorite, MBT_ScriptFavorite, MBT_OT_modifier_favorite) + preferences_ui.classes + (sidebar_data.MBT_NPanelTab, MBT_Preferences)


def register():
    register_classes(classes)


def unregister():
    preferences_ui.cleanup()
    unregister_classes(classes)
