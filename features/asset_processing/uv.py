"""Disposable, texture-set-scoped UV proposals using the existing UV suite."""
from contextlib import contextmanager
import hashlib
from types import SimpleNamespace
import uuid

import bpy

from ..uv_suite import automation, geometry, operations, seams
from ..uv_suite.context import UVSession
from ..uv_suite.settings import MBT_UVSettings
from ..substance_painter.evaluation import available
from . import generation, preview
from .identity import key as set_key

PROTECTED_ATTRIBUTE = 'mbt_uv_protected'


def group(asset, component):
    key = set_key(component, asset)
    return [item for item in asset.components if set_key(item, asset) == key]


def options(context, members):
    """Read UV suite defaults without registering its optional feature or changing UI settings."""
    values = {}
    for name, prop in MBT_UVSettings.__annotations__.items():
        keywords = prop.keywords
        if 'get' in keywords or 'set' in keywords:
            continue
        if 'default' in keywords:
            values[name] = keywords['default']
        elif 'items' in keywords:
            values[name] = keywords['items'][0][0]
        else:
            values[name] = ''
    painter = context.scene.mbt_painter
    resolution = int(painter.resolution)
    for entry in painter.texture_sets:
        if any(item.texture_set_id and item.texture_set_id == entry.set_id or
               item.texture_collection is not None and item.texture_collection == entry.collection for item in members):
            resolution = int(entry.resolution)
            break
    values.update(width=resolution, height=resolution, seams='EXTEND',
                  method='CONFORMAL', auto_shape=False, rotation='CARDINAL',
                  effort='FAST', gap=max(item.uv_gap for item in members),
                  border=max(item.uv_border for item in members))
    return SimpleNamespace(**values)


def settings_signature(context, asset, members):
    settings = options(context, members)
    from .identity import token
    return repr(([(item.component_id, token(context, item, asset), item.uv_mode, item.uv_angle,
                   item.uv_gap, item.uv_border) for item in members], settings.width))


def layout_signature(mesh):
    values = [(layer.name, tuple((tuple(loop.uv), loop.pin_uv) for loop in layer.data)) for layer in mesh.uv_layers]
    return hashlib.sha256(repr((mesh.uv_layers.active_index, values)).encode('utf-8')).hexdigest()


def shape_signature(mesh):
    return (tuple(tuple(vertex.co) for vertex in mesh.vertices),
            tuple(tuple(edge.vertices) for edge in mesh.edges),
            tuple(tuple(face.vertices) for face in mesh.polygons))


def clear_component(component):
    obj = component.uv_preview
    component.uv_preview = None
    component.uv_batch = ''
    component.uv_baseline = ''
    component.uv_proposal_settings = ''
    if obj is not None and obj.get('mbt_uv_proposal') == component.component_id:
        generation.discard(obj)


def clear_all():
    preview.restore()
    if bpy.context.mode == 'EDIT_MESH' and any(obj.get('mbt_uv_proposal') for obj in bpy.context.objects_in_mode):
        bpy.ops.object.mode_set(mode='OBJECT')
    for scene in bpy.data.scenes:
        if hasattr(scene, 'mbt_assets'):
            for asset in scene.mbt_assets.assets:
                for component in asset.components:
                    clear_component(component)


@contextmanager
def selected(context, objects):
    with available(context, objects):
        for obj in context.selected_objects:
            obj.select_set(False)
        for obj in objects:
            obj.select_set(True)
        context.view_layer.objects.active = objects[0]
        try:
            yield
        finally:
            if context.mode == 'EDIT_MESH':
                bpy.ops.object.mode_set(mode='OBJECT')


def writable(context, members):
    all_sources = {item.source.data for asset in context.scene.mbt_assets.assets
                   for item in asset.components if item.source and item.source.type == 'MESH'}
    lows = []
    for item in members:
        low = item.low
        if low is None or low.type != 'MESH' or low.name not in context.scene.objects:
            raise ValueError(item.name + ': generate a working low first')
        if item.uv_mode == 'PRESERVE':
            raise ValueError(item.name + ': Preserve mode prevents joint repacking of this texture set')
        if low.data in all_sources or low == item.source:
            raise ValueError(item.name + ': original/source lows are validation-only; use an independent derived low')
        if low.library or low.data.library or not low.is_editable or not low.data.is_editable or low.data.users != 1:
            raise ValueError(item.name + ': UV processing requires local, single-user mesh data')
        if low in lows:
            raise ValueError('Each texture-set component must reference a separate low')
        owners = [item for asset in context.scene.mbt_assets.assets for item in asset.components if item.low == low]
        if len(owners) != 1:
            raise ValueError(item.name + ': low is shared by multiple component records')
        if len(low.data.polygons) > 50000:
            raise ValueError(item.name + ': UV preparation exceeds the 50,000-face safety limit')
        lows.append(low)
    return lows


