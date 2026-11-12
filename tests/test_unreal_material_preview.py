"""Load real UE-exported preview images in a disposable Blender process."""

import importlib
import json
from pathlib import Path
import sys
import tempfile

import bpy

assert bpy.app.background
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
materials = importlib.import_module(f'{ROOT.name}.features.unreal_bridge.materials')
project = Path((Path(tempfile.gettempdir()) / 'mbt_unreal_latest_test.txt').read_text())
assert project.parent.name.startswith('mbt_unreal_test_')
preview = json.loads((project.parent / 'preview.json').read_text())
material = materials.create_preview(str(project), preview)
textures = [node for node in material.node_tree.nodes if node.type == 'TEX_IMAGE']
assert textures and all(node.image.packed_file for node in textures)
assert material['mbt_unreal_path'] == preview['path']
# Verify normal-map conversion also builds a complete linked graph.
preview['textures']['normal'] = preview['textures']['base_color']
materials.create_preview(str(project), preview)
assert any(node.type == 'NORMAL_MAP' for node in material.node_tree.nodes)
print('PASS real Unreal texture preview / packed images / normal graph')