"""Bold pastel symbols with transparent, premultiplied-alpha backgrounds."""

import bpy.utils.previews
from pathlib import Path

from ..core.section_data import SECTIONS


_previews = None
_action_previews = None

# Normalized 32-unit artwork: broad strokes and filled silhouettes survive
# Blender's small operator-icon rendering. No colored background is baked in.
_STROKES = {
    'tools': (),
    'align': (((6, 5), (6, 26), (27, 26)),
              ((2, 10), (6, 5), (11, 10)), ((22, 21), (27, 26), (22, 30))),
    'resample': (((5, 23), (15, 8), (27, 22)),),
    'script_runner': (((5, 7), (14, 16), (5, 25)), ((18, 25), (28, 25))),
    'geonodes': (((10, 8), (23, 8), (23, 22)),),
    'uv_tools': (((4, 4), (28, 4), (28, 28), (4, 28), (4, 4)),),
    'substance_painter': (),
    'scene_stats': (((4, 4), (4, 28), (29, 28)),),
}

_FILLS = {
    # Open-ended wrench, not a crossed-line approximation.
    'tools': (((6, 3), (6, 10), (11, 14), (23, 28), (28, 23),
               (14, 11), (10, 6), (10, 3), (17, 6), (17, 12),
               (12, 17), (6, 17), (2, 12), (2, 6)),),
    'resample': (((2, 20), (8, 20), (8, 26), (2, 26)),
                 ((12, 5), (18, 5), (18, 11), (12, 11)),
                 ((24, 19), (30, 19), (30, 25), (24, 25))),
    'geonodes': (((3, 3), (12, 3), (12, 12), (3, 12)),
                 ((19, 19), (29, 19), (29, 29), (19, 29))),
    'uv_tools': tuple(((4 + col * 8, 4 + row * 8),
                       (12 + col * 8, 4 + row * 8),
                       (12 + col * 8, 12 + row * 8),
                       (4 + col * 8, 12 + row * 8))
                      for row in range(3) for col in range(3) if (row + col) % 2 == 0),
    # Segmented crescent: broad central roll and tapered, inward-curving tips.
    'substance_painter': (
        ((11, 6), (16, 4), (21, 6), (20, 15), (16, 17), (12, 15)),
        ((5, 10), (9, 7), (10, 16), (13, 19), (9, 21), (6, 18)),
        ((23, 7), (27, 10), (26, 18), (23, 21), (19, 19), (22, 16)),
        ((2, 15), (4, 13), (5, 20), (10, 25), (6, 24), (3, 21)),
        ((28, 13), (30, 15), (29, 21), (26, 24), (22, 25), (27, 20)),
    ),
    'scene_stats': (((9, 18), (13, 18), (13, 24), (9, 24)),
                    ((16, 11), (20, 11), (20, 24), (16, 24)),
                    ((23, 4), (28, 4), (28, 24), (23, 24))),
}


def _inside(x, y, polygon):
    inside = False
    for (ax, ay), (bx, by) in zip(polygon, polygon[1:] + polygon[:1]):
        if (ay > y) != (by > y) and x < (bx - ax) * (y - ay) / (by - ay) + ax:
            inside = not inside
    return inside


def pixels(key, color, size=32):
    """Premultiplied RGBA in Blender's bottom-to-top order; zero RGB outside ink."""
    segments = [(a, b) for stroke in _STROKES[key]
                for a, b in zip(stroke, stroke[1:])]
    result = []
    for y in range(size):
        py = 32 - (y + 0.5) * 32 / size
        for x in range(size):
            px = (x + 0.5) * 32 / size
            distance = 32.0
            for (ax, ay), (bx, by) in segments:
                dx, dy = bx - ax, by - ay
                t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) /
                                     (dx * dx + dy * dy)))
                distance = min(distance, ((px - ax - t * dx) ** 2 +
                                          (py - ay - t * dy) ** 2) ** 0.5)
            alpha = max(0.0, min(1.0, 2.25 - distance))
            if any(_inside(px, py, polygon) for polygon in _FILLS.get(key, ())):
                alpha = 1.0
            # ImagePreview uses premultiplied alpha. Straight RGB here creates
            # a colored square, even where the symbol is fully transparent.
            result.extend((*(channel * alpha for channel in color), alpha))
    return result


def icon_kwargs(key):
    if _action_previews is not None and key in _action_previews:
        return {'icon_value': _action_previews[key].icon_id}
    if key in {'painter_app', 'bake_status'}:
        return {'icon': 'INFO' if key == 'bake_status' else 'FILE_FOLDER'}
    if _previews is not None and key in _previews:
        return {'icon_value': _previews[key].icon_id}
    return {'icon': next(section[2] for section in SECTIONS if section[0] == key)}


def register():
    global _previews, _action_previews
    if _previews is not None or bpy.app.background:
        return
    _previews = bpy.utils.previews.new()
    try:
        for key, label, icon, color, modules in SECTIONS:
            preview = _previews.new(key)
            preview.icon_size = (32, 32)
            preview.icon_pixels_float = pixels(key, color)
        _action_previews = bpy.utils.previews.new()
        _action_previews.load('painter_app', str(Path(__file__).parent / 'icons' / 'substance_painter.png'), 'IMAGE')
        preview = _action_previews.new('bake_status')
        preview.icon_size = (32, 32)
        # Blue information badge; does not change the user's global theme.
        rgba = []
        for y in range(32):
            for x in range(32):
                inside = (x - 15.5) ** 2 + (y - 15.5) ** 2 <= 14 ** 2
                ink = 14 <= x <= 17 and (8 <= y <= 18 or 22 <= y <= 25)
                rgba.extend((1.0, 1.0, 1.0, 1.0) if inside and ink else
                            (0.12, 0.45, 1.0, 1.0) if inside else (0.0, 0.0, 0.0, 0.0))
        preview.icon_pixels_float = rgba
    except Exception:
        unregister()
        raise


def unregister():
    global _previews, _action_previews
    if _action_previews is not None:
        bpy.utils.previews.remove(_action_previews)
        _action_previews = None
    if _previews is not None:
        bpy.utils.previews.remove(_previews)
        _previews = None