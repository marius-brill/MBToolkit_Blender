"""Run any .py file from disk, straight from the N panel."""

import os
import sys
import traceback
import uuid

import bpy
from bpy.props import EnumProperty, StringProperty

from ..core.addon import get_prefs
from ..core.registry import register_classes, unregister_classes


def absolute_path(path):
    return os.path.abspath(bpy.path.abspath(path)) if path else ''


def path_key(path):
    return os.path.normcase(os.path.realpath(absolute_path(path))) if path else ''


def current_favorite(prefs, path):
    key = path_key(path)
    return next((item for item in prefs.script_favorites if path_key(item.path) == key), None) if key else None


def validate_path(path):
    resolved = absolute_path(path)
    if not resolved or os.path.splitext(resolved)[1].lower() != '.py':
        raise ValueError('Choose a Python (.py) script')
    if not os.path.isfile(resolved):
        raise ValueError(f'File not found: {resolved}')
    return resolved


def redraw(context):
    for window in context.window_manager.windows:
        for area in window.screen.areas:
            area.tag_redraw()


class MBT_OT_script_favorite(bpy.types.Operator):
    bl_idname = 'mbt.script_favorite'
    bl_label = 'Script Favorite'
    bl_description = 'Bookmark the current script, select a saved script, or manage favorites'

    action: EnumProperty(items=[(x, x.title(), '') for x in ('TOGGLE', 'SELECT', 'REMOVE', 'UP', 'DOWN')])
    uid: StringProperty(options={'SKIP_SAVE'})

    @classmethod
    def description(cls, context, properties):
        if properties.action == 'SELECT':
            prefs = get_prefs(context)
            item = next((f for f in prefs.script_favorites if f.uid == properties.uid), None) if prefs else None
            return f'Select without running: {item.path}' if item else 'Select a saved script without running it'
        if properties.action == 'TOGGLE':
            return 'Add or remove the current script from favorites (does not copy or run the file)'
        return f'{properties.action.title()} the selected bookmark; the script file is not changed'

    def execute(self, context):
        prefs = get_prefs(context)
        if prefs is None:
            return {'CANCELLED'}
        favorites = prefs.script_favorites
        if self.action == 'TOGGLE':
            item = current_favorite(prefs, context.scene.mbt.script_path)
            if item is not None:
                index = next(i for i, f in enumerate(favorites) if f.uid == item.uid)
                favorites.remove(index)
            else:
                try:
                    path = validate_path(context.scene.mbt.script_path)
                except (ValueError, OSError) as exc:
                    self.report({'ERROR'}, str(exc))
                    return {'CANCELLED'}
                item = favorites.add()
                item.uid = uuid.uuid4().hex
                item.label = os.path.splitext(os.path.basename(path))[0]
                item.path = path
                prefs.script_favorite_index = len(favorites) - 1
        else:
            index = next((i for i, f in enumerate(favorites) if f.uid == self.uid), -1)
            if index < 0:
                self.report({'WARNING'}, 'Favorite no longer exists')
                return {'CANCELLED'}
            if self.action == 'SELECT':
                context.scene.mbt.script_path = favorites[index].path
                prefs.script_favorite_index = index
                if not os.path.isfile(favorites[index].path):
                    self.report({'WARNING'}, 'Script is missing. Relink it in Manage Favorites.')
                redraw(context)
                return {'FINISHED'}
            if self.action == 'REMOVE':
                favorites.remove(index)
            else:
                target = index + (-1 if self.action == 'UP' else 1)
                if not 0 <= target < len(favorites):
                    return {'CANCELLED'}
                favorites.move(index, target)
                prefs.script_favorite_index = target
        prefs.script_favorite_index = min(prefs.script_favorite_index, max(0, len(favorites) - 1))
        context.preferences.is_dirty = True
        redraw(context)
        return {'FINISHED'}


class MBT_OT_script_favorite_edit(bpy.types.Operator):
    bl_idname = 'mbt.script_favorite_edit'
    bl_label = 'Edit / Relink Script Favorite'
    bl_description = 'Rename this bookmark or locate its script; the original file is not changed'

    uid: StringProperty(options={'SKIP_SAVE'})
    label: StringProperty(name='Name')
    path: StringProperty(name='Script', subtype='FILE_PATH')

    def invoke(self, context, event):
        prefs = get_prefs(context)
        item = next((f for f in prefs.script_favorites if f.uid == self.uid), None) if prefs else None
        if item is None:
            return {'CANCELLED'}
        self.label, self.path = item.label, item.path
        return context.window_manager.invoke_props_dialog(self, width=460)

    def draw(self, context):
        self.layout.prop(self, 'label')
        self.layout.prop(self, 'path')

    def execute(self, context):
        prefs = get_prefs(context)
        item = next((f for f in prefs.script_favorites if f.uid == self.uid), None) if prefs else None
        if item is None:
            return {'CANCELLED'}
        try:
            path = validate_path(self.path)
        except (ValueError, OSError) as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        duplicate = current_favorite(prefs, path)
        if duplicate is not None and duplicate.uid != self.uid:
            self.report({'ERROR'}, 'This script is already a favorite')
            return {'CANCELLED'}
        old_key = path_key(item.path)
        item.label = self.label.strip() or os.path.splitext(os.path.basename(path))[0]
        item.path = path
        if path_key(context.scene.mbt.script_path) == old_key:
            context.scene.mbt.script_path = path
        context.preferences.is_dirty = True
        redraw(context)
        return {'FINISHED'}


