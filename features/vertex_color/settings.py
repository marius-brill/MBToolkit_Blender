"""Persistent user choices; preview and edit sessions stay in runtime storage."""

import bpy
from bpy.props import BoolProperty, BoolVectorProperty, EnumProperty, FloatProperty, FloatVectorProperty, StringProperty


CHANNELS = tuple((channel, channel, f'{channel} component') for channel in 'RGBA')
DOMAINS = (('CORNER', 'Face Corner', 'Independent colors across face boundaries'),
           ('POINT', 'Vertex', 'One color per vertex; adjacent faces share values'))
STORAGE = (('BYTE_COLOR', 'Byte Color', 'Compact sRGB storage with 8-bit precision'),
           ('FLOAT_COLOR', 'Float Color', 'Scene-linear floating-point precision'))


class MBT_VertexColorSettings(bpy.types.PropertyGroup):
    color: FloatVectorProperty(name='Color', subtype='COLOR', size=4,
        default=(1, 1, 1, 1), min=0, max=1, description='Last fill color in scene-linear space')
    target: EnumProperty(name='Target', items=(
        ('ACTIVE', 'Active Object', 'Edit the active mesh datablock'),
        ('SELECTED', 'Selected Objects', 'Edit each selected mesh once; matching attributes required')))
    affect: EnumProperty(name='Affect', items=(
        ('ALL', 'All Geometry', 'Include all elements, including hidden geometry'),
        ('SELECTED', 'Selected Geometry', 'Edit Mode selection or Vertex Paint selection mask only')))
    write_mask: BoolVectorProperty(name='Write', size=4, default=(True, True, True, False),
        description='Enabled components can change; disabled components are preserved')
    space: EnumProperty(name='Values', items=(
        ('LINEAR', 'Linear', 'Numeric channel operations use scene-linear RGB'),
        ('SRGB', 'sRGB', 'Numeric channel operations use sRGB RGB; alpha is never gamma converted')))
    channel: EnumProperty(name='Channel', items=CHANNELS)
    destination: EnumProperty(name='To', items=CHANNELS, default='A')
    value: FloatProperty(name='Value', default=1, min=0, max=1)
    tools: BoolProperty(name='Channel Tools', default=False)
    attributes: BoolProperty(name='Attribute Settings', default=False)
    new_name: StringProperty(name='Name', default='Color')
    domain: EnumProperty(name='Domain', items=DOMAINS)
    storage: EnumProperty(name='Storage', items=STORAGE)
    status: StringProperty(name='Inspection', options={'SKIP_SAVE'})