def check_scope(context, asset, members):
    key = set_key(members[0], asset)
    for other in context.scene.mbt_assets.assets:
        if other != asset and any(set_key(item, other) == key for item in other.components):
            raise ValueError('This texture set spans multiple assets; consolidate its components before joint UV preparation')


def build(context, asset, component):
    members = group(asset, component)
    check_scope(context, asset, members)
    lows = writable(context, members)
    preview.restore()
    for item in members:
        clear_component(item)
    created = []
    try:
        for item, low in zip(members, lows):
            mesh = low.data.copy()
            obj = bpy.data.objects.new('MBT UV Proposal ' + item.component_id[:8], mesh)
            context.scene.collection.objects.link(obj)
            obj.matrix_world = low.matrix_world.copy()
            obj['mbt_uv_proposal'] = item.component_id
            created.append(obj)
            for face in mesh.polygons:
                face.hide = False
            for edge in mesh.edges:
                edge.hide = False
            for vertex in mesh.vertices:
                vertex.hide = False
        settings = options(context, members)
        with selected(context, created), UVSession(context, create=True) as session:
            for state in session.states:
                # Match by object rather than relying on Blender's edit-object order.
                item = members[created.index(state.obj)]
                settings.angle = item.uv_angle
                seams.smart(SimpleNamespace(states=[state]), settings)
                # BOOLEAN mesh attributes may be represented as BMesh integer layers.
                original = item.low.data.attributes.get(PROTECTED_ATTRIBUTE)
                if original and original.domain == 'EDGE' and original.data_type == 'BOOLEAN':
                    for edge in state.bm.edges:
                        if original.data[edge.index].value and edge.seam != item.low.data.edges[edge.index].use_seam:
                            raise ValueError(item.name + ': proposed seam crosses a protected edge; mark a different seam manually')
            automation.unwrap(session, settings)
            operations.pack(session, settings)
            report = geometry.inspect(session, settings, padding=True)
            if any(report[key] for key in ('degenerate', 'outside', 'overlaps', 'gap_violations', 'border_violations')):
                raise ValueError('UV proposal failed layout validation')
        batch = str(uuid.uuid4())
        signature = settings_signature(context, asset, members)
        for item, low, obj in zip(members, lows, created):
            item.uv_preview = obj
            item.uv_baseline = generation.fingerprint(low) + layout_signature(low.data)
            item.uv_proposal_settings = signature
            item.uv_batch = batch
            item.uv_report = f'Proposal ready: {len(members)} component(s), {report["islands"]} islands in shared layout.'
            obj.hide_set(True)
        return component.uv_report
    except Exception:
        for obj in created:
            generation.discard(obj)
        raise


