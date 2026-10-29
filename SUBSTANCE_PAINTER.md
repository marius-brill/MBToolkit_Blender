# Substance Painter — Blender-controlled workflow

## Primary workflow: one Bake button

Choose low/high collections and an output folder, then press **Bake**. The button
validates inputs and material replacement policy, resolves bake pairs, exports fresh
evaluated meshes, connects/launches Painter, creates or opens the associated project,
reloads existing project geometry preserving strokes, bakes, saves, exports textures,
and imports Blender materials. An unrelated open project is never closed/replaced.
The job JSON is internal and is no longer shown in the panel.

The croissant **Bake** button has a **×** cancel control on its right (disabled
while idle). The blue-accented **Bake Status** box directly beneath it shows the
current object/phase. **Bake Settings** is collapsed by default and contains
front/rear distances, relative distance, antialiasing, normal format, project
template, material replacement and ID source (when the ID map is requested).
Resolution and requested maps remain visible.

Interactive preparation yields between validation, matching, snapshot and export
steps. Cancel closes the staged job, removes incomplete output/temporary copies
and restores hidden-input state before any Painter work starts. A single native
mesh evaluation or FBX export must return before the UI can process cancellation;
the cross is not an immediate hard stop for those operations. Background scripting
helpers remain synchronous. Explicit Bake Target, Bake Group or `_low`/`_high`
name pairs avoid the more expensive surface-matching fallback.

The collection **+** buttons now MOVE selected meshes: link the destination first,
then remove other collection memberships. Linked inputs, nested low/high collections,
and objects shared across scenes are rejected. Parenting/transforms are unchanged.

Matching is **By Mesh Name**. Existing `_low`/`_high` base names take priority;
otherwise evaluated world-space bounding boxes and sampled surface distances suggest
confident matches. Ambiguous, distant, and unmatched inputs block Bake. Select a high
mesh and set **Bake Target** to explicitly choose its low mesh. Resolved targets are
stored as object pointers. Only temporary export names change (`MBTBake_*_low/high`).
Stored targets take priority on subsequent bakes, even after moving a mesh. Clear
the high mesh's **Bake Target** to request name/surface matching again.
Set **Bake Group** on low/high meshes to share any number of lows and highs in one
explicit group. For example, two lows and one high with group `Body` both use that
high; one low and several highs also work. Shared `_low`/`_high` name prefixes are
supported without a group override. Explicit groups take priority over stored targets.
One texture set per low remains. Changing groups across existing project texture-set
prefixes may require **New Project Next Bake** to preserve safe name matching.

### Input warnings, hidden collections and offset UVs

Validation collects all mesh/UV issues into one popup with object names and reasons.
Choose **Ignore & Continue** and confirm to acknowledge quality warnings for this
request, or **Select Issue Meshes** to stop and reveal/select the affected objects.
Cancel leaves the scene unchanged. Missing UV maps, non-finite UVs, unusable geometry,
linked data and singular transforms remain blocking; Ignore never silently drops meshes.
Collapsed UV triangles and triangles crossing the bake-tile boundary are warnings.

Hidden objects, collection viewport toggles and excluded collection ancestors in the
active scene are temporarily made available for matching/evaluated export, then restored
even on failure. Investigating via Select intentionally leaves issue meshes revealed.

Offset mirrored UVs outside 0–1 are accepted and preserved, not wrapped back into the
bake tile. Wholly out-of-tile triangles do not participate in tile-specific quality
checks. This is still a single-tile project, not UDIM support. Verify a representative
asset in Painter when using offset mirroring; coordinate preservation is regression
tested but production bake results depend on the mesh and Painter configuration.

### Unattended baking and opening the project

During automated baking, Painter's main window is disabled and hidden using its UI
API, then restored to its prior visibility/input state before Blender reports completion.
This is protected unattended operation, **not a separate no-GUI rendering process**.
If the UI guard cannot be installed, baking stops rather than running unprotected.
A five-minute remote-heartbeat watchdog restores the window if Blender disconnects.
Startup/license dialogs and other remote clients are not covered by the main-window guard.

