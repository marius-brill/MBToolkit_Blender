"""Collection-backed texture-set ownership and legacy setup migration."""
import uuid
import bpy
from . import settings as properties


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
    parent = collection if collection is not None else bpy.data.collections.new('Default' if not settings.texture_sets else 'TextureSet')
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
            child = bpy.data.collections.new('MBT_' + role if len(settings.texture_sets) == 1 else parent.name + '_' + role)
        if child.name not in parent.children:
            parent.children.link(child)
        if child.name in context.scene.collection.children:
            context.scene.collection.children.unlink(child)
        setattr(entry, field, child)
    settings.active_texture_set = len(settings.texture_sets) - 1
    properties.select_active(settings, context)
    return entry


def ensure_default(context):
    settings = context.scene.mbt_painter
    if not settings.texture_sets:
        return add_set(context, migrate=True)
    return settings.texture_sets[settings.active_texture_set]