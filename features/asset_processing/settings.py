"""Persistent pointer-based asset relationships, separate from bake settings."""
import bpy
from bpy.props import BoolProperty, CollectionProperty, EnumProperty, FloatProperty, IntProperty, PointerProperty, StringProperty
from ...core.registry import register_classes, unregister_classes


def mesh_reference(self, obj):
    return obj.type == 'MESH'


class MBT_AssetCollectionIdentity(bpy.types.PropertyGroup):
    collection: PointerProperty(type=bpy.types.Collection)
    identity: StringProperty()


class MBT_AssetStage(bpy.types.PropertyGroup):
    name: StringProperty()
    state: StringProperty()
    reason: StringProperty()


class MBT_AssetObjectReference(bpy.types.PropertyGroup):
    mesh: PointerProperty(type=bpy.types.Object, poll=mesh_reference)


class MBT_AssetIssue(bpy.types.PropertyGroup):
    mesh: PointerProperty(type=bpy.types.Object)
    component_id: StringProperty()
    component_name: StringProperty()
    stage: StringProperty()
    severity: EnumProperty(items=(('ERROR', 'Error', ''), ('WARNING', 'Warning', ''), ('INFO', 'Info', '')))
    reason: StringProperty()
    action: StringProperty()


class MBT_AssetComponent(bpy.types.PropertyGroup):
    component_id: StringProperty(options={'HIDDEN'})
    stage_baselines: StringProperty(options={'HIDDEN'})
    stages: CollectionProperty(type=MBT_AssetStage, options={'SKIP_SAVE'})
    source: PointerProperty(name='Source', type=bpy.types.Object, poll=mesh_reference)
    low: PointerProperty(name='Existing Low', type=bpy.types.Object, poll=mesh_reference)
    highs: CollectionProperty(type=MBT_AssetObjectReference)
    generated_high: PointerProperty(type=bpy.types.Object, options={'HIDDEN'})
    high_mode: EnumProperty(name='High Poly', items=(
        ('DYNABOOL', 'DynaBool', 'Generate from an evaluated source snapshot'),
        ('CUSTOM', 'Custom High', 'Use assigned artist meshes without modifying them'),
        ('DISABLED', 'Disabled', 'Prepare a low only')), default='DYNABOOL')
    subdivision: IntProperty(name='Subdivision', default=2, min=0, max=5)
    crease_angle: FloatProperty(name='Crease Angle', default=50, min=0, max=180)
    remesh: BoolProperty(name='Remesh', default=True)
    automatic_resolution: BoolProperty(name='Automatic Resolution', default=True,
        description='Choose and refine resolution automatically; disable to use the manual local voxel size')
    generation_state: StringProperty(default='Not generated', options={'HIDDEN'})
    voxel_size: FloatProperty(name='Voxel Size (local)', default=0.008, min=0.0001)
    smoothing: IntProperty(name='Smooth Iterations', default=0, min=0, max=20)
    detail_tolerance: FloatProperty(name='Detail Tolerance', default=0.01, min=0.0001, max=0.1,
        description='Maximum sampled local surface deviation as a fraction of the source diagonal; lower needs more memory')
    max_faces: IntProperty(name='Face Budget', default=1000000, min=100, max=10000000)
    max_work_gib: FloatProperty(name='Work Allowance (GiB estimate)', default=8.0, min=0, max=1024,
        description='Limit for heuristic sparse-band work, not measured RAM. 0 disables this guard and risks excessive memory use; Face Budget is separate')
    high_signature: StringProperty(options={'HIDDEN'})
    generation_report: StringProperty(options={'HIDDEN'})
    texture_set_id: StringProperty(options={'HIDDEN'})
    texture_collection: PointerProperty(name='Texture Set', type=bpy.types.Collection)
    uv_locked: BoolProperty(name='Protect UV Layout', default=True,
        description='Block application of UV proposals; preview and validation remain available')
    uv_mode: EnumProperty(name='UV Mode', items=(
        ('PRESERVE', 'Preserve', 'Validate only; never modify seams or UVs'),
        ('ASSISTED', 'Assisted', 'Preview added seams, unwrap and joint packing before applying'),
        ('AUTOMATIC', 'Automatic', 'Prepare and apply UVs on unlocked derived lows')), default='ASSISTED')
    uv_angle: FloatProperty(name='Seam Angle', default=66, min=1, max=179)
    uv_gap: FloatProperty(name='Island Gap (px)', default=8, min=0, max=1024)
    uv_border: FloatProperty(name='Tile Border (px)', default=8, min=0, max=1024)
    uv_allow_overlap: BoolProperty(name='Allow UV Overlap', default=False,
        description='Permit intentional stacks during validation; generated proposals still pack without overlaps')
    uv_preview: PointerProperty(type=bpy.types.Object, options={'HIDDEN'})
    uv_baseline: StringProperty(options={'HIDDEN'})
    uv_proposal_settings: StringProperty(options={'HIDDEN'})
    uv_batch: StringProperty(options={'HIDDEN'})
    uv_reference: StringProperty(options={'HIDDEN'})
    uv_report: StringProperty(options={'HIDDEN'})


