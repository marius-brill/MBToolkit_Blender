"""Color access, selection and reversible edits without mode switching."""

import bmesh


def srgb_to_linear(value):
    return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4


def linear_to_srgb(value):
    return 12.92 * value if value <= 0.0031308 else 1.055 * value ** (1 / 2.4) - 0.055


def convert(color, to_srgb=False):
    function = linear_to_srgb if to_srgb else srgb_to_linear
    return (*(function(value) for value in color[:3]), color[3])


def active_attribute(context):
    obj = context.active_object
    return obj.data.color_attributes.active_color if obj and obj.type == 'MESH' else None


def targets(context, settings, unique=True):
    active = context.active_object
    if active is None or active.type != 'MESH':
        raise ValueError('Choose an active mesh object')
    if context.mode not in {'OBJECT', 'EDIT_MESH', 'PAINT_VERTEX'}:
        raise ValueError('Use Object, Edit or Vertex Paint mode')
    if settings.target == 'ACTIVE':
        objects = [active]
    elif context.mode == 'EDIT_MESH':
        objects = list(context.objects_in_mode_unique_data if unique else context.objects_in_mode)
    else:
        objects = list(context.selected_objects)
        if active not in objects:
            objects.append(active)
    result, seen = [], set()
    for obj in objects:
        if obj.type != 'MESH' or (unique and obj.data.as_pointer() in seen):
            continue
        if not obj.data.is_editable:
            raise ValueError(f'{obj.name}: mesh data is read-only')
        seen.add(obj.data.as_pointer())
        result.append(obj)
    return result


class ColorAccess:
    """Always read/write linear RGBA, including byte-color BMesh layers."""

    def __init__(self, mesh, attribute, context=None, selected=False):
        self.mesh = mesh
        self.name = attribute.name
        self.domain = attribute.domain
        self.byte = attribute.data_type == 'BYTE_COLOR'
        self.bm = bmesh.from_edit_mesh(mesh) if mesh.is_editmode else None
        self.layer = None
        if self.bm is not None:
            layers = self.bm.verts.layers if self.domain == 'POINT' else self.bm.loops.layers
            self.layer = (layers.color if self.byte else layers.float_color).get(self.name)
            if self.layer is None:
                raise ValueError(f'Missing editable color layer: {self.name}')
            self.elements = (list(self.bm.verts) if self.domain == 'POINT' else
                             [loop for face in self.bm.faces for loop in face.loops])
        else:
            self.elements = attribute.data
        self.indices = list(range(len(self.elements)))
        if selected:
            if context is None:
                raise ValueError('Selection requires a context')
            self.indices = self._selected(context)

    def _selected(self, context):
        if self.bm is not None:
            vertex, edge, face = context.tool_settings.mesh_select_mode
            if self.domain == 'POINT':
                if face:
                    chosen = {v for f in self.bm.faces if f.select and not f.hide for v in f.verts}
                elif edge:
                    chosen = {v for e in self.bm.edges if e.select and not e.hide for v in e.verts}
                else:
                    chosen = {v for v in self.bm.verts if v.select and not v.hide}
                return [i for i, element in enumerate(self.elements) if element in chosen]
            return [i for i, loop in enumerate(self.elements)
                    if not loop.face.hide and
                    (loop.face.select if face else
                     (loop.edge.select or loop.link_loop_prev.edge.select) if edge else
                     loop.vert.select and not loop.vert.hide)]
        mesh = self.mesh
        if context.mode != 'PAINT_VERTEX':
            raise ValueError('Selected Geometry requires Edit Mode or a Vertex Paint selection mask')
        if mesh.use_paint_mask:
            loops = {i for polygon in mesh.polygons if polygon.select and not polygon.hide
                     for i in polygon.loop_indices}
            if self.domain == 'CORNER':
                return sorted(loops)
            vertices = {mesh.loops[i].vertex_index for i in loops}
            return sorted(vertices)
        if mesh.use_paint_mask_vertex:
            vertices = {v.index for v in mesh.vertices if v.select and not v.hide}
            return (sorted(vertices) if self.domain == 'POINT' else
                    [loop.index for loop in mesh.loops if loop.vertex_index in vertices])
        raise ValueError('Enable a Vertex Paint face or vertex selection mask first')

    def get(self, index):
        element = self.elements[index]
        if self.bm is None:
            return tuple(element.color)
        raw = tuple(element[self.layer])
        return convert(raw) if self.byte else raw

    def set(self, index, color):
        if self.bm is None:
            self.elements[index].color = color
        else:
            self.elements[index][self.layer] = convert(color, to_srgb=True) if self.byte else color

    def update(self):
        if self.bm is not None:
            bmesh.update_edit_mesh(self.mesh, loop_triangles=False, destructive=False)
        else:
            self.mesh.update()


class Transaction:
    """Preflight all targets before writes; preserve the exact baseline for cancel."""

    def __init__(self, context, settings, require_mask=True):
        attribute = active_attribute(context)
        if attribute is None:
            raise ValueError('Create or select a color attribute first')
        self.rows = []
        self.mask = tuple(settings.write_mask)
        if require_mask and not any(self.mask):
            raise ValueError('Enable at least one Write channel')
        name, domain, storage = attribute.name, attribute.domain, attribute.data_type
        for obj in targets(context, settings):
            target = obj.data.color_attributes.get(name)
            if target is None:
                raise ValueError(f'{obj.name}: missing attribute "{name}"; use Create Missing first')
            if (target.domain, target.data_type) != (domain, storage):
                raise ValueError(f'{obj.name}: attribute domain/storage differs from the active object')
            access = ColorAccess(obj.data, target, context, settings.affect == 'SELECTED')
            self.rows.append((access, [(i, access.get(i)) for i in access.indices]))
        if not any(values for access, values in self.rows):
            raise ValueError('No selected color elements; nothing was changed')

    @property
    def count(self):
        return sum(len(values) for access, values in self.rows)

    def apply(self, operation):
        try:
            for access, values in self.rows:
                for index, original in values:
                    desired = operation(original)
                    access.set(index, tuple(desired[i] if self.mask[i] else original[i] for i in range(4)))
                access.update()
        except Exception:
            self.restore()
            raise

    def restore(self):
        for access, values in self.rows:
            try:
                for index, original in values:
                    access.set(index, original)
                access.update()
            except (ReferenceError, RuntimeError, IndexError):
                # A file load or deleted datablock may invalidate a pending popup.
                continue
