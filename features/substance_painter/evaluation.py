"""Scoped access to hidden bake inputs, including excluded collection ancestors."""
from contextlib import contextmanager
from functools import wraps
import logging


def restore_safely(function):
    """Missing RNA must not prevent restoration of unrelated surviving inputs."""
    try:
        function()
    except (ReferenceError, RuntimeError, KeyError, AttributeError, StopIteration) as error:
        logging.getLogger(__name__).warning('Painter state restoration: %s', error)


@contextmanager
def available(context, objects, restore=True):
    objects = list(objects)
    object_state, collection_state, layer_state = [], [], []
    selected = list(context.selected_objects)
    active = context.view_layer.objects.active
    view_layer = context.view_layer

    def find_layer(path):
        layer = view_layer.layer_collection
        for collection in path:
            layer = next(child for child in layer.children if child.collection == collection)
        return layer

    def visit(layer, path=()):
        needed = any(obj in objects for obj in layer.collection.all_objects)
        if not needed:
            return
        layer_state.append((path, layer.exclude, layer.hide_viewport))
        collection = layer.collection
        collection_state.append((collection, collection.hide_viewport, collection.hide_select))
        for child in layer.children:
            visit(child, path + (child.collection,))

    try:
        visit(context.view_layer.layer_collection)
        for path, excluded, hidden in layer_state:
            layer = find_layer(path)
            if layer.exclude:
                layer.exclude = False
            layer.hide_viewport = False
        for collection, hidden, locked in collection_state:
            collection.hide_viewport = False
            collection.hide_select = False
        context.view_layer.update()
        for obj in objects:
            if obj.name not in context.view_layer.objects:
                from .jobs import PainterError
                raise PainterError(f'{obj.name}: collection must belong to the active scene')
            object_state.append((obj, obj.hide_viewport, obj.hide_get(view_layer=context.view_layer), obj.hide_select))
            obj.hide_viewport = False
            obj.hide_select = False
            obj.hide_set(False, view_layer=context.view_layer)
        context.view_layer.update()
        yield
    finally:
        if restore:
            for obj, hidden, local_hidden, locked in reversed(object_state):
                restore_safely(lambda: obj.hide_set(local_hidden, view_layer=view_layer))
                restore_safely(lambda: setattr(obj, 'hide_viewport', hidden))
                restore_safely(lambda: setattr(obj, 'hide_select', locked))
            for collection, hidden, locked in reversed(collection_state):
                restore_safely(lambda: setattr(collection, 'hide_viewport', hidden))
                restore_safely(lambda: setattr(collection, 'hide_select', locked))
            # Disposable export scenes can rebuild LayerCollection RNA wrappers.
            # Resolve from stable paths rather than retaining those wrappers.
            for path, excluded, hidden in layer_state:
                restore_safely(lambda: setattr(find_layer(path), 'hide_viewport', hidden))
            # Reassigning an unchanged ancestor can clear descendant exclusions.
            for path, excluded, hidden in reversed(layer_state):
                def restore_exclusion():
                    layer = find_layer(path)
                    if layer.exclude != excluded:
                        layer.exclude = excluded
                restore_safely(restore_exclusion)
            restore_safely(view_layer.update)
            def restore_selection():
                for obj in view_layer.objects:
                    restore_safely(lambda: obj.select_set(obj in selected, view_layer=view_layer))
                if active is None:
                    view_layer.objects.active = None
                else:
                    restore_safely(lambda: setattr(view_layer.objects, 'active',
                                                  active if active.name in view_layer.objects else None))
            restore_safely(restore_selection)


def bake_inputs(function):
    @wraps(function)
    def wrapped(context, *args, **kwargs):
        from .jobs import meshes
        settings = context.scene.mbt_painter
        with available(context, meshes(settings.low_collection) + meshes(settings.high_collection)):
            return function(context, *args, **kwargs)
    return wrapped


def bake_steps(function):
    """Keep hidden inputs available until a staged job finishes or is closed."""
    @wraps(function)
    def wrapped(context, *args, **kwargs):
        from .jobs import meshes
        settings = context.scene.mbt_painter
        with available(context, meshes(settings.low_collection) + meshes(settings.high_collection)):
            return (yield from function(context, *args, **kwargs))
    return wrapped


def finish_steps(steps):
    """Synchronous adapter for background scripts and existing public helpers."""
    try:
        while True:
            next(steps)
    except StopIteration as result:
        return result.value
    finally:
        steps.close()