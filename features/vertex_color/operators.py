"""Undoable attribute operations and an explicitly reversible live color dialog."""

import bpy
from bpy.props import EnumProperty, FloatVectorProperty, StringProperty

from . import mesh, preview
from .settings import DOMAINS, STORAGE


class MeshOperator:
    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == 'MESH' and obj.data.is_editable

    def fail(self, error):
        self.report({'WARNING'}, str(error))
        return {'CANCELLED'}


class MBT_OT_vertex_color_attribute(MeshOperator, bpy.types.Operator):
    bl_idname = 'mbt.vertex_color_attribute'
    bl_label = 'Color Attribute'
    bl_options = {'REGISTER', 'UNDO'}

    action: EnumProperty(items=tuple((key, label, description) for key, label, description in (
        ('CREATE', 'Create Color Attribute', 'Create an opaque white color attribute'),
        ('MISSING', 'Create Missing', 'Create a matching opaque white attribute on selected meshes'),
        ('RENAME', 'Rename Attribute', 'Rename the active attribute on the active mesh'),
        ('DUPLICATE', 'Duplicate Attribute', 'Duplicate all values on the active mesh'),
        ('DELETE', 'Delete Attribute', 'Delete the active color attribute'),
        ('RENDER', 'Set Render Default', 'Use this attribute when a shader requests the default color'),
        ('CONVERT', 'Convert Attribute', 'Explicitly convert the active attribute domain/storage'),
        ('SINGLE', 'Make Single User', 'Copy selected shared mesh datablocks before editing'))))
    name: StringProperty(name='Name', default='Color')
    domain: EnumProperty(name='Domain', items=DOMAINS)
    storage: EnumProperty(name='Storage', items=STORAGE)

    def invoke(self, context, event):
        attribute = mesh.active_attribute(context)
        settings = context.scene.mbt_vertex_color
        self.name = attribute.name if attribute and self.action == 'RENAME' else settings.new_name
        self.domain, self.storage = settings.domain, settings.storage
        if attribute and self.action == 'CONVERT':
            self.domain, self.storage = attribute.domain, attribute.data_type
        if self.action in {'CREATE', 'RENAME', 'CONVERT'}:
            return context.window_manager.invoke_props_dialog(self, width=320)
        if self.action == 'DELETE':
            return context.window_manager.invoke_confirm(self, event)
        return self.execute(context)

    def draw(self, context):
        if self.action in {'CREATE', 'RENAME'}:
            self.layout.prop(self, 'name')
        if self.action in {'CREATE', 'CONVERT'}:
            self.layout.prop(self, 'domain')
            self.layout.prop(self, 'storage')
        if self.action == 'CONVERT':
            self.layout.label(text='Conversion may merge corners or quantize values.', icon='ERROR')

    def execute(self, context):
        settings = context.scene.mbt_vertex_color
        obj = context.active_object
        attribute = mesh.active_attribute(context)
        try:
            if context.mode != 'OBJECT':
                raise ValueError('Attribute management requires Object Mode; color editing also supports Edit Mode')
            if self.action == 'SINGLE':
                for target in mesh.targets(context, settings, unique=False):
                    if target.data.users > 1:
                        target.data = target.data.copy()
                preview.invalidate()
                return {'FINISHED'}
            if self.action in {'CREATE', 'MISSING'}:
                name = self.name.strip() if self.action == 'CREATE' else (attribute.name if attribute else '')
                if not name:
                    raise ValueError('Choose a non-empty attribute name')
                domain = self.domain if self.action == 'CREATE' else attribute.domain
                storage = self.storage if self.action == 'CREATE' else attribute.data_type
                objects = mesh.targets(context, settings)
                for target in objects:
                    existing = target.data.attributes.get(name)
                    if existing and (self.action == 'CREATE' or existing.data_type not in {'BYTE_COLOR', 'FLOAT_COLOR'}
                                     or existing.domain != domain or existing.data_type != storage):
                        raise ValueError(f'{target.name}: "{name}" already exists or is incompatible')
                created = []
                try:
                    for target in objects:
                        if target.data.color_attributes.get(name):
                            continue
                        layer = target.data.color_attributes.new(name=name, type=storage, domain=domain)
                        created.append((target.data, layer))
                        for value in layer.data:
                            value.color = (1, 1, 1, 1)
                        target.data.color_attributes.active_color = layer
                        target.data.update()
                except Exception:
                    for data, layer in reversed(created):
                        data.color_attributes.remove(layer)
                    raise
                settings.new_name = name
                settings.domain, settings.storage = domain, storage
            elif attribute is None:
                raise ValueError('Select a color attribute first')
            elif self.action == 'DELETE':
                obj.data.color_attributes.remove(attribute)
            elif self.action == 'RENAME':
                name = self.name.strip()
                if not name or (obj.data.attributes.get(name) and name != attribute.name):
                    raise ValueError('Name is empty or already used by another attribute')
                attribute.name = name
            elif self.action == 'DUPLICATE':
                values = [tuple(value.color) for value in attribute.data]
                layer = obj.data.color_attributes.new(name=attribute.name + ' Copy',
                    type=attribute.data_type, domain=attribute.domain)
                for value, color in zip(layer.data, values):
                    value.color = color
                obj.data.color_attributes.active_color = layer
            elif self.action == 'RENDER':
                obj.data.color_attributes.render_color_index = obj.data.color_attributes.active_color_index
            elif self.action == 'CONVERT':
                result = bpy.ops.geometry.color_attribute_convert(domain=self.domain, data_type=self.storage)
                if result != {'FINISHED'}:
                    raise ValueError('Blender could not convert this attribute')
            settings.status = ''
            preview.invalidate()
            return {'FINISHED'}
        except (ValueError, RuntimeError) as exc:
            return self.fail(exc)


