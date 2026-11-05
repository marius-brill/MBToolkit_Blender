"""Structured, navigable bake diagnostics. Drawing never changes scene selection."""
import json
import textwrap

import bpy
from bpy.props import BoolProperty, CollectionProperty, IntProperty, PointerProperty, StringProperty


class MBT_PainterIssueTarget(bpy.types.PropertyGroup):
    mesh: PointerProperty(type=bpy.types.Object)


class MBT_PainterIssue(bpy.types.PropertyGroup):
    mesh: PointerProperty(type=bpy.types.Object)
    object_name: StringProperty()
    reason: StringProperty()
    blocking: BoolProperty()
    texture_set: StringProperty()
    payload: StringProperty()
    targets: CollectionProperty(type=MBT_PainterIssueTarget)


def publish(context, entries):
    """Bind once, while names are current; never rebind a deleted row by name."""
    from .texture_sets import entries as texture_sets
    from .jobs import meshes
    settings = context.scene.mbt_painter
    owners = {obj: (entry.collection.name if getattr(entry, 'collection', None) else 'Default')
              for entry in texture_sets(settings)
              for collection in (entry.low_collection, entry.high_collection)
              for obj in meshes(collection)}
    settings.issue_rows.clear()
    for entry in entries:
        row = settings.issue_rows.add()
        row.object_name = entry['object']
        row.mesh = context.scene.objects.get(entry['object'])
        row.reason = entry['reason']
        row.blocking = entry.get('blocking', False)
        row.texture_set = owners.get(row.mesh, '')
        # RNA pointers survive rename/save/load and become None on deletion.
        for name in dict.fromkeys(entry.get('targets', [])):
            obj = context.scene.objects.get(name)
            if obj is not None:
                row.targets.add().mesh = obj
        row.payload = json.dumps(entry)
    settings.issue_index = 0


def select(context, objects):
    from .evaluation import available
    objects = list(dict.fromkeys(obj for obj in objects if obj is not None))
    if not objects:
        raise ValueError('Issue mesh is missing; revalidate the setup')
    if context.mode != 'OBJECT':
        raise ValueError('Switch to Object Mode to select issue meshes')
    with available(context, objects, restore=False):
        for obj in context.view_layer.objects:
            obj.select_set(False)
        for obj in objects:
            obj.select_set(True)
            if context.space_data and context.space_data.type == 'VIEW_3D' and context.space_data.local_view:
                obj.local_view_set(context.space_data, True)
        context.view_layer.objects.active = objects[0]


class MBT_OT_painter_issue_select(bpy.types.Operator):
    bl_idname = 'mbt.painter_issue_select'
    bl_label = 'Select Issue Mesh'
    bl_description = 'Reveal, select and activate this mesh; Frame is a separate action'
    index: IntProperty(default=-1)
    all_meshes: BoolProperty(default=False)
    candidates: BoolProperty(default=False)
    frame: BoolProperty(default=False)

    @classmethod
    def poll(cls, context):
        from .runtime import busy
        return context.scene is not None and not busy()

    def execute(self, context):
        settings = context.scene.mbt_painter
        rows = settings.issue_rows
        index = self.index if self.index >= 0 else settings.issue_index
        if not self.all_meshes and not 0 <= index < len(rows):
            return {'CANCELLED'}
        if self.all_meshes:
            objects = [row.mesh for row in rows]
        else:
            settings.issue_index = index
            row = rows[index]
            if self.candidates:
                objects = [target.mesh for target in row.targets]
            else:
                objects = [row.mesh]
        try:
            select(context, objects)
            if self.frame:
                area = context.area if context.area and context.area.type == 'VIEW_3D' else next(
                    (area for area in context.screen.areas if area.type == 'VIEW_3D'), None) if context.screen else None
                region = next((region for region in area.regions if region.type == 'WINDOW'), None) if area else None
                if region:
                    with context.temp_override(area=area, region=region):
                        bpy.ops.view3d.view_selected(use_all_regions=False)
                else:
                    self.report({'INFO'}, 'Mesh selected; no 3D viewport available to frame')
        except (ValueError, RuntimeError) as error:
            self.report({'WARNING'}, str(error))
            return {'CANCELLED'}
        return {'FINISHED'}


