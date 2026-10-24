"""Dependency-free repository checks; run directly with Python 3.11+."""

import ast
from pathlib import Path
import re
import tomllib
import unittest
from urllib.parse import unquote, urlsplit
import zipfile


ROOT = Path(__file__).resolve().parents[1]


class RepositoryTests(unittest.TestCase):
    def test_metadata_matches_entry_point(self):
        manifest = tomllib.loads((ROOT / 'blender_manifest.toml').read_text(encoding='utf-8'))
        tree = ast.parse((ROOT / '__init__.py').read_text(encoding='utf-8'))
        info = next(ast.literal_eval(node.value) for node in tree.body
                    if isinstance(node, ast.Assign)
                    and any(isinstance(target, ast.Name) and target.id == 'bl_info'
                            for target in node.targets))
        self.assertEqual(manifest['version'], '.'.join(map(str, info['version'])))
        self.assertEqual(manifest['blender_version_min'], '.'.join(map(str, info['blender'])))
        self.assertEqual(manifest['name'], info['name'])
        self.assertEqual(manifest['license'], ['SPDX:GPL-3.0-or-later'])
        self.assertEqual(set(manifest['permissions']), {'files', 'network'})

    def test_repository_documents_exist(self):
        for name in ('README.md', 'LICENSE', 'CONTRIBUTING.md', 'SECURITY.md',
                     'CHANGELOG.md', 'UV_SUITE.md', 'SUBSTANCE_PAINTER.md',
                     'tests/README.md', '.github/workflows/checks.yml',
                     '.github/dependabot.yml', '.github/pull_request_template.md',
                     '.github/ISSUE_TEMPLATE/bug_report.md',
                     '.github/ISSUE_TEMPLATE/feature_request.md'):
            with self.subTest(name=name):
                self.assertTrue((ROOT / name).is_file(), name)
                self.assertTrue((ROOT / name).read_text(encoding='utf-8').strip())
        license_text = (ROOT / 'LICENSE').read_text(encoding='utf-8')
        self.assertIn('GNU GENERAL PUBLIC LICENSE', license_text)
        self.assertIn('Version 3, 29 June 2007', license_text)
        self.assertIn('END OF TERMS AND CONDITIONS', license_text)

    def test_local_document_links(self):
        documents = list(ROOT.glob('*.md')) + list((ROOT / 'tests').glob('*.md'))
        documents += list((ROOT / '.github').rglob('*.md'))
        for document in documents:
            for target in re.findall(r'\[[^\]]*\]\(([^\s)]+)\)',
                                     document.read_text(encoding='utf-8')):
                parsed = urlsplit(target)
                if parsed.scheme or parsed.netloc or not parsed.path:
                    continue
                with self.subTest(document=document.name, target=target):
                    self.assertTrue((document.parent / unquote(parsed.path)).exists())

    def test_build_exclusions(self):
        manifest = tomllib.loads((ROOT / 'blender_manifest.toml').read_text(encoding='utf-8'))
        patterns = manifest['build']['paths_exclude_pattern']
        for pattern in ('/.git/', '/.github/', '/.vscode/', '/tests/', '/dist/',
                        '__pycache__/', '/*.zip', '*.py[cod]'):
            self.assertIn(pattern, patterns)

    def test_built_archives_when_present(self):
        archives = list((ROOT / 'dist').glob('mbtoolkit-*.zip'))
        if not archives:
            self.skipTest('Build with Blender to also check archive contents')
        for archive in archives:
            with self.subTest(archive=archive.name), zipfile.ZipFile(archive) as package:
                names = package.namelist()
                for required in ('blender_manifest.toml', '__init__.py', 'LICENSE', 'README.md'):
                    self.assertIn(required, names)
                for name in names:
                    self.assertFalse(set(Path(name).parts) &
                                     {'.git', '.github', '.vscode', 'tests', 'dist', '__pycache__'}, name)
                    self.assertFalse(name.endswith(('.pyc', '.pyo', '.zip')), name)


if __name__ == '__main__':
    unittest.main(verbosity=2)