class MBT_Asset(bpy.types.PropertyGroup):
    asset_id: StringProperty(options={'HIDDEN'})
    stage_baselines: StringProperty(options={'HIDDEN'})
    stages: CollectionProperty(type=MBT_AssetStage, options={'SKIP_SAVE'})
    outdated_report: StringProperty(options={'SKIP_SAVE'})
    components: CollectionProperty(type=MBT_AssetComponent)
    active_component: IntProperty(default=0, min=0, options={'SKIP_SAVE'})
    generated_collection: PointerProperty(type=bpy.types.Collection, options={'HIDDEN'})
    issues: CollectionProperty(type=MBT_AssetIssue)
    issue_index: IntProperty(default=0, min=0, options={'SKIP_SAVE'})
    validation_report: StringProperty(options={'SKIP_SAVE'})


class MBT_AssetProcessingSettings(bpy.types.PropertyGroup):
    schema_version: IntProperty(default=1, options={'HIDDEN'})
    assets: CollectionProperty(type=MBT_Asset)
    collection_ids: CollectionProperty(type=MBT_AssetCollectionIdentity)
    active_asset: IntProperty(default=0, min=0, options={'SKIP_SAVE'})
    source_collection: PointerProperty(name='Source Collection', type=bpy.types.Collection)
    show_collection: BoolProperty(name='Create from Collection', default=False, options={'SKIP_SAVE'})
    show_component: BoolProperty(name='Component Details', default=False, options={'SKIP_SAVE'})
    report: StringProperty(options={'SKIP_SAVE'})
    show_processing: BoolProperty(name='Generation Settings', default=False, options={'SKIP_SAVE'})
    show_inspector: BoolProperty(name='Inspector', default=False, options={'SKIP_SAVE'})
    show_uv: BoolProperty(name='UV Settings', default=False, options={'SKIP_SAVE'})
    show_validation: BoolProperty(name='Validation', default=False, options={'SKIP_SAVE'})
    last_export: StringProperty(name='Last Export', subtype='DIR_PATH')
    export_low: BoolProperty(name='Low Poly', default=True)
    export_high: BoolProperty(name='High Poly', default=True)


def active_asset(settings):
    index = settings.active_asset
    return settings.assets[index] if 0 <= index < len(settings.assets) else None


def active_component(asset):
    index = asset.active_component if asset else -1
    return asset.components[index] if asset and 0 <= index < len(asset.components) else None


classes = (MBT_AssetCollectionIdentity, MBT_AssetStage, MBT_AssetObjectReference, MBT_AssetIssue, MBT_AssetComponent, MBT_Asset, MBT_AssetProcessingSettings)


def register():
    register_classes(classes)
    bpy.types.Scene.mbt_assets = PointerProperty(type=MBT_AssetProcessingSettings)


def unregister():
    del bpy.types.Scene.mbt_assets
    unregister_classes(classes)