class MBT_UL_painter_issues(bpy.types.UIList):
    def draw_filter(self, context, layout):
        row = layout.row(align=True)
        row.prop(self, 'filter_name', text='', icon='VIEWZOOM')
        row.prop(context.scene.mbt_painter, 'issue_blocking_only', text='Blocking Only')

    def filter_items(self, context, data, propname):
        search = self.filter_name.casefold()
        blocking = data.issue_blocking_only
        return [self.bitflag_filter_item if (not blocking or row.blocking) and
                (not search or search in (' '.join((row.mesh.name if row.mesh else row.object_name,
                                                    row.reason, row.texture_set))).casefold()) else 0
                for row in getattr(data, propname)], []

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname,
                  index=0, flt_flag=0):
        row = layout.row(align=True)
        row.alert = item.blocking
        op = row.operator('mbt.painter_issue_select', text=item.mesh.name if item.mesh else item.object_name + ' (missing)',
                          icon='ERROR' if item.blocking else 'INFO', emboss=False)
        op.index = index
        row.label(text=item.texture_set)


class MBT_OT_painter_issue_faces(bpy.types.Operator):
    bl_idname = 'mbt.painter_issue_faces'
    bl_label = 'Select Issue Faces'
    bl_description = 'Select UV issue faces only when evaluated and source topology agree and diagnostics are still current'

    @classmethod
    def poll(cls, context):
        from .runtime import busy
        return context.scene is not None and context.mode == 'OBJECT' and not busy()

    def execute(self, context):
        from .evaluation import available
        from .jobs import validate_uv, ValidationIssues
        settings = context.scene.mbt_painter
        if not 0 <= settings.issue_index < len(settings.issue_rows):
            return {'CANCELLED'}
        row = settings.issue_rows[settings.issue_index]
        obj = row.mesh
        payload = json.loads(row.payload)
        faces = payload.get('faces', [])
        if obj is None or not faces:
            return {'CANCELLED'}
        try:
            with available(context, [obj]):
                graph = context.evaluated_depsgraph_get()
                evaluated = obj.evaluated_get(graph)
                mesh = evaluated.to_mesh(preserve_all_data_layers=True, depsgraph=graph)
                try:
                    if (len(mesh.vertices) != len(obj.data.vertices) or len(mesh.polygons) != len(obj.data.polygons)
                            or any(tuple(a.vertices) != tuple(b.vertices) for a, b in zip(mesh.polygons, obj.data.polygons))):
                        raise ValueError('Topology modifiers changed face indices; select the mesh and inspect the evaluated result')
                    current = []
                    try:
                        validate_uv(mesh, obj.name, stage=payload.get('stage', 'mesh'))
                    except ValidationIssues as error:
                        current = error.issues
                    if not any(entry.get('faces') == faces and entry.get('uv_map') == payload.get('uv_map')
                               and entry['reason'] == row.reason for entry in current):
                        raise ValueError('UV diagnostics changed; revalidate before selecting faces')
                finally:
                    evaluated.to_mesh_clear()
            select(context, [obj])
            if obj.data.users > 1:
                raise ValueError('Mesh data is shared; make it single-user before selecting faces')
            for vertex in obj.data.vertices:
                vertex.select = False
            for edge in obj.data.edges:
                edge.select = False
            for polygon in obj.data.polygons:
                polygon.select = polygon.index in faces
            context.tool_settings.mesh_select_mode = (False, False, True)
            bpy.ops.object.mode_set(mode='EDIT')
        except (ValueError, RuntimeError) as error:
            self.report({'WARNING'}, str(error))
            return {'CANCELLED'}
        return {'FINISHED'}


def text_width(context, fallback=36):
    region = context.region
    if region is None:
        return fallback
    unit = 20 * (context.preferences.system.ui_scale or 1.0)
    left = region.view2d.region_to_view(0, 0)[0]
    right = region.view2d.region_to_view(region.width, 0)[0]
    return max(16, min(100, int(abs(right - left) / unit * 2) - 10))


def wrapped(layout, text, width):
    for paragraph in text.splitlines():
        for line in textwrap.wrap(paragraph, width=width) or ['']:
            layout.label(text=line)


