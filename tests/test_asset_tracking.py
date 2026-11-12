"""Explicit dependency checks and protected UV guards; disposable Blender only."""
import importlib
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace

import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
sys.path.insert(0, str(ROOT / 'tests'))
from test_asset_uv import refuses
from test_painter_ui_parity import Layout


def state(owner, name):
    return next(item.state for item in owner.stages if item.name == name)


def main():
    assert bpy.app.background
    addon = importlib.import_module(ROOT.name)
    addon.register()
    addon.feature_manager.sync(SimpleNamespace(enable_substance_painter=True))
    prefix = ROOT.name + '.features.asset_processing.'
    generation, uv, tracking, identity, model, validation = [importlib.import_module(prefix + name)
        for name in ('generation', 'uv', 'tracking', 'identity', 'ui', 'validation')]
    try:
        bpy.ops.mesh.primitive_cube_add()
        source = bpy.context.object
        bpy.ops.mbt.asset_edit(action='CREATE')
        settings = bpy.context.scene.mbt_assets
        asset = settings.assets[0]
        component = asset.components[0]
        tracking.check(bpy.context, asset)
        assert state(component, 'LOW') == 'NOT_PROCESSED'
        component.subdivision = 0
        generation.generate(bpy.context, asset, component)
        before = generation.fingerprint(component.low)
        tracking.check(bpy.context, asset)
        assert state(component, 'LOW') == state(component, 'HIGH') == 'CURRENT'
        assert state(component, 'UV') == 'BLOCKED'
        component.crease_angle += 1
        tracking.check(bpy.context, asset)
        assert state(component, 'HIGH') == 'OUTDATED' and state(component, 'LOW') == 'CURRENT'
        component.crease_angle -= 1
        modifier = source.modifiers.new('Artist Bevel', 'BEVEL')
        modifier.width = 0.15
        tracking.check(bpy.context, asset)
        assert state(component, 'LOW') == state(component, 'HIGH') == 'OUTDATED'
        source.modifiers.remove(modifier)
        source.data.vertices[0].co.x += 0.1
        tracking.check(bpy.context, asset)
        assert state(component, 'HIGH') == 'OUTDATED'
        assert generation.fingerprint(component.low) == before
        source.data.vertices[0].co.x -= 0.1
        generation.generate(bpy.context, asset, component)
        collection = bpy.data.collections.new('Artist Texture Set')
        component.texture_collection = collection
        key = identity.token(bpy.context, component, asset)
        component.uv_locked = False
        uv.build(bpy.context, asset, component)
        signature = component.uv_proposal_settings
        collection.name = 'Renamed Artist Set'
        assert identity.token(bpy.context, component, asset) == key
        assert uv.settings_signature(bpy.context, asset, [component]) == signature
        uv.apply(bpy.context, asset, component)
        tracking.check(bpy.context, asset)
        assert state(component, 'UV') == 'CURRENT'
        # Source-only edits do not invalidate UV inputs for preserved working lows.
        source.data.vertices[0].co.z += 0.2
        tracking.check(bpy.context, asset)
        assert state(component, 'UV') == 'CURRENT'
        baseline = component.stage_baselines
        low = component.low
        low.data.uv_layers.new(name='Alternate')
        low.data.uv_layers.active_index = 0
        uv.build(bpy.context, asset, component)
        protection = low.data.attributes.new(uv.PROTECTED_ATTRIBUTE, 'BOOLEAN', 'EDGE')
        protection.data[0].value = True
        refuses(lambda: uv.apply(bpy.context, asset, component), 'changed')
        low.data.attributes.remove(protection)
        uv.build(bpy.context, asset, component)
        low.data.uv_layers.active_index = 1
        refuses(lambda: uv.apply(bpy.context, asset, component), 'changed')
        low.data.uv_layers.active_index = 0
        # Directly tamper an originally pinned proposal; working low remains untouched.
        uv.clear_component(component)
        low.data.uv_layers.active.data[0].pin_uv = True
        proposal = bpy.data.objects.new('Pinned proposal', low.data.copy())
        bpy.context.scene.collection.objects.link(proposal)
        proposal['mbt_uv_proposal'] = component.component_id
        component.uv_preview = proposal
        component.uv_batch = 'test'
        component.uv_baseline = generation.fingerprint(low) + uv.layout_signature(low.data)
        component.uv_proposal_settings = uv.settings_signature(bpy.context, asset, [component])
        proposal.data.uv_layers.active.data[0].uv.x += 0.1
        refuses(lambda: uv.apply(bpy.context, asset, component), 'artist-pinned')
        uv.clear_component(component)
        low.data.uv_layers.active.data[0].pin_uv = False
        duplicate = asset.components.add()
        duplicate.component_id = 'duplicate'
        duplicate.low = low
        refuses(lambda: uv.writable(bpy.context, [component]), 'shared by multiple')
        asset.components.remove(1)
        # UI performs no scans or baseline adoption.
        tracking.check(bpy.context, asset)
        assert state(component, 'UV') == 'OUTDATED'
        model.draw(Layout([]), bpy.context, False)
        assert component.stage_baselines == baseline
        validation.validate(bpy.context, asset)
        assert any('base mesh only' in row.reason for row in asset.issues)
        tracking.check(bpy.context, asset)
        assert state(asset, 'VALIDATION') == 'CURRENT'
        low.data.vertices[0].co.x += 0.01
        tracking.check(bpy.context, asset)
        assert state(asset, 'VALIDATION') == 'OUTDATED'
        # Preview restores selection and never changes collection restrictions.
        uv.build(bpy.context, asset, component)
        selected, active = list(bpy.context.selected_objects), bpy.context.active_object
        uv.show(bpy.context, asset, component)
        uv.preview.restore()
        assert list(bpy.context.selected_objects) == selected and bpy.context.active_object == active
        # Handler restoration and failure paths do not unlock artist collections.
        uv.show(bpy.context, asset, component)
        uv.preview.before_save_or_load(None)
        assert list(bpy.context.selected_objects) == selected and bpy.context.active_object == active
        component.uv_preview.hide_select = True
        refuses(lambda: uv.show(bpy.context, asset, component), 'selection-locked')
        assert component.uv_preview.hide_select
        component.uv_preview.hide_select = False
        with tempfile.TemporaryDirectory() as directory:
            exporter = importlib.import_module(prefix + 'export')
            bpy.context.scene.mbt_painter.output_dir = directory
            exporter.export_asset(bpy.context, asset)
            tracking.check(bpy.context, asset)
            assert state(asset, 'EXPORT') == 'CURRENT'
            bpy.context.scene.mbt_painter.normal_format = 'DIRECTX'
            tracking.check(bpy.context, asset)
            assert state(asset, 'EXPORT') == 'OUTDATED'
            # A shared member changes the UV signature; unrelated scene edits do not.
            previous = tracking.uv_inputs(bpy.context, asset, component)
            bpy.ops.mesh.primitive_cube_add(location=(10, 0, 0))
            unrelated = bpy.context.object
            assert tracking.uv_inputs(bpy.context, asset, component) == previous
            duplicate = asset.components.add()
            duplicate.component_id = 'shared-layout-member'
            duplicate.low = unrelated
            duplicate.texture_collection = component.texture_collection
            duplicate.texture_set_id = component.texture_set_id
            assert tracking.uv_inputs(bpy.context, asset, component) != previous
            asset.components.remove(1)
            bpy.ops.wm.save_as_mainfile(filepath=str(Path(directory) / 'tracking.blend'))
            bpy.ops.wm.open_mainfile(filepath=str(Path(directory) / 'tracking.blend'))
            asset = bpy.context.scene.mbt_assets.assets[0]
            component = asset.components[0]
            assert identity.token(bpy.context, component, asset) == key
            tracking.check(bpy.context, asset)
            assert state(component, 'HIGH') == 'OUTDATED'
            # Legacy/invalid/versioned baselines never become current by checking.
            component.stage_baselines = '{}'
            tracking.check(bpy.context, asset)
            assert state(component, 'LOW') == 'UNKNOWN'
            component.stage_baselines = json.dumps({'LOW': {'revision': -1, 'inputs': 'old'}})
            tracking.check(bpy.context, asset)
            assert state(component, 'LOW') == 'UNKNOWN'
        print('PASS: stage signatures, source/settings changes, preserved lows, UV guards, collection identity, validation freshness, preview restoration, reload and legacy baselines')
    finally:
        addon.unregister()


if __name__ == '__main__':
    main()