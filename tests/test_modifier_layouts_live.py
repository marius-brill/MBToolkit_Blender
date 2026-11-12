"""Real-layout all-type audit; run disposable GUI Blender without --background."""

import importlib
from pathlib import Path
import sys
import tempfile
import traceback

import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon = importlib.import_module(ROOT.name)
ui = importlib.import_module(ROOT.name + '.features.modifier_layouts')
audit = importlib.import_module(ROOT.name + '.tests.test_modifier_layouts')
RESULT = Path(tempfile.gettempdir()) / 'mbt_modifier_layouts_live_result.txt'
pending = []
seen = set()
errors = []
current = None
original_section = ui.section


def open_section(layout, md, title, state, popup, **kwargs):
    ui._section_open[ui.section_key(md, title)] = True
    return original_section(layout, md, title, state, popup, **kwargs)


def draw(self, context):
    if current is None:
        return
    obj, md = current
    try:
        with context.temp_override(object=obj, active_object=obj):
            ui.draw(self.layout, context, md)
            # Exercise popup-compatible boxes with real widgets as well.
            ui.draw(self.layout, context, md, popup=True)
        seen.add(md.type)
    except Exception:
        errors.append(md.type + '\n' + traceback.format_exc())


def finish(message):
    RESULT.write_text(message, encoding='utf-8')
    bpy.ops.wm.quit_blender()


def step():
    global current
    try:
        if errors:
            raise AssertionError('\n'.join(errors))
        if current:
            assert current[1].type in seen, current[1].type
        if not pending:
            assert seen == set(ui.LAYOUTS), set(ui.LAYOUTS) - seen
            finish(f'PASS {len(seen)} types with real UI layouts / all sections open / popup widgets')
            return None
        current = pending.pop(0)
        obj, md = current
        bpy.context.view_layer.objects.active = obj
        obj.modifiers.active = md
        for area in bpy.context.screen.areas:
            if area.type == 'PROPERTIES':
                area.spaces.active.context = 'MODIFIER'
                area.tag_redraw()
        return 0.15
    except Exception:
        finish(traceback.format_exc())
        return None


def start():
    try:
        assert not bpy.app.background
        addon.register()
        ui.section = open_section
        from bl_ui.properties_data_modifier import DATA_PT_modifiers
        DATA_PT_modifiers.draw = draw
        owners = audit.fixtures()
        for kind in sorted(ui.LAYOUTS):
            for obj in owners:
                try:
                    md = obj.modifiers.new('Audit ' + kind, kind)
                except RuntimeError:
                    continue
                if md is not None:
                    break
            else:
                assert kind == 'PARTICLE_SYSTEM'
                obj = owners[0]
                bpy.context.view_layer.objects.active = obj
                obj.select_set(True)
                bpy.ops.object.particle_system_add()
                md = next(m for m in obj.modifiers if m.type == kind)
            md.show_viewport = False
            md.show_render = False
            for prop in md.bl_rna.properties:
                if prop.identifier.startswith('open_') and prop.type == 'BOOLEAN' and not prop.is_readonly:
                    setattr(md, prop.identifier, True)
            if kind == 'BEVEL':
                md.profile_type = 'CUSTOM'
            if kind == 'GREASE_PENCIL_TIME':
                md.mode = 'CHAIN'
            # Build a populated node input interface, not just an empty GN slot.
            if kind == 'NODES':
                group = bpy.data.node_groups.new('UILayoutAudit', 'GeometryNodeTree')
                group.interface.new_socket(name='Geometry', in_out='INPUT', socket_type='NodeSocketGeometry')
                group.interface.new_socket(name='Amount', in_out='INPUT', socket_type='NodeSocketFloat')
                md.node_group = group
            pending.append((obj, md))
        bpy.app.timers.register(step, first_interval=0.5)
    except Exception:
        finish(traceback.format_exc())
    return None


bpy.app.timers.register(start, first_interval=1.0)
print(f'All modifier layout GUI result: {RESULT}', flush=True)