"""Optional Blender to Unreal static mesh bridge and dedicated viewport sidebar."""

from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import uuid

import bpy
from bpy.props import BoolProperty, CollectionProperty, EnumProperty, FloatProperty, IntProperty, PointerProperty, StringProperty

from ...core.registry import register_classes, unregister_classes
from .common import (BridgeError, content_path, engine_root, engine_version, folder_from_disk,
                     installed_engines, normalize_engine, project_discovery, project_file)
from .export import descendants, export_root, selected_roots, validate_roots
from .connection import execute
from . import materials

_pool = None
_future = None
_scene = None


def _engine_input(value):
    # Strip Explorer's Copy as path quotes before Blender resolves relative paths.
    return bpy.path.abspath(value.strip().strip('"').strip("'"))


def _material_changed(settings, context):
    record = settings.materials.get(settings.material_name)
    if record:
        settings.material_path = record.path


def _set_material_list(settings, paths):
    """Display short names, retaining exact object paths (including duplicates)."""
    previous = settings.material_path
    settings.materials.clear()
    for path in paths:
        name = path.rsplit('.', 1)[-1]
        label, index = name, 2
        while settings.materials.get(label):
            label = f'{name} ({index})'
            index += 1
        record = settings.materials.add()
        record.name, record.path = label, path
        if path == previous:
            settings.material_name = label


def _engine_changed(settings, context):
    try:
        if settings.engine.strip():
            root = normalize_engine(_engine_input(settings.engine))
        elif settings.project.strip():
            root = engine_root(bpy.path.abspath(settings.project))
        else:
            settings.engine_status = 'Choose a project for automatic detection, or browse an engine'
            return
        version = '.'.join(map(str, engine_version(root))) or 'version unknown'
        settings.engine_status = f'UE {version}: {root}'
    except (BridgeError, OSError, ValueError) as exc:
        settings.engine_status = str(exc)
    _discovery_changed(settings, context)


def _discovery_changed(settings, context):
    try:
        if not settings.project.strip():
            settings.discovery_status = 'Select a project to read its discovery endpoint'
            return
        engine = None
        try:
            engine = engine_root(bpy.path.abspath(settings.project),
                                 _engine_input(settings.engine) if settings.engine.strip() else '')
        except (BridgeError, OSError, ValueError):
            pass
        info = project_discovery(bpy.path.abspath(settings.project), engine, settings.discovery_endpoint)
        settings.discovery_status = f'Discovery: {info["endpoint"]} ({info["source"]})'
    except (BridgeError, OSError, ValueError) as exc:
        settings.discovery_status = str(exc)


class MBT_UnrealBuild(bpy.types.PropertyGroup):
    path: StringProperty()
    version: StringProperty()


class MBT_UnrealSettings(bpy.types.PropertyGroup):
    show_connection: BoolProperty(name='Connection Setup', default=True,
                                 description='Show project, engine and remote connection settings')
    project: StringProperty(name='Unreal Project', subtype='FILE_PATH',
                            update=_engine_changed,
                            description='Target .uproject; open this project in Unreal before connecting')
    engine: StringProperty(name='Engine Directory', subtype='DIR_PATH',
                           update=_engine_changed,
                           description='Install root, Engine folder or UnrealEditor.exe; clear to use project auto-detection')
    engine_status: StringProperty(default='Choose a project or detect installed builds', options={'SKIP_SAVE'})
    builds: CollectionProperty(type=MBT_UnrealBuild, options={'SKIP_SAVE'})
    build_index: IntProperty(default=0, options={'SKIP_SAVE'})
    export_scale: FloatProperty(name='Export Scale', default=1.0, min=0.000001, soft_max=100.0,
        description='Multiply exported geometry around the root Empty without changing source objects')
    materials: CollectionProperty(type=MBT_UnrealBuild, options={'SKIP_SAVE'})
    material_path: StringProperty(name='Unreal Material', description='Exact Unreal material object path')
    material_name: StringProperty(name='Material', update=_material_changed,
                                 description='Unreal material name; numbered suffixes distinguish duplicate names')
    material_project: StringProperty(options={'SKIP_SAVE'})
    editors: CollectionProperty(type=MBT_UnrealBuild, options={'SKIP_SAVE'})
    editor_name: StringProperty(name='Editor', description='Choose an editor if this project has multiple open sessions')
    editor_project: StringProperty(options={'SKIP_SAVE'})
    discovery_endpoint: StringProperty(name='Discovery Endpoint', update=_discovery_changed,
        description='Blank reads project configuration; override with multicast IP:port if Unreal runtime settings differ')
    discovery_status: StringProperty(default='Endpoint is read from project configuration', options={'SKIP_SAVE'})
    destination: StringProperty(name='Content Folder', default='/Game/Props',
                                description='Unreal package folder, for example /Game/Props/Furniture')
    replace_existing: BoolProperty(name='Replace Existing', default=False,
                                   description='Reimport existing Interchange Static Meshes, retaining their import settings')
    report: StringProperty(default='Choose a project, then Test Connection', options={'SKIP_SAVE'})


