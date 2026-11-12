"""All-type selected UI audit; disposable Blender --background --factory-startup."""

import importlib
from pathlib import Path
import sys
from types import SimpleNamespace

import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon = importlib.import_module(ROOT.name)
ui = importlib.import_module(ROOT.name + '.features.modifier_layouts')


class Layout:
    def __init__(self):
        self.props = []
        self.labels = []
        self.operators = []
        self.operator_options = []

    def row(self, **kwargs):
        return self

    column = box = row

    def panel(self, identifier, **kwargs):
        return self, self

    def panel_prop(self, data, name):
        assert name in data.bl_rna.properties
        return self, self

    def context_pointer_set(self, name, data):
        assert name in {'modifier', 'mbt_modifier_settings'} and isinstance(data, bpy.types.Modifier)

    def label(self, **kwargs):
        self.labels.append(kwargs['text'])

    def prop(self, data, name, **kwargs):
        assert name in data.bl_rna.properties, (data, name)
        assert not data.bl_rna.properties[name].is_hidden, (data, name)
        self.props.append((data, name))

    def prop_search(self, data, name, owner, collection, **kwargs):
        assert collection in owner.bl_rna.properties
        self.prop(data, name, **kwargs)

    def template_ID(self, data, name, **kwargs):
        self.prop(data, name)

    def template_curveprofile(self, data, name):
        assert isinstance(getattr(data, name), bpy.types.CurveProfile)

    def template_curve_mapping(self, data, name):
        assert isinstance(getattr(data, name), bpy.types.CurveMapping)

    def template_color_ramp(self, data, name, **kwargs):
        assert isinstance(getattr(data, name), bpy.types.ColorRamp)

    def template_list(self, listname, list_id, data, collection, owner, active, **kwargs):
        assert collection in data.bl_rna.properties
        assert active in owner.bl_rna.properties

    def operator(self, name, **kwargs):
        category, identifier = name.split('.')
        rna = getattr(getattr(bpy.ops, category), identifier).get_rna_type()
        self.operators.append((name, rna))
        self.operator_options.append((name, kwargs))

        class Operator:
            def __setattr__(self, key, value):
                prop = rna.properties.get(key)
                assert prop is not None, (name, key)
                if prop.type == 'ENUM':
                    assert value in prop.enum_items.keys(), (name, key, value, prop.enum_items.keys())

        return Operator()


def parity_cases(obj):
    md = obj.modifiers.new('Parity Array', 'ARRAY')
    context = SimpleNamespace(object=obj, selected_objects=[])
    try:
        ui._section_open.clear()
        def signature(popup):
            layout = Layout()
            ui.draw(layout, context, md, popup=popup)
            return ([name for data, name in layout.props], layout.operator_options)
        assert signature(False) == signature(True)
        names, _ = signature(False)
        assert 'relative_offset_displace' in names
        assert 'use_relative_offset' in names
        assert 'constant_offset_displace' in names  # native-style body remains disabled when off
        key = ui.section_key(md, 'Relative Offset')
        assert bpy.ops.mbt.modifier_section(key=key, object_name=obj.name,
            object_uid=str(obj.session_uid), uid=md.persistent_uid,
            state='', opened=True) == {'FINISHED'}
        assert signature(False) == signature(True)
        assert 'relative_offset_displace' not in signature(True)[0]
        for fit, expected in (('FIXED_COUNT', 'count'), ('FIT_LENGTH', 'fit_length'), ('FIT_CURVE', 'curve')):
            md.fit_type = fit
            names, _ = signature(False)
            assert expected in names
            assert all(name not in names for name in {'count', 'fit_length', 'curve'} - {expected})
        print('PASS popup/Properties control parity / shared section toggle / Array native-style headers and fit branches')
    finally:
        obj.modifiers.remove(md)
        ui._section_open.clear()


def fixtures():
    result = []
    for data in (bpy.data.meshes.new('LayoutMesh'), bpy.data.curves.new('LayoutCurve', 'CURVE'),
                 bpy.data.lattices.new('LayoutLattice'), bpy.data.volumes.new('LayoutVolume'),
                 bpy.data.hair_curves.new('LayoutCurves'), bpy.data.grease_pencils.new('LayoutGP')):
        obj = bpy.data.objects.new(data.name, data)
        bpy.context.collection.objects.link(obj)
        result.append(obj)
    return result


def run():
    assert bpy.app.background
    addon.register()
    try:
        owners = fixtures()
        parity_cases(owners[0])
        types = {item.identifier for item in bpy.types.Modifier.bl_rna.properties['type'].enum_items_static}
        original_section = ui.section
        def open_section(layout, md, title, state, popup, **kwargs):
            ui._section_open[ui.section_key(md, title)] = True
            if state and state in md.bl_rna.properties:
                setattr(md, state, True)
            return original_section(layout, md, title, state, popup, **kwargs)
        ui.section = open_section
        assert types == set(ui.LAYOUTS), (types - set(ui.LAYOUTS), set(ui.LAYOUTS) - types)
        checked = set()
        for kind in sorted(types):
            for obj in owners:
                try:
                    md = obj.modifiers.new('UIAudit', kind)
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
            obj.modifiers.active = md
            context = SimpleNamespace(object=obj, selected_objects=[])
            signature = tuple(obj.modifiers)
            for popup in (False, True):
                layout = Layout()
                ui.draw(layout, context, md, popup=popup)
                assert tuple(obj.modifiers) == signature and obj.modifiers.active == md
                # Exercise enum branches instead of only the default state.
                for prop in md.bl_rna.properties:
                    if prop.type != 'ENUM' or prop.is_readonly or prop.is_enum_flag:
                        continue
                    original = getattr(md, prop.identifier)
                    try:
                        for item in prop.enum_items:
                            try:
                                setattr(md, prop.identifier, item.identifier)
                            except TypeError:
                                continue  # Context-dependent enums may offer fewer choices.
                            ui.draw(Layout(), context, md, popup=popup)
                    finally:
                        setattr(md, prop.identifier, original)
            checked.add(kind)
            obj.modifiers.remove(md)
        assert checked == types
        print(f'PASS {len(checked)} modifier types / all writable enum branches / Properties and popup / valid RNA and operators / no draw-time stack mutation')
    finally:
        ui.section = original_section
        addon.unregister()


if __name__ == '__main__':
    run()