"""UI adapters for the Blender half of the Painter workflow."""
import json
import bpy
from bpy.props import BoolProperty, EnumProperty, StringProperty
from ...core.registry import register_classes, unregister_classes
from . import jobs, materials
from . import bridge, runtime
from ...core.addon import get_prefs


def show_issues(context, error, action, connect=False):
    if bpy.app.background:
        return False
    bpy.ops.mbt.painter_issues('INVOKE_DEFAULT', issues=json.dumps(error.issues),
                             action=action, connect=connect)
    return True


class MBT_OT_painter_issues(bpy.types.Operator):
    bl_idname = 'mbt.painter_issues'
    bl_label = 'Bake Mesh Issues'
    issues: StringProperty(options={'HIDDEN'})
    action: StringProperty(options={'HIDDEN'})
    connect: BoolProperty(options={'HIDDEN'})
    choice: EnumProperty(items=(('SELECT', 'Select Issue Meshes', 'Stop and reveal meshes for investigation'),
                                ('IGNORE', 'Ignore & Continue', 'Continue with quality warnings acknowledged for this job')))

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=620)

    def draw(self, context):
        import textwrap
        entries = json.loads(self.issues)
        for entry in entries:
            box = self.layout.box()
            box.label(text=entry['object'], icon='ERROR' if entry['blocking'] else 'INFO')
            for line in textwrap.wrap(entry['reason'], 85):
                box.label(text=line)
        if any(entry['blocking'] for entry in entries):
            self.layout.label(text='Blocking issues must be fixed before continuing.', icon='ERROR')
        self.layout.prop(self, 'choice', expand=True)

    def execute(self, context):
        entries = json.loads(self.issues)
        if self.choice == 'SELECT':
            from .evaluation import available
            objects = [bpy.data.objects.get(entry['object']) for entry in entries]
            objects = list(dict.fromkeys(obj for obj in objects if obj is not None))
            with available(context, objects, restore=False):
                for obj in context.view_layer.objects:
                    obj.select_set(False)
                for obj in objects:
                    obj.select_set(True)
                if objects:
                    context.view_layer.objects.active = objects[0]
            return {'FINISHED'}
        if any(entry['blocking'] for entry in entries):
            self.report({'WARNING'}, 'Fix blocking issues first; no meshes were skipped')
            return {'CANCELLED'}
        operator = bpy.ops.mbt.painter_connect if self.connect else bpy.ops.mbt.painter_action
        return operator(action=self.action, ignore_warnings=True)


class MBT_OT_painter_texture_set(bpy.types.Operator):
    bl_idname = 'mbt.painter_texture_set'
    bl_label = 'Edit Texture Sets'
    bl_options = {'REGISTER', 'UNDO'}
    action: EnumProperty(items=(('ADD', 'Add Texture Set', ''),
                                ('REMOVE', 'Remove Texture Set', 'Keep its collection and meshes')))

    @classmethod
    def poll(cls, context):
        return context.scene is not None and not runtime.busy()

    def execute(self, context):
        from .texture_sets import add_set, ensure_default
        from .settings import select_active
        settings = context.scene.mbt_painter
        if self.action == 'ADD':
            if not settings.texture_sets:
                ensure_default(context)
            else:
                add_set(context)
        elif len(settings.texture_sets) > 1:
            settings.texture_sets.remove(settings.active_texture_set)
            settings.active_texture_set = min(settings.active_texture_set, len(settings.texture_sets) - 1)
            select_active(settings, context)
        else:
            self.report({'WARNING'}, 'Keep at least one texture set')
            return {'CANCELLED'}
        return {'FINISHED'}


class MBT_OT_painter_assign(bpy.types.Operator):
    bl_idname = 'mbt.painter_assign'
    bl_label = 'Move Selected Meshes to Bake Collection'
    bl_description = 'Move selected meshes out of their existing collections into this bake collection'
    bl_options = {'REGISTER', 'UNDO'}
    role: EnumProperty(items=(('LOW', 'Low Poly', ''), ('HIGH', 'High Poly', '')))

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and any(obj.type == 'MESH' for obj in context.selected_objects)

    def execute(self, context):
        settings = context.scene.mbt_painter
        objects = [obj for obj in context.selected_objects if obj.type == 'MESH']
        attribute = 'low_collection' if self.role == 'LOW' else 'high_collection'
        opposite = settings.high_collection if self.role == 'LOW' else settings.low_collection
        collection = getattr(settings, attribute)
        if collection is not None and (collection == opposite or
                (opposite and (collection in opposite.children_recursive or opposite in collection.children_recursive))):
            self.report({'WARNING'}, 'Low/high collections must be separate, not nested')
            return {'CANCELLED'}
        if any(obj.library or obj.data.library or any(c.library for c in obj.users_collection)
               or len(obj.users_scene) > 1 for obj in objects):
            self.report({'WARNING'}, 'Cannot move linked meshes or meshes shared across scenes')
            return {'CANCELLED'}
        if collection is not None and collection.library:
            self.report({'WARNING'}, 'Choose a local collection')
            return {'CANCELLED'}
        if collection is None:
            from .texture_sets import ensure_default
            entry = ensure_default(context)
            collection = getattr(settings, attribute)
            if collection is None:
                collection = bpy.data.collections.new(entry.collection.name + '_' + self.role.title())
                entry.collection.children.link(collection)
                setattr(settings, attribute, collection)
        elif not settings.texture_sets:
            from .texture_sets import ensure_default
            ensure_default(context)
        for obj in objects:
            if obj.name not in collection.objects:
                collection.objects.link(obj)
            for previous in tuple(obj.users_collection):
                if previous != collection:
                    previous.objects.unlink(obj)
        return {'FINISHED'}