class MBT_UL_unreal_builds(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row()
        row.label(text='UE ' + item.version, icon='FILE_FOLDER')
        row.label(text=item.path)


class MBT_OT_unreal_detect_engine(bpy.types.Operator):
    bl_idname = 'mbt.unreal_detect_engine'
    bl_label = 'Detect Installed Builds'
    bl_description = 'Refresh installed Unreal builds and choose the engine to use'

    def _refresh(self, context):
        settings = context.scene.mbt_unreal
        settings.builds.clear()
        for record in installed_engines():
            item = settings.builds.add()
            item.path = str(record['root'])
            item.version = '.'.join(map(str, record['version'])) or 'unknown'
        settings.build_index = 0
        try:
            preferred = engine_root(bpy.path.abspath(settings.project),
                                    _engine_input(settings.engine) if settings.engine.strip() else '')
            for index, item in enumerate(settings.builds):
                if Path(item.path) == preferred:
                    settings.build_index = index
                    break
        except (BridgeError, OSError, ValueError):
            pass

    def invoke(self, context, event):
        self._refresh(context)
        if not context.scene.mbt_unreal.builds:
            context.scene.mbt_unreal.engine_status = 'No valid registered builds found. Use Browse Engine for a custom installation'
            self.report({'WARNING'}, 'No valid registered Unreal builds found; use Browse Engine')
            return {'CANCELLED'}
        return context.window_manager.invoke_props_dialog(self, width=700)

    def draw(self, context):
        settings = context.scene.mbt_unreal
        self.layout.label(text='Select the build used by your open Unreal project:')
        self.layout.template_list('MBT_UL_unreal_builds', '', settings, 'builds', settings, 'build_index', rows=4)

    def execute(self, context):
        settings = context.scene.mbt_unreal
        if not settings.builds:
            self._refresh(context)
        if not 0 <= settings.build_index < len(settings.builds):
            self.report({'ERROR'}, 'No installed build selected; use Browse Engine')
            return {'CANCELLED'}
        try:
            settings.engine = str(normalize_engine(settings.builds[settings.build_index].path))
        except (BridgeError, OSError, ValueError) as exc:
            settings.engine_status = str(exc)
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        return {'FINISHED'}


class MBT_OT_unreal_engine_path(bpy.types.Operator):
    bl_idname = 'mbt.unreal_engine_path'
    bl_label = 'Browse Engine'
    bl_description = 'Choose the Unreal installation folder, Engine subfolder, or UnrealEditor executable'
    filepath: StringProperty(subtype='FILE_PATH')
    directory: StringProperty(subtype='DIR_PATH')
    filter_glob: StringProperty(default='*.exe;UnrealEditor;UnrealEditor-Cmd', options={'HIDDEN'})

    def invoke(self, context, event):
        settings = context.scene.mbt_unreal
        try:
            root = engine_root(bpy.path.abspath(settings.project),
                               _engine_input(settings.engine) if settings.engine.strip() else '')
            self.directory = str(root) + '/'
        except (BridgeError, OSError, ValueError):
            self.directory = str(Path('C:/Program Files/Epic Games')) + '/'
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        settings = context.scene.mbt_unreal
        try:
            root = normalize_engine(_engine_input(self.filepath or self.directory))
            settings.engine = str(root)
        except (BridgeError, OSError, ValueError) as exc:
            settings.engine_status = str(exc)
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        return {'FINISHED'}


class MBT_OT_unreal_folder(bpy.types.Operator):
    bl_idname = 'mbt.unreal_folder'
    bl_label = 'Choose Unreal Content Folder'
    bl_description = 'Choose a directory inside the target project Content folder'
    directory: StringProperty(subtype='DIR_PATH')
    filter_folder: BoolProperty(default=True, options={'HIDDEN'})

    def invoke(self, context, event):
        try:
            project = project_file(bpy.path.abspath(context.scene.mbt_unreal.project))
            self.directory = str(project.parent / 'Content') + '/'
        except BridgeError as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        try:
            settings = context.scene.mbt_unreal
            project = project_file(bpy.path.abspath(settings.project))
            settings.destination = folder_from_disk(project, self.directory)
        except (BridgeError, OSError) as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        return {'FINISHED'}


def _poll_result():
    global _future, _scene
    if _future is None:
        return None
    if not _future.done():
        return 0.2
    try:
        result = _future.result()
        message = result['message']
        if _scene and hasattr(_scene, 'mbt_unreal'):
            settings = _scene.mbt_unreal
            if 'materials' in result:
                _set_material_list(settings, result['materials'])
                settings.material_project = result['project']
            if 'editors' in result:
                settings.editors.clear()
                for node in result['editors']:
                    record = settings.editors.add()
                    record.name = node['node_id']
                    record.path = node['node_id']
                settings.editor_project = result['project']
            if result.get('node_id'):
                settings.editor_name = result['node_id']
                settings.editor_project = result['project']
            if 'preview' in result:
                materials.create_preview(result['project'], result['preview'])
                message = 'Material preview updated'
                if result['preview'].get('warnings'):
                    message += ' ' + '; '.join(result['preview']['warnings'])
    except Exception as exc:
        message = 'Failed: ' + str(exc) + '. Earlier assets in a batch may already be imported; inspect Unreal.'
    try:
        if _scene and hasattr(_scene, 'mbt_unreal'):
            _scene.mbt_unreal.report = message
    except ReferenceError:
        pass  # The originating scene was deleted or a different .blend was loaded.
    _future, _scene = None, None
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            area.tag_redraw()
    return None


class MBT_OT_unreal_send(bpy.types.Operator):
    bl_idname = 'mbt.unreal_send'
    bl_label = 'Send to Unreal'
    bl_description = 'Send each selected root Empty and all its mesh descendants as one Static Mesh'
    action: EnumProperty(items=[('SEND', 'Send', ''), ('TEST', 'Test Connection', ''),
                               ('MATERIALS', 'Refresh Materials', ''), ('PREVIEW', 'Fetch Preview', ''),
                               ('EDITORS', 'Find Editors', '')], default='SEND')

    @classmethod
    def poll(cls, context):
        return context.scene is not None and _future is None

    def execute(self, context):
        global _pool, _future, _scene
        settings = context.scene.mbt_unreal
        try:
            project = project_file(bpy.path.abspath(settings.project))
            engine = engine_root(project, _engine_input(settings.engine) if settings.engine.strip() else '')
            _engine_changed(settings, context)
            info = project_discovery(project, engine, settings.discovery_endpoint)
            request = {'action': self.action, 'project': str(project), 'discovery_endpoint': info['endpoint']}
            if settings.editor_project == str(project) and settings.editor_name:
                request['node_id'] = settings.editor_name
            if self.action == 'PREVIEW':
                if not settings.material_path.strip():
                    raise BridgeError('Choose an Unreal material first')
                request['material'] = settings.material_path.strip()
            if self.action == 'SEND':
                destination = content_path(settings.destination)
                roots = validate_roots(context)
                # Unique retained sources: failed sends never replace sources of a prior import.
                cache = project.parent / 'Saved/MBToolkit/UnrealBridge' / uuid.uuid4().hex
                cache.mkdir(parents=True, exist_ok=False)
                assets = []
                context.window_manager.progress_begin(0, len(roots))
                try:
                    for index, root in enumerate(roots):
                        context.window_manager.progress_update(index)
                        path = cache / (root.name + '.fbx')
                        bindings = export_root(context, root, path, settings.export_scale, str(project))
                        assets.append({'name': root.name, 'file': str(path), 'materials': bindings})
                finally:
                    context.window_manager.progress_end()
                request.update(destination=destination, replace=settings.replace_existing, assets=assets,
                               export_scale=settings.export_scale)
                (cache / 'request.json').write_text(json.dumps(request, indent=2), encoding='utf-8')
            if _pool is None:
                _pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='MBT_Unreal')
            _future = _pool.submit(execute, str(engine), request)
            _scene = context.scene
            settings.report = self.action.title() + ' via ' + info['endpoint'] + '…'
            bpy.app.timers.register(_poll_result, first_interval=0.2, persistent=True)
        except Exception as exc:
            settings.report = 'Failed: ' + str(exc)
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        return {'FINISHED'}


