"""Metadata-only asset editing. Never alter source meshes or legacy bake setup."""
import uuid
import bpy
from bpy.props import EnumProperty
from ...core.registry import register_classes, unregister_classes
from .settings import active_asset, active_component


def meshes(objects):
    return sorted((obj for obj in objects if obj.type == 'MESH'), key=lambda obj: obj.name)


def add_components(asset, objects):
    existing = {component.source for component in asset.components}
    added = 0
    for obj in objects:
        if obj in existing:
            continue
        component = asset.components.add()
        component.name = obj.name
        component.component_id = str(uuid.uuid4())
        component.source = obj
        existing.add(obj)
        added += 1
    return added


def create_asset(settings, name, objects):
    asset = settings.assets.add()
    asset.name = name
    asset.asset_id = str(uuid.uuid4())
    add_components(asset, objects)
    settings.active_asset = len(settings.assets) - 1
    return asset


def adopt(context):
    """Read existing associations without migrating sets or running auto matching."""
    from ..substance_painter.texture_sets import entries
    painter = context.scene.mbt_painter
    sets = entries(painter)
    if not 0 <= painter.active_texture_set < len(sets):
        raise ValueError('Choose an active texture set in Bake first')
    entry = sets[painter.active_texture_set]
    lows = meshes(entry.low_collection.all_objects) if entry.low_collection else []
    highs = meshes(entry.high_collection.all_objects) if entry.high_collection else []
    if not lows:
        raise ValueError('The active texture set has no low-poly meshes')
    settings = context.scene.mbt_assets
    collection = getattr(entry, 'collection', None)
    set_id = getattr(entry, 'set_id', '')
    # Identical adoption is idempotent, including legacy setups without set IDs.
    for asset in settings.assets:
        for component in asset.components:
            if component.low in lows:
                raise ValueError('This bake setup is already represented by an asset')
    asset = create_asset(settings, collection.name if collection else 'Existing Bake Setup', lows)
    assigned = set()
    for component in asset.components:
        component.high_mode = 'CUSTOM'
        component.low = component.source
        from .uv import layout_signature
        component.uv_reference = layout_signature(component.low.data)
        component.texture_set_id = set_id
        component.texture_collection = collection
        group = component.low.mbt_bake_group.strip()
        for high in highs:
            high_group = high.mbt_bake_group.strip()
            explicit = high.mbt_bake_target
            manual = explicit is not None and explicit != high.mbt_bake_auto_target
            if (high_group and group == high_group) or (not high_group and manual and explicit == component.low):
                component.highs.add().mesh = high
                assigned.add(high)
    return len(lows), len(highs) - len(assigned)


class MBT_OT_asset_edit(bpy.types.Operator):
    bl_idname = 'mbt.asset_edit'
    bl_label = 'Edit Asset Records'
    bl_description = 'Edit asset metadata only; keep all objects, UVs, materials and bake settings unchanged'
    bl_options = {'REGISTER', 'UNDO'}

    action: EnumProperty(items=(
        ('CREATE', 'Create from Selection', 'Create one component per selected mesh'),
        ('COLLECTION', 'Create from Collection', 'Reference meshes recursively without moving them'),
        ('ADOPT', 'Adopt Active Bake Setup', 'Reference existing lows and explicitly assigned highs without changing the setup'),
        ('ADD', 'Add Selected', 'Add selected meshes to the active asset; skip existing sources'),
        ('REMOVE_ASSET', 'Remove Asset Record', 'Keep all objects and bake settings'),
        ('REMOVE_COMPONENT', 'Remove Component Record', 'Keep its objects and bake settings')))

    @classmethod
    def poll(cls, context):
        from ..substance_painter import runtime
        return (context.scene is not None and hasattr(context.scene, 'mbt_assets')
                and context.mode == 'OBJECT' and not runtime.busy())

    def execute(self, context):
        settings = context.scene.mbt_assets
        asset = active_asset(settings)
        from . import uv, preview
        try:
            if self.action == 'ADOPT':
                count, unresolved = adopt(context)
                settings.report = f'Adopted {count} lows; {unresolved} highs have no explicit link.'
            elif self.action in {'CREATE', 'COLLECTION', 'ADD'}:
                collection = settings.source_collection
                objects = meshes(collection.all_objects if self.action == 'COLLECTION' and collection
                                 else [] if self.action == 'COLLECTION' else context.selected_objects)
                if not objects:
                    raise ValueError('Choose a collection with meshes' if self.action == 'COLLECTION' else 'Select at least one mesh')
                if self.action == 'ADD':
                    if asset is None:
                        raise ValueError('Create or select an asset first')
                    count = add_components(asset, objects)
                    settings.report = f'Added {count} components; existing sources skipped.'
                else:
                    name = collection.name if self.action == 'COLLECTION' else objects[0].name
                    create_asset(settings, name, objects)
                    settings.report = f'Created asset with {len(objects)} components. Sources unchanged.'
            elif self.action == 'REMOVE_ASSET':
                if asset is None:
                    raise ValueError('Select an asset first')
                preview.restore()
                for component in asset.components:
                    uv.clear_component(component)
                settings.assets.remove(settings.active_asset)
                settings.active_asset = max(0, min(settings.active_asset, len(settings.assets) - 1))
                settings.report = 'Asset record removed. All objects kept.'
            else:
                if active_component(asset) is None:
                    raise ValueError('Select a component first')
                preview.restore()
                uv.clear_component(active_component(asset))
                asset.components.remove(asset.active_component)
                asset.active_component = max(0, min(asset.active_component, len(asset.components) - 1))
                settings.report = 'Component record removed. All objects kept.'
        except ValueError as error:
            self.report({'WARNING'}, str(error))
            return {'CANCELLED'}
        return {'FINISHED'}