def summary(reason):
    if 'unmatched' in reason.lower() and 'surface' in reason.lower():
        return ('Surface mismatch', 'Some high-poly regions have no close matching low surface.',
                'Inspect the assigned low mesh and cage reach.')
    if 'ambiguous' in reason.lower():
        return ('Ambiguous match', 'Several low surfaces are similarly close.',
                'Select the mesh and set its target in Mesh Matching.')
    if 'UV' in reason:
        return ('UV issue', reason.split('. ')[0], 'Inspect the mesh UVs; see Full Details.')
    return ('Mesh issue', reason.split('. ')[0], 'Inspect the mesh; see Full Details.')


class MBT_OT_painter_issue_details(bpy.types.Operator):
    bl_idname = 'mbt.painter_issue_details'
    bl_label = 'Bake Issue Details'
    report_text: StringProperty(options={'HIDDEN', 'SKIP_SAVE'})

    def invoke(self, context, event):
        settings = context.scene.mbt_painter
        if not 0 <= settings.issue_index < len(settings.issue_rows):
            return {'CANCELLED'}
        self.report_text = details_text(settings.issue_rows[settings.issue_index])
        return context.window_manager.invoke_props_dialog(self, width=680)

    def draw(self, context):
        wrapped(self.layout, self.report_text, 85)

    def execute(self, context):
        return {'FINISHED'}


def details_text(item):
    payload = json.loads(item.payload)
    lines = [item.mesh.name if item.mesh else item.object_name,
             'Blocking error' if item.blocking else 'Warning', item.reason]
    if item.texture_set:
        lines.append('Texture set: ' + item.texture_set)
    for candidate in payload.get('candidates', []):
        lines.extend(('', 'Candidate: ' + candidate['group'],
                      f"Score: {candidate['score']:.4g}",
                      f"Surface coverage: {candidate['coverage']:.0%} ({candidate['sample_count']} samples)"))
        if candidate.get('targets'):
            lines.append('Meshes: ' + ', '.join(candidate['targets']))
    return '\n'.join(lines)


def draw(layout, context):
    from . import action_rows, card
    settings = context.scene.mbt_painter
    if not settings.issue_rows:
        return
    from .runtime import busy
    box = card(layout, 'Bake Issues', 'ERROR')
    blocking = sum(item.blocking for item in settings.issue_rows)
    box.label(text=f'{len(settings.issue_rows)} issues ({blocking} blocking, {len(settings.issue_rows) - blocking} warnings)')
    box.template_list('MBT_UL_painter_issues', '', settings, 'issue_rows', settings, 'issue_index', rows=4, maxrows=8)
    controls = box.column()
    controls.enabled = not busy()
    row = action_rows(controls, context)
    row.operator('mbt.painter_issue_select', text='Select All').all_meshes = True
    row.operator('mbt.painter_action', text='Revalidate', icon='FILE_REFRESH').action = 'VALIDATE'
    if not 0 <= settings.issue_index < len(settings.issue_rows):
        return
    item = settings.issue_rows[settings.issue_index]
    width = text_width(context)
    title, explanation, action = summary(item.reason)
    controls.separator(factor=0.5)
    summary_box = controls.box()
    wrapped(summary_box, item.mesh.name if item.mesh else item.object_name, width)
    summary_box.label(text=title, icon='ERROR' if item.blocking else 'INFO')
    wrapped(summary_box, explanation, width)
    summary_box.separator(factor=0.35)
    wrapped(summary_box, action, width)
    row = action_rows(controls, context)
    row.operator('mbt.painter_issue_select', text='Select Mesh')
    row.operator('mbt.painter_issue_select', text='Frame').frame = True
    payload = json.loads(item.payload)
    if item.targets:
        controls.operator('mbt.painter_issue_select', text='Select Assigned / Candidate Lows').candidates = True
    details = controls.row()
    details.operator_context = 'INVOKE_DEFAULT'
    details.operator('mbt.painter_issue_details', text='Full Details…', icon='TEXT')
    wrapped(controls, 'Snapshot — revalidate after editing.', width)
    if payload.get('faces'):
        controls.operator('mbt.painter_issue_faces', text='Select Issue Faces', icon='FACESEL')
        controls.label(text='Face selection verifies topology first.', icon='INFO')


classes = (MBT_OT_painter_issue_select, MBT_OT_painter_issue_faces,
           MBT_OT_painter_issue_details, MBT_UL_painter_issues)