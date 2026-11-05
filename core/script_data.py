"""Persistent script bookmarks; independent of the optional runner runtime."""

import bpy
from bpy.props import StringProperty


def changed(self, context):
    if context is not None:
        context.preferences.is_dirty = True


class MBT_ScriptFavorite(bpy.types.PropertyGroup):
    uid: StringProperty()
    label: StringProperty(name='Name', update=changed)
    path: StringProperty(name='Script', subtype='FILE_PATH', update=changed)