class MBT_OT_unreal_assign_material(bpy.types.Operator):
    bl_idname = 'mbt.unreal_assign_material'
    bl_label = 'Assign & Preview'
    bl_description = 'Assign to selected meshes or faces immediately and load the material preview in the background'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.scene is not None and _future is None

    def execute(self, context):
        settings = context.scene.mbt_unreal
        try:
            project = str(project_file(bpy.path.abspath(settings.project)))
            path = settings.material_path.strip()
            if not path or not path.startswith('/') or '.' not in path:
                raise BridgeError('Choose an Unreal material first')
            material = materials.linked_material(project, path)
            needs_preview = material is None or not material.get('mbt_unreal_preview_ready', False)
            if material is None:
                material = materials.create_preview(project, {'path': path})
            count = materials.assign(context, material)
            settings.report = f'Assigned Unreal material to {count} mesh(es); preview is approximate'
            if needs_preview:
                # Assign now so a later selection change cannot retarget this job.
                # The worker only refreshes the same material's preview nodes.
                bpy.ops.mbt.unreal_send(action='PREVIEW')
        except (BridgeError, RuntimeError, OSError) as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        return {'FINISHED'}


class MBT_PT_unreal(bpy.types.Panel):
    bl_idname = 'MBT_PT_unreal'
    bl_label = 'Blender to Unreal Bridge'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'MBT Unreal'

    def draw(self, context):
        layout = self.layout
        layout.use_property_decorate = False
        settings = context.scene.mbt_unreal
        controls = layout.column()
        controls.enabled = _future is None
        import textwrap
        width = max(24, int(context.region.width / (7 * context.preferences.system.ui_scale)) - 4)
        connection_box = controls.box()
        connection_box.prop(settings, 'show_connection', text='Connection Setup', emboss=False,
                            icon='TRIA_DOWN' if settings.show_connection else 'TRIA_RIGHT')
        if settings.show_connection:
            setup = connection_box.column()
            setup.prop(settings, 'project')
            setup.prop(settings, 'engine')
            row = setup.row(align=True)
            row.operator('mbt.unreal_detect_engine', text='Detect Installed Builds', icon='FILE_REFRESH')
            row.operator('mbt.unreal_engine_path', text='Browse Engine', icon='FILE_FOLDER')
            for line in textwrap.wrap(settings.engine_status, width=width):
                setup.label(text=line)
            setup.prop(settings, 'discovery_endpoint')
            for line in textwrap.wrap(settings.discovery_status, width=width):
                setup.label(text=line)
            setup.operator('mbt.unreal_send', text='Test Connection', icon='LINKED').action = 'TEST'
            row = setup.row(align=True)
            row.prop_search(settings, 'editor_name', settings, 'editors', text='Editor')
            row.operator('mbt.unreal_send', text='', icon='FILE_REFRESH').action = 'EDITORS'
        row = controls.row(align=True)
        row.prop(settings, 'destination')
        row.operator('mbt.unreal_folder', text='', icon='FILE_FOLDER')
        controls.prop(settings, 'replace_existing')
        controls.prop(settings, 'export_scale')
        material_box = controls.box()
        material_box.label(text='Unreal Materials', icon='MATERIAL')
        material_box.operator('mbt.unreal_send', text='Refresh Material List', icon='FILE_REFRESH').action = 'MATERIALS'
        material_box.prop_search(settings, 'material_name', settings, 'materials', text='Material')
        material_box.operator('mbt.unreal_assign_material', icon='MATERIAL')
        material_box.operator('mbt.unreal_send', text='Refresh Preview').action = 'PREVIEW'
        material_box.label(text='Approximate preview • use Material Preview shading')
        box = controls.box()
        roots = selected_roots(context)
        if roots:
            for root in roots[:8]:
                box.label(text=f'{root.name}  ({len(descendants(root))} meshes)', icon='OUTLINER_OB_EMPTY')
            if len(roots) > 8:
                box.label(text=f'… and {len(roots) - 8} more')
        else:
            box.label(text='Select an Empty with child meshes', icon='INFO')
        controls.operator('mbt.unreal_send', icon='EXPORT').action = 'SEND'
        # Wrap status without requiring an external UI library.
        for line in textwrap.wrap(settings.report, width=width):
            layout.label(text=line)
        layout.separator()
        layout.label(text='Uses project mesh import settings', icon='INFO')
        if settings.show_connection:
            layout.label(text='Unreal: enable Python Remote Execution')
            layout.label(text='Trusted local projects only')


