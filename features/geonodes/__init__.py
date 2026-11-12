"""Geometry Nodes setups that get built from code and added as modifiers."""

from . import crease_by_angle, dynabool, sdf_remesh
from ...core.registry import register_modules, unregister_modules

_modules = (sdf_remesh, crease_by_angle, dynabool)


def register():
    register_modules(_modules)


def unregister():
    unregister_modules(_modules)
