"""Optional vertex-color setter, channel editor and non-destructive inspector."""

import bpy
from bpy.props import PointerProperty

from ...core.registry import register_classes, unregister_classes
from . import operators, preview
from .settings import MBT_VertexColorSettings
from .ui import draw


classes = (MBT_VertexColorSettings,) + operators.classes


def register():
    register_classes(classes)
    try:
        bpy.types.Scene.mbt_vertex_color = PointerProperty(type=MBT_VertexColorSettings)
        preview.register()
    except Exception:
        preview.unregister()
        if hasattr(bpy.types.Scene, 'mbt_vertex_color'):
            del bpy.types.Scene.mbt_vertex_color
        unregister_classes(classes)
        raise


def unregister():
    preview.unregister()
    if hasattr(bpy.types.Scene, 'mbt_vertex_color'):
        del bpy.types.Scene.mbt_vertex_color
    unregister_classes(classes)