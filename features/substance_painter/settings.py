"""Blend-file-local settings for the Painter handoff."""
import bpy
from bpy.props import BoolProperty, CollectionProperty, EnumProperty, FloatProperty, IntProperty, PointerProperty, StringProperty
from ...core.registry import register_classes, unregister_classes


BAKE_MAPS = (
    ('NORMAL', 'Normal'), ('AO', 'Ambient Occlusion'), ('CURVATURE', 'Curvature'),
    ('POSITION', 'Position'), ('THICKNESS', 'Thickness'),
    ('WORLD_SPACE_NORMAL', 'World Space Normal'), ('ID', 'ID'),
)


SET_FIELDS = ('low_collection', 'high_collection', 'resolution', 'bake_maps',
              'auto_distances', 'front_distance', 'rear_distance', 'relative_distance', 'antialiasing', 'id_source', 'projection_normals')
_syncing = False


def save_active(self, context):
    if not _syncing:
        from .texture_sets import color_collections
        color_collections(self)
    if not _syncing and self.texture_sets and 0 <= self.active_texture_set < len(self.texture_sets):
        entry = self.texture_sets[self.active_texture_set]
        for field in SET_FIELDS:
            setattr(entry, field, getattr(self, field))
        parent = entry.collection
        if parent and not parent.library:
            for child in (entry.low_collection, entry.high_collection):
                if (child and not child.library and child != parent
                        and parent not in child.children_recursive and child.name not in parent.children):
                    parent.children.link(child)
                    if context and child.name in context.scene.collection.children:
                        context.scene.collection.children.unlink(child)


def select_active(self, context):
    global _syncing
    if _syncing:
        return
    _syncing = True
    try:
        if self.texture_sets and 0 <= self.active_texture_set < len(self.texture_sets):
            entry = self.texture_sets[self.active_texture_set]
            self.texture_collection = entry.collection
            for field in SET_FIELDS:
                setattr(self, field, getattr(entry, field))
            from .texture_sets import color_collections
            color_collections(entry)
        else:
            self.texture_collection = None
    finally:
        _syncing = False


def select_collection(self, context):
    if _syncing:
        return
    if self.texture_collection is None:
        select_active(self, context)
        return
    from .texture_sets import add_set
    for index, entry in enumerate(self.texture_sets):
        if entry.collection == self.texture_collection:
            self.active_texture_set = index
            return
    try:
        add_set(context, self.texture_collection)
    except ValueError as error:
        self.report = str(error)
        select_active(self, context)


def manual_target(self, context):
    # Any user assignment, including assigning the same target, pins the choice.
    self.mbt_bake_auto_target = None


from .issues import MBT_PainterIssue, MBT_PainterIssueTarget


class MBT_PainterSettings(bpy.types.PropertyGroup):
    ui_tab: EnumProperty(name='Baking Tab', items=(
        ('MODEL', 'Model', 'Asset and component records; source meshes remain unchanged'),
        ('BAKE', 'Bake', 'Complete Painter setup, baking and texture workflow'),
        ('EXPORT', 'Export', 'Export the active asset as Painter-ready FBX without launching Painter')),
        default='BAKE')
    issue_rows: CollectionProperty(type=MBT_PainterIssue)
    issue_index: IntProperty(default=0, min=0, options={'SKIP_SAVE'})
    issue_blocking_only: BoolProperty(default=False, options={'SKIP_SAVE'})
    texture_collection: PointerProperty(name='Texture Set', type=bpy.types.Collection, update=select_collection)
    active_texture_set: IntProperty(default=0, min=0, update=select_active)
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
    auto_distances: BoolProperty(name='Automatic Cage Distances', default=True,
        description='Estimate front/rear reach from evaluated matched geometry at preparation; uses absolute centimeters')
    front_distance: FloatProperty(name='Front Distance', default=0.01, min=0, max=1e12)
    projection_normals: EnumProperty(name='Projection Normals', items=(
        ('AVERAGED', 'Averaged — Edge Coverage', 'Explicitly average projection normals; raised detail can skew'),
        ('FACE', 'Mesh Normals — No Averaging', 'Use imported mesh normals, not necessarily face-perpendicular rays; may miss detail at hard edges')),
        default='AVERAGED')
    rear_distance: FloatProperty(name='Rear Distance', default=0.01, min=0, max=1e12)
    relative_distance: BoolProperty(name='Relative to Bounding Box', default=True,
        description='Distances are bounding-box fractions; otherwise Painter scene units (centimeters)')
    antialiasing: EnumProperty(name='Antialiasing', items=(('None', 'None', ''),
        ('Supersampling 4x', '2×2', ''), ('Supersampling 16x', '4×4', '')), default='Supersampling 4x')
    id_source: EnumProperty(name='ID Source', items=(('Material Color', 'Material Color', ''),
        ('Vertex Color', 'Vertex Color', '')), default='Material Color')
    last_job: StringProperty(name='Job Manifest', subtype='FILE_PATH',
        description='Prepared job.json used for importing; may also point to an earlier job')
    report: StringProperty(name='Last Result')
    matching_report: StringProperty(name='Matching Issues', options={'HIDDEN'})
    preparation_timings: StringProperty(name='Preparation Timings', options={'SKIP_SAVE'},
        description='JSON timings for preparation steps, excluding time between UI ticks')
    projection_threshold: FloatProperty(name='Skew Warning (px)', default=1.0, min=0.01, max=1000,
        description='Estimated displacement threshold; analysis does not apply correction')
    projection_report: StringProperty(name='Projection Analysis', options={'SKIP_SAVE'})


class MBT_PainterTextureSet(bpy.types.PropertyGroup):
    collection: PointerProperty(name='Texture Set', type=bpy.types.Collection)
    set_id: StringProperty(options={'HIDDEN'})


# Keep the active-set UI fields compatible with existing scripts and blend files.
# The collection entries own the persisted values; these fields mirror the selection.
for _field in SET_FIELDS:
    _property = MBT_PainterSettings.__annotations__[_field]
    MBT_PainterTextureSet.__annotations__[_field] = _property.function(**_property.keywords)
    MBT_PainterSettings.__annotations__[_field] = _property.function(**dict(_property.keywords, update=save_active))
MBT_PainterSettings.__annotations__['texture_sets'] = CollectionProperty(type=MBT_PainterTextureSet)

classes = (MBT_PainterIssueTarget, MBT_PainterIssue, MBT_PainterTextureSet, MBT_PainterSettings)


def register():
    register_classes(classes)
    bpy.types.Scene.mbt_painter = PointerProperty(type=MBT_PainterSettings)
    bpy.types.Object.mbt_bake_group = StringProperty(name='Bake Group',
        description='Shared group for any number of low and high meshes; overrides automatic matching')
    bpy.types.Object.mbt_bake_target = PointerProperty(name='Bake Target', type=bpy.types.Object,
        poll=lambda self, obj: obj.type == 'MESH' and obj != self,
        update=manual_target,
        description='Stored low target takes priority on each bake; clear to re-run name/surface matching')
    bpy.types.Object.mbt_bake_auto_target = PointerProperty(type=bpy.types.Object, options={'HIDDEN'})


def unregister():
    del bpy.types.Object.mbt_bake_group
    del bpy.types.Object.mbt_bake_target
    del bpy.types.Object.mbt_bake_auto_target
    del bpy.types.Scene.mbt_painter
    unregister_classes(classes)