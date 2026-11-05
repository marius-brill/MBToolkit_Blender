"""Lightweight sidebar catalog and ordered selection; no feature runtime imports."""

import json


# Feature key, heading, fallback icon, accent color, draw modules.
SECTIONS = (
    ('tools', 'Tools', 'TOOL_SETTINGS', (1.0, 0.82, 0.61), ('rename', 'clean_up')),
    ('align', 'Align', 'ORIENTATION_GLOBAL', (0.70, 0.86, 1.0), ('align',)),
    ('resample', 'Resample', 'OUTLINER_DATA_CURVE', (0.66, 0.94, 0.81), ('resample',)),
    ('script_runner', 'Script Runner', 'CONSOLE', (0.85, 0.76, 1.0), ('script_runner',)),
    ('geonodes', 'Low to High', 'GEOMETRY_NODES', (0.78, 0.94, 0.63),
     ('geonodes.dynabool', 'geonodes.crease_by_angle', 'geonodes.sdf_remesh')),
    ('uv_tools', 'UV', 'GROUP_UVS', (1.0, 0.93, 0.65), ('uv_tools',)),
    ('vertex_color', 'Vertex Color', 'GROUP_VCOL', (0.96, 0.70, 0.93), ('vertex_color',)),
    ('substance_painter', 'Bake', 'RENDER_STILL', (1.0, 0.73, 0.72), ('substance_painter',)),
    ('scene_stats', 'Scene Performance', 'GRAPH', (0.67, 0.92, 0.95), ('scene_stats',)),
)
SECTION_BY_KEY = {section[0]: section for section in SECTIONS}
DEFAULT_SELECTION = json.dumps(list(SECTION_BY_KEY))


def decode_selection(value):
    """Tolerate old/invalid settings, remove duplicates, and preserve click order."""
    try:
        keys = json.loads(value)
    except (TypeError, ValueError):
        keys = list(SECTION_BY_KEY)
    if not isinstance(keys, list):
        keys = list(SECTION_BY_KEY)
    return list(dict.fromkeys(key for key in keys
                              if isinstance(key, str) and key in SECTION_BY_KEY))


def select_section(value, key, extend=False):
    """Click isolates; Shift-click removes or appends without sorting survivors."""
    keys = decode_selection(value)
    if key not in SECTION_BY_KEY:
        raise ValueError(f'Unknown sidebar section: {key}')
    if not extend:
        keys = [key]
    elif key in keys:
        keys.remove(key)
    else:
        keys.append(key)
    return json.dumps(keys)