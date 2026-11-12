"""Unreal-only integration check. Use ONLY the generated mbt_unreal_test_ project."""

import json
from pathlib import Path
import tempfile

import unreal

ROOT = Path(__file__).resolve().parents[1]
project = Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.get_project_file_path())).resolve()
assert project.parent.name.startswith('mbt_unreal_test_'), 'Disposable test project required'
scope = {}
exec((ROOT / 'features/unreal_bridge/unreal_side.py').read_text(), scope)
request = {'action': 'SEND', 'project': str(project), 'destination': '/Game/Props',
           'replace': False, 'assets': [{'name': 'SM_BridgeTest',
                                        'file': str(project.parent / 'SM_BridgeTest.fbx')}]}
result = scope['run'](request)
assert result['assets'] == ['/Game/Props/SM_BridgeTest']
mesh = unreal.EditorAssetLibrary.load_asset('/Game/Props/SM_BridgeTest')
assert isinstance(mesh, unreal.StaticMesh)
assert isinstance(mesh.get_editor_property('asset_import_data'), unreal.InterchangeAssetImportData)
bounds = mesh.get_bounds()
assert abs(bounds.box_extent.x - 250) < 3, str(bounds)
assert abs(bounds.box_extent.z - 100) < 3, str(bounds)
try:
    scope['run'](request)
except RuntimeError as exc:
    assert 'already exists' in str(exc)
else:
    raise AssertionError('Overwrite protection failed')
request['replace'] = True
assert scope['run'](request)['assets'] == result['assets']
tools = unreal.AssetToolsHelpers.get_asset_tools()
material = tools.create_asset('M_Test', '/Game/Materials', unreal.Material, unreal.MaterialFactoryNew())
library = unreal.MaterialEditingLibrary
color = library.create_material_expression(material, unreal.MaterialExpressionVectorParameter, -300, 0)
color.set_editor_property('parameter_name', 'BaseColor')
color.set_editor_property('default_value', unreal.LinearColor(0.8, 0.1, 0.2, 1))
library.connect_material_property(color, '', unreal.MaterialProperty.MP_BASE_COLOR)
library.recompile_material(material)
unreal.EditorAssetLibrary.save_loaded_asset(material)
listed = scope['run']({'action': 'MATERIALS', 'project': str(project)})
assert '/Game/Materials/M_Test.M_Test' in listed['materials'], listed
preview = scope['run']({'action': 'PREVIEW', 'project': str(project), 'material': material.get_path_name()})
assert abs(preview['preview']['base_color'][0] - 0.8) < 0.001, preview
texture = unreal.load_asset('/Engine/EngineResources/DefaultTexture.DefaultTexture')
assert isinstance(texture, unreal.Texture2D)
sample = library.create_material_expression(material, unreal.MaterialExpressionTextureSampleParameter2D, -300, 200)
sample.set_editor_property('parameter_name', 'Albedo')
sample.set_editor_property('texture', texture)
library.recompile_material(material)
instance = tools.create_asset('MI_Test', '/Game/Materials', unreal.MaterialInstanceConstant,
                              unreal.MaterialInstanceConstantFactoryNew())
library.set_material_instance_parent(instance, material)
library.set_material_instance_vector_parameter_value(instance, 'BaseColor', unreal.LinearColor(0.2, 0.3, 0.4, 1))
instance_preview = scope['run']({'action': 'PREVIEW', 'project': str(project), 'material': instance.get_path_name()})
assert abs(instance_preview['preview']['base_color'][0] - 0.2) < 0.001, instance_preview
assert Path(instance_preview['preview']['textures']['base_color']).is_file(), instance_preview
(project.parent / 'preview.json').write_text(json.dumps(instance_preview['preview']))
bindings = json.loads((project.parent / 'material_bindings.json').read_text())
request['assets'] = [{'name': 'SM_Scaled', 'file': str(project.parent / 'SM_Scaled.fbx'), 'materials': bindings}]
request['replace'] = False
before_linked = set(unreal.EditorAssetLibrary.list_assets('/Game', recursive=True))
scope['run'](request)
scaled = unreal.load_asset('/Game/Props/SM_Scaled')
assert abs(scaled.get_bounds().box_extent.x - 625) < 6
assert scaled.get_material(0) == material
created = set(unreal.EditorAssetLibrary.list_assets('/Game', recursive=True)) - before_linked
assert created == {'/Game/Props/SM_Scaled.SM_Scaled'}, created
request['replace'] = True
scope['run'](request)
assert scaled.get_material(0) == material
assert set(unreal.EditorAssetLibrary.list_assets('/Game', recursive=True)) - before_linked == created
# A second mesh using the same linked material must not create shader artifacts.
request['replace'] = False
request['assets'][0]['name'] = 'SM_ScaledSecond'
scope['run'](request)
assert unreal.load_asset('/Game/Props/SM_ScaledSecond').get_material(0) == material
created = set(unreal.EditorAssetLibrary.list_assets('/Game', recursive=True)) - before_linked
assert created == {'/Game/Props/SM_Scaled.SM_Scaled', '/Game/Props/SM_ScaledSecond.SM_ScaledSecond'}, created
request['project'] = str(project.parent / 'Wrong.uproject')
try:
    scope['run'](request)
except RuntimeError as exc:
    assert 'differs' in str(exc)
else:
    raise AssertionError('Project identity check failed')
message = 'PASS UE 5.7 import / export scale / material list / instance parameters / texture export / linked material reimport / safety guards'
(project.parent / 'unreal_result.txt').write_text(message)
unreal.log(message)