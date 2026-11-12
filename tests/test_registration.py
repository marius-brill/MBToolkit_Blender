"""Destructive integration tests: run ONLY in --background --factory-startup."""

import contextlib
import importlib
import io
from pathlib import Path
import sys

import bpy
import bmesh

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon = importlib.import_module(ROOT.name)
resample = importlib.import_module(f'{ROOT.name}.features.resample')


def lifecycle(function):
    output = io.StringIO()
    with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
        function()
    assert 'Failed' not in output.getvalue() and 'Traceback' not in output.getvalue(), output.getvalue()


def mesh_object(vertices, edges=(), faces=(), face_mode=False):
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for obj in list(bpy.context.scene.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    mesh = bpy.data.meshes.new('ResampleTest')
    mesh.from_pydata(vertices, edges, faces)
    obj = bpy.data.objects.new('ResampleTest', mesh)
    bpy.context.collection.objects.link(obj)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.context.tool_settings.mesh_select_mode = (False, not face_mode, face_mode)
    bpy.ops.object.mode_set(mode='EDIT')
    bm = bmesh.from_edit_mesh(mesh)
    for elements in (bm.faces, bm.edges, bm.verts):
        for element in elements:
            element.select_set(False)
    return obj, bm


def snapshot():
    bm = bmesh.from_edit_mesh(bpy.context.edit_object.data)
    for elements in (bm.verts, bm.edges, bm.faces):
        elements.index_update()
    return (
        tuple((tuple(v.co), v.select, v.hide) for v in bm.verts),
        tuple((tuple(v.index for v in e.verts), e.select, e.hide, e.seam) for e in bm.edges),
        tuple((tuple(v.index for v in f.verts), f.select, f.hide, f.material_index) for f in bm.faces),
    )


def wire(count, method='LINEAR'):
    obj, bm = mesh_object([(i, 0, 0) for i in range(4)], [(i, i+1) for i in range(3)])
    layer = bm.verts.layers.float.new('wire_weight')
    for vertex in bm.verts:
        vertex[layer] = 0.5
    for edge in bm.edges:
        edge.seam = True
        edge.select_set(True)
    bmesh.update_edit_mesh(obj.data)
    assert bpy.ops.mbt.resample_wire(count=count, method=method) == {'FINISHED'}
    bm = bmesh.from_edit_mesh(obj.data)
    assert len(bm.verts) == count and len(bm.edges) == count-1
    for i, vertex in enumerate(sorted(bm.verts, key=lambda v: v.co.x)):
        assert abs(vertex.co.x - 3*i/(count-1)) < 1e-5
        assert vertex.select
    assert all(e.select for e in bm.edges)
    layer = bm.verts.layers.float.get('wire_weight')
    assert layer is not None and all(abs(v[layer]-0.5) < 1e-6 for v in bm.verts)
    assert all(e.seam for e in bm.edges)


def strip(count, face_mode, curved=False, caps=False):
    source = 4
    vertices = [(i, y, 0.2*i*i if curved else 0) for i in range(source) for y in (0, 1)]
    faces = [(2*i, 2*i+2, 2*i+3, 2*i+1) for i in range(source-1)]
    if caps:
        vertices += [(-1, 0, 0), (-1, 1, 0)]
        faces += [(8, 0, 1, 9)]
    obj, bm = mesh_object(vertices, faces=faces, face_mode=face_mode)
    uv = bm.loops.layers.uv.new('TestUV')
    attr = bm.verts.layers.float.new('test_weight')
    for v in bm.verts:
        v[attr] = 0.7
    for f in bm.faces:
        f.material_index = 2
        for loop in f.loops:
            loop[uv].uv = (loop.vert.co.x, loop.vert.co.y)
    if face_mode:
        for face in list(bm.faces)[:3]:
            face.select_set(True)
    else:
        for edge in bm.edges:
            if edge.verts[0].co.x == edge.verts[1].co.x and edge.verts[0].co.x >= 0:
                edge.select_set(True)
    bmesh.update_edit_mesh(obj.data)
    assert bpy.ops.mbt.resample_surface(count=count, roundness=0.85 if curved else 0) == {'FINISHED'}
    bm = bmesh.from_edit_mesh(obj.data)
    assert len(bm.verts) == 2*count + (2 if caps else 0), (count, len(bm.verts))
    assert len(bm.faces) == count-1 + int(caps)
    assert all(len(f.verts) == 4 and f.material_index == 2 for f in bm.faces)
    assert bm.loops.layers.uv.get('TestUV') is not None
    attr = bm.verts.layers.float.get('test_weight')
    assert attr is not None and all(abs(v[attr]-0.7) < 1e-5 for v in bm.verts)
    if not curved:
        for y in (0, 1):
            rail = sorted((v for v in bm.verts if abs(v.co.y-y) < 1e-6 and v.co.x >= 0), key=lambda v: v.co.x)
            assert len(rail) == count
            assert all(abs(v.co.x-3*i/(count-1)) < 1e-5 for i, v in enumerate(rail))
    assert sum(f.select for f in bm.faces) == count-1 if face_mode else sum(e.select for e in bm.edges) == count
    assert bpy.ops.mbt.resample_surface(count=count, roundness=0) == {'FINISHED'}


def rejected(vertices, edges, faces, surface=False, face_mode=False):
    obj, bm = mesh_object(vertices, edges, faces, face_mode)
    for element in (bm.faces if face_mode else bm.edges):
        element.select_set(True)
    bmesh.update_edit_mesh(obj.data)
    before = snapshot()
    op = bpy.ops.mbt.resample_surface if surface else bpy.ops.mbt.resample_wire
    assert op(count=6) == {'CANCELLED'}
    assert snapshot() == before


def extra_cases():
    for surface in (False, True):
        vertices = [(i, y+offset, 0) for offset in (0, 3) for i in range(3) for y in (0, 1)]
        faces = [(base+2*i, base+2*i+2, base+2*i+3, base+2*i+1)
                 for base in (0, 6) for i in range(2)]
        if surface:
            obj, bm = mesh_object(vertices, faces=faces, face_mode=True)
            for face in bm.faces:
                face.select_set(True)
            op = bpy.ops.mbt.resample_surface
        else:
            obj, bm = mesh_object([(i, offset, 0) for offset in (0, 3) for i in range(3)],
                                  [(0,1),(1,2),(3,4),(4,5)])
            for edge in bm.edges:
                edge.select_set(True)
            op = bpy.ops.mbt.resample_wire
        bmesh.update_edit_mesh(obj.data)
        assert op(count=5) == {'FINISHED'}
        bm = bmesh.from_edit_mesh(obj.data)
        assert len(bm.verts) == (20 if surface else 10)
    # A boundary chain can move on a surface, but cannot change count.
    obj, bm = mesh_object([(0,0,0),(1,0,0),(2,0,0),(0,1,0),(1,1,0),(2,1,0)],
                          faces=[(0,1,4,3),(1,2,5,4)])
    for edge in bm.edges:
        if all(v.co.y == 0 for v in edge.verts):
            edge.select_set(True)
    bmesh.update_edit_mesh(obj.data)
    assert bpy.ops.mbt.resample_wire(count=3) == {'FINISHED'}
    before = snapshot()
    assert bpy.ops.mbt.resample_wire(count=5) == {'CANCELLED'}
    assert snapshot() == before
    # Hidden edges cannot be used to form a valid chain.
    obj, bm = mesh_object([(0,0,0),(1,0,0)], [(0,1)])
    for edge in bm.edges:
        edge.select_set(True)
        edge.hide_set(True)
    bmesh.update_edit_mesh(obj.data)
    before = snapshot()
    assert bpy.ops.mbt.resample_wire(count=5) == {'CANCELLED'}
    assert snapshot() == before
    # Connected rails remain supported without detaching neighboring geometry.
    obj, bm = mesh_object([(x,y,0) for y in range(3) for x in range(3)],
                          faces=[(0,1,4,3),(1,2,5,4),(3,4,7,6),(4,5,8,7)], face_mode=True)
    for face in list(bm.faces)[:2]:
        face.select_set(True)
    bmesh.update_edit_mesh(obj.data)
    assert bpy.ops.mbt.resample_surface(count=5) == {'FINISHED'}
    # Shape keys and multi-object edit are explicit unsupported cases.
    bpy.ops.object.mode_set(mode='OBJECT')
    obj.shape_key_add(name='Basis')
    bpy.ops.object.mode_set(mode='EDIT')
    before = snapshot()
    assert bpy.ops.mbt.resample_surface(count=5) == {'CANCELLED'}
    assert snapshot() == before
    bpy.ops.object.mode_set(mode='OBJECT')
    other = bpy.data.objects.new('OtherTest', bpy.data.meshes.new('OtherTest'))
    bpy.context.collection.objects.link(other)
    other.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    assert len(bpy.context.objects_in_mode) == 2
    before = snapshot()
    assert bpy.ops.mbt.resample_wire(count=5) == {'CANCELLED'}
    assert snapshot() == before
    print('PASS disconnected components / surface chains / hidden / side adjacency / shape keys / multi-object')


def connected_strip_cases():
    for both_sides in (False, True):
        for count in (2, 4, 7):
            ys = (-1, 0, 1, 2) if both_sides else (0, 1, 2)
            vertices = [(x, y, 0) for y in ys for x in range(4)]
            faces = [(4*j+i, 4*j+i+1, 4*(j+1)+i+1, 4*(j+1)+i)
                     for j in range(len(ys)-1) for i in range(3)]
            obj, bm = mesh_object(vertices, faces=faces, face_mode=True)
            uv = bm.loops.layers.uv.new('ConnectedUV')
            for face in bm.faces:
                center = face.calc_center_median()
                face.material_index = 1 if 0 < center.y < 1 else 2
                if 0 < center.y < 1:
                    face.select_set(True)
                for loop in face.loops:
                    loop[uv].uv = loop.vert.co.xy
            perimeter = {tuple(v.co) for v in bm.verts if v.co.y not in (0, 1)}
            bmesh.update_edit_mesh(obj.data)
            assert bpy.ops.mbt.resample_surface(count=count, roundness=0) == {'FINISHED'}
            bm = bmesh.from_edit_mesh(obj.data)
            assert sum(f.select for f in bm.faces) == count-1
            assert all(len(f.verts) == 4 for f in bm.faces if f.select)
            assert all(f.normal.z > 0.99 for f in bm.faces)
            assert perimeter == {tuple(v.co) for v in bm.verts if v.co.y not in (0, 1)}
            assert all(len(e.link_faces) in (1, 2) for e in bm.edges)
            assert all(len(e.link_faces) == 2 for e in bm.edges
                       if all(abs(v.co.y-1) < 1e-6 for v in e.verts))
            assert all(f.material_index == (1 if f.select else 2) for f in bm.faces)
            assert bm.loops.layers.uv.get('ConnectedUV') is not None
            unseen = set(bm.verts)
            stack = [next(iter(unseen))]
            while stack:
                vertex = stack.pop()
                if vertex not in unseen:
                    continue
                unseen.remove(vertex)
                stack.extend(e.other_vert(vertex) for e in vertex.link_edges)
            assert not unseen, 'Strip became detached'
            # Reusing the new connected result must also work.
            assert bpy.ops.mbt.resample_surface(count=5, roundness=0) == {'FINISHED'}
    print('PASS connected strips / increase-decrease-same / side n-gons / normals / perimeter / materials / repeat')


def modifier_list_cases():
    """Exercise real RNA callbacks and draw construction without an interactive UI."""
    from types import SimpleNamespace
    feature = importlib.import_module(f'{ROOT.name}.features.modifier_list')

    class Layout:
        def __init__(self):
            self.calls = []

        def row(self, **kwargs):
            return self

        column = row
        box = row
        column_flow = row
        split = row

        def template_modifier_asset_menu_items(self, **kwargs):
            pass

        def label(self, **kwargs):
            self.calls.append(('label', kwargs))

        def prop(self, data, name, **kwargs):
            assert name in data.bl_rna.properties, name
            self.calls.append(('prop', name))

        def template_list(self, list_type, list_id, data, collection, active_data, active_name, **kwargs):
            assert list_type == 'MBT_UL_modifiers'
            assert active_name in active_data.bl_rna.properties
            assert active_data.bl_rna.properties[active_name].type == 'INT'
            self.calls.append(('list', len(getattr(data, collection))))

        def operator(self, idname, **kwargs):
            namespace, name = idname.split('.')
            getattr(getattr(bpy.ops, namespace), name).get_rna_type()
            self.calls.append(('operator', idname))
            return SimpleNamespace()

    obj, _ = mesh_object([(0,0,0)])
    bpy.ops.object.mode_set(mode='OBJECT')
    assert obj.mbt_modifier_index == 0
    original_keys = set(bpy.context.scene.keys()), set(obj.keys())
    feature.draw(Layout(), bpy.context)
    first = obj.modifiers.new('First', 'BEVEL')
    second = obj.modifiers.new('Second', 'SUBSURF')
    obj.mbt_modifier_index = 0
    assert obj.modifiers.active == first
    obj.modifiers.active = second
    assert obj.mbt_modifier_index == 1
    obj.mbt_modifier_index = 999
    assert obj.modifiers.active == second
    bpy.ops.object.modifier_move_up(modifier=second.name)
    assert obj.mbt_modifier_index == 0
    obj.modifiers.remove(second)
    assert obj.mbt_modifier_index == 0
    for _ in range(3):
        feature.draw(Layout(), bpy.context)
    assert original_keys == (set(bpy.context.scene.keys()), set(obj.keys()))
    for kind in ('DEFAULT', 'COMPACT', 'GRID'):
        feature.MBT_UL_modifiers.draw_item(SimpleNamespace(layout_type=kind), bpy.context,
            Layout(), obj, first, 0, obj, feature.INDEX_PROPERTY)
    bpy.ops.object.mode_set(mode='EDIT')
    feature.draw(Layout(), bpy.context)
    assert not feature.MBT_OT_modifier_add_menu.poll(bpy.context)
    bpy.ops.object.mode_set(mode='OBJECT')
    assert feature.MBT_OT_modifier_add_menu.poll(bpy.context)
    from bl_ui.properties_data_modifier import DATA_PT_modifiers
    assert DATA_PT_modifiers.draw is feature._draw_native
    assert not hasattr(bpy.types, 'MBT_PT_modifier_list')
    # A pinned Properties object differs from the viewport's active object.
    pinned = bpy.data.objects.new('PinnedTest', bpy.data.meshes.new('PinnedTest'))
    pinned.modifiers.new('PinnedModifier', 'BEVEL')
    pinned_context = SimpleNamespace(object=pinned, active_object=obj, preferences=bpy.context.preferences)
    layout = Layout()
    feature.draw(layout, pinned_context)
    assert ('list', 1) in layout.calls
    assert pinned.mbt_modifier_index == 0
    # No object, unsupported object, and non-editable data paths.
    feature.draw(Layout(), SimpleNamespace(object=None))
    camera = bpy.data.objects.new('CameraTest', bpy.data.cameras.new('CameraTest'))
    feature.draw(Layout(), SimpleNamespace(object=camera, preferences=bpy.context.preferences))
    assert not feature.MBT_OT_modifier_add_menu.poll(SimpleNamespace(
        object=camera, window=bpy.context.window, mode='OBJECT'))
    readonly = SimpleNamespace(is_editable=False)
    feature._set_index(readonly, 0)
    readonly = SimpleNamespace(is_editable=False, type='MESH', modifiers=obj.modifiers, bl_rna=obj.bl_rna)
    readonly.mbt_modifier_locks = obj.mbt_modifier_locks
    readonly.mode = 'OBJECT'
    feature.draw(Layout(), SimpleNamespace(object=readonly, preferences=bpy.context.preferences))
    assert not feature.MBT_OT_modifier_add_menu.poll(SimpleNamespace(
        object=readonly, window=bpy.context.window, mode='OBJECT'))
    other = bpy.data.objects.new('EmptyStack', bpy.data.meshes.new('EmptyStack'))
    assert other.mbt_modifier_index == 0 and obj.modifiers.active == first
    obj.modifiers.remove(first)
    feature.draw(Layout(), bpy.context)
    assert obj.mbt_modifier_index == 0
    assert original_keys == (set(bpy.context.scene.keys()), set(obj.keys()))
    print('PASS modifier list RNA selection / object switching / deletion / reorder / read-only draw / contexts / Properties navigation')


def modifier_workflow_cases():
    from types import SimpleNamespace
    feature = importlib.import_module(f'{ROOT.name}.features.modifier_list')
    preferences = importlib.import_module(f'{ROOT.name}.preferences')
    from bl_ui.properties_data_modifier import DATA_PT_modifiers
    obj = bpy.context.object
    obj.modifiers.clear()
    mods = [obj.modifiers.new(str(i), 'BEVEL') for i in range(6)]
    for index in (1, 4):
        assert bpy.ops.mbt.modifier_lock(uid=mods[index].persistent_uid) == {'FINISHED'}
    obj.modifiers.move(4, 0)
    obj.modifiers.move(list(obj.modifiers).index(mods[1]), 5)
    feature.enforce_locks(obj)
    assert obj.modifiers[1] == mods[1] and obj.modifiers[4] == mods[4]
    mods[1].name = 'RenamedLock'
    obj.modifiers.move(1, 3)
    feature._reset_locks()
    feature._enforce_pending()
    assert obj.modifiers[1] == mods[1]
    # Shrink below the second requested index, then add enough to restore it.
    for modifier in (mods[0], mods[2], mods[3]):
        obj.modifiers.remove(modifier)
    feature.enforce_locks(obj)
    assert list(obj.modifiers).index(mods[4]) == 1
    for i in range(3):
        obj.modifiers.new('Extra', 'SUBSURF')
    feature.enforce_locks(obj)
    assert list(obj.modifiers).index(mods[4]) == 4
    obj.modifiers.remove(mods[1])
    feature.enforce_locks(obj)
    assert len(obj.mbt_modifier_locks) == 1
    assert bpy.ops.mbt.modifier_lock(uid=mods[4].persistent_uid) == {'FINISHED'}
    assert not obj.mbt_modifier_locks
    obj.modifiers[-1].use_pin_to_last = True
    feature.enforce_locks(obj)
    native = obj.modifiers[-1]
    assert any(p.uid == native.persistent_uid and p.native_pin for p in obj.mbt_modifier_locks)
    assert bpy.ops.mbt.modifier_lock(uid=mods[4].persistent_uid) == {'FINISHED'}
    assert bpy.ops.mbt.modifier_lock(uid=mods[4].persistent_uid) == {'FINISHED'}
    obj.modifiers[-1].use_pin_to_last = False
    feature.enforce_locks(obj)
    assert not obj.mbt_modifier_locks
    entry = feature.catalog('MESH')[0]
    count = len(obj.modifiers)
    assert bpy.ops.mbt.modifier_add(key='object.modifier_add:BEVEL', object_name=obj.name) == {'FINISHED'}
    assert len(obj.modifiers) == count+1
    # Bottom-relative pins keep the tail below new modifiers.
    tail = obj.modifiers[-1]
    second_tail = obj.modifiers[-2]
    assert bpy.ops.mbt.modifier_lock(uid=tail.persistent_uid) == {'FINISHED'}
    assert bpy.ops.mbt.modifier_lock(uid=second_tail.persistent_uid) == {'FINISHED'}
    assert bpy.ops.mbt.modifier_add(key='object.modifier_add:SOLIDIFY', object_name=obj.name) == {'FINISHED'}
    assert obj.modifiers[-1] == tail and obj.modifiers[-2] == second_tail
    moved = obj.modifiers[0]
    assert bpy.ops.mbt.modifier_manage(uid=moved.persistent_uid, action='DOWN') == {'FINISHED'}
    assert obj.modifiers.active == moved
    assert bpy.ops.mbt.modifier_manage(uid=tail.persistent_uid, action='UP') == {'CANCELLED'}
    assert bpy.ops.mbt.modifier_manage(uid=second_tail.persistent_uid, action='DELETE') == {'FINISHED'}
    assert obj.modifiers[-1] == tail
    assert len(obj.mbt_modifier_locks) == 1
    # Upgrade old exact-index records from current positions once, outside draw.
    obj.mbt_modifier_locks.clear()
    legacy = obj.mbt_modifier_locks.add()
    legacy.uid, legacy.index = tail.persistent_uid, len(obj.modifiers)-1
    feature.enforce_locks(obj)
    assert legacy.from_bottom and legacy.index == 0
    before = len(obj.modifiers)
    assert bpy.ops.mbt.modifier_manage(uid=tail.persistent_uid, action='DELETE') == {'FINISHED'}
    assert len(obj.modifiers) == before-1 and not obj.mbt_modifier_locks
    camera = bpy.data.objects.new('UnsupportedAdd', bpy.data.cameras.new('UnsupportedAdd'))
    bpy.context.collection.objects.link(camera)
    assert bpy.ops.mbt.modifier_add(key='object.modifier_add:BEVEL', object_name=camera.name) == {'CANCELLED'}
    # Attach an actual preferences entry (register() alone does not enable an add-on).
    addon_entry = bpy.context.preferences.addons.get(ROOT.name)
    created = addon_entry is None
    if created:
        addon_entry = bpy.context.preferences.addons.new()
        addon_entry.module = ROOT.name
    prefs = addon_entry.preferences
    assert isinstance(prefs, preferences.MBT_Preferences)
    prefs.modifier_favorites.clear()
    for kind in ('BEVEL', 'SUBSURF'):
        assert bpy.ops.mbt.modifier_favorite(key='object.modifier_add:'+kind,
            label=kind, action='TOGGLE') == {'FINISHED'}
    assert len(prefs.modifier_favorites) == 2
    # Exercise preferences, favorites toolbar and overview construction too.
    class DrawLayout:
        def prop(self, data, name, **kwargs):
            assert name in data.bl_rna.properties
        def row(self, **kwargs):
            return self
        column = row
        column_flow = row
        box = row
        split = row
        def label(self, **kwargs):
            pass
        def operator(self, idname, **kwargs):
            namespace, name = idname.split('.')
            getattr(getattr(bpy.ops, namespace), name).get_rna_type()
            return SimpleNamespace()
        def template_modifier_asset_menu_items(self, **kwargs):
            assert kwargs['catalog_path'] in feature.CATEGORIES
        def template_list(self, *args, **kwargs):
            pass
    preferences.draw_modifier_preferences(DrawLayout(), prefs)
    feature.draw(DrawLayout(), bpy.context)
    feature.MBT_MT_modifier_overview.draw(SimpleNamespace(layout=DrawLayout()), bpy.context)
    bpy.ops.mbt.modifier_favorite(action='UP', index=1)
    assert prefs.modifier_favorites[0].key.endswith('SUBSURF')
    bpy.ops.mbt.modifier_favorite(action='REMOVE', index=1)
    assert len(prefs.modifier_favorites) == 1
    prefs.modifier_favorites.clear()
    if created:
        bpy.context.preferences.addons.remove(addon_entry)
    assert DATA_PT_modifiers.draw is feature._draw_native
    assert feature._stack_changed in bpy.app.handlers.depsgraph_update_post
    assert len(feature.catalog('MESH')) > 40
    assert not any(e['args'].get('type') == 'BEVEL' for e in feature.catalog('EMPTY'))
    print('PASS favorites / add targeting / bottom-relative pins / migration / reorder / delete / shrink-grow / native pin conflict')


def modifier_editor_cases():
    from types import SimpleNamespace
    feature = importlib.import_module(f'{ROOT.name}.features.modifier_list')
    obj = bpy.context.object
    obj.modifiers.clear()
    first = obj.modifiers.new('EditorBevel', 'BEVEL')
    second = obj.modifiers.new('EditorSubdivision', 'SUBSURF')
    obj.modifiers.active = first

    class Layout:
        def __init__(self):
            self.props = []
            self.operators = []
        def row(self, **kwargs):
            return self
        box = row
        column = row
        def label(self, **kwargs):
            pass
        def context_pointer_set(self, name, value):
            assert name in {'modifier', 'mbt_modifier_settings'} and value == obj.modifiers.active
        def prop(self, data, name, **kwargs):
            assert name in data.bl_rna.properties or name.startswith('["')
            self.props.append((data, name))
        def operator(self, idname, **kwargs):
            self.operators.append((idname, kwargs))
            return SimpleNamespace()
        def template_curve_mapping(self, data, name):
            assert isinstance(getattr(data, name), bpy.types.CurveMapping)
        def template_curveprofile(self, data, name):
            assert isinstance(getattr(data, name), bpy.types.CurveProfile)
        def template_color_ramp(self, data, name, **kwargs):
            assert isinstance(getattr(data, name), bpy.types.ColorRamp)
        def template_ID(self, data, name, **kwargs):
            assert name in data.bl_rna.properties
        def prop_search(self, data, name, owner, collection, **kwargs):
            self.prop(data, name, **kwargs)
        def template_list(self, *args, **kwargs):
            pass

    layout = Layout()
    feature.draw_active_settings(layout, bpy.context)
    assert (first, 'width') in layout.props
    assert not any(data == second for data, name in layout.props)
    assert feature.modifier_icon(first) == 'MOD_BEVEL'
    assert feature.modifier_icon(second) == 'MOD_SUBSURF'
    layout = Layout()
    feature.MBT_UL_modifiers.draw_item(SimpleNamespace(layout_type='DEFAULT'), bpy.context,
        layout, obj, first, 0, obj, feature.INDEX_PROPERTY)
    realtime = next(kwargs for idname, kwargs in layout.operators if idname == 'mbt.modifier_viewport_toggle')
    assert realtime['icon'] == 'RESTRICT_VIEW_OFF' and realtime['depress'] == first.show_viewport
    old = first.show_viewport
    assert bpy.ops.mbt.modifier_viewport_toggle(uid=first.persistent_uid) == {'FINISHED'}
    assert first.show_viewport != old
    render = next(kwargs for idname, kwargs in layout.operators if idname == 'mbt.modifier_render_toggle')
    assert render['icon'] == 'RESTRICT_RENDER_OFF' and render['depress'] == first.show_render
    for state in (False, True):
        first.show_render = state
        assert bpy.ops.mbt.modifier_render_toggle(uid=first.persistent_uid) == {'FINISHED'}
        assert first.show_render != state
    assert bpy.ops.mbt.modifier_render_toggle(uid=-1) == {'CANCELLED'}
    assert bpy.ops.mbt.modifier_lock(uid=second.persistent_uid) == {'FINISHED'}
    assert second.use_pin_to_last
    second.use_pin_to_last = False
    feature.enforce_locks(obj)
    assert not obj.mbt_modifier_locks
    second.use_pin_to_last = True
    assert bpy.ops.mbt.modifier_lock(uid=second.persistent_uid) == {'FINISHED'}
    assert not second.use_pin_to_last and not obj.mbt_modifier_locks
    for count in range(25):
        rows = list(feature.favorite_rows(list(range(count))))
        assert len(rows) == (count + 3) // 4
        assert [item for row in rows for item in row] == list(range(count))
        assert all(len(row) == 4 for row in rows[:-1])
        assert not rows or 1 <= len(rows[-1]) <= 4
    assert list(feature.favorite_rows(list(range(5)))) == [[0, 1, 2, 3], [4]]
    entry = bpy.context.preferences.addons.get(ROOT.name)
    created = entry is None
    if created:
        entry = bpy.context.preferences.addons.new()
        entry.module = ROOT.name
    prefs = entry.preferences
    assert prefs.modifier_popup_key == 'W' and prefs.modifier_popup_shift
    prefs.modifier_popup_key = 'E'
    feature.rebuild_keymap()
    if bpy.context.window_manager.keyconfigs.addon is not None:
        assert len(feature._keymap_items) == 1
        assert feature._keymap_items[0][1].type == 'E'
    prefs.modifier_popup_key = 'NONE'
    assert not feature._keymap_items
    prefs.modifier_popup_key = 'W'
    if created:
        bpy.context.preferences.addons.remove(entry)
    feature.rebuild_keymap()
    assert feature.MBT_OT_modifier_popup.poll(SimpleNamespace(
        area=SimpleNamespace(type='VIEW_3D'), object=obj))
    calls = []
    operator = SimpleNamespace(layout=Layout())
    def invoke_popup(value, **kwargs):
        assert value is operator and kwargs == {'width': 440}
        calls.append('popup')
        return {'RUNNING_MODAL'}
    assert feature.MBT_OT_modifier_popup.invoke(operator, SimpleNamespace(
        window_manager=SimpleNamespace(invoke_popup=invoke_popup)), None) == {'RUNNING_MODAL'}
    original_draw, original_settings = feature.draw, feature.draw_active_settings
    feature.draw = lambda layout, context: calls.append('list')
    feature.draw_active_settings = lambda layout, context: calls.append('selected')
    try:
        feature.MBT_OT_modifier_popup.draw(operator, bpy.context)
    finally:
        feature.draw, feature.draw_active_settings = original_draw, original_settings
    assert calls == ['popup', 'list', 'selected']
    # External creation: no MBToolkit add operator or catalog entry involved.
    gn = importlib.import_module(f'{ROOT.name}.core.gn')
    group = bpy.data.node_groups.new('ForeignInputsTest', 'GeometryNodeTree')
    geometry = group.interface.new_socket(name='Geometry', in_out='INPUT', socket_type='NodeSocketGeometry')
    angle = group.interface.new_socket(name='Angle', in_out='INPUT', socket_type='NodeSocketFloat')
    toggle = group.interface.new_socket(name='Ignore Sharpness', in_out='INPUT', socket_type='NodeSocketBool')
    hidden = group.interface.new_socket(name='Hidden', in_out='INPUT', socket_type='NodeSocketFloat')
    hidden.hide_in_modifier = True
    group.interface.new_socket(name='Result', in_out='OUTPUT', socket_type='NodeSocketGeometry')
    group.interface.new_panel('Foreign Panel')
    foreign = obj.modifiers.new('Foreign Auto Smooth', 'NODES')
    foreign.node_group = group
    obj.modifiers.active = foreign
    gn.set_modifier_input(foreign, angle.identifier, 0.7)
    gn.set_modifier_input(foreign, toggle.identifier, True)
    layout = Layout()
    feature.draw_active_settings(layout, bpy.context)
    assert (getattr(foreign.properties.inputs, angle.identifier), 'value') in layout.props
    assert (getattr(foreign.properties.inputs, toggle.identifier), 'value') in layout.props
    assert (getattr(foreign.properties.inputs, hidden.identifier), 'value') not in layout.props
    assert abs(getattr(foreign.properties.inputs, angle.identifier).value - 0.7) < 1e-6
    assert not gn.legacy_modifier_input_exists(foreign, geometry.identifier)
    for identifier in (geometry.identifier, 'MissingSocket'):
        try:
            gn.set_modifier_input(foreign, identifier, 1)
        except ValueError:
            pass
        else:
            raise AssertionError('Non-value inputs must not use legacy IDProperties')
    # Missing/incomplete modern input RNA must not fall through to IDProperties.
    incomplete = SimpleNamespace(node_group=group, properties=SimpleNamespace(inputs=SimpleNamespace()))
    feature._draw_node_inputs(Layout(), incomplete)
    # Legacy read/write compatibility without depending on an older executable.
    class Legacy(dict):
        pass
    legacy = Legacy({angle.identifier: 0.2})
    legacy.node_group = group
    gn.set_modifier_input(legacy, angle.identifier, 0.4)
    assert gn.legacy_modifier_input_exists(legacy, angle.identifier)
    feature._draw_node_inputs(SimpleNamespace(prop=lambda *args, **kwargs: None), legacy)
    # Use the same Essentials node group that MACHIN3tools appends.
    asset_path = Path(bpy.utils.system_resource('DATAFILES')) / 'assets' / 'nodes' / 'geometry_nodes_essentials.blend'
    with bpy.data.libraries.load(str(asset_path), link=False) as (source, target):
        assert 'Smooth by Angle' in source.node_groups
        target.node_groups = ['Smooth by Angle']
    smooth_group = target.node_groups[0]
    foreign.node_group = smooth_group
    layout = Layout()
    feature.draw_active_settings(layout, bpy.context)
    assert any(name == 'value' for data, name in layout.props)
    feature._enforce_pending()
    assert foreign.show_expanded and not first.show_expanded and not second.show_expanded
    first.show_expanded = True
    feature._enforce_pending()
    assert first.show_expanded, 'Manual expansion must survive unchanged selection'
    obj.mbt_modifier_index = list(obj.modifiers).index(second)
    assert second.show_expanded and not foreign.show_expanded and not first.show_expanded
    # Native rendering delegates to Blender instead of the compact RNA editor.
    original_draw = feature.draw
    calls = []
    feature.draw = lambda layout, context: calls.append('list')
    try:
        feature._draw_native(SimpleNamespace(layout=SimpleNamespace(
            row=lambda **kwargs: SimpleNamespace(prop=lambda *args, **kwargs: None),
            template_modifiers=lambda: calls.append('native'))), bpy.context)
    finally:
        feature.draw = original_draw
    assert calls == ['list', 'native']
    foreign.node_group = None
    obj.modifiers.active = foreign
    feature.draw_active_settings(Layout(), bpy.context)
    obj.modifiers.remove(foreign)
    feature._enforce_pending()
    bpy.data.node_groups.remove(group)
    bpy.data.node_groups.remove(smooth_group)
    print('PASS foreign populated Geometry Nodes / Smooth by Angle / non-value sockets / legacy storage / native layouts / expansion')
    # Walk every mesh-compatible modifier's settings for RNA regressions.
    for item in bpy.types.Modifier.bl_rna.properties['type'].enum_items_static:
        try:
            modifier = obj.modifiers.new('SettingsTest', item.identifier)
        except RuntimeError:
            continue
        if modifier is None:
            continue
        obj.modifiers.active = modifier
        feature.draw_active_settings(Layout(), bpy.context)
        obj.modifiers.remove(modifier)
    print('PASS selected settings / native icons / monitor toggle / bidirectional pins / four-column favorite wrapping / popup hotkeys')


def run():
    assert bpy.app.background, 'Run tests in a disposable background Blender process'
    for cycle in range(2):
        lifecycle(addon.register)
        addon.feature_manager.sync(type('Settings', (), {'enable_resample': True})())
        for module in addon._modules:
            for cls in getattr(module, 'classes', ()):
                assert cls.is_registered, cls.__name__
        assert bpy.ops.mbt.resample_wire.get_rna_type().identifier == 'MBT_OT_resample_wire'
        assert bpy.ops.mbt.resample_surface.get_rna_type().identifier == 'MBT_OT_resample_surface'
        assert addon.panels.SECTION_BY_KEY['resample'][4] == ('resample',)
        assert addon.panels.MBT_PT_main.is_registered
        assert bpy.ops.mbt.select_section.get_rna_type().identifier == 'MBT_OT_select_section'
        if cycle == 0:
            lifecycle(addon.unregister)
            assert not hasattr(bpy.types, 'MBT_PT_resample')
            assert not hasattr(bpy.types.Object, 'mbt_modifier_index')
    print('PASS registration / unregister / re-register')
    modifier_list_cases()
    modifier_workflow_cases()
    modifier_editor_cases()
    connected_strip_cases()
    for count in (2, 4, 9):
        for method in ('LINEAR', 'CATMULL'):
            wire(count, method)
    print('PASS wire counts / interpolation / selection')
    for face_mode in (False, True):
        for count in (2, 4, 7):
            strip(count, face_mode)
            strip(count, face_mode, curved=True)
            strip(count, face_mode, caps=True)
    print('PASS surface counts / selection / profiles / end neighbors / custom data')
    rejected([(0,0,0),(1,0,0),(0,1,0),(-1,0,0)], [(0,1),(0,2),(0,3)], [])
    rejected([(0,0,0),(1,0,0),(0,1,0)], [(0,1),(1,2),(2,0)], [])
    rejected([(0,0,0),(0,0,0)], [(0,1)], [])
    rejected([(0,0,0),(1,0,0),(0,1,0)], [], [(0,1,2)], True, True)
    rejected([(x,y,0) for y in range(3) for x in range(3)], [],
             [(0,1,4,3),(1,2,5,4),(3,4,7,6),(4,5,8,7)], True, True)
    print('PASS invalid selections leave mesh unchanged')
    wire(4)
    before = snapshot()
    def fail(work):
        work.verts.new((9,9,9))
        raise RuntimeError('intentional staging failure')
    try:
        resample._transaction(bpy.context, fail)
    except RuntimeError:
        pass
    else:
        raise AssertionError('Expected staging failure')
    assert snapshot() == before
    real_update = bmesh.update_edit_mesh
    calls = []
    def fail_commit(*args, **kwargs):
        calls.append(True)
        if len(calls) == 1:
            raise RuntimeError('intentional commit failure')
        return real_update(*args, **kwargs)
    bmesh.update_edit_mesh = fail_commit
    try:
        try:
            resample._transaction(bpy.context, lambda work: work.verts.new((9,9,9)))
        except RuntimeError:
            pass
        else:
            raise AssertionError('Expected commit failure')
    finally:
        bmesh.update_edit_mesh = real_update
    assert snapshot() == before
    assert not any(m.name.startswith('__mbt_resample_') for m in bpy.data.meshes)
    print('PASS staging failure / commit rollback / temporary data cleanup')
    extra_cases()
    bpy.ops.object.mode_set(mode='OBJECT')
    assert not bpy.ops.mbt.resample_wire.poll() and not bpy.ops.mbt.resample_surface.poll()
    lifecycle(addon.unregister)
    assert not hasattr(bpy.types.Object, 'mbt_modifier_index')
    assert not hasattr(bpy.types.Object, 'mbt_modifier_locks')
    feature = importlib.import_module(f'{ROOT.name}.features.modifier_list')
    assert feature._stack_changed not in bpy.app.handlers.depsgraph_update_post
    assert not bpy.app.timers.is_registered(feature._enforce_pending)
    assert not bpy.app.timers.is_registered(feature._init_keymap)
    assert not feature._keymap_items
    from bl_ui.properties_data_modifier import DATA_PT_modifiers
    assert DATA_PT_modifiers.draw is not feature._draw_native
    print('ALL MODIFIER LIST AND RESAMPLE TESTS PASSED')


if __name__ == '__main__':
    run()