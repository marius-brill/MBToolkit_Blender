"""Standalone Painter FBX handoff using the existing snapshot exporter."""
import json
from pathlib import Path
import shutil
import tempfile
import bpy
from ..substance_painter import jobs
from ..substance_painter.evaluation import available, finish_steps
from .identity import token


def high_objects(component):
    if component.high_mode == 'DYNABOOL':
        return [component.generated_high] if component.generated_high else []
    if component.high_mode == 'CUSTOM':
        return list(dict.fromkeys(reference.mesh for reference in component.highs if reference.mesh))
    return []


def plan(context, asset, export_low=True, export_high=True):
    if not export_low and not export_high:
        raise ValueError('Enable Low Poly or High Poly export')
    if not asset.components:
        raise ValueError('Asset has no components')
    lows, highs, names, materials = [], [], {}, []
    material_keys = {}
    for component in asset.components:
        prefix = 'MBTA_' + asset.asset_id.replace('-', '') + '_' + component.component_id.replace('-', '')
        if export_low:
            low = component.low
            if low is None:
                raise ValueError(component.name + ': prepare a low first')
            if low in lows:
                raise ValueError('A low is assigned to more than one component')
            lows.append(low)
            names[low] = prefix + '_low'
            set_key = token(context, component, asset)
            material_name = 'MBTAsset_' + jobs.safe_name(set_key)
            if material_name in material_keys and material_keys[material_name] != set_key:
                raise ValueError('Texture-set names collide after sanitization')
            material_keys[material_name] = set_key
            materials.append(material_name)
        if export_high:
            objects = high_objects(component)
            if component.high_mode == 'DISABLED':
                continue
            if not objects:
                raise ValueError(component.name + ': generate or assign high meshes first')
            for index, high in enumerate(objects):
                if high in highs:
                    raise ValueError('Shared highs across components need an explicit shared bake group; export separately for now')
                highs.append(high)
                names[high] = prefix + '_high' + (f'_{index:03d}' if index else '')
    if set(lows) & set(highs):
        raise ValueError('Low and high inputs must be separate mesh objects')
    for obj in lows + highs:
        if obj.type != 'MESH' or obj.name not in context.scene.objects:
            raise ValueError('Export inputs must be meshes in the current scene')
        if jobs.singular_transform(obj.matrix_world):
            raise ValueError(obj.name + ': singular transform')
    if not lows and not highs:
        raise ValueError('No exportable meshes')
    return lows, highs, names, materials


def export_asset(context, asset):
    settings = context.scene.mbt_assets
    lows, highs, names, materials = plan(context, asset, settings.export_low, settings.export_high)
    output = context.scene.mbt_painter.output_dir
    if not output.strip() or (output.startswith('//') and not bpy.data.filepath):
        raise ValueError('Choose an absolute output folder or save the blend file first')
    parent = Path(bpy.path.abspath(output)).resolve()
    parent.mkdir(parents=True, exist_ok=True)
    directory = Path(tempfile.mkdtemp(prefix=jobs.safe_name(asset.name) + '_', dir=parent))
    try:
        with available(context, lows + highs):
            # The decorated bake exporter scopes legacy texture-set inputs. Supply
            # our explicit asset inputs instead, without registering another exporter.
            if lows:
                finish_steps(jobs.export_steps.__wrapped__(context, lows, directory / 'low.fbx',
                    low=True, names=names, material_names=materials))
            if highs:
                finish_steps(jobs.export_steps.__wrapped__(context, highs, directory / 'high.fbx', names=names))
        manifest = {'schema_version': 1, 'asset_id': asset.asset_id, 'asset': asset.name,
                    'destination': 'Substance 3D Painter', 'normal_format': context.scene.mbt_painter.normal_format,
                    'low': 'low.fbx' if lows else None, 'high': 'high.fbx' if highs else None,
                    'names': {obj.name: name for obj, name in names.items()},
                    'texture_sets': materials,
                    'components': [{'id': component.component_id, 'name': component.name} for component in asset.components]}
        (directory / 'asset.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    except Exception:
        shutil.rmtree(directory)
        raise
    settings.last_export = str(directory)
    from . import tracking
    tracking.record(asset, 'EXPORT', tracking.export_inputs(context, asset))
    return 'Exported to ' + str(directory)