# Contributing and release setup

## Development environment

Use Blender 5.2+ for runtime testing and Python 3.11+ for repository-only checks
(`tomllib` is part of Python 3.11+). No third-party Python dependencies are needed.
Clone the repository into a folder named `MBToolkit`; integration tests import the
checkout by its directory name. Use a separate development checkout if possible,
rather than editing a production installation.

PowerShell example (replace the absolute checkout path with your own):

```powershell
$root = 'C:\dev\MBToolkit'
git clone https://github.com/marius-brill/MBToolkit.git "$root"
python "$root\tests\verify_structure.py"
python "$root\tests\test_repository.py"
python "$root\tests\test_sidebar_sections.py"
```

For interactive development, install a built extension ZIP into a disposable
Blender configuration. To test code directly from the checkout, use the scripts
in [tests/README.md](tests/README.md); they handle importing the source checkout.
Restart Blender after module/lifecycle changes to avoid stale Python state.

## Code and pull requests

- Follow the surrounding code: four-space Python indentation, relative imports,
  and Blender's bundled APIs. Do not add dependencies without discussing them.
- Features expose `register()` / `unregister()` and are lazily loaded through
  `core/feature_manager.py`. Register property storage before consumers and remove
  timers, handlers, keymaps, and UI overrides during teardown.
- Keep changes focused. Include a reproduction or regression test and document
  user-visible changes in the README/feature guide and CHANGELOG.md.
- Run repository checks, registration tests, and tests for affected features.
  UI behavior also needs a manual smoke test; plain Python CI is not Blender CI.
- Do not run blanket test discovery. Some scripts execute immediately and can
  delete scene data, save preferences, or quit Blender. Read tests/README.md first.
- Submit contributions under the repository's GPL-3.0-or-later license. Do not
  copy third-party code/assets unless their license is compatible and attribution
  and source obligations are preserved.

## Build an installable extension

Use Blender's native extension builder, not GitHub's source ZIP:

```powershell
$root = 'C:\dev\MBToolkit'
$blender = 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe'
$dist = Join-Path $root 'dist'
New-Item -ItemType Directory -Force -Path $dist | Out-Null
& $blender --factory-startup --command extension validate "$root"
if ($LASTEXITCODE -ne 0) { throw 'Manifest validation failed' }
& $blender --factory-startup --command extension build --source-dir "$root" --output-dir "$dist"
if ($LASTEXITCODE -ne 0) { throw 'Extension build failed' }
```

The expected filename is `mbtoolkit-<version>.zip`. The manifest and add-on entry
point must be at the archive root. The build excludes tests, Git/GitHub metadata,
editor configuration, bytecode, and prior build output. Keep LICENSE and user
documentation in the archive. Do not package private .blend files or bake output.

Official command reference:
<https://docs.blender.org/manual/en/latest/advanced/command_line/extension_arguments.html>

## Release checklist

1. Review changes and update CHANGELOG.md. Keep `bl_info` in `__init__.py` and
   `blender_manifest.toml` versions/minimum Blender versions synchronized.
2. Run the three Python checks above, plus Blender registration and affected
   background tests using disposable configurations. Record the exact Blender
   version and platform. Perform UI smoke tests for installation, feature toggles,
   preferences persistence, shortcuts, and disable/re-enable behavior.
3. Validate/build with Blender. Inspect the ZIP contents and install the ZIP into
   a clean disposable configuration. Verify the displayed version and uninstall.
4. Commit reviewed changes, then create/push a matching `v<version>` tag and create
   a GitHub Release. Attach the built extension ZIP, not the automatic source ZIP.
   Describe known limitations and tested Blender versions/platforms.

Releases are deliberately manual; CI does not publish, tag, or change repository
settings. GitHub Actions runs dependency-free checks on pushes and pull requests.
It does not establish Blender compatibility or exercise Painter/GUI behavior.

## GitHub maintainer settings

These settings require a repository administrator and are not configured by files:

- Enable Actions and require the **Repository checks** job in branch protection
  after its first successful run. Consider requiring PR reviews.
- Enable **Private vulnerability reporting** under the repository's security settings
  before inviting confidential reports through GitHub (see SECURITY.md).
- Keep Issues enabled for the supplied bug/feature templates.
- Review GitHub's Dependency graph and Dependabot alerts if available. There are
  no pip dependencies; Dependabot is configured for GitHub Actions updates only.
- Review release contents and license provenance before publishing. This checklist
  does not imply a release already exists or that all platforms have been tested.