**Open Painter Project**, directly below Bake, shows/opens the associated saved `.spp`
for texturing without reloading meshes or baking. It never replaces an unrelated open
project. **Advanced > Update Textures (No Bake)** imports subsequent painting changes.

Optional `.spt` project templates come from Painter preferences or the scene override,
and apply only on creation. Resolution/normal settings override the template.
Existing-project normal-format or low-membership changes require **Advanced > New
Project Next Bake**. That action preserves files and does not close Painter.
Source object IDs preserve import targets and texture-set/export names across renames.
Save the blend file to persist the project association. Missing internal data is an
error rather than a reason to guess which Painter project to modify.

If **Saved bake job.json is missing** appears, the blend still references a bake
folder that was deleted or moved. Restore that folder at the reported location to
retain the existing project mapping. If the old project is disposable, use **New
Project Next Bake** (also offered below that error), confirm, close the old project
in Painter, then Bake again. Resetting preserves existing files. Missing job data
is checked before expensive mesh preparation; it is never silently reconstructed
because that could mismatch existing painting and texture sets.

Texture export defaults to the inline **MBToolkit Blender PBR** definition; no preset
installation is necessary. Advanced **Custom Export Mapping** accepts a JSON file:

```json
{
  "preset": "resource://starter_assets/PBR%20MetalRough",
  "channels": {
    "base_color": "{texture_set}_BaseColor.png",
    "roughness": "{texture_set}_Roughness.png",
    "metallic": "{texture_set}_Metallic.png",
    "normal": "{texture_set}_Normal.png"
  }
}
```

Use the actual installed preset resource URL and its exact output filenames. Required
channels are base_color, roughness, metallic, normal; ao is optional. Only unpacked
PNG maps are supported. Configure the preset's normal convention to match Blender's
setting. Existence/output compatibility is confirmed by Painter during export;
the add-on validates mapping structure before baking. Packed-channel import is not
implemented. **Update Textures (No Bake)** handles painting-only updates.

`tests/test_painter_workflow.py` covers moves, grouping, ambiguity, refreshed snapshots,
project reuse, normal/membership guards, final export-name validation,
template/mapping preflight and controlled asynchronous reload handling.
`tests/test_painter_runtime.py` covers the automatic worker/main-thread handoff,
failure/cancellation gates, scene/job changes, teardown/restart and real file reload.
It runs with the same disposable background Blender invocation as the other tests.

### Legacy action/API reference

The older operators below remain available to scripts, but are not the main panel flow.

Open **3D View > Sidebar > MBToolkit > Bake**.

1. Choose low/high collections, or select meshes and use the **+** beside each field.
   Assignment moves objects out of their previous collections.
   Child collections are included. Low/high inputs must not overlap.
2. Use Object Mode. Inputs must be local meshes in collections belonging to the active
   scene; hidden/excluded collections are handled automatically. Low-poly meshes need
   finite active UV maps; intentional offset mirrored UVs are allowed.
3. Set a project name, output folder, resolution, requested bake maps, and normal format.
   A relative output folder requires a saved blend file.
4. **Validate** checks the setup. **Prepare Bake Job** makes a unique job folder
   containing `low.fbx`, `high.fbx`, `job.json`, and `textures/`.
5. Alternatively use **Send to Painter** to prepare a new job, connect/launch Painter,
   create a project from the low FBX, verify texture-set names, and save its `.spp`.
   Painter must have no project open. Sending alone does not bake.
   Use **Bake New Project** instead for prepare → create → bake → save → export → import,
   or **Bake Current Job** to bake the matching open project using its saved snapshots.
6. Click **Import Maps / Update Material**. Enable **Replace Existing Materials**
   only if you want all existing slots replaced. Otherwise existing artist materials
   are protected. Integration-owned material graphs are rebuilt on reimport, so do
   not put custom edits inside them. Unrelated materials are not deleted.

## Current contract

- The local **MBT PBR — Unpacked PNG** layout is a filename contract, **not** a
  bundled or automatically installed Painter export preset.
- Each low object exports with one temporary material/texture set. Its actual
  exported material name and expected filenames are recorded in the manifest.
  Original per-face material splits are intentionally flattened in the export copy.
  High-poly material assignments and mesh color attributes remain in the snapshots
   for ID-baker configuration.
