"""Run only in a disposable Blender process with --factory-startup."""

import importlib
from pathlib import Path
import sys
from types import SimpleNamespace

import bpy
import bmesh


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))


def close(actual, expected, tolerance=0.009):
    assert all(abs(a - b) < tolerance for a, b in zip(actual, expected)), (actual, expected)


def fixture(name='ColorTest'):
    if bpy.context.object and bpy.context.object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT')
    data = bpy.data.meshes.new(name)
    data.from_pydata([(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)], [], [(0, 1, 2), (0, 2, 3)])
    obj = bpy.data.objects.new(name, data)
    bpy.context.collection.objects.link(obj)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    return obj


def run():
    assert bpy.app.background
    addon = importlib.import_module(ROOT.name)
    addon.register()
    entry = bpy.context.preferences.addons.new()
    entry.module = ROOT.name
    prefs = entry.preferences
    prefs.enable_vertex_color = True
    addon.feature_manager.sync(prefs)
    feature = importlib.import_module(ROOT.name + '.features.vertex_color')
    mesh, preview = feature.operators.mesh, feature.preview
    settings = bpy.context.scene.mbt_vertex_color
    try:
        for domain in ('CORNER', 'POINT'):
            for storage in ('BYTE_COLOR', 'FLOAT_COLOR'):
                obj = fixture(domain + storage)
                result = bpy.ops.mbt.vertex_color_attribute(action='CREATE', name='Color', domain=domain, storage=storage)
                assert result == {'FINISHED'}
                attribute = obj.data.color_attributes.active_color
                assert attribute.name == 'Color'
                assert all(tuple(value.color) == (1, 1, 1, 1) for value in attribute.data)
                for value in attribute.data:
                    value.color = (0.2, 0.4, 0.6, 0.35)
                settings.write_mask = (True, False, True, False)
                settings.color = (0.8, 0.1, 0.3, 1)
                assert bpy.ops.mbt.vertex_color_apply(action='FILL') == {'FINISHED'}
                close(attribute.data[0].color, (0.8, 0.4, 0.3, 0.35))
                original = tuple(attribute.data[0].color)
                transaction = mesh.Transaction(bpy.context, settings)
                transaction.apply(lambda color: (0.1, 0.2, 0.9, 0))
                transaction.restore()
                close(attribute.data[0].color, original, 1e-6)

                # Face selection affects only its own corners, or its shared vertices.
                bpy.ops.object.mode_set(mode='EDIT')
                attribute = obj.data.color_attributes.active_color
                bm = bmesh.from_edit_mesh(obj.data)
                for face in bm.faces:
                    face.select_set(False)
                for edge in bm.edges:
                    edge.select_set(False)
                for vertex in bm.verts:
                    vertex.select_set(False)
                bpy.context.tool_settings.mesh_select_mode = (False, False, True)
                list(bm.faces)[0].select_set(True)
                settings.affect = 'SELECTED'
                attribute = obj.data.color_attributes.active_color
                access = mesh.ColorAccess(obj.data, attribute, bpy.context, True)
                assert len(access.indices) == 3
                close(access.get(0), original)
                transaction = mesh.Transaction(bpy.context, settings)
                transaction.apply(lambda color: (0.25, 0.8, 0.75, 0))
                close(access.get(0), (0.25, original[1], 0.75, original[3]))
                untouched = 3
                close(access.get(untouched), original)
                transaction.restore()
                close(access.get(0), original, 1e-6)
                positions, colors = preview.geometry(obj, bpy.context.evaluated_depsgraph_get(),
                                                     'Color', 'RGB', 'LINEAR')
                assert len(positions) == 6
                close(access.get(0), original, 1e-6)
                for face in bm.faces:
                    face.select_set(False)
                try:
                    mesh.Transaction(bpy.context, settings)
                    raise AssertionError('Empty selection accepted')
                except ValueError:
                    pass
                bpy.ops.object.mode_set(mode='OBJECT')
                settings.affect = 'ALL'
                attribute = obj.data.color_attributes.active_color
                close(attribute.data[0].color, original, 1e-6)
                print('PASS domain/storage / masked fill / Edit Mode selection / cancel:', domain, storage)

        obj = fixture('Channels')
        bpy.ops.mbt.vertex_color_attribute(action='CREATE', name='Color', storage='FLOAT_COLOR')
        attribute = obj.data.color_attributes.active_color
        settings.write_mask = (True, True, True, True)
        settings.space = 'SRGB'
        settings.channel = 'R'
        settings.value = 0.5
        bpy.ops.mbt.vertex_color_apply(action='SET')
        close(attribute.data[0].color, (mesh.srgb_to_linear(0.5), 1, 1, 1), 1e-6)
        settings.destination = 'A'
        bpy.ops.mbt.vertex_color_apply(action='COPY')
        assert abs(attribute.data[0].color[3] - 0.5) < 1e-6
        settings.space = 'LINEAR'
        settings.channel = 'A'
        bpy.ops.mbt.vertex_color_apply(action='INVERT')
        assert abs(attribute.data[0].color[3] - 0.5) < 1e-6
        settings.channel, settings.destination = 'R', 'A'
        before = tuple(attribute.data[0].color)
        bpy.ops.mbt.vertex_color_apply(action='SWAP')
        close(attribute.data[0].color, (before[3], before[1], before[2], before[0]), 1e-6)
        bpy.ops.mbt.vertex_color_apply(action='INSPECT')
        assert settings.status.startswith('Uniform')
        attribute.data[-1].color = (0, 0, 0, 0)
        bpy.ops.mbt.vertex_color_apply(action='INSPECT')
        assert settings.status.startswith('Mixed')
        bpy.ops.mbt.vertex_color_apply(action='SAMPLE')
        close(settings.color, tuple(attribute.data[0].color), 1e-6)
        settings.write_mask = (False, False, False, False)
        assert bpy.ops.mbt.vertex_color_apply(action='INSPECT') == {'FINISHED'}
        assert bpy.ops.mbt.vertex_color_apply(action='SAMPLE') == {'FINISHED'}
        settings.write_mask = (True, True, True, True)
        # Object Mode must not reinterpret an old selection as the current edit scope.
        settings.affect = 'SELECTED'
        try:
            mesh.Transaction(bpy.context, settings)
            raise AssertionError('Object Mode selection accepted')
        except ValueError:
            pass
        bpy.ops.object.mode_set(mode='VERTEX_PAINT')
        obj.data.use_paint_mask = True
        for polygon in obj.data.polygons:
            polygon.select = polygon.index == 0
        transaction = mesh.Transaction(bpy.context, settings)
        assert transaction.count == 3
        before = [tuple(value.color) for value in obj.data.color_attributes.active_color.data]
        transaction.apply(lambda original: (0.1, 0.2, 0.3, 0.4))
        close(obj.data.color_attributes.active_color.data[3].color, before[3], 1e-6)
        transaction.restore()
        bpy.ops.object.mode_set(mode='OBJECT')
        settings.affect = 'ALL'
        attribute = obj.data.color_attributes.active_color
        material = bpy.data.materials.new('Constant Base')
        material.use_nodes = True
        obj.data.materials.append(material)
        principled = next(node for node in material.node_tree.nodes if node.type == 'BSDF_PRINCIPLED')
        principled.inputs['Base Color'].default_value = (0.2, 0.3, 0.4, 1)
        bpy.ops.mbt.vertex_color_apply(action='MATERIAL')
        close(settings.color, (0.2, 0.3, 0.4, 1), 1e-6)
        print('PASS numeric space / channel set, copy, invert, swap / sample / mixed inspection')
        print('PASS no-write inspection / Object Mode selection rejection / Vertex Paint mask / material sample')

        # Batch preflight must not partially fill objects before discovering a missing attribute.
        other = fixture('Missing')
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        settings.target = 'SELECTED'
        baseline = tuple(attribute.data[0].color)
        try:
            mesh.Transaction(bpy.context, settings)
            raise AssertionError('Missing layer accepted')
        except ValueError:
            pass
        close(attribute.data[0].color, baseline, 1e-6)
        bpy.ops.mbt.vertex_color_attribute(action='MISSING')
        assert other.data.color_attributes['Color'].data_type == 'FLOAT_COLOR'
        transaction = mesh.Transaction(bpy.context, settings)
        assert len(transaction.rows) == 2
        linked = bpy.data.objects.new('Linked', obj.data)
        bpy.context.collection.objects.link(linked)
        linked.select_set(True)
        assert len(mesh.Transaction(bpy.context, settings).rows) == 2
        assert len(mesh.targets(bpy.context, settings, unique=False)) == 3
        linked.select_set(False)
        settings.target = 'ACTIVE'
        bpy.ops.mbt.vertex_color_attribute(action='SINGLE')
        assert obj.data != linked.data
        print('PASS batch validation / create missing / shared mesh deduplication / single user')

        attribute = obj.data.color_attributes.active_color
        bpy.ops.mbt.vertex_color_attribute(action='DUPLICATE')
        duplicate = obj.data.color_attributes.active_color
        close(duplicate.data[0].color, attribute.data[0].color, 1e-6)
        bpy.ops.mbt.vertex_color_attribute(action='RENAME', name='Renamed')
        assert obj.data.color_attributes.active_color.name == 'Renamed'
        bpy.ops.mbt.vertex_color_attribute(action='RENDER')
        assert obj.data.color_attributes.default_color_name == 'Renamed'
        bpy.ops.mbt.vertex_color_attribute(action='CONVERT', domain='POINT', storage='BYTE_COLOR')
        attribute = obj.data.color_attributes.active_color
        assert (attribute.domain, attribute.data_type) == ('POINT', 'BYTE_COLOR')
        bpy.ops.mbt.vertex_color_attribute(action='DELETE')
        assert obj.data.color_attributes.get('Renamed') is None
        print('PASS duplicate / rename / render default / conversion / delete')

        obj.data.color_attributes.active_color = obj.data.color_attributes['Color']
        materials = tuple(obj.data.materials)
        baseline = [tuple(value.color) for value in obj.data.color_attributes['Color'].data]
        positions, colors = preview.geometry(obj, bpy.context.evaluated_depsgraph_get(), 'Color', 'A', 'LINEAR')
        assert len(positions) == len(colors) == 6
        assert all(color[0] == color[1] == color[2] and color[3] == 1 for color in colors)
        close(preview.diagnostic_color((0.2, 0.4, 0.6, 0.3), 'A', 'SRGB'), (0.3, 0.3, 0.3, 1), 1e-6)
        assert tuple(obj.data.materials) == materials
        assert baseline == [tuple(value.color) for value in obj.data.color_attributes['Color'].data]
        transaction = mesh.Transaction(bpy.context, settings)
        preview._sessions.append(transaction)
        transaction.apply(lambda original: (0, 0, 0, 0))
        preview.reset()
        assert baseline == [tuple(value.color) for value in obj.data.color_attributes['Color'].data]
        assert not preview._sessions and not preview._cache and not preview._views
        print('PASS preview extraction / alpha grayscale / data and material preservation / session reset')
    finally:
        if bpy.context.object and bpy.context.object.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        addon.unregister()
        bpy.context.preferences.addons.remove(entry)
    assert not hasattr(bpy.types.Scene, 'mbt_vertex_color')
    assert preview._depsgraph not in bpy.app.handlers.depsgraph_update_post
    assert preview.reset not in bpy.app.handlers.load_pre
    print('ALL VERTEX COLOR TESTS PASSED')


if __name__ == '__main__':
    run()