def apply(context, asset, component):
    members = group(asset, component)
    check_scope(context, asset, members)
    lows = writable(context, members)
    signature = settings_signature(context, asset, members)
    if any(item.uv_locked for item in members):
        raise ValueError('UV layout protected: explicitly unlock every component in this texture set before applying')
    batch = component.uv_batch
    for item, low in zip(members, lows):
        obj = item.uv_preview
        if not batch or item.uv_batch != batch or obj is None or obj.get('mbt_uv_proposal') != item.component_id:
            raise ValueError('Preview the complete texture-set proposal before applying')
        if item.uv_proposal_settings != signature or generation.fingerprint(low) + layout_signature(low.data) != item.uv_baseline:
            raise ValueError('Working low or UV settings changed; build a fresh proposal')
        if shape_signature(obj.data) != shape_signature(low.data):
            raise ValueError('Proposal geometry changed; only UV and seam editing is supported')
        if obj.data.uv_layers.active is None:
            raise ValueError('Proposal has no active UV map')
        original = low.data.uv_layers.active
        proposed = obj.data.uv_layers.active
        if original and proposed.name != original.name:
            raise ValueError('Proposal active UV map changed; preview again')
        if original:
            for before, after in zip(original.data, proposed.data):
                if before.pin_uv and (not after.pin_uv or (before.uv - after.uv).length > 1e-7):
                    raise ValueError('Proposal moved or unpinned an artist-pinned UV')
        protected = low.data.attributes.get(PROTECTED_ATTRIBUTE)
        for edge, proposed in zip(low.data.edges, obj.data.edges):
            if edge.use_seam and not proposed.use_seam:
                raise ValueError('Proposal removed an artist seam; preview again')
            if protected and protected.domain == 'EDGE' and protected.data_type == 'BOOLEAN' and protected.data[edge.index].value and edge.use_seam != proposed.use_seam:
                raise ValueError('Proposal changed a protected edge')
    # Validate again: proposals can be adjusted manually after generation.
    import bmesh
    states, meshes = [], []
    try:
        for item in members:
            bm = bmesh.new()
            meshes.append(bm)
            bm.from_mesh(item.uv_preview.data)
            states.append(SimpleNamespace(bm=bm, layer=bm.loops.layers.uv.active,
                                          targets=set(bm.faces), obj=item.uv_preview))
        report = geometry.inspect(SimpleNamespace(states=states), options(context, members), padding=True)
        if any(report[key] for key in ('degenerate', 'outside', 'overlaps', 'gap_violations', 'border_violations')):
            raise ValueError('Edited proposal fails UV layout validation; working lows unchanged')
    finally:
        for bm in meshes:
            bm.free()
    staged = []
    try:
        for item, low in zip(members, lows):
            mesh = low.data.copy()
            staged.append(mesh)
            proposal = item.uv_preview.data
            source = proposal.uv_layers.active
            target = mesh.uv_layers.active or mesh.uv_layers.new(name=source.name)
            for dest, origin in zip(target.data, source.data):
                dest.uv = origin.uv
                dest.pin_uv = origin.pin_uv
            for dest, origin in zip(mesh.edges, proposal.edges):
                dest.use_seam = origin.use_seam
        preview.restore()
        originals = [low.data for low in lows]
        try:
            for low, mesh in zip(lows, staged):
                low.data = mesh
        except Exception:
            for low, original in zip(lows, originals):
                low.data = original
            raise
        for item, low, mesh in zip(members, lows, staged):
            item.uv_reference = layout_signature(mesh)
            item.uv_report = 'UVs applied jointly. Review before texturing; enable Protect UV Layout when approved.'
        for old in originals:
            if old.users == 0:
                bpy.data.meshes.remove(old)
        staged = []
        for item in members:
            clear_component(item)
        from . import tracking
        for item in members:
            tracking.record(item, 'UV', tracking.uv_inputs(context, asset, item))
        return 'UVs applied to ' + str(len(members)) + ' component(s). Sources unchanged.'
    finally:
        for mesh in staged:
            if mesh.users == 0:
                bpy.data.meshes.remove(mesh)


def show(context, asset, component):
    members = group(asset, component)
    objects = [item.uv_preview for item in members]
    if any(obj is None for obj in objects):
        raise ValueError('Build a UV proposal first')
    preview.restore()
    from .export import high_objects
    preview.capture_selection(context)
    layer = context.view_layer
    for obj in dict.fromkeys([item.source for item in members] + [item.low for item in members] +
                             [obj for item in members for obj in high_objects(item)] + objects):
        if obj is not None and obj.name in layer.objects:
            preview._state.append((obj, layer, obj.hide_get(view_layer=layer)))
            obj.hide_set(obj not in objects, view_layer=layer)
    try:
        for obj in objects:
            if (not obj.visible_get() or obj.hide_select or context.scene.collection.hide_select or
                    any(collection.hide_select for collection in obj.users_collection)):
                raise ValueError('Proposal collection is hidden or selection-locked; reveal it before preview')
        for obj in context.selected_objects:
            obj.select_set(False)
        for obj in objects:
            obj.select_set(True)
        layer.objects.active = objects[0]
    except Exception:
        preview.restore()
        raise