- Texture filenames are `<texture_set>_BaseColor.png`, `_Roughness.png`,
  `_Metallic.png`, `_Normal.png`, and `_AO.png` by default. Custom mappings supply
  their own exact unpacked PNG filenames.
- At least one shader map must exist for every target before import proceeds.
  Missing maps are reported; AO alone cannot produce a shader import.
- Base Color uses sRGB. Scalar maps and normals use Non-Color. Normals connect
  through a tangent-space Normal Map node; DirectX green is inverted if requested.
  AO is loaded as an unconnected inspection node, not multiplied into Base Color.
- An explicit UV Map node uses the UV layer captured when preparing the job.
- Meshes export as evaluated, triangulated snapshots using viewport modifiers and
  world transforms. Source objects, selection, visibility, modifiers and materials
  are not changed during preparation. Geometry Nodes instances must be realized.
- Import uses stable source-object IDs in the current scene; older manifests without
  IDs fall back to original names. Object renames are supported. Renaming a captured
  UV layer requires preparing another job.
- One active setup per scene; settings persist in the blend file. Internal manifests
  are managed by Bake; legacy scripts can select one through `last_job`.
  Every preparation gets a new directory;
  delete old job folders yourself when no longer needed.
- JSON schema version 1 records requested bake maps separately from returned PBR
   textures. Legacy preparation uses `match_method: ALWAYS`; the unified Bake action
   uses `BY_NAME`. Custom cages are not implemented.

## Automated baking

- Select Normal, AO, Curvature, Position, Thickness, World Space Normal and/or ID.
  Only selected bakers are enabled; Curvature uses the high mesh (From Mesh).
- Front/Rear Distance control projection. Relative distances are bounding-box
  fractions; absolute distances use Painter scene units (centimeters).
- Antialiasing offers None, 2×2 (Supersampling 4x) and 4×4 (Supersampling 16x).
  ID supports Material Color or Vertex Color from the high-poly snapshot.
- Projection is distance-based. Automatic Bake filters high geometry by matched
  export names. Legacy preparation uses all high geometry for each low texture set;
  separate those legacy jobs where unrelated highs would interfere.
- **Bake Current Job** updates bake settings in the selected manifest but does
  not re-export geometry. Prepare a new job after mesh changes.
- Progress uses Painter's asynchronous bake events. Only a confirmed successful
  bake followed by a successful save proceeds to export and main-thread import.
- **Cancel Bake** requests cooperative cancellation. It cannot interrupt an
  in-flight save/export HTTP request; cancellation during export skips material
  import but retains successfully recorded texture paths. Cancellation during
  project creation waits for that request and prevents subsequent baking.
- The bake/save polling window is 30 minutes. Timeout or lost communication is
  an uncertain result, not proof that Painter stopped. No automatic retry or
  export/import follows; inspect Painter before retrying.

Not implemented: installed Painter preset discovery, packed channels, UDIMs and
custom cages. Custom preset resource URLs are supported through explicit unpacked
PNG mappings; there is no preset browser. **Legacy Prepare is not Bake.**

## Export from Painter / Import

After manually baking/painting, keep the associated saved project open in Painter
and use **Advanced > Update Textures (No Bake)**. Legacy scripts can select the
matching `job.json` and invoke **Export from Painter / Import**.
The action connects only (it does not launch Painter), verifies the open `.spp`
path and texture sets, and exports our inline unpacked PBR PNG layout. No separate
Painter plugin or project repository is required: the worker runs inside Painter,
while Blender orchestrates the request and imports materials on its main thread.

Each export uses a fresh `textures/export_*` directory. Painter's returned paths
are checked for required channels and existing files before atomically updating
the manifest. The material importer then uses those paths. Existing-material
protection still applies; if import is blocked, enable replacement only if intended
and use **Import Maps / Update Material** without exporting again. Old exports are
retained and can be deleted manually.

Exports include Base Color, Roughness, Metallic, mixed tangent-space Normal in the
job's convention, and mixed AO when available. Baking is NOT triggered. The inline
MBT layout is the default; custom mappings use the configured preset URL. Painter export
warnings may indicate missing unbaked sources; inspect the exported maps.

