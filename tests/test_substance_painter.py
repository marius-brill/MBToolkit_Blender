"""Destructive integration tests: ONLY --background --factory-startup."""
import contextlib
import importlib
import io
import json
from pathlib import Path
import sys
import tempfile

import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon = importlib.import_module(ROOT.name)
jobs = importlib.import_module(f'{ROOT.name}.features.substance_painter.jobs')
materials = importlib.import_module(f'{ROOT.name}.features.substance_painter.materials')


def expect_error(function, text):
    try:
        function()
    except jobs.PainterError as error:
        assert text in str(error), str(error)
    else:
        raise AssertionError(f'Expected error containing {text}')


def counts():
    return tuple(len(data) for data in (bpy.data.objects, bpy.data.meshes,
                                      bpy.data.materials, bpy.data.scenes))


def main():
    assert bpy.app.background, 'Run only in a disposable background process'
    output = io.StringIO()
    with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
        addon.register()
        addon.feature_manager.sync(type('Settings', (), {'enable_substance_painter': True})())
    assert 'Traceback' not in output.getvalue() and 'Failed' not in output.getvalue(), output.getvalue()
    ctx = bpy.context
    settings = ctx.scene.mbt_painter
    expect_error(lambda: jobs.validate(ctx), 'non-empty')
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    bpy.ops.mesh.primitive_cube_add()
    low = ctx.object
    low.name = 'Test Low'
    low.location = (1, 2, 3)
    assert bpy.ops.mbt.painter_assign(role='LOW') == {'FINISHED'}
    # Use a differently named object with more evaluated faces for the high mesh.
    bpy.ops.mesh.primitive_cube_add()
    high = ctx.object
    high.name = 'Test High'
    high.location = low.location
    high.modifiers.new('Subdivision', 'SUBSURF').levels = 1
    assert bpy.ops.mbt.painter_assign(role='HIGH') == {'FINISHED'}
    original = bpy.data.materials.new('Original')
    low.data.materials.append(original)
    modifier = low.modifiers.new('Triangulate', 'TRIANGULATE')
    with tempfile.TemporaryDirectory() as folder:
        settings.output_dir = folder
        settings.project_name = '../Unsafe:Asset'
        assert jobs.validate(ctx) == ([low], [high])
        settings.high_collection.objects.link(low)
        expect_error(lambda: jobs.validate(ctx), 'share')
        settings.high_collection.objects.unlink(low)
        uv = low.data.uv_layers.active.data[0].uv.copy()
        low.data.uv_layers.active.data[0].uv = (2, 2)
        expect_error(lambda: jobs.validate(ctx), 'bake-tile boundary')
        low.data.uv_layers.active.data[0].uv = uv
        selected, active = list(ctx.selected_objects), ctx.view_layer.objects.active
        before = counts()
        matrices = [obj.matrix_world.copy() for obj in (low, high)]
        jobs.prepare(ctx)
        assert counts() == before, (counts(), before)
        assert list(ctx.selected_objects) == selected and ctx.view_layer.objects.active == active
        assert low.data.materials[0] == original and low.modifiers[0] == modifier
        assert all(obj.matrix_world == matrix for obj, matrix in zip((low, high), matrices))
        job = jobs.read_job(settings.last_job)
        first_job = settings.last_job
        assert job['status'] == 'prepared' and job['resolution'] == 2048
        entry = job['texture_sets'][0]
        assert Path(job['low_mesh']).stat().st_size > 100
        assert Path(job['high_mesh']).stat().st_size > 100
        assert Path(settings.last_job).parent.parent == Path(folder)
        # Verify actual FBX content independently of source data.
        scene = bpy.data.scenes.new('ImportVerification')
        try:
            with ctx.temp_override(scene=scene, view_layer=scene.view_layers[0]):
                bpy.ops.import_scene.fbx(filepath=job['low_mesh'])
                imported = [obj for obj in scene.objects if obj.type == 'MESH']
                assert len(imported) == 1
                assert len(imported[0].data.polygons) == 12
                assert imported[0].data.materials[0].name.startswith(entry['texture_set'])
                assert (imported[0].matrix_world.translation - low.matrix_world.translation).length < 1e-4
        finally:
            for obj in list(scene.objects):
                mesh = obj.data
                bpy.data.objects.remove(obj, do_unlink=True)
                if isinstance(mesh, bpy.types.Mesh):
                    bpy.data.meshes.remove(mesh)
            bpy.data.scenes.remove(scene)
        # Repeated jobs must not overwrite an earlier project.
        jobs.prepare(ctx)
        assert settings.last_job != first_job and Path(first_job).is_file()
        settings.last_job = first_job
        expect_error(lambda: materials.import_maps(ctx), 'protected')
        settings.replace_materials = True
        expect_error(lambda: materials.import_maps(ctx), 'no shader maps')
        for path in entry['textures'].values():
            image = bpy.data.images.new('TestTexture', width=4, height=4)
            image.filepath_raw = path
            image.file_format = 'PNG'
            image.save()
            bpy.data.images.remove(image)
        # Returned output paths replace expectations only after complete validation.
        response = {'state': 'EXPORTED', 'job_id': job['job_id'], 'texture_sets': [
            {'object': low.name, 'textures': dict(entry['textures'])}]}
        jobs.record_export(first_job, response)
        assert jobs.read_job(first_job)['status'] == 'exported'
        response['job_id'] = 'wrong-job'
        expect_error(lambda: jobs.record_export(first_job, response), 'does not match')
        materials.import_maps(ctx)
        material = low.data.materials[0]
        assert original.name in bpy.data.materials
        assert material.get('mbt_painter_job') == job['job_id']
        nodes = material.node_tree.nodes
        assert nodes['MBT_base_color'].image.colorspace_settings.name == 'sRGB'
        assert nodes['MBT_normal'].image.colorspace_settings.name == 'Non-Color'
        assert not nodes['MBT_ao'].outputs['Color'].is_linked
        assert next(node for node in nodes if node.type == 'NORMAL_MAP').outputs['Normal'].is_linked
        settings.replace_materials = False
        images_before = len(bpy.data.images)
        mats_before = len(bpy.data.materials)
        materials.import_maps(ctx)
        assert low.data.materials[0] == material
        assert len(bpy.data.images) == images_before
        assert len(bpy.data.materials) == mats_before
        # The manifest convention, rather than mutable UI settings, drives import.
        job['normal_format'] = 'DIRECTX'
        Path(first_job).write_text(json.dumps(job), encoding='utf-8')
        materials.import_maps(ctx)
        assert any(node.type == 'MATH' and node.operation == 'SUBTRACT'
                   for node in material.node_tree.nodes)
        # A shared mesh/material must not be modified underneath another object.
        duplicate = bpy.data.objects.new('UnrelatedDuplicate', low.data)
        ctx.scene.collection.objects.link(duplicate)
        shared_mesh = duplicate.data
        materials.import_maps(ctx)
        assert duplicate.data == shared_mesh and low.data != shared_mesh
        assert duplicate.data.materials[0] == material
        assert low.data.materials[0] != material
        material = low.data.materials[0]
        # Blender-side failure during actual export still cleans all snapshots.
        counts_before = counts()
        try:
            jobs.export_meshes(ctx, [low], Path(folder) / 'missing' / 'failed.fbx', low=True)
        except (RuntimeError, OSError):
            pass
        else:
            raise AssertionError('Expected FBX failure')
        assert counts() == counts_before
        # Saved settings survive a real blend-file reload.
        blend = str(Path(folder) / 'settings.blend')
        bpy.ops.wm.save_as_mainfile(filepath=blend)
        bpy.ops.wm.open_mainfile(filepath=blend)
        ctx = bpy.context
        settings = ctx.scene.mbt_painter
        low = ctx.scene.objects['Test Low']
        material = low.data.materials[0]
        assert settings.last_job == first_job
        assert settings.low_collection.name.startswith('MBT_Low')
        assert settings.bake_maps == {'NORMAL', 'AO', 'CURVATURE'}
        # Invalid manifests and missing targets fail before any slots are changed.
        job['texture_sets'][0]['object'] = 'MissingTarget'
        job['texture_sets'][0].pop('object_id', None)
        Path(first_job).write_text(json.dumps(job), encoding='utf-8')
        expect_error(lambda: materials.import_maps(ctx), 'not found')
        assert low.data.materials[0] == material
        # FBX failures clean temporary data and incomplete job folders.
        previous = jobs.export_steps
        def fail(*args, **kwargs):
            raise RuntimeError('Simulated exporter failure')
        jobs.export_steps = fail
        directories = set(Path(folder).iterdir())
        try:
            jobs.prepare(ctx)
        except RuntimeError:
            pass
        finally:
            jobs.export_steps = previous
        assert set(Path(folder).iterdir()) == directories
    output = io.StringIO()
    with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
        addon.unregister()
        addon.register()
        addon.unregister()
    assert 'Traceback' not in output.getvalue() and 'Failed' not in output.getvalue(), output.getvalue()
    assert not hasattr(bpy.types.Scene, 'mbt_painter')
    print('PASS: Painter registration, validation, FBX export, scene preservation, materials and cleanup', flush=True)


if __name__ == '__main__':
    main()