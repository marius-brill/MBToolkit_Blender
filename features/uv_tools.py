"""Compatibility operators for existing MBToolkit pies and shortcuts."""
import bpy
from bpy.props import FloatProperty
from ..core.registry import register_classes, unregister_classes
from . import uv_suite
from .uv_suite.operators import MeshPoll, execute_action


class MBT_OT_mark_seams_by_angle(MeshPoll, bpy.types.Operator):
    bl_idname = 'mbt.mark_seams_by_angle'
    bl_label = 'Mark Angle Seams'
    bl_options = {'REGISTER', 'UNDO'}
    angle_threshold: FloatProperty(name='Angle', default=66, min=0, max=180)

    def execute(self, context):
        return execute_action(self, context, 'SEAMS', self.angle_threshold)


class MBT_OT_find_connectivity(MeshPoll, bpy.types.Operator):
    bl_idname = 'mbt.find_connectivity'
    bl_label = 'Count UV Islands'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        return execute_action(self, context, 'COUNT')


class MBT_OT_pack_uvs(MeshPoll, bpy.types.Operator):
    bl_idname = 'mbt.pack_uvs'
    bl_label = 'Smart Pack UVs'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        return execute_action(self, context, 'PACK')


class MBT_OT_straighten_uvs(MeshPoll, bpy.types.Operator):
    bl_idname = 'mbt.straighten_uvs'
    bl_label = 'Straighten UVs'
    bl_description = 'Topology-aware quadrify or boundary rectify with quality checks'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        return execute_action(self, context, 'STRAIGHTEN')


classes = (MBT_OT_mark_seams_by_angle, MBT_OT_find_connectivity,
           MBT_OT_pack_uvs, MBT_OT_straighten_uvs)
draw = uv_suite.draw


def register():
    uv_suite.register()
    try:
        register_classes(classes)
    except Exception:
        uv_suite.unregister()
        raise


def unregister():
    try:
        unregister_classes(classes)
    finally:
        uv_suite.unregister()