Manual import still uses exact manifest paths, but missing-map errors now list the
active job, expected filenames, searched folders and files found (up to 30 names).
Simply putting differently named PNGs in the same directory does not map channels.
Automatic filename guessing/channel remapping is not implemented.

Export configuration/identity checks and manifest recording have automated tests.
Live bake, save, export and Blender material import have passed on a disposable
512-pixel cube job with Painter 11.0.3 and Blender 5.2. This verifies the basic
round trip, not production assets or every map/ID/antialiasing combination.

## Painter connection

In **MBToolkit Preferences > Painter**, use **Detect** or choose the executable.
The default local port is 60041. **Test Connection** never launches Painter;
**Launch / Connect** and **Send to Painter** can launch it with
`--enable-remote-scripting`. Custom ports are connect-only.

The client tries IPv4 `127.0.0.1` and IPv6 `::1` loopback using Adobe's `/run.json`
protocol. Painter 11.0.3 on this machine listens on IPv6 loopback only.
Launch removes the inherited `OCIO` environment override for the Painter child
process only; Blender and the system environment are not modified.
Remote scripting executes code: keep the port firewalled and use a trusted machine.
The add-on does not control which interfaces Painter's own server binds to.
It never closes/replaces an open Painter project. Project creation refuses to
overwrite an existing `.spp`; a successful bake intentionally saves the matching
open job in place.
If Painter is already running without remote scripting, save/close it yourself
and relaunch using the button. Complete any startup/license dialogs manually.

Network requests run off Blender's UI thread. Interactive preparation advances on
main-thread timer ticks; individual evaluation/export calls remain synchronous.
Startup and project creation have bounded waits. A timeout does not terminate Painter
or retry project creation; inspect Painter before trying again. Disabling the add-on
requests cooperative cancellation of a running bake but cannot undo requests
already sent to Painter. Failed sends keep their prepared job folder for inspection.
Loading a blend file also requests cancellation, removes the polling timer and
invalidates queued results so they cannot import into the newly loaded scene.
Neither loading nor disabling terminates Painter; inspect it before starting again
if a remote request was already in flight.
Connection/bake results appear in Last Result; successful exports update exact
texture paths in the manifest.

Local installation detected during development: Painter 11.0.3. Live connection
and low-FBX project creation now work after adding IPv6 loopback support. The live
test exposed premature saving before edition state; saving now waits until both
edition state and not-busy are true. An initial test cube project was left open;
the corrected create/save cycle has also passed its live test.
The reported Python API version is not the Painter application version.

Progress displays the actual stage and elapsed seconds while connecting, validating
remote Python/API availability, creating, and waiting to save. Connection failures
and script failures are reported separately; completion/failure releases busy state.

## Tests

See `tests/README.md` for the test inventory and safe execution examples.

Run `tests/test_substance_painter.py` using Blender 5.2 with
`--background --factory-startup --python-exit-code 1 --python <absolute-test-path>`.
The script is destructive and must not run inside an existing working session.

`tests/test_painter_bridge.py` tests the transport and controlled Painter API behavior.
Appending `-- --live` explicitly opts into launching Painter and creating a cube
project in a retained temporary folder. It skips creation if a project is open,
never closes Painter, and leaves a successfully created test project open.

`tests/test_painter_baking.py` adds controlled configuration, event cleanup, bake failure,
cancellation, timeout, save gating and success-chain tests. `-- --live` opts into
baking a disposable test project, saving, exporting, then verifying Blender
material import. It may reuse an open project only when its parent directory has
the `MBToolkit_Painter_Live_` prefix; do not use that prefix for personal projects.
Run tests in a separate background Blender process, never a working session.

## Development stages and next steps

### Preparation reliability and profiling

Preparation reacquires the dependency graph after yields and checks structural
input/settings changes between interactive ticks. Changes to object membership,
names, mesh identity/counts, transforms, UV layer names, frame, matching overrides,
and writable scalar modifier settings stop the job before the next step. This is
not a full scene lock: same-topology coordinate/UV edits, node-tree edits, animated
dependencies and external-file changes are not exhaustively fingerprinted. Do not
edit bake inputs during preparation.