class MBT_MT_script_favorites(bpy.types.Menu):
    bl_label = 'Script Favorites'

    def draw(self, context):
        layout = self.layout
        prefs = get_prefs(context)
        if prefs is None:
            return
        favorites = prefs.script_favorites
        selected = path_key(context.scene.mbt.script_path)
        labels = [f.label for f in favorites]
        if not favorites:
            layout.label(text='Choose a script and click the star', icon='INFO')
        for item in favorites:
            label = item.label
            if labels.count(label) > 1:
                label = f'{label} — {os.path.dirname(item.path)}'
            icon = 'ERROR' if not os.path.isfile(item.path) else ('CHECKMARK' if path_key(item.path) == selected else 'FILE_SCRIPT')
            op = layout.operator('mbt.script_favorite', text=label, icon=icon)
            op.action, op.uid = 'SELECT', item.uid
        layout.separator()
        layout.operator_context = 'INVOKE_DEFAULT'
        layout.operator('mbt.script_favorites_manage', text='Manage Favorites…', icon='PREFERENCES')


class MBT_UL_script_favorites(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        layout.label(text=item.label, icon='FILE_SCRIPT' if os.path.isfile(item.path) else 'ERROR')


class MBT_OT_script_favorites_manage(bpy.types.Operator):
    bl_idname = 'mbt.script_favorites_manage'
    bl_label = 'Manage Script Favorites'
    bl_description = 'Rename, relink, reorder or remove script bookmarks'

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=500)

    def draw(self, context):
        layout = self.layout
        prefs = get_prefs(context)
        if prefs is None:
            return
        favorites = prefs.script_favorites
        if favorites:
            row = layout.row()
            row.template_list('MBT_UL_script_favorites', '', prefs, 'script_favorites', prefs, 'script_favorite_index', rows=5)
            index = min(prefs.script_favorite_index, len(favorites) - 1)
            item = favorites[index]
            buttons = row.column(align=True)
            for action, icon, enabled in (('UP', 'TRIA_UP', index > 0), ('DOWN', 'TRIA_DOWN', index < len(favorites) - 1), ('REMOVE', 'REMOVE', True)):
                button = buttons.row(align=True)
                button.enabled = enabled
                op = button.operator('mbt.script_favorite', text='', icon=icon)
                op.action, op.uid = action, item.uid
            layout.label(text=item.path, icon='FILE_SCRIPT')
            if not os.path.isfile(item.path):
                layout.label(text='File missing. Use Edit / Relink to locate it.', icon='ERROR')
            layout.operator_context = 'INVOKE_DEFAULT'
            layout.operator('mbt.script_favorite_edit', icon='FILE_FOLDER').uid = item.uid
        else:
            layout.label(text='No favorites yet. Choose a script and click the star.', icon='INFO')
        layout.separator()
        layout.label(text='Bookmarks reference files; scripts are not copied or run.')
        if not context.preferences.use_preferences_save:
            layout.label(text='Auto-save is off. Save Preferences to keep changes.', icon='INFO')
            layout.operator('wm.save_userpref', text='Save Preferences', icon='FILE_TICK')

    def execute(self, context):
        return {'FINISHED'}


class MBT_OT_script_run(bpy.types.Operator):
    bl_idname = "mbt.script_run"
    bl_label = "Run Script"
    bl_description = "Run the selected script (re-read from disk every time)"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return bool(context.scene.mbt.script_path)

    def execute(self, context):
        path = os.path.abspath(bpy.path.abspath(context.scene.mbt.script_path))
        if not os.path.isfile(path):
            self.report({"ERROR"}, f"File not found: {path}")
            return {"CANCELLED"}

        try:
            with open(path, "r", encoding="utf-8-sig") as f:
                source = f.read()
        except (OSError, UnicodeError) as exc:
            self.report({'ERROR'}, f'Cannot read script: {exc}')
            return {'CANCELLED'}

        script_dir = os.path.dirname(path)
        added = script_dir not in sys.path
        if added:
            sys.path.insert(0, script_dir)  # lets scripts import their neighbours
        try:
            exec(compile(source, path, "exec"), {"__name__": "__main__", "__file__": path})
        except Exception as exc:
            traceback.print_exc()
            self.report({"ERROR"}, f"{type(exc).__name__}: {exc} (see system console)")
            return {"CANCELLED"}
        finally:
            if added and script_dir in sys.path:
                sys.path.remove(script_dir)

        self.report({"INFO"}, f"Ran {os.path.basename(path)}")
        return {"FINISHED"}


classes = (MBT_OT_script_favorite, MBT_OT_script_favorite_edit,
           MBT_MT_script_favorites, MBT_UL_script_favorites,
           MBT_OT_script_favorites_manage, MBT_OT_script_run)


def draw(layout, context):
    props = context.scene.mbt
    prefs = get_prefs(context)
    favorite = current_favorite(prefs, props.script_path) if prefs else None
    row = layout.row(align=True)
    row.menu('MBT_MT_script_favorites', text=favorite.label if favorite is not None else 'Favorites', icon='SOLO_ON')
    row.operator_context = 'INVOKE_DEFAULT'
    row.operator('mbt.script_favorites_manage', text='', icon='PREFERENCES')
    row = layout.row(align=True)
    row.prop(props, "script_path", text="")
    star = row.row(align=True)
    star.enabled = prefs is not None and bool(props.script_path)
    star.operator('mbt.script_favorite', text='', icon='SOLO_ON' if favorite is not None else 'SOLO_OFF', depress=favorite is not None).action = 'TOGGLE'
    if props.script_path and not os.path.isfile(absolute_path(props.script_path)):
        layout.label(text='Script missing. Choose a file or relink the favorite.', icon='ERROR')
    layout.operator("mbt.script_run", icon="PLAY")


def register():
    register_classes(classes)


def unregister():
    unregister_classes(classes)