class MBT_OT_painter_action(bpy.types.Operator):
    bl_idname = 'mbt.painter_action'
    bl_label = 'Painter Workflow'
    bl_description = 'Validate, prepare FBX and JSON files, or import manually exported textures; does not run Painter'
    action: EnumProperty(items=(('VALIDATE', 'Validate Setup', ''),
        ('PREPARE', 'Prepare Bake Job', ''), ('IMPORT', 'Import Maps / Update Material', '')))
    ignore_warnings: BoolProperty(options={'HIDDEN', 'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        return context.scene is not None and not runtime.busy()

    def execute(self, context):
        try:
            if self.action == 'VALIDATE':
                low, high = jobs.validate(context, ignore_warnings=self.ignore_warnings)
                from .matching import resolve_sets
                resolve_sets(context)
                message = f'Valid setup: {len(low)} low / {len(high)} high meshes; all pairs resolved'
            elif self.action == 'PREPARE':
                message = jobs.prepare(context, ignore_warnings=self.ignore_warnings)
            else:
                message = materials.import_maps(context)
        except (jobs.PainterError, OSError, RuntimeError, json.JSONDecodeError) as error:
            if isinstance(error, jobs.ValidationIssues) and show_issues(context, error, self.action):
                return {'CANCELLED'}
            context.scene.mbt_painter.report = str(error)
            self.report({'WARNING'}, str(error))
            return {'CANCELLED'}
        context.scene.mbt_painter.report = message
        self.report({'INFO'}, message)
        return {'FINISHED'}


class MBT_OT_painter_connect(bpy.types.Operator):
    bl_idname = 'mbt.painter_connect'
    bl_label = 'Painter Connection'
    bl_description = 'Connect locally or launch Painter with remote scripting; never closes an open project'
    ignore_warnings: BoolProperty(options={'HIDDEN', 'SKIP_SAVE'})
    action: EnumProperty(items=(('OPEN', 'Open Painter Project', 'Open the associated project for texturing without refreshing or baking'),
                               ('DETECT', 'Detect Executable', ''), ('TEST', 'Test Connection', ''),
                               ('CONNECT', 'Launch / Connect', ''), ('SEND', 'Send to Painter', ''),
                               ('EXPORT', 'Export from Painter / Import', 'Export current job textures and update Blender materials'),
                               ('BAKE', 'Bake Current Job', 'Bake the matching open job, save, export and import'),
                               ('BAKE_NEW', 'Bake New Project', 'Prepare, create project, bake, save, export and import'),
                               ('AUTO', 'Bake', 'Refresh meshes, create or update the associated Painter project, bake and import textures')))

    @classmethod
    def poll(cls, context):
        return context.scene is not None and not runtime.busy()

    def execute(self, context):
        try:
            if self.action == 'DETECT':
                prefs = get_prefs(context)
                path = bridge.detect_executable()
                if prefs is None or not path:
                    raise jobs.PainterError('Painter not found in standard locations; choose the executable manually')
                prefs.painter_executable = path
                context.preferences.is_dirty = True
                context.scene.mbt_painter.report = 'Detected: ' + path
            else:
                if self.ignore_warnings:
                    runtime.start(context, self.action, ignore_warnings=True)
                else:
                    runtime.start(context, self.action)
        except (jobs.PainterError, OSError, RuntimeError, json.JSONDecodeError) as error:
            if isinstance(error, jobs.ValidationIssues) and show_issues(context, error, self.action, connect=True):
                return {'CANCELLED'}
            self.report({'WARNING'}, str(error))
            return {'CANCELLED'}
        return {'FINISHED'}


class MBT_OT_painter_new_project(bpy.types.Operator):
    bl_idname = 'mbt.painter_new_project'
    bl_label = 'New Project Next Bake'
    bl_description = 'Forget the project association; existing project files are kept. Close the old project in Painter yourself'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.scene is not None and not runtime.busy()

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        context.scene.mbt_painter.project_file = ''
        context.scene.mbt_painter.last_job = ''
        context.scene.mbt_painter.report = 'Next Bake creates a new project. Close the previous project in Painter first.'
        return {'FINISHED'}


class MBT_OT_painter_cancel(bpy.types.Operator):
    bl_idname = 'mbt.painter_cancel'
    bl_label = 'Cancel Bake'
    bl_description = 'Cancel preparation between steps, or ask Painter to stop baking; an active mesh evaluation or FBX export must finish first'

    @classmethod
    def poll(cls, context):
        return runtime.busy() and runtime._cancel is not None

    def execute(self, context):
        runtime.cancel()
        return {'FINISHED'}


classes = (MBT_OT_painter_issues, MBT_OT_painter_texture_set, MBT_OT_painter_assign, MBT_OT_painter_action, MBT_OT_painter_connect,
           MBT_OT_painter_new_project, MBT_OT_painter_cancel)


def register():
    register_classes(classes)
    runtime.register()


def unregister():
    runtime.unregister()
    unregister_classes(classes)