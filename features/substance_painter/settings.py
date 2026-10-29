"""Blend-file-local settings for the Painter handoff."""
import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, PointerProperty, StringProperty
from ...core.registry import register_classes, unregister_classes


BAKE_MAPS = (
    ('NORMAL', 'Normal'), ('AO', 'Ambient Occlusion'), ('CURVATURE', 'Curvature'),
    ('POSITION', 'Position'), ('THICKNESS', 'Thickness'),
    ('WORLD_SPACE_NORMAL', 'World Space Normal'), ('ID', 'ID'),
)


class MBT_PainterSettings(bpy.types.PropertyGroup):
    low_collection: PointerProperty(name='Low Poly', type=bpy.types.Collection)
    high_collection: PointerProperty(name='High Poly', type=bpy.types.Collection)
    project_name: StringProperty(name='Project', default='Asset')
    project_template: StringProperty(name='Project Template', subtype='FILE_PATH',
        description='Optional Painter .spt template; used only when creating a project')
    project_file: StringProperty(name='Associated Project', subtype='FILE_PATH', options={'HIDDEN'})
    advanced: BoolProperty(name='Advanced / Troubleshooting', default=False)
    bake_settings: BoolProperty(name='Bake Settings', default=False)
    export_config: StringProperty(name='Custom Export Mapping', subtype='FILE_PATH',
        description='Optional JSON mapping for an existing Painter export preset; empty uses automatic MBToolkit PBR')
    output_dir: StringProperty(name='Output Folder', subtype='DIR_PATH')
    resolution: EnumProperty(name='Resolution', items=tuple(
        (str(size), str(size), '') for size in (512, 1024, 2048, 4096, 8192)), default='2048')
    bake_maps: EnumProperty(name='Bake Maps', options={'ENUM_FLAG'}, items=tuple(
        (key, label, '', 1 << index) for index, (key, label) in enumerate(BAKE_MAPS)),
        default={'NORMAL', 'AO', 'CURVATURE'})
    export_preset: EnumProperty(name='Texture Layout', items=(
        ('MBT_PBR', 'MBT PBR — Unpacked PNG',
         'Local filename contract, not an installed Painter export preset'),), default='MBT_PBR')
    normal_format: EnumProperty(name='Normal Format', items=(
        ('OPENGL', 'OpenGL (+Y)', ''), ('DIRECTX', 'DirectX (-Y)', 'Invert green on import')),
        default='OPENGL')
    replace_materials: BoolProperty(name='Replace Existing Materials', default=False,
        description='Replace all material slots on each low-poly object; otherwise protect existing materials')
    front_distance: FloatProperty(name='Front Distance', default=0.01, min=0, max=1000)
    rear_distance: FloatProperty(name='Rear Distance', default=0.01, min=0, max=1000)
    relative_distance: BoolProperty(name='Relative to Bounding Box', default=True,
        description='Distances are bounding-box fractions; otherwise Painter scene units (centimeters)')
    antialiasing: EnumProperty(name='Antialiasing', items=(('None', 'None', ''),
        ('Supersampling 4x', '2×2', ''), ('Supersampling 16x', '4×4', '')), default='Supersampling 4x')
    id_source: EnumProperty(name='ID Source', items=(('Material Color', 'Material Color', ''),
        ('Vertex Color', 'Vertex Color', '')), default='Material Color')
    last_job: StringProperty(name='Job Manifest', subtype='FILE_PATH',
        description='Prepared job.json used for importing; may also point to an earlier job')
    report: StringProperty(name='Last Result')
    preparation_timings: StringProperty(name='Preparation Timings', options={'SKIP_SAVE'},
        description='JSON timings for preparation steps, excluding time between UI ticks')


classes = (MBT_PainterSettings,)


def register():
    register_classes(classes)
    bpy.types.Scene.mbt_painter = PointerProperty(type=MBT_PainterSettings)
    bpy.types.Object.mbt_bake_group = StringProperty(name='Bake Group',
        description='Shared group for any number of low and high meshes; overrides automatic matching')
    bpy.types.Object.mbt_bake_target = PointerProperty(name='Bake Target', type=bpy.types.Object,
        poll=lambda self, obj: obj.type == 'MESH' and obj != self,
        description='Stored low target takes priority on each bake; clear to re-run name/surface matching')


def unregister():
    del bpy.types.Object.mbt_bake_group
    del bpy.types.Object.mbt_bake_target
    del bpy.types.Scene.mbt_painter
    unregister_classes(classes)