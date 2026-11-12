# Development checks

The Unreal editor integration check asserts linked import/reimport and a second
mesh create only mesh assets (no placeholder material packages). The live sidebar
check draws Connection Setup in both its expanded and collapsed states.

`test_unreal_material_assignment.py` verifies short-name selection, duplicate-name
identities, first-click assignment and delayed-preview selection safety in Blender.
`test_unreal_editor_selection.py` runs without Blender and checks discovery node
deduplication, explicit editor selection and stale-node handling. The disposable
remote connection test also sends two assets together using the connected node.

Unreal material/scale checks: `test_unreal_bridge.py` covers scaled FBX, preview
proxies, face assignment and slot bindings. `test_unreal_bridge_editor.py` checks
material listing, instance parameters, texture export, scaled dimensions and
original-material reimport in the generated disposable project only.

`test_unreal_engine_detection.py` runs in ordinary Python for installed-build
discovery and manual path regressions. In disposable background Blender it also
tests RNA callbacks and the Detect/Browse operators without opening an artist project.

Unreal bridge checks: `test_unreal_bridge.py` runs in disposable background
Blender and generates a disposable `.uproject` plus FBX; then
`test_unreal_bridge_editor.py` runs inside that UE project only. See
[Unreal bridge testing](../UNREAL_BRIDGE.md#development-checks). Never target an
artist project when running these scripts.

`test_dynabool_shapes.py` runs only in disposable background Blender. It tests
shape-driven sampling, closed/manifold finite output, sampled surface error,
sphere face-normal deviation, uniform scale stability, narrow-gap separation,
tiny-edge insensitivity, graph/Python policy parity, work-limit signaling and a
12-object output/timing smoke test. It optionally accepts `-- --fixture` followed
by an absolute path to a library containing Cube.029 (not included in the repo).
The exported personal fixture is read only; no artist project is opened or saved.

`test_dynabool_resolution.py` runs in disposable background Blender and checks
revision-4 upgrades, visible/editable automatic resolution, relative triangle
density without a triangle target, manual override precedence, save/reload, manual component generation,
quality-failure rollback and returning to automatic mode.

These scripts are development-only; they are not required to use MBToolkit.
Keep them in the repository, but exclude this directory from distributed add-on
archives. The extension build settings do this automatically; when creating a ZIP
manually, omit this directory too.

Run scripts individually, not through blanket unittest/pytest discovery: most
require Blender, some execute at import time, and GUI checks quit their process.
All Blender checks must run in a **new disposable process**, never in a working
session. Tests may delete objects, change preferences, save files, or quit Blender.

## Quick checks (ordinary Python)

`test_skew_metrics.py` checks decoded-image hashing, missing-detail failures,
centroid/shape separation and region-limited normal-detail thresholds without
Blender or Painter. Run it individually like the other ordinary-Python scripts.

The live `test_painter_skew_live.py` also accepts `--cage-probe --edge-fixture`
after `-- --live`. These enable a test-only custom-cage adapter and a beveled-panel
edge witness. The adapter never modifies production bake helpers on disk; remote
helpers are restored after each bake. It records full common/baker property keys
and public baking/resource docstrings in `backend_discovery.json`. Both cages and
both projection modes are checked through save/reopen. Inspect `result.json` for
detail recall, shape overlap, centroid error and edge-reference measurements.
These are thresholded normal-detail metrics, not full high-surface coverage.
The current edge witness does not distinguish projection modes. The test restores
distance-based/averaged settings but leaves experimental baked maps in its project.

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

`test_modifier_actions.py` checks Apply/Duplicate/Copy to Selected, differing active
and source objects, stale targets, hover-path resolution, and shortcut poll scope.
`test_modifier_actions_live.py` uses a disposable GUI process with
`--enable-event-simulate --factory-startup` to apply a modifier using actual hover
and Ctrl+A events. Result: `$env:TEMP\mbt_modifier_actions_live_result.txt`.
Text-field focus, visual icon placement and interactive Undo still need manual checks.

`test_modifier_layouts.py` audits all 83 installed Blender 5.2 modifier types on
compatible object data and checks popup/Properties control parity, shared disclosure
state, and Array's native-style header/fit controls. The GUI audit uses the same
disclosure renderer in both views rather than expanded popup-only boxes.

The all-type audit covers
compatible object data, every context-available writable enum branch, valid property
and operator references, and draw-time stack immutability. Both Properties sections
and popup box layouts are exercised. This validates drawing, not action execution or
pixel-level equivalence to Blender's native panels.

`test_modifier_layouts_live.py` is a **GUI** check: omit `--background`, use a disposable
`--factory-startup` process. It draws all types through real UILayouts with sections
open, including a custom bevel profile, chained Grease Pencil time segments and
populated Geometry Nodes inputs. Inspect the console for RNA warnings as well as
`$env:TEMP\mbt_modifier_layouts_live_result.txt`. Visual parity, operator execution,
and conditional states beyond the fixtures still require manual testing.

`generate_modifier_layouts.py` is an offline development generator, not a test.
Run in disposable background Blender with `-- --source-dir` pointing to an absolute
path containing the matching Blender source `MOD_*.cc` files, and `--output` pointing
to the absolute path of `features/modifier_layout_data.py` in this checkout. The
current data is pinned to Blender source commit `fbe6228777e7`. It extracts literal
panel organization and widget hints, not C++ control flow; review runtime conditions
and specialized helper handling whenever regenerating. No downloads occur at runtime.

`test_concepting.py` checks all six projection directions, rotated/scaled/offset
coordinates, corner-domain UV output, per-object active map selection without extra
maps, no-UV fallback, base/other UV preservation, legacy group defaults, shared group reuse,
repeat prevention, all-slot clay material assignment, Bevel shader wiring, material
reuse, small bevel defaults and one-time stock-radius migration/custom preservation,
unselected shared-mesh isolation (with and without existing slots), operator
polls and registration cycles. Run in a disposable process with `--background
--factory-startup --python-exit-code 1 --python` and its absolute script path.
The sidebar section integration and live tests cover the new Concepting buttons.
Actual texture appearance, bevel appearance and interactive Undo require a manual
smoke test in the appropriate viewport shading mode.

`test_modifier_search.py` also checks the Selected Settings default, active-only RNA
drawing, selection/reorder/removal, empty stacks, Native Stack and missing-preferences
fallbacks, and viewport popup isolation from the Properties preference.
`test_modifier_search_live.py` performs three Native Stack → Selected Settings round
trips in two Properties editors, checks pinned-object/tab/space preservation and the
private empty template owner's lifecycle, then opens search and the viewport popup.
Mode controls are preferences-only; background tests check their absence from the list
and the search button's neutral unpressed style. Visual tone depends on theme.

`test_modifier_search.py` checks compatible search enum lifetime, fixed toolbar
layout, new-modifier selection, pinned-target handling, stale-target rejection,
pinned-tail preservation, native settings dispatch, expansion and empty stacks.
Run in a disposable process with `--background --factory-startup
--python-exit-code 1 --python` and the absolute script path. The existing
`test_registration.py` also checks the native expansion workflow.

`test_modifier_search_live.py` checks real native Properties layouts without a
settings toggle, floating search invocation and the viewport popup. Run in a disposable GUI
process (omit `--background`) with `--factory-startup --python-exit-code 1 --python`
and the absolute script path. It auto-quits; require `PASS` in the system-temp
`mbt_modifier_search_live_result.txt`. Actual OS typing, result clicks and
interactive undo/redo still require a manual smoke test.

`test_runtime_health.py` checks read-only diagnostics, repair of active runtime
timers/shortcuts, non-resurrection of external hidden panels and partial class/UV/
Geometry Nodes registration rollback and retry. Injected tracebacks are expected.

`test_sidebar_visibility_live.py` requires a disposable GUI process (omit
`--background`). It observes the actual UI-region Panel instance, verifies owner
preservation through apply/restore and File New, tests workspace owner exclusion
and re-inclusion, and validates clipboard diagnostics. It auto-quits and writes
system-temp `mbt_sidebar_visibility_result.json`; require `status: PASS`. Static
RNA category enums return UNSUPPORTED in this Blender build, so the test records
the live active category and actual panel drawing instead.

`test_lifecycle_recovery.py` checks interrupted deferred enable, File New, repeated
blend loads, intentional tab hiding, isolated teardown failures and third-party
panel restoration failures. Run in a disposable process with `--factory-startup
--python-exit-code 1 --python` and the absolute script path. Background mode checks
load events synchronously; omitting `--background` also checks real event-loop
initialization after File New, auto-quits and writes the system-temp file
`mbt_lifecycle_recovery_result.txt`. Injected-failure tracebacks are expected.

`test_generation_failures.py` checks mixed batches (curved solids, loose geometry,
open surfaces), optional remesh, always-on resolution, named errors/counts and sparse
work bounds independent of the empty bounding-box volume.
It also checks a simulated 6.50-GiB estimate against configurable allowances and
verifies subdivision does not change initial source-feature voxel selection.

`test_resolution_policy.py` checks conservative complete seam welding, genuine
openings, tiny sharp-edge hints, missing disconnected shells within global tolerance,
and tighter local thin-wall acceptance constraints.

`test_auto_generation.py` checks automatic always-remesh generation, scale-aware
resolution, strict failure preservation, stable refresh, automatic collection/set
registration, matching and Bake validation without selecting generated outputs.

`test_dynabool.py` reproduces the old fine-voxel disappearance and checks repaired
SDF extraction, manifoldness/bounds, thin and overlapping/disconnected solids,
open-surface fallback/strict refusal, protected upgrades, save/reload, processor
fingerprint migration, voxel budgets and rollback. Run in disposable background
Blender with the arguments documented in [DYNABOOL.md](../DYNABOOL.md).

`test_asset_tracking.py` checks explicit stage baselines, source/modifier/settings
changes, protected working lows, shared UV dependencies, export/validation freshness,
rename-stable collection identities, pinned-proposal and shared-low guards, preview
selection restoration, reload and unknown legacy/versioned baselines. Requires a
disposable background Blender; it exports only to a temporary directory, without Painter.

`test_asset_uv.py` checks textured source/material and secondary-map preservation,
UV locks and reviewed baselines, disposable proposals, stale/tampered proposal guards,
preserved seams/protected edges, failure cleanup, shared-layout packing, Preserve /
Automatic modes, read-only stage diagnostics, issue pointers and save/load/record
cleanup. It requires a disposable background Blender, not Painter. Run with the same
arguments as `test_registration.py` below. `test_painter_ui_live.py` also draws the
expanded UV and Validation sections in a real Blender window.

`test_painter_ui_parity.py` checks baking UI properties and operator actions,
all seven map choices, narrow/wide layouts, busy-state gating, issue filters,
unchanged defaults and side-effect-free drawing in disposable background Blender.

`test_baking_workspace.py` checks separate Tools/Baking N-panels, feature lifecycle,
sidebar-manager discovery, preserved section buttons, collision-safe collection
names, role colors, and visibility controls for hidden/excluded collections.
`test_painter_ui_parity.py` checks the complete workflow and original control order
in Bake, Model asset actions, standalone Export controls, and cross-tab cancellation.
Run in disposable background Blender.

`test_painter_skew_fixtures.py` requires disposable background Blender, not
Painter. It checks eight-vertex topology, joined/separate high inputs, an actual
corner gap missed by both adjacent perpendicular ray families, a nonempty angled
ray witness, source preservation and the lack of local sparse-cage controls.
Run with the same `--background --factory-startup --python-exit-code 1 --python`
arguments as the other background scripts.

The live coverage harness also accepts `--sparse [--edge-gap]`; `--edge-gap`
requires `--sparse`. The gap run passes only if averaged projection covers a
nonempty blue witness while mesh-normal projection loses over 90% of it.
Neither sparse run applies correction or claims automatic readiness. Refusal
to replace an unrelated open project is intentional; do not bypass the guard.

`test_painter_planar.py` checks read-only planar grouping, geometric boundaries,
triangulation diagonals, transforms/scales, gentle bends, invalid/nonfinite and
nonmanifold rejection. It does not contact Painter.

`test_painter_skew_coverage_live.py` requires disposable background Blender with
`-- --live`; optional `--joined` joins evaluated high inputs before export.
It refuses open projects unless `--replace-test <absolute-spp>` names the exact
retained skew fixture. It retains material-ID maps including flat caps, a dense
synthetic low, expanded/vertical/local cages, discovery and result JSON. Its local
field uses known fixture positions; it never remeshes artist assets. PASS requires
interior ID placement/overlap/recall and a nonempty preserved boundary witness.
`automatic_correction_ready` stays false: boundary-ray preservation is not correct
hard-edge coverage. Inspect `result.json`, including limitations, not just the exit
code. The disposable project is left open with distance-based/averaged settings
restored, while its baked maps remain experimental.

```powershell
$blender = 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe'
& $blender --background --factory-startup --python-exit-code 1 --python "$root\tests\test_registration.py"
```

Use the same invocation with one of these scripts:

| Script | Coverage |
| --- | --- |
| `verify_structure.py` | Syntax and add-on module/import assumptions |
| `test_registration.py` | Registration, Modifier List and Resample regressions |
| `test_script_runner.py` | Script favorites CRUD, selection safety, execution, validation and feature lifecycle |
| `test_feature_preferences.py` | Optional-feature preferences and lifecycle |
| `test_modifier_timings.py` | Modifier evaluation timing behavior |
| `test_modifier_catalog.py` | Native modifier catalogs with appended/prepended third-party menu callbacks |
| `test_n_panel.py` | Sidebar tab visibility, ordering and lifecycle |
| `test_preferences.py` | Preference data, command pickers, shortcuts and drawing |
| `test_scene_performance.py` | Scene scanning, selection, cancellation and lifecycle |
| `test_sidebar_sections.py` | Selection logic and sidebar integration |
| `test_vertex_color.py` | Storage/domain matrix, selection, channel math, rollback, batch/shared meshes, attributes and preview data |
| `test_substance_painter.py` | Painter jobs, validation and material integration |
| `test_painter_bridge.py` | Transport and controlled Painter API behavior |
| `test_painter_baking.py` | Bake configuration, cancellation, errors and save gating |
| `test_painter_distances.py` | Automatic signed front/rear estimates, scene units, evaluated transforms/modifiers, set scoping, manual override and exported-geometry rebake consistency |
| `test_painter_projection.py` | Pixel-space estimates, plane/box fixtures, transformed geometry, curvature/UV skips, state restoration and read-only capability gating |
| `test_painter_workflow.py` | Grouping, matching, project reuse and workflow regressions |
| `test_asset_processing.py` | Metadata-only asset CRUD/adoption, source preservation, UUID/pointer persistence, missing sources, Model UI, busy gating and lifecycle |
| `test_asset_generation.py` | Real DynaBool/subdivision/SDF, preserved sources/lows/UVs, stable high refresh, edit/budget/failure guards, reversible previews, actual standalone FBX export, cleanup and save/reload |
| `test_painter_texture_sets.py` | Shared default set, parent/child collections, per-set controls, real FBX material sharing, shared image import, rebake, persistence and legacy protection |
| `test_painter_inputs.py` | Aggregated issues, popup actions, offset UV preservation, hidden/excluded collection restoration, many-to-many bake groups |
| `test_painter_issues.py` | Individual/candidate/all selection, hidden mesh reveal, rename/delete/save/load identities, filters, safe UV face navigation, trailing roles, tiny/mirrored transforms, auto/manual provenance and inactive-set guards |
| `test_painter_matching_diagnostics.py` | Group-union surface matching, strict diagnostics, best-effort bake assignments/report persistence, invalid overrides, spatial samples, scoped validation and evaluated UV diagnostics |
| `test_painter_status.py` | Fixed-row long/short status, independent elapsed clock, throttled text, preparation handoff, cancellation and details operator |
| `test_painter_guard.py` | Controlled Painter window guard/watchdog and safe project opening; optional `-- --live-ui` launches/connects Painter and briefly hides/disables/restores its window without changing projects |
| `test_painter_inputs_live.py` | Opt-in background `-- --live`: real two-low/one-high bake, offset islands, hidden collection and window protection; refuses existing projects, retains test files, closes only its exact test project |
| `test_painter_runtime.py` | AUTO worker/main-thread handoff, cancellation, failure gates, scene/job changes, teardown/restart and real file reload |
| `test_painter_preparation.py` | Staged preparation, cancellation at each yield, temporary/output cleanup, hidden-state restoration and early runtime cancellation |
| `test_painter_performance.py` | Synthetic subdivided high-mesh preparation timings; system temp `mbt_painter_performance.json`; no Painter launch or fixed performance threshold |
| `test_uv_suite.py` | UV packing, shapes, seams and rollback |

Painter checks use controlled responses by default. Passing `-- --live` to the
bridge or baking script explicitly opts into using installed Painter and creating
a disposable project. These checks may launch Painter and leave a test project
open. See SUBSTANCE_PAINTER.md in the project root before using live mode.

## Interactive Blender checks

### Painter remote access preflight

Official reference:
<https://experienceleague.adobe.com/en/docs/substance-3d-painter/using/scripting-and-development/scripts-and-plugins/remote-control-with-scripting>

Painter must be started with `--enable-remote-scripting` and finish startup. The
protocol is HTTP POST `/run.json`, port `60041`, JSON containing a Base64 UTF-8
`python` expression; Python results must be explicitly serialized. Our bridge
handles the returned JSON/string layers and probes both IPv4 and IPv6 localhost.

For future agent sessions, run this **connect-only, read-only** preflight first:

```powershell
$root = 'C:\Users\mariu\AppData\Roaming\Blender Foundation\Blender\5.2\scripts\addons\MBToolkit'
$python = 'C:\Program Files\Blender Foundation\Blender 5.2\5.2\python\bin\python.exe'
& $python "$root\tests\probe_painter_remote.py"
if ($LASTEXITCODE -ne 0) { throw 'Painter preflight failed; inspect the report before live tests' }
Get-Content (Join-Path $env:TEMP 'mbt_painter_remote_probe.json')
```

No Blender process or third-party library is required. The script dynamically loads
the existing bridge without importing `bpy`, tries `127.0.0.1` then `::1`, verifies
Python, and runs helper discovery in an isolated namespace. It does not replace
helpers/state in Painter globals, launch/close Painter, open/save/reload a project,
set bake properties or bake. `--port` and `--output` can override defaults. A failed
probe writes a failure report and exits nonzero. A successful transport with no
ready project reports projection `NOT_READY`, not verified correction support.

Verified November 4, 2026: only `::1:60041` responded; the process command line
included `--enable-remote-scripting`. Painter executable version was `11.0.3`,
whereas Python API `substance_painter.__version__` was `0.3.4` (not the application
version). Read-only discovery on the already-open project exposed `SmoothNormals`,
`CageMesh`, distance/automatic/custom cage modes and no skew-named common/detail
property. This does not prove that every possible API lacks skew support.

If unavailable, inspect the running process command line and test **both** address
families. An existing process without the launch flag cannot be fixed by changing
the HTTP request: have the user save/close it before restarting. Only launch
Painter yourself when no existing instance/project can be disturbed; use
`bridge.launch()` (it strips inherited Blender `OCIO`) or the documented executable
flag. Do not change firewall rules or expose the listener outside localhost.
An open project is fine for this probe but not for destructive live suites: never
close an unrelated project or bypass their disposable-project guards.

Controlled probe tests: run `test_painter_remote_probe.py` with ordinary Python.

#### Agent-managed startup (no user launch needed)

Use the same script with `--launch` to connect to an existing remote-enabled
instance or automatically start Painter when none is running:

```powershell
& $python "$root\tests\probe_painter_remote.py" --launch
```

This reuses `bridge.launch()` with `--enable-remote-scripting`, removes inherited
`OCIO`, auto-detects the executable and waits up to 90 seconds for IPv4/IPv6 access.
Override with `--executable <absolute-exe-path>` or `--startup-timeout <seconds>`.
Windows process discovery prevents a second launch if any Painter-named process
is running but unreachable; failed process discovery also prevents launch. It
never kills/restarts a session. Custom ports remain connect-only. The report's
`launched` flag records whether this invocation started Painter. Startup dialogs
can still require user interaction; on timeout the application is left running.
Agents should use this command themselves for future tests instead of asking the
user to start Painter. If an existing non-remote session blocks access, preserve
its unsaved work and ask the user to save/close it before retrying.

### Opt-in Painter live matrix

`test_painter_skew_live.py` runs in a disposable background Blender process with
`-- --live`. It requires a connected, idle Painter with no open project and
retains `MBToolkit_Painter_Skew_*` artifacts. It bakes a panel/bolt fixture in
averaged, perpendicular and averaged-repeat modes, checks footprint statistics,
queries the actual mode, and verifies save/reopen persistence. It leaves its test
project open. Inspect `result.json`, not only the exit code. A rerun may explicitly
pass `--replace-test <absolute-spp-path>` after `--live`; it saves/closes only that
exact existing path beneath a retained skew-test directory, never an unrelated
project. This is not a general correction/coverage certification.

`test_painter_live_workflow.py` requires `-- --live` in a disposable GUI Blender
process. It launches/connects Painter, refuses any pre-existing open project,
creates retained `MBToolkit_Painter_Matrix_*` artifacts, and exercises overlapping
mesh groups, all maps, project reuse/renames/geometry changes, retained fill/paint
layer markers, both ID sources, all AA choices, texture-only updates and both normal
conventions. It saves/closes only its own exact project to change conventions and
leaves the final project open. Check `result.json`, not just the process exit code.

With that final project still open, run `test_painter_live_update.py` in another
disposable GUI Blender process with `-- --live --blend <absolute-matrix-blend-path>`.
It discovers the installed PBR Metallic Roughness preset's actual filenames,
tests an explicit custom mapping, checks stale-AO removal and draws the Bake UI in
a real popup layout. It creates `update_result.json` beside the retained blend.
It neither bakes nor saves/closes Painter. It defers GUI work until after file-load
context restoration. Both live scripts require result-file inspection; neither
certifies brush-stroke reprojection, production assets or real OS input behavior.

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
| `test_script_runner.py -- gui` | Native favorites menu, management list and sidebar drawing; result in system temp `mbt_script_runner_ui_result.txt` |
| `test_scene_initialization_live.py` | Scene initialization in an interactive process |
| `test_scene_performance_live.py` | Scheduled collection, real selection and editor isolation |
| `test_sidebar_sections_live.py` | Sidebar section UI drawing |
| `test_vertex_color_live.py` | Native color UI, GPU channel previews, transaction cancel, mixed accept and undo/redo; results in system temp `mbt_vertex_color_live_result.txt` |
| `test_painter_ui_live.py` | Painter real-layout collapsed/expanded/busy drawing, action icons and status; result in system temp `mbt_painter_ui_result.txt` |

For `test_vertex_color_live.py`, also pass `--enable-event-simulate` to dismiss the
startup splash in the disposable process. It validates native picker layout and
the live transaction callbacks, not OS-driven dragging/acceptance of the modal dialog.

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

Script favorites persistence uses `test_script_runner.py -- write` followed by
`test_script_runner.py -- read` in two background Blender processes. Set
`BLENDER_USER_CONFIG` to a fresh disposable directory whose name contains
`mbt_script_test_config`; create that exact directory before launching Blender
(a nonexistent path can fall back to the real configuration). The test also
checks Blender's resolved configuration path before saving. Use
`--factory-startup` only for the write process.
Restore the environment variable afterward. Never run persistence checks against
your normal configuration.

Run quick checks first, then the background checks for changed features plus
registration. Run the corresponding GUI checks for UI changes, and the two-process
check for sidebar preference persistence changes. Similar filenames usually cover
different execution modes or feature layers; do not remove them based on names alone.