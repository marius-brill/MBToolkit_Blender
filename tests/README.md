# Development checks

These scripts are development-only; they are not required to use MBToolkit.
Keep them in the repository, but exclude this directory from distributed add-on
archives. The extension build settings do this automatically; when creating a ZIP
manually, omit this directory too.

Run scripts individually, not through blanket unittest/pytest discovery: most
require Blender, some execute at import time, and GUI checks quit their process.
All Blender checks must run in a **new disposable process**, never in a working
session. Tests may delete objects, change preferences, save files, or quit Blender.

## Quick checks (ordinary Python)

From PowerShell, using absolute paths (adjust these for your checkout):

```powershell
$root = 'C:\Users\mariu\AppData\Roaming\Blender Foundation\Blender\5.2\scripts\addons\MBToolkit'
python "$root\tests\verify_structure.py"
python "$root\tests\test_repository.py"
python "$root\tests\test_sidebar_sections.py"
```

The structure checker parses all project Python files. Without Blender, the
sidebar script runs only its pure-Python selection tests and skips integration.
The repository checker requires Python 3.11+ and checks metadata consistency,
required documents, local documentation links, build exclusions, and ZIP contents
when a built archive exists under `dist`. CI runs these three scripts without
Blender; it does not run integration or GUI tests.

## Background Blender checks

```powershell
$blender = 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe'
& $blender --background --factory-startup --python-exit-code 1 --python "$root\tests\test_registration.py"
```

Use the same invocation with one of these scripts:

| Script | Coverage |
| --- | --- |
| `verify_structure.py` | Syntax and add-on module/import assumptions |
| `test_registration.py` | Registration, Modifier List and Resample regressions |
| `test_feature_preferences.py` | Optional-feature preferences and lifecycle |
| `test_modifier_timings.py` | Modifier evaluation timing behavior |
| `test_modifier_catalog.py` | Native modifier catalogs with appended/prepended third-party menu callbacks |
| `test_n_panel.py` | Sidebar tab visibility, ordering and lifecycle |
| `test_preferences.py` | Preference data, command pickers, shortcuts and drawing |
| `test_scene_performance.py` | Scene scanning, selection, cancellation and lifecycle |
| `test_sidebar_sections.py` | Selection logic and sidebar integration |
| `test_substance_painter.py` | Painter jobs, validation and material integration |
| `test_painter_bridge.py` | Transport and controlled Painter API behavior |
| `test_painter_baking.py` | Bake configuration, cancellation, errors and save gating |
| `test_painter_workflow.py` | Grouping, matching, project reuse and workflow regressions |
| `test_uv_suite.py` | UV packing, shapes, seams and rollback |

Painter checks use controlled responses by default. Passing `-- --live` to the
bridge or baking script explicitly opts into using installed Painter and creating
a disposable project. These checks may launch Painter and leave a test project
open. See SUBSTANCE_PAINTER.md in the project root before using live mode.

## Interactive Blender checks

These need a real GUI; do **not** add `--background`. Use event simulation for
the interactive group:

```powershell
& $blender --factory-startup --enable-event-simulate --python-exit-code 1 --python "$root\tests\test_preferences_live.py"
```

| Script | Coverage |
| --- | --- |
| `test_favorite_tiles_live.py` | Native favorite-tile press dispatch |
| `test_modifier_popup.py` | In-viewport popup and window behavior |
| `test_modifier_catalog_extension.py` | Standard extension ZIP install and real-layout modifier-preferences drawing with wrapped menus; requires isolated configuration (below) |
| `test_n_panel_live.py` | Sidebar tab manager UI |
| `test_preferences_live.py` | Shortcut capture, tiles, drag reorder and rollback |
| `test_scene_initialization_live.py` | Scene initialization in an interactive process |
| `test_scene_performance_live.py` | Scheduled collection, real selection and editor isolation |
| `test_sidebar_sections_live.py` | Sidebar section UI drawing |

Several GUI scripts write result files (some under `C:\tmp`); inspect their output
paths and create that directory if needed. Review both logs and result files:
timer-driven GUI failures are not necessarily reflected in the process exit code.
Visual appearance, real OS input, focus, and interactive undo/redo still need manual
smoke testing.

For `test_modifier_catalog_extension.py`, set both `BLENDER_USER_CONFIG` and
`BLENDER_USER_EXTENSIONS` to disposable directories under a temporary parent whose
name starts with `mbt_extension_test_`. Restore these environment variables after
the process finishes. The script installs its own ZIP with Blender's standard
extension installer and draws the installed modifier-preferences builder in a test
panel; it does not simulate the OS drop gesture. Check
`$env:TEMP\mbt_modifier_extension_result.txt` for `PASS` and the process error log
for drawing errors. Do not run against your normal extension repository.

## Sidebar persistence (two processes)

This check writes preferences, so use a disposable configuration directory. The
script requires `mbt_npanel_test_config` in its path as a safety guard. The second
process intentionally omits `--factory-startup` so it can load saved settings.

```powershell
$previousConfig = $env:BLENDER_USER_CONFIG
$config = Join-Path ([System.IO.Path]::GetTempPath()) ('mbt_npanel_test_config_' + [guid]::NewGuid())
New-Item -ItemType Directory -Path $config | Out-Null
try {
    $env:BLENDER_USER_CONFIG = $config
    & $blender --background --factory-startup --python-exit-code 1 --python "$root\tests\test_n_panel_persistence.py" -- write
    if ($LASTEXITCODE -ne 0) { throw 'Persistence write failed' }
    & $blender --background --python-exit-code 1 --python "$root\tests\test_n_panel_persistence.py" -- read
    if ($LASTEXITCODE -ne 0) { throw 'Persistence read failed' }
} finally {
    $env:BLENDER_USER_CONFIG = $previousConfig
    Remove-Item -LiteralPath $config -Recurse -Force
}
```

## Choosing what to run

Run quick checks first, then the background checks for changed features plus
registration. Run the corresponding GUI checks for UI changes, and the two-process
check for sidebar preference persistence changes. Similar filenames usually cover
different execution modes or feature layers; do not remove them based on names alone.