class MBT_OT_asset_process(bpy.types.Operator):
    bl_idname = 'mbt.asset_process'
    bl_label = 'Process Asset'
    bl_options = {'REGISTER', 'UNDO'}
    action: EnumProperty(items=(
        ('UV_PREVIEW', 'Preview UV Proposal', 'Build and inspect a disposable texture-set layout'),
        ('UV_SHOW', 'Show UV Proposal', 'Reveal the existing proposal without rebuilding it'),
        ('UV_APPLY', 'Apply UV Proposal', 'Apply to unlocked unchanged derived lows only'),
        ('UV_PREPARE', 'Prepare UVs', 'Preserve validates; Assisted previews; Automatic applies only when unlocked'),
        ('UV_DISCARD', 'Discard UV Proposal', 'Keep working low UVs unchanged'),
        ('UV_BASELINE', 'Acknowledge Current UVs', 'Record reviewed UVs as the protected baseline'),
        ('VALIDATE', 'Validate Asset', 'Read-only geometry, UV and export diagnostics'),
        ('CHECK_OUTDATED', 'Check Outdated', 'Check stage dependencies without reprocessing any output'),
        ('ISSUE_SELECT', 'Select Issue Mesh', 'Reveal and select the affected mesh'),
        ('ISSUE_FRAME', 'Frame Issue Mesh', 'Select and frame the affected mesh'),
        ('GENERATE', 'Generate Active Component', 'Preserve existing lows and edited highs'),
        ('GENERATE_ASSET', 'Generate Asset', 'Process components independently; report failures'),
        ('SELECT_FAILED', 'Select Failed Sources', 'Reveal and select sources that failed generation'),
        ('ASSIGN_HIGH', 'Add Selected Highs', 'Reference selected meshes without modifying them'),
        ('CLEAR_HIGH', 'Clear Custom High Links', 'Keep all objects'),
        ('EXPORT', 'Export Active Asset', 'Write low/high FBX into a new output folder; never overwrite existing exports'),
        ('SOURCE', 'Source', 'Preview source visibility'),
        ('LOW', 'Low', 'Preview low visibility'),
        ('HIGH', 'High', 'Preview high visibility'),
        ('RESTORE', 'Restore Preview', 'Restore visibility before preview')))

    @classmethod
    def poll(cls, context):
        return MBT_OT_asset_edit.poll(context)

    def execute(self, context):
        from . import generation, preview
        from .export import export_asset
        settings = context.scene.mbt_assets
        asset = active_asset(settings)
        component = active_component(asset)
        try:
            if self.action == 'RESTORE':
                preview.restore()
                return {'FINISHED'}
            if asset is None:
                raise ValueError('Select an asset first')
            if self.action == 'CHECK_OUTDATED':
                from .tracking import check
                settings.report = check(context, asset)
            elif self.action == 'VALIDATE':
                from .validation import validate
                settings.report = validate(context, asset)
            elif self.action in {'ISSUE_SELECT', 'ISSUE_FRAME'}:
                from ..substance_painter.issues import select
                if not 0 <= asset.issue_index < len(asset.issues):
                    raise ValueError('Choose a validation issue first')
                issue = asset.issues[asset.issue_index]
                select(context, [issue.mesh])
                if self.action == 'ISSUE_FRAME':
                    area = context.area if context.area and context.area.type == 'VIEW_3D' else next(
                        (area for area in context.screen.areas if area.type == 'VIEW_3D'), None) if context.screen else None
                    region = next((region for region in area.regions if region.type == 'WINDOW'), None) if area else None
                    if region:
                        with context.temp_override(area=area, region=region):
                            bpy.ops.view3d.view_selected(use_all_regions=False)
            elif self.action == 'EXPORT':
                preview.restore()
                settings.report = export_asset(context, asset)
            elif self.action == 'SELECT_FAILED':
                from ..substance_painter.issues import select
                select(context, [item.source for item in asset.components
                                 if item.generation_state == 'Failed' and item.source])
            elif self.action == 'GENERATE_ASSET':
                preview.restore()
                failures = []
                succeeded = skipped = 0
                for item in asset.components:
                    try:
                        generation.generate(context, asset, item)
                        if item.generation_state == 'Skipped':
                            skipped += 1
                        else:
                            succeeded += 1
                    except (ValueError, RuntimeError) as error:
                        failures.append(item.generation_report)
                settings.report = f'{succeeded} succeeded, {len(failures)} failed, {skipped} skipped. ' + '; '.join(failures)
                if failures:
                    self.report({'WARNING'}, settings.report)
            else:
                if component is None:
                    raise ValueError('Select a component first')
                if self.action.startswith('UV_'):
                    from . import uv
                    if self.action == 'UV_BASELINE':
                        if component.low is None:
                            raise ValueError('Prepare a low first')
                        component.uv_reference = uv.layout_signature(component.low.data)
                        component.uv_report = 'Current UV layout acknowledged as reviewed.'
                        settings.report = component.uv_report
                    elif self.action == 'UV_DISCARD':
                        preview.restore()
                        for item in uv.group(asset, component):
                            uv.clear_component(item)
                        settings.report = 'UV proposals discarded. Working lows unchanged.'
                    elif self.action == 'UV_APPLY':
                        settings.report = uv.apply(context, asset, component)
                    elif self.action == 'UV_SHOW':
                        uv.show(context, asset, component)
                    elif component.uv_mode == 'PRESERVE':
                        from .validation import validate
                        settings.report = validate(context, asset)
                    else:
                        members = uv.group(asset, component)
                        if self.action == 'UV_PREPARE' and component.uv_mode == 'AUTOMATIC' and any(
                                item.uv_locked or item.uv_mode != 'AUTOMATIC' for item in members):
                            raise ValueError('Automatic UVs require every texture-set member to be Automatic and explicitly unlocked')
                        settings.report = uv.build(context, asset, component)
                        if self.action == 'UV_PREPARE' and component.uv_mode == 'AUTOMATIC':
                            settings.report = uv.apply(context, asset, component)
                        else:
                            uv.show(context, asset, component)
                elif self.action == 'GENERATE':
                    preview.restore()
                    settings.report = generation.generate(context, asset, component)
                elif self.action == 'ASSIGN_HIGH':
                    existing = {reference.mesh for reference in component.highs}
                    candidates = [obj for obj in meshes(context.selected_objects)
                                  if obj not in {component.source, component.low} and obj not in existing]
                    if not candidates:
                        raise ValueError('Select separate high meshes; existing assignments are skipped')
                    for obj in candidates:
                        component.highs.add().mesh = obj
                    component.high_mode = 'CUSTOM'
                    settings.report = 'Custom highs assigned; their geometry and bake settings are unchanged.'
                elif self.action == 'CLEAR_HIGH':
                    component.highs.clear()
                    settings.report = 'Custom high links cleared. Objects kept.'
                else:
                    preview.show(context, component, self.action)
        except (ValueError, RuntimeError, OSError) as error:
            settings.report = str(error)
            self.report({'WARNING'}, str(error))
            return {'CANCELLED'}
        return {'FINISHED'}


class MBT_UL_assets(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        layout.prop(item, 'name', text='', emboss=False, icon='OUTLINER_COLLECTION')
        layout.label(text=str(len(item.components)))


class MBT_UL_asset_components(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        layout.prop(item, 'name', text='', emboss=False, icon='MESH_DATA' if item.source else 'ERROR')
        if item.source is None:
            layout.label(text='Missing source', icon='ERROR')


class MBT_UL_asset_issues(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        layout.label(text=item.component_name + ' / ' + item.stage,
                     icon='ERROR' if item.severity == 'ERROR' else 'INFO')
        layout.label(text=item.severity.title())


classes = (MBT_OT_asset_edit, MBT_OT_asset_process, MBT_UL_assets, MBT_UL_asset_components, MBT_UL_asset_issues)


def register():
    register_classes(classes)


def unregister():
    unregister_classes(classes)