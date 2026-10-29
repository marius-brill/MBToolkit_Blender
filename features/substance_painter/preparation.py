"""Lightweight input guards and operation timings for staged preparation."""
import json
import time

from . import jobs


def signature(context):
    """No mesh copies: detect structural/settings changes between UI ticks.

    This deliberately does not hash millions of vertex coordinates per tick.
    Same-topology coordinate edits and external dependency changes need separate
    dependency tracking; callers must not present this as a complete scene lock.
    """
    settings = context.scene.mbt_painter
    values = []
    for prop in settings.bl_rna.properties:
        key = prop.identifier
        if key in {'rna_type', 'report', 'advanced', 'bake_settings', 'preparation_timings'}:
            continue
        value = getattr(settings, key)
        values.append((key, tuple(sorted(value)) if isinstance(value, set) else
                       value.as_pointer() if hasattr(value, 'as_pointer') else value))
    objects = []
    for obj in jobs.meshes(settings.low_collection) + jobs.meshes(settings.high_collection):
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
    return tuple(values), tuple(objects), context.scene.frame_current


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