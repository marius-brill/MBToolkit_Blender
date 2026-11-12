"""Additive asset metadata; owned by the existing Baking feature lifecycle."""
from . import settings, operators, preview


def register():
    settings.register()
    try:
        operators.register()
        preview.register()
    except Exception:
        settings.unregister()
        raise


def unregister():
    preview.unregister()
    operators.unregister()
    settings.unregister()