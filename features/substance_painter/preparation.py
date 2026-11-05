"""Lightweight input guards and operation timings for staged preparation."""
import json
import time
import bpy

from . import jobs

_geometry_revision = 0


def _geometry_changed(scene, depsgraph):
    global _geometry_revision
    if any(update.is_updated_geometry for update in depsgraph.updates):
        _geometry_revision += 1


def begin_tracking():
    if _geometry_changed not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(_geometry_changed)
    return _geometry_revision


def geometry_revision():
    return _geometry_revision


def end_tracking():
    if _geometry_changed in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(_geometry_changed)


def signature(context):
    """No mesh copies: detect structural/settings changes between UI ticks.

    This deliberately does not hash millions of vertex coordinates per tick.
    Runtime separately tracks dependency-graph geometry revisions between steps.
    Conservative tracking also stops on unrelated geometry edits during a bake.
    """
    settings = context.scene.mbt_painter
    values = []
    for prop in settings.bl_rna.properties:
        key = prop.identifier
        if key in {'rna_type', 'report', 'matching_report', 'advanced', 'bake_settings', 'preparation_timings',
                    'issue_rows', 'issue_index', 'issue_blocking_only', 'projection_report'}:
            continue
        value = getattr(settings, key)
        values.append((key, tuple(sorted(value)) if isinstance(value, set) else
                       value.as_pointer() if hasattr(value, 'as_pointer') else value))
    objects = []
    from .texture_sets import inputs, entries, properties
    set_values = tuple((getattr(entry, 'set_id', ''), tuple(
        (field, tuple(sorted(value)) if isinstance(value, set) else
         value.as_pointer() if hasattr(value, 'as_pointer') else value)
        for field in properties.SET_FIELDS for value in [getattr(entry, field)])) for entry in entries(settings))
    for obj in dict.fromkeys(inputs(settings)):
        modifiers = []
        for modifier in obj.modifiers:
            properties = []
            for prop in modifier.bl_rna.properties:
                if not prop.is_readonly and prop.type in {'BOOLEAN', 'INT', 'FLOAT', 'STRING', 'ENUM'}:
                    value = getattr(modifier, prop.identifier)
                    properties.append((prop.identifier, tuple(value) if prop.is_array else value))
            modifiers.append((modifier.type, tuple(properties)))
        objects.append((obj.as_pointer(), obj.name, obj.data.as_pointer(),
                        len(obj.data.vertices), len(obj.data.polygons), len(obj.data.loops),
                        tuple(tuple(row) for row in obj.matrix_world),
                        tuple(uv.name for uv in obj.data.uv_layers),
                        obj.mbt_bake_group,
                        obj.mbt_bake_target.as_pointer() if obj.mbt_bake_target else 0,
                        tuple(modifiers)))
    return tuple(values), set_values, tuple(objects), context.scene.frame_current


def measured_steps(context, steps):
    """Measure active generator execution, not user think time or timer delays."""
    records = []
    label = 'Preparation setup'
    try:
        while True:
            started = time.perf_counter()
            try:
                message = next(steps)
            except StopIteration as result:
                records.append({'stage': label, 'seconds': time.perf_counter() - started})
                return result.value
            except Exception:
                records.append({'stage': label, 'seconds': time.perf_counter() - started, 'failed': True})
                raise
            finally:
                elapsed = time.perf_counter() - started
            records.append({'stage': label, 'seconds': elapsed})
            label = message
            context.scene.mbt_painter.preparation_timings = json.dumps(records)
            yield message
    finally:
        try:
            steps.close()
        finally:
            context.scene.mbt_painter.preparation_timings = json.dumps(records)