Cleanup uses collection identity paths so renaming a collection does not prevent
restoration. Removed RNA is reported as a cleanup warning while surviving state
continues restoring. Exact surviving selection and the active object are restored.

Advanced / Troubleshooting shows total active preparation time and the five
slowest staged operations. Times exclude idle gaps between ticks; a stage includes
all work until the next yield, rather than claiming isolated native-call timings.
The raw JSON is available in `scene.mbt_painter.preparation_timings` (not saved).
`test_painter_performance.py` supplies a synthetic subdivided-sphere fixture and
writes `mbt_painter_performance.json` in system temp. It does not launch Painter,
measure Painter bake/save/import, or certify a production heavy asset.

### Expanded live validation — October 28, 2026

Blender 5.2.0 LTS and installed Painter **11.0.3** (Python API **0.3.4**) passed
the GUI-driven synthetic live matrix at 512 pixels: two overlapping lows/four
beveled highs, all seven bake maps, material and vertex ID sources, all three AA
settings, source rename, geometry reload into the same project, stable texture
sets, fill-color and layer-marker retention, texture-only update, and a new DirectX
project with Blender green inversion. Exported files, dimensions, color spaces,
material identities and non-flat/different group normal pixels were checked.

The live test found and fixed an actual rebake failure: a completed mesh reload
omitted `project_file` from its response. The response now contains project path
and texture-set names, with a controlled regression assertion.

An additional live pass used the installed **PBR Metallic Roughness** preset with
its discovered exact filenames; custom-mapping export/import and stale-AO removal
passed. Bake controls drew successfully in a real Blender popup layout. The normal
sidebar tab was not selected (panel draw count zero), so this is not an OS-input
or full sidebar usability test. GUI test setup must wait for file-load context
restoration before changing region visibility.

See tests/README.md for the two opt-in live scripts and safety constraints. Inspect
their `result.json` and `update_result.json`, not process exit code alone. Synthetic
meshes and pixel statistics are not production-asset or human visual certification.
The retained paint layer is empty: real painted brush-stroke reprojection still
needs validation. Interactive target clearing, failure recovery and full sidebar
interaction also remain manual acceptance tasks. Scope expansion remains deferred.

### Controlled baseline

Validation on October 28, 2026: Windows, Blender 5.2.0 LTS
(`fbe6228777e7`). The five Painter scripts (including runtime), registration and
feature-preferences checks all exited 0 in disposable background processes with
isolated configuration paths. Ordinary-Python structure, repository and sidebar
selection checks also passed. Painter responses were controlled; this run did not
launch Painter or establish live visual correctness. The material-integration test
intentionally prints an FBX missing-file traceback to exercise failure cleanup.

1. **Implemented baseline:** the one-button workflow and controlled tests cover
   preparation, matching, project reuse, asynchronous reload, baking, save/export
   gating and material import. Historical live validation is the cube round trip
   above, not production-asset certification.
2. **Orchestration hardening:** runtime regression coverage exercises worker/main-thread
   handoff, cancellation, failed requests, scene/job guards, file-load cleanup and
   disable/re-enable lifecycle. Final reused mesh/texture-set names are checked
   before export. Keep these cases passing when changing the workflow.
3. **Partially validated — realistic assets:** the synthetic live matrix above passed;
   use disposable production-like projects to verify multiple
   lows, several highs per low, overlapping groups, renamed sources, geometry updates
   with retained painting, both normal conventions, both ID sources, antialiasing
   choices and custom mappings. Record exact versions and visually inspect results.
4. **Partially validated — usability:** real popup-layout drawing passed. Smoke-test
   actual sidebar interaction, stored-target clearing, uncertain-result recovery,
   feature toggles, collection moves and material protection in the interactive UI.
5. **Later — scope expansion:** specify and test cages, packed channels, UDIMs or
   preset discovery independently, after the reliability gates above are satisfied.

Follow CONTRIBUTING.md and tests/README.md: use disposable background processes,
run repository checks plus registration and affected tests, and perform manual UI
checks. Do not use blanket discovery or a production Painter project for tests.