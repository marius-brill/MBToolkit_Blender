"""Regenerate source-ordered modifier UI data from a local Blender source directory.

Run in disposable background Blender with -- --source-dir <modifiers/intern>
--output <absolute path>. No networking or code execution from source text.
"""

import argparse
from pathlib import Path
import pprint
import re
import sys

import bpy


def functions(text):
    result = {}
    for match in re.finditer(r'\b(?:static\s+)?void\s+(\w+)\([^;{}]*\)\s*\{', text):
        start = match.end()
        depth = 1
        end = start
        while depth and end < len(text):
            depth += (text[end] == '{') - (text[end] == '}')
            end += 1
        result[match[1]] = text[start:end - 1]
    return result


def properties(body):
    result = []
    # Native property flags and labels are retained; layout pointers may be
    # written with either '.' or '->'. Only modifier-owned properties belong here.
    pattern = r'(?:\.|->)(prop|prop_search)\(\s*(?:ptr|modifier_ptr),\s*"([^"]+)"\s*,([^;]*?);'
    for match in re.finditer(pattern, body, re.S):
        name, args = match[2], match[3]
        if any(item[0] == name for item in result):
            continue
        label = re.search(r'(?:IFACE_|TIP_)\("([^"]*)"\)', args)
        options = {}
        if label:
            options['text'] = label[1]
        if 'ITEM_R_EXPAND' in args:
            options['expand'] = True
        if 'ITEM_R_SLIDER' in args:
            options['slider'] = True
        result.append((name, options))
    # Shared vertex-group helper owns its own search/inversion widgets.
    for match in re.finditer(r'modifier_vgroup_ui\([^;]*?"([^"]+)"\s*,\s*"([^"]+)"', body, re.S):
        for name in match.groups():
            if not any(item[0] == name for item in result):
                result.append((name, {}))
    for match in re.finditer(r'template_(curve_mapping|curve_profile|color_ramp)\([^;]*?ptr,\s*"([^"]+)"', body, re.S):
        result.append((match[2], {'widget': match[1]}))
    return result


def sections(text):
    funcs = functions(text)
    body = funcs.get('panel_draw', '')
    # Inline native panels (especially modern Grease Pencil modifiers) are split
    # before collecting properties, so Influence is not flattened into the body.
    boundaries = list(re.finditer(r'\.panel_prop\(\s*C,\s*ptr,\s*"([^"]+)"(?:\s*,\s*IFACE_\("([^"]+)"\))?', body))
    main = body[:boundaries[0].start()] if boundaries else body
    result = [('Settings', properties(main), None)]
    for index, match in enumerate(boundaries):
        end = boundaries[index + 1].start() if index + 1 < len(boundaries) else len(body)
        content = body[match.end():end]
        title = match[2] or match[1].removeprefix('open_').removesuffix('_panel').replace('_', ' ').title()
        props = properties(content)
        for helper in re.findall(r'greasepencil::(draw_\w+_settings)\(', content):
            props.append(('@' + helper, {}))
        result.append((title, props, match[1]))
    # Registered native subpanels, in registration order rather than source order.
    register = funcs.get('panel_register', '')
    for match in re.finditer(r'modifier_subpanel_register\(\s*region_type,\s*"([^"]+)",\s*"([^"]*)",\s*(\w+),\s*(\w+)', register, re.S):
        identifier, title, header, draw = match.groups()
        title = title or identifier.replace('_', ' ').title()
        props = properties(funcs.get(header, '') + funcs.get(draw, ''))
        result.append((title, props, None))
    return result


def main():
    assert bpy.app.background, 'Run only in a disposable background Blender process'
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
    source = {}
    for path in sorted(args.source_dir.glob('MOD_*.cc')):
        text = path.read_text(encoding='utf-8')
        match = re.search(r'/\*srna\*/\s*&RNA_(\w+)', text)
        if match and 'panel_draw' in text:
            source[match[1]] = (path.name, sections(text))
    layouts = {}
    # Walk object compatibility instead of assuming every enum is a mesh modifier.
    owners = []
    for kind, data in (
            ('MESH', bpy.data.meshes.new('LayoutAudit')),
            ('CURVE', bpy.data.curves.new('LayoutAudit', 'CURVE')),
            ('LATTICE', bpy.data.lattices.new('LayoutAudit')),
            ('VOLUME', bpy.data.volumes.new('LayoutAudit')),
            ('CURVES', bpy.data.hair_curves.new('LayoutAudit')),
            ('GREASEPENCIL', bpy.data.grease_pencils.new('LayoutAudit'))):
        owners.append(bpy.data.objects.new('LayoutAudit' + kind, data))
    for item in bpy.types.Modifier.bl_rna.properties['type'].enum_items_static:
        for obj in owners:
            try:
                modifier = obj.modifiers.new('LayoutAudit', item.identifier)
            except RuntimeError:
                continue
            if modifier is None:
                continue
            rna = modifier.bl_rna.identifier
            if rna not in source:
                raise RuntimeError(f'Missing native source for {item.identifier}: {rna}')
            layouts[item.identifier] = source[rna]
            obj.modifiers.remove(modifier)
            break
        else:
            # Particle System is created through its dedicated operator, not new().
            if item.identifier == 'PARTICLE_SYSTEM':
                layouts[item.identifier] = source['ParticleSystemModifier']
            else:
                raise RuntimeError(f'Uninstantiated modifier: {item.identifier}')
    header = '''# SPDX-FileCopyrightText: 2005-2026 Blender Authors
# SPDX-FileCopyrightText: 2026 MBToolkit contributors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Generated native panel order/labels; do not edit by hand.

Source: Blender fbe6228777e7, source/blender/modifiers/intern/MOD_*.cc.
Regenerate with tests/generate_modifier_layouts.py; runtime never downloads source.
This describes panel organization, not executable native C++ draw callbacks.
"""

SOURCE_COMMIT = 'fbe6228777e7'

'''
    args.output.write_text(header + 'LAYOUTS = ' + pprint.pformat(layouts, width=100, sort_dicts=True) + '\n', encoding='utf-8')
    print(f'Generated {len(layouts)} native-style modifier layouts: {args.output}')


if __name__ == '__main__':
    main()