def _live_color(self, context):
    transaction = getattr(self, '_transaction', None)
    if transaction is not None and transaction in preview._sessions:
        try:
            transaction.apply(lambda original: tuple(self.color))
            preview.invalidate()
        except (ValueError, RuntimeError, ReferenceError) as exc:
            self._error = str(exc)


class MBT_OT_vertex_color_edit(MeshOperator, bpy.types.Operator):
    bl_idname = 'mbt.vertex_color_edit'
    bl_label = 'Edit Vertex Color'
    bl_description = 'Live color edit; OK commits one undo step, Cancel restores all original values'
    bl_options = {'REGISTER', 'UNDO'}

    color: FloatVectorProperty(name='Color', subtype='COLOR', size=4,
        default=(1, 1, 1, 1), min=0, max=1, update=_live_color)

    def invoke(self, context, event):
        try:
            self._transaction = mesh.Transaction(context, context.scene.mbt_vertex_color)
        except ValueError as exc:
            return self.fail(exc)
        self._error = ''
        first = next(color for access, values in self._transaction.rows for index, color in values)
        self.color = first
        self._mixed = any(any(abs(color[i] - first[i]) > 1e-6 for i in range(4))
                          for access, values in self._transaction.rows for index, color in values)
        preview._sessions.append(self._transaction)
        try:
            if getattr(context, 'area', None) and context.area.type == 'VIEW_3D' and preview.mode(context) == 'OFF':
                preview.set_mode(context, 'RGB')
            return context.window_manager.invoke_props_dialog(self, width=340)
        except Exception:
            self.cancel(context)
            raise

    def draw(self, context):
        self.layout.template_color_picker(self, 'color', value_slider=True)
        self.layout.prop(self, 'color', text='Color')
        self.layout.label(text='Mixed colors — changing the picker fills enabled channels' if self._mixed
                          else 'Changes are live; Cancel restores the original colors', icon='INFO')
        if self._error:
            self.layout.label(text=self._error, icon='ERROR')

    def execute(self, context):
        transaction = getattr(self, '_transaction', None)
        try:
            if transaction is not None:
                if transaction not in preview._sessions:
                    raise ValueError('Edit session was reset; reopen the color editor')
                if self._error:
                    raise ValueError(self._error)
                # With no picker changes, opening/accepting must not flatten mixed colors.
                preview._sessions.remove(transaction)
                self._transaction = None
            else:
                transaction = mesh.Transaction(context, context.scene.mbt_vertex_color)
                transaction.apply(lambda original: tuple(self.color))
            context.scene.mbt_vertex_color.color = self.color
            context.scene.mbt_vertex_color.status = ''
            preview.invalidate()
            return {'FINISHED'}
        except (ValueError, RuntimeError) as exc:
            self.cancel(context)
            return self.fail(exc)

    def cancel(self, context):
        transaction = getattr(self, '_transaction', None)
        if transaction is not None and transaction in preview._sessions:
            transaction.restore()
            preview._sessions.remove(transaction)
        self._transaction = None
        preview.invalidate()