classes = (MBT_UnrealBuild, MBT_UnrealSettings, MBT_UL_unreal_builds,
            MBT_OT_unreal_detect_engine, MBT_OT_unreal_engine_path,
            MBT_OT_unreal_folder, MBT_OT_unreal_send, MBT_OT_unreal_assign_material, MBT_PT_unreal)


def register():
    register_classes(classes)
    try:
        bpy.types.Scene.mbt_unreal = PointerProperty(type=MBT_UnrealSettings)
        if _future is not None and not bpy.app.timers.is_registered(_poll_result):
            bpy.app.timers.register(_poll_result, first_interval=0.2, persistent=True)
    except Exception:
        if hasattr(bpy.types.Scene, 'mbt_unreal'):
            del bpy.types.Scene.mbt_unreal
        unregister_classes(classes)
        raise


def unregister():
    global _pool, _future, _scene
    if bpy.app.timers.is_registered(_poll_result):
        bpy.app.timers.unregister(_poll_result)
    if _pool:
        _pool.shutdown(wait=False, cancel_futures=True)
        _pool = None
    # Running imports cannot safely be cancelled; the worker touches no bpy data.
    # Keep the future until completion so a quick disable/re-enable cannot launch
    # a second import while the old worker is still running.
    _scene = None
    if hasattr(bpy.types.Scene, 'mbt_unreal'):
        del bpy.types.Scene.mbt_unreal
    unregister_classes(classes)