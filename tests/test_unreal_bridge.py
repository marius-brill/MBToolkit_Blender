"""Run in disposable background Blender; exports FBX and tests bridge lifecycle."""

import importlib
import json
from pathlib import Path
import sys
import tempfile

import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
bridge = importlib.import_module(f'{ROOT.name}.features.unreal_bridge')
common = importlib.import_module(f'{ROOT.name}.features.unreal_bridge.common')
export = importlib.import_module(f'{ROOT.name}.features.unreal_bridge.export')


def rejects(function, *args):
    try:
        function(*args)
    except common.BridgeError:
        return
    raise AssertionError(f'Expected validation error: {args}')


def run():
    assert bpy.app.background, 'Disposable background process only'
    for cycle in range(2):
        bridge.register()
        assert hasattr(bpy.types.Scene, 'mbt_unreal')
        assert bridge.MBT_PT_unreal.is_registered
        assert bpy.context.scene.mbt_unreal.destination == '/Game/Props'
        assert bpy.context.scene.mbt_unreal.export_scale == 1.0
        bridge.unregister()
        assert not hasattr(bpy.types.Scene, 'mbt_unreal')

    for value in ('SM_Chair', '_Mesh', 'Part123'):
        assert common.asset_name(value) == value
    for value in ('Chair.001', '../escape', 'two words', '', '1Mesh', 'x' * 101):
        rejects(common.asset_name, value)
    for value in ('/Engine/Props', '/Game/../Escape', '/Game//Props', '/Game/Bad.Name'):
        rejects(common.content_path, value)
    assert common.content_path('/Game/Props/') == '/Game/Props'

    work = Path(tempfile.mkdtemp(prefix='mbt_unreal_test_'))
    project = work / 'BridgeTest.uproject'
    project.write_text(json.dumps({'FileVersion': 3, 'EngineAssociation': '5.7',
                                 'Plugins': [{'Name': 'PythonScriptPlugin', 'Enabled': True},
                                             {'Name': 'EditorScriptingUtilities', 'Enabled': True}]}))
    (work / 'Content/Props').mkdir(parents=True)
    assert common.project_file(str(project)) == project
    assert common.folder_from_disk(project, work / 'Content') == '/Game'
    assert common.folder_from_disk(project, work / 'Content/Props') == '/Game/Props'
    rejects(common.folder_from_disk, project, work)

    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    root = bpy.data.objects.new('SM_BridgeTest', None)
    bpy.context.collection.objects.link(root)
    root.location = (10, 20, 30)
    root.rotation_euler.z = 0.4
    root.scale = (2, 2, 2)
    nested = bpy.data.objects.new('Nested', None)
    bpy.context.collection.objects.link(nested)
    nested.parent = root
    material = bpy.data.materials.new('BridgeTestMaterial')
    for index in range(2):
        bpy.ops.mesh.primitive_cube_add()
        obj = bpy.context.object
        obj.name = 'Part' + str(index)
        obj.parent = nested
        obj.location = (index * 3, 0, 0)
        obj.data.materials.append(material)
        uv = obj.data.uv_layers.active
        assert uv is not None
        if index == 1:
            obj.scale.x = -1
            obj.modifiers.new('Bevel', 'BEVEL').width = 0.1
    bpy.ops.object.select_all(action='DESELECT')
    root.select_set(True)
    nested.select_set(True)
    bpy.context.view_layer.objects.active = root
    bpy.context.view_layer.update()
    assert export.selected_roots(bpy.context) == [root]
    assert len(export.descendants(root)) == 2
    assert export.validate_roots(bpy.context) == [root]
    before = (set(bpy.data.objects), set(bpy.data.meshes), set(bpy.data.scenes),
              set(bpy.context.selected_objects), bpy.context.view_layer.objects.active,
              {obj: obj.matrix_world.copy() for obj in bpy.context.scene.objects})
    filepath = work / 'SM_BridgeTest.fbx'
    export.export_root(bpy.context, root, filepath)
    assert filepath.stat().st_size > 1000
    assert before[:5] == (set(bpy.data.objects), set(bpy.data.meshes), set(bpy.data.scenes),
                          set(bpy.context.selected_objects), bpy.context.view_layer.objects.active)
    assert all(obj.matrix_world == matrix for obj, matrix in before[5].items())
    # Round trip in a separate scene, preserving the source hierarchy.
    scene = bpy.data.scenes.new('RoundTrip')
    with bpy.context.temp_override(scene=scene, view_layer=scene.view_layers[0]):
        bpy.ops.import_scene.fbx(filepath=str(filepath))
    imported = [obj for obj in scene.objects if obj.type == 'MESH']
    assert len(imported) == 1
    assert len(imported[0].data.materials) == 1
    assert imported[0].data.uv_layers
    coords = [imported[0].matrix_world @ v.co for v in imported[0].data.vertices]
    assert abs(min(v.x for v in coords) + 1) < 0.02
    assert abs(max(v.x for v in coords) - 4) < 0.02
    assert max(abs(v.z) for v in coords) < 1.02
    materials = importlib.import_module(f'{ROOT.name}.features.unreal_bridge.materials')
    preview = materials.create_preview(str(project), {'path': '/Game/Materials/M_Test.M_Test',
        'base_color': [0.8, 0.1, 0.2, 1.0], 'roughness': 0.25, 'metallic': 0.7})
    assert materials.assign(bpy.context, preview) == 2
    assert preview.node_tree.nodes.get('Principled BSDF').inputs['Metallic'].default_value > 0.69
    materials_before = set(bpy.data.materials)
    scaled = work / 'SM_Scaled.fbx'
    bindings = export.export_root(bpy.context, root, scaled, 2.5, str(project))
    assert list(bindings.values()) == ['/Game/Materials/M_Test.M_Test']
    assert materials_before == set(bpy.data.materials), 'Temporary proxy materials leaked'
    rejects(export.export_root, bpy.context, root, scaled, 0, str(project))
    rejects(export.export_root, bpy.context, root, scaled, float('nan'), str(project))
    rejects(export.export_root, bpy.context, root, scaled, 1, str(work / 'Other.uproject'))
    scaled_scene = bpy.data.scenes.new('ScaledRoundTrip')
    with bpy.context.temp_override(scene=scaled_scene, view_layer=scaled_scene.view_layers[0]):
        bpy.ops.import_scene.fbx(filepath=str(scaled))
    scaled_obj = next(obj for obj in scaled_scene.objects if obj.type == 'MESH')
    scaled_coords = [scaled_obj.matrix_world @ v.co for v in scaled_obj.data.vertices]
    assert abs(min(v.x for v in scaled_coords) + 2.5) < 0.05
    assert abs(max(v.x for v in scaled_coords) - 10) < 0.05
    (work / 'material_bindings.json').write_text(json.dumps(bindings))
    # Selected faces only in Edit Mode.
    bpy.ops.object.select_all(action='DESELECT')
    target = export.descendants(root)[0]
    target.select_set(True)
    bpy.context.view_layer.objects.active = target
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='DESELECT')
    import bmesh
    bm = bmesh.from_edit_mesh(target.data)
    bm.faces.ensure_lookup_table()
    bm.faces[0].select = True
    assert materials.assign(bpy.context, material) == 1
    bpy.ops.object.mode_set(mode='OBJECT')
    assert target.data.polygons[0].material_index != target.data.polygons[1].material_index
    # Export failure must still remove temporary data and not change sources.
    snapshot = (set(bpy.data.objects), set(bpy.data.meshes), set(bpy.data.scenes))
    try:
        export.export_root(bpy.context, root, work / 'missing/fail.fbx', project=str(project))
    except (RuntimeError, OSError):
        pass
    else:
        raise AssertionError('Expected export failure')
    assert snapshot == (set(bpy.data.objects), set(bpy.data.meshes), set(bpy.data.scenes))
    print('PASS Unreal bridge naming / paths / registration / hierarchy / FBX / cleanup')
    print('UNREAL_TEST_PROJECT=' + str(project))
    (Path(tempfile.gettempdir()) / 'mbt_unreal_latest_test.txt').write_text(str(project))


if __name__ == '__main__':
    run()