class MBT_OT_vertex_color_apply(MeshOperator, bpy.types.Operator):
    bl_idname = 'mbt.vertex_color_apply'
    bl_label = 'Apply Vertex Color'
    bl_options = {'REGISTER', 'UNDO'}

    action: EnumProperty(items=tuple((key, label, description) for key, label, description in (
        ('FILL', 'Fill', 'Fill enabled Write components with the chosen color'),
        ('SET', 'Set Channel', 'Set the chosen component; its Write button must be enabled'),
        ('INVERT', 'Invert Channel', 'Invert the chosen component in the selected value space'),
        ('COPY', 'Copy Channel', 'Copy one component to another; destination must be enabled'),
        ('SWAP', 'Swap Channels', 'Swap two enabled components'),
        ('SAMPLE', 'Sample First Selected', 'Load the first affected element into the fill color'),
        ('INSPECT', 'Inspect Values', 'Read uniform/mixed state and min/max without changing values'),
        ('MATERIAL', 'Use Material Base Color', 'Load the active Principled material constant Base Color'))))

    def execute(self, context):
        settings = context.scene.mbt_vertex_color
        try:
            if self.action == 'MATERIAL':
                material = context.active_object.active_material
                nodes = ([node for node in material.node_tree.nodes if node.type == 'BSDF_PRINCIPLED']
                         if material and material.use_nodes and material.node_tree else [])
                if len(nodes) != 1 or nodes[0].inputs['Base Color'].is_linked:
                    raise ValueError('Requires one Principled BSDF with an unlinked Base Color')
                settings.color = nodes[0].inputs['Base Color'].default_value
                return {'FINISHED'}
            transaction = mesh.Transaction(context, settings, require_mask=self.action not in {'SAMPLE', 'INSPECT'})
            first = next(color for access, values in transaction.rows for index, color in values)
            if self.action == 'SAMPLE':
                settings.color = first
                settings.status = 'Sampled first affected element (not an average)'
                return {'FINISHED'}
            if self.action == 'INSPECT':
                values = [mesh.convert(color, to_srgb=True) if settings.space == 'SRGB' else color
                          for access, rows in transaction.rows for index, color in rows]
                low = [min(color[i] for color in values) for i in range(4)]
                high = [max(color[i] for color in values) for i in range(4)]
                uniform = all(abs(a - b) < 1e-6 for a, b in zip(low, high))
                settings.status = ('Uniform' if uniform else 'Mixed') + ' · ' + ' | '.join(
                    f'{channel}: {a:.4g}–{b:.4g}' for channel, a, b in zip('RGBA', low, high))
                self.report({'INFO'}, settings.status)
                return {'FINISHED'}
            source, destination = 'RGBA'.index(settings.channel), 'RGBA'.index(settings.destination)
            required = ([destination] if self.action == 'COPY' else [source, destination]
                        if self.action == 'SWAP' else [source])
            if self.action != 'FILL' and any(not settings.write_mask[i] for i in required):
                raise ValueError('Enable Write for every component this operation changes')

            def operation(original):
                if self.action == 'FILL':
                    return tuple(settings.color)
                color = list(mesh.convert(original, to_srgb=True) if settings.space == 'SRGB' else original)
                if self.action == 'SET':
                    color[source] = settings.value
                elif self.action == 'INVERT':
                    color[source] = 1 - color[source]
                elif self.action == 'COPY':
                    color[destination] = color[source]
                elif self.action == 'SWAP':
                    color[source], color[destination] = color[destination], color[source]
                result = mesh.convert(color) if settings.space == 'SRGB' else color
                changed = required
                return tuple(result[i] if i in changed else original[i] for i in range(4))

            transaction.apply(operation)
            settings.status = ''
            preview.invalidate()
            self.report({'INFO'}, f'Updated {transaction.count} color elements')
            return {'FINISHED'}
        except (ValueError, RuntimeError) as exc:
            return self.fail(exc)


class MBT_OT_vertex_color_preview(bpy.types.Operator):
    bl_idname = 'mbt.vertex_color_preview'
    bl_label = 'Preview Vertex Color'
    bl_description = 'Non-destructive Solid viewport diagnostic; RGB ignores alpha, components show grayscale'
    bl_options = {'INTERNAL'}

    component: EnumProperty(items=tuple((key, key.title(), '') for key in ('OFF', 'RGB', 'R', 'G', 'B', 'A')))

    def execute(self, context):
        try:
            preview.set_mode(context, self.component)
        except ValueError as exc:
            self.report({'WARNING'}, str(exc))
            return {'CANCELLED'}
        return {'FINISHED'}


classes = (MBT_OT_vertex_color_attribute, MBT_OT_vertex_color_edit,
           MBT_OT_vertex_color_apply, MBT_OT_vertex_color_preview)