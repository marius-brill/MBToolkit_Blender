"""Custom pie menus (data-driven, edited in the add-on preferences)."""
from ...core.registry import register_modules, unregister_modules

def register():
    from . import keymap, ops, runtime, ui
    register_modules((ui, ops, runtime, keymap))


def unregister():
    from . import keymap, ops, runtime, ui
    unregister_modules((ui, ops, runtime, keymap))
