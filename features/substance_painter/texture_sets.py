"""Collection-backed texture-set ownership and legacy setup migration."""
import uuid
import bpy
from . import settings as properties


ROLE_COLORS = {'low_collection': 'COLOR_05', 'high_collection': 'COLOR_02'}


def color_collections(entry):
    for field, color in ROLE_COLORS.items():
        collection = getattr(entry, field)
        if collection is not None and not collection.library:
            collection.color_tag = color


def next_name():
    number = 1
    while any(name in bpy.data.collections for name in
              (f'TextureSet{number}', f'TextureSet{number}_low', f'TextureSet{number}_high')):
        number += 1
    return f'TextureSet{number}'


def layer_collections(context, collection):
    """All occurrences in the active view layer, including excluded branches."""
    def visit(layer):
        if layer.collection == collection:
            yield layer
        for child in layer.children:
            yield from visit(child)
    return list(visit(context.view_layer.layer_collection)) if collection is not None else []


def draw_visibility(layout, context, collection):
    if collection is None:
        return
    controls = layout.row(align=True)
    controls.enabled = not collection.library
    for layer in layer_collections(context, collection):
        controls.prop(layer, 'exclude', text='', icon='CHECKBOX_HLT')
        eye = controls.row(align=True)
        eye.enabled = not layer.exclude
        # Boolean RNA buttons select the paired state icon themselves. Passing
        # HIDE_ON for the true state advances twice and displays the next icon.
        eye.prop(layer, 'hide_viewport', text='', icon='HIDE_OFF')


def entries(settings):
    """Legacy files remain readable before their first collection-edit operation."""
    return list(settings.texture_sets) or [settings]


def inputs(settings):
    from .jobs import meshes
    return [obj for entry in entries(settings) for collection in
            (entry.low_collection, entry.high_collection) for obj in meshes(collection)]


def add_set(context, collection=None, migrate=False):
    settings = context.scene.mbt_painter
    values = {field: getattr(settings, field) for field in properties.SET_FIELDS}
    parent = collection if collection is not None else bpy.data.collections.new(next_name())
    if parent.library:
        raise ValueError('Choose a local texture-set collection')
    children = {}
    for role, field in (('Low', 'low_collection'), ('High', 'high_collection')):
        child = values[field] if migrate else next((child for child in parent.children
            if child.name.lower().endswith(('_' + role.lower(), role.lower()))), None)
        if child is not None and (child.library or child == parent or parent in child.children_recursive):
            raise ValueError('Choose local low/high children, not the texture-set parent or its ancestors')
        children[field] = child
    if parent.name not in context.scene.collection.children and parent not in context.scene.collection.children_recursive:
        context.scene.collection.children.link(parent)
    entry = settings.texture_sets.add()
    entry.collection = parent
    entry.set_id = str(uuid.uuid4())
    for field in properties.SET_FIELDS:
        if field not in ('low_collection', 'high_collection'):
            setattr(entry, field, values[field])
    for role, field in (('Low', 'low_collection'), ('High', 'high_collection')):
        child = children[field]
        if child is None:
            child = bpy.data.collections.new(parent.name + '_' + role.lower())
        if child.name not in parent.children:
            parent.children.link(child)
        if child.name in context.scene.collection.children:
            context.scene.collection.children.unlink(child)
        setattr(entry, field, child)
    color_collections(entry)
    settings.active_texture_set = len(settings.texture_sets) - 1
    properties.select_active(settings, context)
    return entry


def ensure_default(context):
    settings = context.scene.mbt_painter
    if not settings.texture_sets:
        return add_set(context, migrate=True)
    return settings.texture_sets[settings.active_texture_set]