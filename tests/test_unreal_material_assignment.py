"""Single-click assignment and delayed preview regressions in disposable Blender."""

from concurrent.futures import Future
import importlib
import json
from pathlib import Path
import sys
import tempfile

import bpy

assert bpy.app.background
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
bridge = importlib.import_module(f'{ROOT.name}.features.unreal_bridge')


class DeferredPool:
    def submit(self, function, engine, request):
        self.request = request
        self.future = Future()
        return self.future

    def shutdown(self, **kwargs):
        pass


bridge.register()
try:
    with tempfile.TemporaryDirectory(prefix='mbt_material_assignment_') as folder:
        project = Path(folder) / 'Test.uproject'
        project.write_text(json.dumps({'EngineAssociation': '5.7'}))
        settings = bpy.context.scene.mbt_unreal
        settings.project = str(project)
        paths = ['/Game/A/M_Wood.M_Wood', '/Game/B/M_Wood.M_Wood']
        bridge._set_material_list(settings, paths)
        assert [item.name for item in settings.materials] == ['M_Wood', 'M_Wood (2)']
        settings.material_name = 'M_Wood (2)'
        assert settings.material_path == paths[1]
        bpy.ops.mesh.primitive_cube_add()
        target = bpy.context.object
        pool = DeferredPool()
        bridge._pool = pool
        assert bpy.ops.mbt.unreal_assign_material() == {'FINISHED'}
        proxy = target.active_material
        assert proxy['mbt_unreal_path'] == paths[1], 'First click must assign immediately'
        assert pool.request['material'] == paths[1]
        bpy.ops.object.select_all(action='DESELECT')
        bpy.ops.mesh.primitive_cube_add()
        other = bpy.context.object
        pool.future.set_result({'project': str(project), 'message': 'Ready',
                               'preview': {'path': paths[1], 'textures': {}, 'base_color': [0.8, 0.1, 0.2, 1]}})
        if bpy.app.timers.is_registered(bridge._poll_result):
            bpy.app.timers.unregister(bridge._poll_result)
        bridge._poll_result()
        assert target.active_material == proxy
        assert not other.data.materials, 'Delayed preview must not retarget selection'
        assert proxy['mbt_unreal_preview_ready']
        assert proxy.diffuse_color[0] > 0.79
        assert bpy.ops.mbt.unreal_assign_material() == {'FINISHED'}
        assert other.active_material == proxy
        assert bridge._future is None, 'Cached preview must not fetch again'
        print('PASS short material names / duplicate paths / first-click assignment / delayed preview target safety')
finally:
    bridge.unregister()