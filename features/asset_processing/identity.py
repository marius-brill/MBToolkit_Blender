"""Shared texture-set identity without renaming or tagging artist collections."""
import uuid


def key(component, asset):
    if component.texture_set_id:
        return ('SET', component.texture_set_id)
    if component.texture_collection:
        return ('COLLECTION', component.texture_collection)
    return ('ASSET', asset.asset_id)


def token(context, component, asset):
    kind, value = key(component, asset)
    if kind != 'COLLECTION':
        return kind + ':' + value
    records = context.scene.mbt_assets.collection_ids
    for record in records:
        if record.collection == value:
            return 'COLLECTION:' + record.identity
    record = records.add()
    record.collection = value
    record.identity = str(uuid.uuid4())
    return 'COLLECTION:' + record.identity