"""Control/action parity and side-effect-free drawing in disposable Blender."""
import importlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch

import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))


class Layout:
    def __init__(self, records, enabled=True):
        self.records = records
        self.enabled = enabled

    def row(self, **kwargs):
        return Layout(self.records, self.enabled)

    column = row
    box = row
    split = row

    def label(self, **kwargs):
        self.records.append(('label', kwargs.get('text'), self.enabled))

    def separator(self, **kwargs):
        pass

    def prop(self, obj, name, **kwargs):
        assert hasattr(obj, name), name
        self.records.append(('prop', name, self.enabled))

    def prop_enum(self, obj, name, value, **kwargs):
        assert value in obj.bl_rna.properties[name].enum_items.keys()
        self.records.append(('map', value, self.enabled))

    def template_list(self, *args, **kwargs):
        self.records.append(('list', args[0], self.enabled))

    def operator(self, name, **kwargs):
        category, action = name.split('.')
        assert getattr(getattr(bpy.ops, category), action).get_rna_type()
        arguments = SimpleNamespace()
        self.records.append(('operator', name, arguments, self.enabled))
        return arguments


def main():
    assert bpy.app.background, 'Use disposable background Blender'
    addon = importlib.import_module(ROOT.name)
    addon.register()
    addon.feature_manager.sync(SimpleNamespace(enable_substance_painter=True))
    painter = importlib.import_module(ROOT.name + '.features.substance_painter')
    issues = importlib.import_module(ROOT.name + '.features.substance_painter.issues')
    runtime = painter.operators.runtime
    try:
        bpy.ops.mbt.painter_texture_set(action='ADD')
        props = bpy.context.scene.mbt_painter
        assert props.ui_tab == 'BAKE'
        assert props.bake_maps == {'NORMAL', 'AO', 'CURVATURE'}
        props.bake_maps = {key for key, _ in painter.settings.BAKE_MAPS}
        props.bake_settings = props.advanced = True
        props.projection_report = 'Projection fixture'
        props.matching_report = 'Matching fixture'
        props.preparation_timings = json.dumps([{'stage': 'Long stage ' * 20, 'seconds': 2.5}])
        props.report = 'Saved bake job.json is missing: fixture'
        bpy.ops.mesh.primitive_cube_add()
        obj = bpy.context.object
        issues.publish(bpy.context, [{'object': obj.name, 'reason': 'UV fixture',
            'blocking': True, 'targets': [obj.name], 'faces': [0]}])
        before = (set(props.bake_maps), props.texture_collection, obj.mbt_bake_target,
                  tuple(bpy.context.selected_objects), bpy.context.active_object)
        for width in (240, 720):
            view = SimpleNamespace(region_to_view=lambda x, y: (x, y))
            context = SimpleNamespace(scene=bpy.context.scene, active_object=obj,
                view_layer=bpy.context.view_layer, preferences=bpy.context.preferences,
                region=SimpleNamespace(width=width, view2d=view))
            for busy in (False, True):
                records = []
                with patch.object(runtime, 'busy', return_value=busy), \
                        patch.object(runtime, '_cancel', SimpleNamespace(is_set=lambda: False)):
                    for tab in ('BAKE', 'MODEL', 'EXPORT'):
                        props.ui_tab = tab
                        tab_records = []
                        painter.draw(Layout(tab_records), context)
                        assert ('prop', 'ui_tab', True) in tab_records
                        if tab == 'MODEL':
                            assert any(r[0] == 'operator' and r[1] == 'mbt.asset_edit'
                                       and r[3] == (not busy) for r in tab_records)
                        if tab == 'EXPORT':
                            assert any(r[0] == 'operator' and r[1] == 'mbt.asset_process' for r in tab_records)
                        if busy:
                            assert any(r[0] == 'operator' and r[1] == 'mbt.painter_cancel'
                                       and r[3] for r in tab_records), tab
                        if tab == 'BAKE':
                            records.extend(tab_records)
                # Preserve the pre-split workflow in Bake, not merely across tabs.
                order = [('prop', 'texture_collection'), ('prop', 'low_collection'),
                         ('prop', 'high_collection'), ('prop', 'project_name'),
                         ('prop', 'output_dir'), ('prop', 'resolution'),
                         ('label', 'Requested Bake Maps'), ('label', 'Mesh Matching'),
                         ('label', 'Bake'), ('prop', 'bake_settings'),
                         ('label', 'Bake Settings'), ('label', 'Bake Status'),
                         ('prop', 'advanced'), ('prop', 'export_config')]
                positions = [next(i for i, record in enumerate(records)
                                  if record[:2] == item) for item in order]
                assert positions == sorted(positions), positions
                maps = {record[1] for record in records if record[0] == 'map'}
                assert maps == props.bake_maps
                fields = {record[1] for record in records if record[0] == 'prop'}
                required = (set(painter.settings.SET_FIELDS) - {'bake_maps'}) | {
                    'project_name', 'output_dir', 'normal_format', 'project_template',
                    'replace_materials', 'projection_threshold', 'export_config',
                    'mbt_bake_group', 'mbt_bake_target', 'bake_settings', 'advanced'}
                assert required <= fields, required - fields
                ops = [record for record in records if record[0] == 'operator']
                def has(name, **args):
                    return any(record[1] == name and all(getattr(record[2], key, None) == value
                        for key, value in args.items()) for record in ops)
                for action in ('AUTO', 'OPEN', 'EXPORT', 'TEST', 'CONNECT', 'CAPABILITIES'):
                    assert has('mbt.painter_connect', action=action), action
                connection_order = [record[2].action for record in ops
                                    if record[1] == 'mbt.painter_connect']
                assert connection_order == ['AUTO', 'OPEN', 'EXPORT', 'TEST', 'CONNECT', 'CAPABILITIES']
                for action in ('PROJECTION', 'VALIDATE', 'IMPORT'):
                    assert has('mbt.painter_action', action=action), action
                for role in ('LOW', 'HIGH'):
                    assert has('mbt.painter_assign', role=role)
                for action in ('ADD', 'REMOVE'):
                    assert has('mbt.painter_texture_set', action=action)
                for flag in ('all_meshes', 'frame', 'candidates'):
                    assert has('mbt.painter_issue_select', **{flag: True})
                for name in ('mbt.painter_issue_details', 'mbt.painter_issue_faces',
                             'mbt.painter_new_project', 'mbt.painter_status_details'):
                    assert has(name), name
                assert next(record[3] for record in ops if record[1] == 'mbt.painter_cancel') == busy
                assert next(record[3] for record in ops if record[1] == 'mbt.painter_connect'
                            and record[2].action == 'AUTO') == (not busy)
        assert before == (set(props.bake_maps), props.texture_collection, obj.mbt_bake_target,
                          tuple(bpy.context.selected_objects), bpy.context.active_object)
        props.advanced = props.bake_settings = False
        props.ui_tab = 'BAKE'
        records = []
        painter.draw(Layout(records), bpy.context)
        assert ('prop', 'advanced', True) in records
        assert ('prop', 'bake_settings', True) in records
        assert not any(r[0] == 'prop' and r[1] == 'export_config' for r in records)
        records = []
        issues.MBT_UL_painter_issues.draw_filter(SimpleNamespace(filter_name=''), bpy.context, Layout(records))
        assert ('prop', 'issue_blocking_only', True) in records
        print('PASS: unchanged Bake order, Model records, cross-tab cancellation, narrow/wide, busy/idle, all controls/actions, filters and side-effect-free drawing')
    finally:
        addon.unregister()


if __name__ == '__main__':
    main()