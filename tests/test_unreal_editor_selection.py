"""Discovery identity regressions; no editor or network required."""

import importlib
from pathlib import Path
import sys
import types
import unittest

ROOT = Path(__file__).resolve().parents[1]
package = types.ModuleType('mbt_selection_test')
package.__path__ = [str(ROOT / 'features/unreal_bridge')]
sys.modules[package.__name__] = package
connection = importlib.import_module(package.__name__ + '.connection')


class EditorSelectionTests(unittest.TestCase):
    def setUp(self):
        self.project = ROOT / 'Fixture/Test.uproject'
        self.node = {'node_id': 'editor-a', 'project_root': str(self.project.parent), 'project_name': 'Test'}

    def test_duplicate_replies_are_one_editor(self):
        candidates = connection.matching_editors([self.node, dict(self.node)], self.project)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(connection.select_editor(candidates)['node_id'], 'editor-a')

    def test_distinct_sessions_need_selection(self):
        other = dict(self.node, node_id='editor-b')
        candidates = connection.matching_editors([self.node, other], self.project)
        with self.assertRaises(connection.BridgeError):
            connection.select_editor(candidates)
        self.assertEqual(connection.select_editor(candidates, 'editor-b'), other)

    def test_exact_project_and_stale_preference(self):
        wrong = dict(self.node, project_root=str(ROOT / 'Other'))
        self.assertEqual(connection.matching_editors([wrong], self.project), [])
        self.assertEqual(connection.select_editor([self.node], 'closed-editor'), self.node)


if __name__ == '__main__':
    unittest.main()