"""Transactional collection registration; no selection-dependent operators."""
from contextlib import contextmanager

import bpy

from ..substance_painter import settings as properties, texture_sets


@contextmanager
def prepared(context, asset, component, low, highs):
    settings = context.scene.mbt_painter
    old_collections = set(bpy.data.collections)
    old_sets = len(settings.texture_sets)
    old_active = settings.active_texture_set
    old_fields = {field: getattr(settings, field) for field in properties.SET_FIELDS}
    old_parent = settings.texture_collection
    old_identity = component.texture_set_id, component.texture_collection
    objects = [low] + list(highs)
    links = {obj: list(obj.users_collection) for obj in objects}
    obsolete = component.generated_high if component.generated_high not in highs else None
    if obsolete:
        links[obsolete] = list(obsolete.users_collection)
    parent_links = {collection: list(collection.children) for collection in bpy.data.collections}
    root_links = list(context.scene.collection.children)
    try:
        # Preserve a legacy manual setup before add_set changes the active mirrors.
        if not settings.texture_sets and (settings.low_collection or settings.high_collection):
            if not settings.low_collection or not settings.high_collection:
                raise ValueError('Existing Bake setup is incomplete; complete it before automatic asset registration')
            texture_sets.ensure_default(context)
        entry = next((e for e in settings.texture_sets
                      if (component.texture_set_id and e.set_id == component.texture_set_id)
                      or (component.texture_collection and e.collection == component.texture_collection)), None)
        if entry is None:
            if component.texture_set_id:
                raise ValueError('Assigned texture set is missing; resolve the asset texture-set assignment')
            parent = component.texture_collection
            if parent is None:
                parent = next((c for c in bpy.data.collections if c.get('mbt_bake_asset') == asset.asset_id), None)
            if parent is None:
                parent = bpy.data.collections.new(asset.name + '_Bake')
                parent['mbt_bake_asset'] = asset.asset_id
            entry = next((e for e in settings.texture_sets if e.collection == parent), None)
            if entry is None:
                entry = texture_sets.add_set(context, parent)
        if any(c is None or c.library for c in (entry.collection, entry.low_collection, entry.high_collection)):
            raise ValueError('Bake collections must be local and complete')
        for obj in objects:
            destination = entry.low_collection if obj == low else entry.high_collection
            opposite = entry.high_collection if obj == low else entry.low_collection
            if obj.name in opposite.all_objects:
                raise ValueError('Bake low/high roles overlap')
            for other in settings.texture_sets:
                if other != entry and any(c and obj.name in c.all_objects for c in (other.low_collection, other.high_collection)):
                    raise ValueError('A generated/custom mesh already belongs to another texture set')
            if obj.name not in destination.objects:
                destination.objects.link(obj)
            # Only remove toolkit staging links, not artist collection memberships.
            for collection in list(obj.users_collection):
                if obj.get('mbt_component_id') == component.component_id and (
                        collection == asset.generated_collection or collection == context.scene.collection):
                    collection.objects.unlink(obj)
        if obsolete and obsolete.get('mbt_component_id') == component.component_id:
            if obsolete.name in entry.high_collection.objects:
                entry.high_collection.objects.unlink(obsolete)
        component.texture_set_id = entry.set_id
        component.texture_collection = entry.collection
        settings.active_texture_set = next(i for i, e in enumerate(settings.texture_sets) if e == entry)
        properties.select_active(settings, context)
        yield entry
    except Exception:
        for obj, original in links.items():
            for collection in original:
                if obj.name not in collection.objects:
                    collection.objects.link(obj)
            for collection in list(obj.users_collection):
                if collection not in original:
                    collection.objects.unlink(obj)
        component.texture_set_id, component.texture_collection = old_identity
        while len(settings.texture_sets) > old_sets:
            settings.texture_sets.remove(len(settings.texture_sets) - 1)
        for collection in set(bpy.data.collections) - old_collections:
            bpy.data.collections.remove(collection)
        for parent, children in parent_links.items():
            for child in list(parent.children):
                if child not in children:
                    parent.children.unlink(child)
            for child in children:
                if child.name not in parent.children:
                    parent.children.link(child)
        for child in root_links:
            if child.name not in context.scene.collection.children:
                context.scene.collection.children.link(child)
        settings.active_texture_set = old_active
        properties._syncing = True
        try:
            settings.texture_collection = old_parent
            for field, value in old_fields.items():
                setattr(settings, field, value)
        finally:
            properties._syncing = False
        raise