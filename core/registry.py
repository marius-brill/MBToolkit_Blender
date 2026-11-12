import bpy
from contextlib import contextmanager
import sys


@contextmanager
def registration_owner(module_name, explicit=None):
    """Match Blender's addon_utils ownership scope for deferred registration.

    Blender exposes no public ownership context manager. Use the same bundled
    _bpy functions as addon_utils, always restoring the previous scope.
    """
    from _bpy import _bl_owner_id_get, _bl_owner_id_set
    owner = explicit
    if owner is None:
        owner = ''
        parts = module_name.split('.')
        for end in range(len(parts), 0, -1):
            module = sys.modules.get('.'.join(parts[:end]))
            if module is not None and module.__dict__.get('__addon_enabled__'):
                owner = module.__name__
                break
    previous = _bl_owner_id_get()
    _bl_owner_id_set(owner)
    try:
        yield
    finally:
        _bl_owner_id_set(previous)


def register_classes(classes):
    registered = []
    try:
        for cls in classes:
            bpy.utils.register_class(cls)
            registered.append(cls)
    except Exception as exc:
        errors = []
        for cls in reversed(registered):
            try:
                bpy.utils.unregister_class(cls)
            except Exception as rollback:
                errors.append(f'{cls.__name__}: {rollback}')
        if errors:
            raise RuntimeError(f'{exc}; rollback failed: ' + '; '.join(errors)) from exc
        raise


def unregister_classes(classes):
    errors = []
    for cls in reversed(classes):
        if cls.is_registered:
            try:
                bpy.utils.unregister_class(cls)
            except Exception as exc:
                errors.append(f'{cls.__name__}: {exc}')
    if errors:
        raise RuntimeError('; '.join(errors))


def register_modules(modules):
    """Compose modules that clean up their own failing registration step."""
    completed = []
    try:
        for module in modules:
            module.register()
            completed.append(module)
    except Exception as exc:
        try:
            unregister_modules(completed)
        except Exception as rollback:
            raise RuntimeError(f'{exc}; rollback failed: {rollback}') from exc
        raise


def unregister_modules(modules):
    errors = []
    for module in reversed(modules):
        try:
            module.unregister()
        except Exception as exc:
            errors.append(f'{module.__name__}: {exc}')
    if errors:
        raise RuntimeError('; '.join(errors))
