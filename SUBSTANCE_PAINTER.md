# Substance Painter — Blender-controlled workflow

## Baking sidebar and collections

The **MBT Baking** N-panel is separate from the **MBToolkit** tools N-panel.
Its **Model / Bake / Export** selector reuses the expanded button-row layout:

- **Bake** is the default and contains the complete workflow in its original order:
  texture-set and Low/High collection setup, project name/output folder, resolution,
  Requested Bake Maps, Mesh Matching, Bake/Cancel and inline Bake Settings,
  Bake Status/Issues, Open Painter Project, then Advanced / Troubleshooting.
  Advanced includes custom export mapping, Update Textures (No Bake), New Project
  Next Bake, connection/diagnostic actions and Retry Material Import.
- **Model** contains assets/components, DynaBool generation, custom high assignment
  protected UV preparation, stage diagnostics and reversible visibility previews (see below).
- **Export** writes the active asset's low/high FBX and a manifest without Painter.

Bake Status is available in Bake; Cancel remains available on every tab while a
job is running. Switching tabs does not invalidate preparation.
Narrow sidebars stack collection fields, map choices and paired actions;
wider sidebars show two map columns. Low/High assignment buttons, collection
visibility controls, issue search/filtering, Select All, Revalidate and applicable
UV-face selection remain available. This is a presentation change only: existing
settings, map defaults, assignments and baking behavior are unchanged.

The tools panel retains its section buttons and selection, with no Tools/Baking
switch or duplicate Bake icon. Enable Substance Painter in add-on preferences to
show MBT Baking. Both categories can be managed independently by the Sidebar Tab
Manager.

New sets use the next available `TextureSet1`, `TextureSet2`, … name, with
`TextureSet1_low` and `TextureSet1_high` children. Existing custom collection names
are preserved. Low collections are tagged blue and high collections orange, with
matching indicators beside their fields; mesh materials are not recolored.

The parent and low/high collection fields use matching widths. Beside each, use
the checkbox to include or exclude the collection in the active view layer and
the eye for view-layer visibility. Collection-wide viewport restrictions remain
available in the Outliner, not duplicated here. Hidden ancestors or
individually hidden objects can still prevent meshes from appearing. Collection
visibility does not remove bake inputs; preparation restores temporary visibility
changes after evaluating/exporting them.

**Mesh Matching** is the single assignment editor for the active mesh, separate
from Requested Bake Maps. The compact **Bake Issues** area shows a short summary
and suggested action for the selected issue; Select Mesh activates its mesh for
editing in Mesh Matching. Full Details opens the original diagnostic and candidate
scores/coverage in a wider dialog. Select All, Frame, candidate-low selection,
Revalidate and applicable UV-face selection remain available. Diagnostics are
snapshots: revalidate after editing.

## Model: assets, generation and preview

For the current task-oriented manual, start with the
[Asset Processor wiki](docs/asset-processor/README.md). It covers optional Remesh,
configurable work allowance, automatic generation-time Bake registration and
protected UV workflows. Older implementation statements below are superseded
where they conflict with that reference.

### UV preparation and validation

After generating a low, choose **UV Preparation**:

- **Preserve** validates existing UVs without changing seams or coordinates.
- **Assisted** (default) builds disposable proposals using the existing UV suite's
  seam-region generation, unwrap-method search and packing. Select a proposal and
  enter Edit Mode / the UV Editor to inspect or adjust it. **Show UV Proposal**
  reveals the current proposal; **Prepare UVs** rebuilds it. Return to Object Mode
  before applying or discarding.
- **Automatic** prepares and applies only when every member of the same texture set
  is also Automatic and explicitly unlocked. It never silently bypasses UV protection.

**Protect UV Layout** defaults on, including textured meshes. Proposals do not change
working lows or source objects. Applying requires every shared member unlocked and
unchanged since preview; it updates only active UV coordinates/pins and seam flags
on independent, local, single-user lows, keeping low object pointers stable. Other
UV maps, material pointers/indices, shape/topology and mesh selections remain intact.
Original/adopted lows that share source geometry are validation-only. There is no
automatic source replacement or material reassignment. Review before texturing and
re-enable protection once approved. **Acknowledge Reviewed UVs** updates the reviewed
baseline without changing UVs; it is not an automatic repair.

Existing seams and pins remain artist constraints. For edges that must not acquire
new seams, use a Boolean edge-domain mesh attribute named `mbt_uv_protected` on the
working low. Preparation refuses a proposal crossing those protected edges instead
of forcing a cut. Proposal application rechecks seams, geometry, padding and overlap.

Components sharing a texture-set ID/collection are packed jointly. Components
without a set assignment share their asset's layout, consistent with standalone
export materials. Resolution follows the assigned set or global Bake resolution;
the strictest requested gap/border across members wins. Packing currently targets
tile 1001 only. Cross-asset shared sets are refused; consolidate them before UV
preparation. A Preserve member blocks joint repacking. Unchanged and locked members
cannot be silently moved to accommodate another member.

Use **Restore Visibility** or **Discard Proposal** to leave the preview. Proposals
are disposable and removed before save/load or feature disable and when their
records are removed; they are not exported or assigned to Bake collections. Existing
visibility-preview undo/redo restoration also applies. UV work is synchronous, with
a 50,000-face per-low limit and the UV suite's exact-check budgets.

Expand **Validation** and click **Validate Asset** for read-only ANALYZE, GENERATE,
GEOMETRY, UV and EXPORT findings. Select a finding for its reason, suggested action,
and pointer-based Select/Frame controls. Diagnostics cover missing inputs, transform
issues, non-finite/degenerate geometry, boundary/non-manifold edges, missing/collapsed
UVs, cross-component overlaps, padding, tile bounds, texel-density variation,
protected-layout drift and export planning. Open meshes, intentional stacks and
non-unit scales may be valid: warnings require review, not blind repair. Enable
**Allow UV Overlap** for every texture-set member only for deliberate stacks; new
proposals still require nonoverlapping packing. Large geometry skips detailed scans
and reports that limitation. Reports are snapshots, not bake-readiness guarantees;
revalidate after edits. This validation does not replace the existing Bake diagnostics
or assert thin-feature, projection, shading or texture quality.

Dependency-aware **Reprocess Outdated**, partial atlas rebakes, shared-high processing
and Blender-native baking remain deferred. A changed source never refreshes artist
low geometry or UVs through generation.

### Check Outdated (read-only dependency snapshots)

Use **Dependency Status → Check Outdated** to compare current inputs with the last
successful operation. It reports the selected component's low provenance, generated
high and shared UV dependencies, plus asset validation and export freshness.
States are Current, Outdated, Not Processed, Blocked and Unknown. Reasons explain
which class of dependency changed. Reports are explicit snapshots: check again after
editing. Panel drawing does not evaluate meshes or compute signatures.

Low provenance is recorded only when a low is first generated. Source changes never
authorize refreshing that low. Generated-high baselines are separate from the
ownership/edit guard; edited or shared highs remain blocked. UV baselines are recorded
after application, separately from artist-reviewed UV references. Protected/Preserve
members block automatic UV eligibility; a source-only change does not invalidate a
preserved working-low layout. Shared membership, geometry, seams, pins, active maps,
protection attributes, resolution and padding participate in UV dependencies.

Existing files without baselines report Unknown; checking never adopts their outputs
as current. Versioned baselines persist across save/load; displayed snapshots do not.
Collection-only assignments use pointer-backed IDs in processor metadata, not mutable
collection names, without tagging or renaming artist collections. Explicit set UUIDs
remain authoritative. Export material identifiers for collection-only/fallback groups
now use this canonical identity, so an export made before this change can have different
material names; inspect the new manifest before updating an existing Painter project.

Checks evaluate source/export snapshots synchronously and may be expensive for dense
modifier stacks. Current means dependency equality, not verified visual quality,
availability of previously exported files, or bake readiness. Incomplete validation
does not receive a current baseline. Bake handoff and Reprocess Outdated remain
unimplemented; no check launches Painter or changes existing Bake assignments.

Use **From Selection** for one component per selected mesh. Expand **Create from
Collection** to reference all meshes in a collection and its children. These
actions record object pointers and stable IDs only: they do not duplicate, rename,
move or modify objects, mesh data, UVs, materials, modifiers or bake assignments.
Asset records are stored in the blend file and do not require Painter to run.

**Adopt Bake Setup** reads the active Bake texture set without migrating or
reorganizing it. Its low meshes become component source/low references; existing
manual Bake Targets and explicit Bake Groups supply high references. Automatic
name/surface matching is deliberately not run. Unlinked highs are reported rather
than guessed. Repeated adoption of an already represented low setup is refused.

The compact asset/component lists allow renaming records, adding selected source
meshes (duplicates within an asset are skipped) and removing records. Removing a
record never deletes objects or changes the Bake setup. Expand **Component Details**
to inspect/reassign its source, inspect adopted low/high relationships, and record
**Protect UV Layout** intent (enabled by default). Deleted source pointers become
missing; a newly created same-named object is never silently substituted.

### Generate Component / Generate Asset

Choose **DynaBool**, **Custom High** or **Disabled** per component. DynaBool uses
the crease/subdivision/optional SDF-remesh node group on an independent
evaluated source snapshot, not the source object. Expand **Generation Settings**
for subdivision, crease angle, detail tolerance/smoothing and face budget. Resolution
is automatic, with feature/thickness estimates and bounded sampled quality checks.
Automatic Resolution stays enabled; Remesh can be unchecked for subdivision-only
highs. Manual voxel values do not control processor generation. Generate Asset reports
fresh per-object results and provides Select Failed Sources.
See [automatic remeshing](AUTO_REMESH.md) for quality limits and standalone differences.

The first generation creates an independent evaluated low if none is assigned.
An existing low is **never refreshed**, even after source geometry changes: this
protects artist edits, material assignments and textured UVs. To derive a new low,
create a new component/asset deliberately rather than replacing a textured one.
Generated meshes are registered automatically in reusable Bake texture-set Low/High
collections; no manual selection/assignment is required. They have internal work names
rather than reserved FBX export names. Source objects are not hidden or moved.

High refresh keeps its object pointer stable. It refuses shared, foreign or edited
generated high data. To retain an edited high, select it and use **Add Selected
Highs**, switching the component to Custom High. Custom assignment does not change
geometry or bake pointers on the artist's meshes. Multiple custom highs/floaters
can be added; **Clear High Links** removes references only. Adopted bake components
start in Custom High mode to avoid replacing their existing setup.

Subdivision/voxel estimates reject excessive settings before DynaBool evaluation;
an evaluated face limit rejects oversized results. These are safety bounds, not
precise RAM/time predictions. Remeshing can lose thin features and needs visual
review. Generate Asset processes components independently and reports failures;
successful components are retained if another fails. Generation is synchronous:
an individual evaluation cannot be cancelled mid-operation in this milestone.

Expand **Inspector** for Source / Low / High visibility and **Restore Visibility**.
Only referenced component meshes' view-layer hidden state is changed; unrelated
objects and excluded collections are not changed. Preview is restored on save,
load, undo/redo, feature disable and before generation/export. It is not a full
isolated comparison workspace or artifact detector.

### Standalone Export tab

Choose Low Poly / High Poly and the shared Output Folder, then **Export Active
Asset**. Each export creates a fresh asset-named folder containing `low.fbx`,
`high.fbx` as requested, and `asset.json`. UUID-based `_low` / `_high` names stay
stable across record/object renames. Components with no adopted set share one
asset material; adopted texture-set membership is used for temporary export
materials. Original material assignments are untouched. Missing generated/custom
inputs, singular transforms, invalid low UVs and export naming conflicts refuse
export; failed export folders are cleaned up. Disabled high mode contributes no
high meshes. High-only and low-only output are supported.

Shared custom highs across different components are currently refused rather than
silently given an incorrect pairing. Fusion/shared processing groups, map exports,
changed-only export and per-component projection overrides remain future work.
Export does not launch Painter, change the existing job/project association or
wire generated meshes into existing Bake collections. Use the existing Bake
collection assignment controls explicitly when you want to bake generated meshes.

Asset-stage UV proposals and validation are described above; full dependency tracking
remains deferred. Protect UV Layout gates processor UV application, not Blender's
native UV editing tools or existing UV operators. Existing lows are always preserved
by generation, regardless of that setting. The existing Bake workflow is unchanged.

## Shared materials and automatic cage reach

Map import assigns one shared material datablock per texture set to all of its
low-poly members. Reimport updates that material without creating per-object
copies; unrelated users remain protected. If members use differently named UV
maps, import selects each member's recorded map as its active-render UV and uses
that map for both texture coordinates and tangent-space normals.

**Automatic Cage Distances** is enabled by default for each texture set. During
preparation, evaluated world-space low surfaces are compared with all matched
high vertices and triangle centers. Front and rear reach are estimated separately,
with 10% padding plus a small set-scale margin. Automatic values use absolute
centimeters (Relative to Bounding Box is disabled), matching the FBX export units.
Disable the option to author distances and relative mode manually.

These are signed nearest-surface estimates, not a guarantee of Painter ray
coverage or skew correction. Ambiguous receiver samples enlarge both distances;
their count and the estimation method are recorded in the job manifest. Rebaking
an existing export retains its calculated distances; prepare again after geometry
changes. Jobs prepared before automatic estimates existed must be prepared again
before rebaking with this option enabled.

## Projection/skew investigation — diagnostic increment

### Sparse-topology/backend prerequisite (November 5, 2026)

The non-averaged option is now **Mesh Normals — No Averaging** (the persisted
`FACE` identifier remains compatible). It follows imported mesh normals, which
are not necessarily geometric face normals. The diagnostic now interpolates
evaluated corner normals in this mode, including smooth/custom shading, instead
of incorrectly predicting zero skew for every planar face.

Multi-set jobs with differing bake options unlink Painter common parameters
before acquiring property handles or setting resolutions. If the API cannot
isolate them, the bake fails before starting instead of silently sharing the
last set's distances/projection mode. Single-set/legacy linking is unchanged.

Read-only discovery reports custom-cage availability, skew-named candidates and
common-parameter isolation support separately from verification. No candidate
is treated as proof of working correction. Automatic correction remains disabled.

The coverage harness accepts `--sparse` for an eight-vertex receiver and
`--sparse --edge-gap` for a blue corner witness outside both adjacent low-face
extents. Its live acceptance requires nonempty averaged coverage and substantial
loss with non-averaged flat mesh normals. This is a prerequisite experiment,
not correction acceptance. The independent offline fixture test checks the
geometric ray gap; it does not establish Painter's actual projection behavior.
There are no interior sparse-cage vertices to correct independently of edges.

### Local cage and full detail-ID coverage milestone

The next disposable experiment adds material-ID bakes, including flat caps that
normal-detail masks cannot see. Two interior bolts have different heights and a
third colored witness straddles the receiver boundary. The synthetic low is a
dense, topology-matched cube from the outset; artist meshes are never subdivided.
Expanded, vertical-interior and locally blended cages are compared. The local
field uses known bolt positions, keeps boundary displacement unchanged, and checks
triangle orientation against the original geometry. This is not automatic detail
detection, a production cage exporter or a solution for sparse artist topology.

Both separate-high and joined-high runs passed. The final joined run retained in
`MBToolkit_Painter_Skew_gpels_vf` under the system temporary directory reports PASS:
interior bolt ID recall 1.000 for both heights, shape IoU approximately 0.992 and
centroid errors 0.0073px / 0.0046px. Expanded-cage errors were 4.66px / 6.99px.
Local correction preserved the expanded cage's blue boundary-witness mask exactly
(IoU 1.000), while global perpendicular rays produced a different mask. All three
cage settings survived save/reopen; source low coordinates remained unchanged.
ID classification includes caps but does not certify normal-map fidelity or all
surface hits. These subpixel fixture metrics are not general accuracy guarantees.

Crucially, the preserved blue witness itself differs from the perpendicular
reference. Preserving baseline rays is proof of locality, NOT proof that those
rays are correct or that hard-edge coverage is solved. A fixture demonstrating
actual missing hard-edge detail is still an outstanding acceptance gate.
`automatic_correction_ready` remains false. Painter is left with the disposable
project open, restored distance-based/averaged settings and experimental maps.

The new read-only `planar.py` foundation groups edge-connected coplanar polygons
against a fixed seed plane, calculates an area-weighted representative normal and
protected boundary segments, and measures boundary distance. It does not chain
small bends into a plane; UV seams and triangulation diagonals are not boundaries.
Invalid/nonplanar/nonmanifold faces are unassessed. It currently has standalone
tests and live-fixture checks, not UI or automatic bake integration. Returned face
IDs belong to the exact input snapshot, not necessarily source Edit Mode topology.

### Next-stage validation and cage feasibility

November 4, 2026 follow-up: the live harness now uses non-overlapping, non-collapsed
side-face UV islands, explicitly reads normal maps as non-color, and compares
decoded full-image hashes on repeated bakes. Both explicit projection settings
are checked through save/close/reopen. An independent Blender BVH orthographic
reference measures thresholded normal-detail placement, shape overlap and recall.
This is not a measurement of every high-surface ray hit: flat bolt caps are not
normal-detail pixels, and rasterization/antialiasing differ between the reference
and Painter. Earlier area/centroid statistics remain historical mode comparisons.

On the 512px box/bolt fixture, averaged projection had 2.943px centroid error,
0.231 intersection-over-union and 0.570 normal-detail recall against that reference.
Perpendicular projection had 0.187px error, 0.932 overlap and 0.970 recall. A
test-only custom-cage adapter produced the averaged output with an expanded cage
and the perpendicular output with a vertical-top cage. Cage mode/file settings
survived save/reopen for both cages. This proves direction control on this
eight-vertex fixture, NOT arbitrary localized correction or general export-order
validation. Production jobs still use distance-based projection.

An additional high-panel bevel provides a nonempty edge witness: all tested modes
retained approximately 0.931 of the reference edge-normal detail, with no measured
regression. Because this witness did not distinguish modes, it does not prove an
edge-protection solution. Sparse cage vertices cannot express arbitrary local
per-texel control around a bolt. Native map assignment remains unverified; the
captured common/detail property keys exposed no skew-named parameter. Newer
Painter documentation must not be treated as proof of installed 11.0.3 support.

Latest guarded run: `MBToolkit_Painter_Skew_60n8fu98` beneath the system temporary
directory. Its `result.json` reports PASS, both cage persistence checks and the
edge-witness nonregression check. `backend_discovery.json` records runtime property
keys and public baking/resource docstrings. Five normal PNGs, two cage FBXs,
fixture and project are retained. The disposable project is left open with
distance-based/averaged settings restored; its last baked maps are experimental.

Next gate: create a fixture that exposes hard-edge coverage loss, add a full-hit
coverage/ID witness and multi-height/joined/near-edge cases, then prove a genuinely
local backend before implementing planar patches and automatic correction.

### Live bake findings and explicit projection control

November 4, 2026: the guarded launcher started Painter without manual startup.
A retained synthetic 512px panel/hex-bolt experiment completed real bake/save/
export cycles in Painter 11.0.3 (Python API 0.3.4). Averaged projection produced
3,446 thresholded normal-detail pixels; perpendicular projection produced 1,709.
Their footprint centroids differed by 3.076 pixels. Switching back to averaged
projection reproduced the original footprint statistics exactly. The final
projection setting survived an actual save/close/reopen of the exact test project.
These measurements describe the thresholded normal-detail footprint, not coverage,
geometric accuracy or proof that the smaller footprint is universally better.

**Bake Settings → Projection Normals** now explicitly controls Painter's
`SmoothNormals` per texture set: **Averaged — Edge Coverage** (default) or
**Mesh Normals — No Averaging** (formerly Perpendicular — Flat Detail). This is an opt-in whole-set option,
not automatic local skew correction; it can lose detail at hard edges. Source
shading normals remain unchanged. New jobs set the mode explicitly to prevent
inheriting stale Painter settings. Older manifests without this field preserve
their historical behavior until bake settings are refreshed.

The analyzer now respects this mode and accumulates each polygon once per corner,
avoiding triangle-diagonal weighting bias. A relative coplanar tolerance removes
tiny coincident-surface numerical warnings. Checked/skipped counts no longer
double-count invalid projection samples. The improved model flagged the raised
bolt (39.64px approximate maximum) and not the coincident panel; face mode reported
no estimated skew on this fixture. That maximum is not the measured 3.076px
centroid difference: they measure different quantities, and the approximation is
not numerically calibrated to Painter rays.

Final retained artifacts:
`C:\Users\mariu\AppData\Local\Temp\MBToolkit_Painter_Skew_uis8dwu3`
contain `result.json`, three normal PNGs, `fixture.blend`, FBXs, manifest and SPP.
The disposable test project is left open in Painter. Only exact previously-created
test paths were saved/closed during reruns. General edge-safe correction, custom
cages, coverage and production-asset visual certification remain unverified.

**Bake Settings → Analyze Projection** estimates raised-detail displacement in
output pixels using world-space geometric polygon-normal averaging and the local
UV mapping. **Skew Warning (px)** defaults to one pixel. Results appear in Bake
Issues with assigned-low navigation; **Projection Details** contains sample counts
and the model description. This is an explicitly requested diagnostic, not an
automatic bake-stage change. It does not change source normals, geometry, UVs,
distances, cages or Painter settings, and does not claim to fix skew.

The current model is an approximation, not Painter's actual ray field: it uses
area-weighted polygon normals, not backend-specific averaging, imported custom
normals or cage interpolation. It samples 256 high-surface locations per object;
small details on joined meshes can be missed. Gently curved triangles, ambiguous
receivers, missing UVs and invalid projections are reported as unassessed, not
certified safe. It does not yet fit planar patches, generate correction masks,
detect UV overlaps, validate ray coverage or protect edges. Analysis currently
runs synchronously from the UI and may pause it on large meshes; its generator
supports early close/state restoration for future staged integration. Results are
snapshots: rerun after edits or texture-resolution changes.

**Advanced → Inspect Projection Capabilities** connects to an already running
remote-enabled Painter and reads relevant bake property values/enums. It neither
launches Painter nor opens/changes projects. No ready project yields `NOT_READY`;
discovery failure yields `UNAVAILABLE`. Even a property containing `Skew` is not
proof of a writable/persistent correction map: `correction_verified` remains false.
Full results are available through Bake Status Details.

Validation on November 4, 2026: the new disposable Blender suite passed flat-plane
and box-face fixtures, pixel-space math, rotation/translation invariance, curved
shell rejection, missing-UV reporting, singular-transform rejection, hidden-input
restoration and controlled read-only API discovery. Existing baking, runtime,
registration, preparation and repository checks passed. These checks do not
establish real Painter ray accuracy. The local Painter remote endpoint could not
be reached on IPv4 or IPv6; no live correction bake was run.

Next gate: discover the installed runtime properties in a disposable project,
prove supported skew-map writing and save/reopen/reload persistence (or measure a
custom-cage fallback), then implement planar patches, edge-protected masks and
coverage validation. Automatic correction remains deliberately unavailable until
that experiment succeeds. Existing artist-painted corrections must be preserved.

Remote-access follow-up on November 4, 2026: a read-only preflight subsequently
connected successfully through IPv6 `::1:60041` to the user's remote-enabled
Painter, without modifying its open project. The installed executable reports
11.0.3 and its Python API reports 0.3.4. Common/detail discovery exposed
`SmoothNormals`, `CageMesh`, and distance-based/automatic/custom-file cage modes,
but no skew-named property. This supersedes the earlier connection failure, not
the outstanding correction-bake verification. Repeatable access instructions and
the standalone probe are documented in tests/README.md; future agents should use
that preflight before live tests. No correction bake or persistence test was run.

## Clickable bake diagnostics

Validation on November 4, 2026 used disposable Blender 5.2.0 LTS processes.
Affected background suites, registration/feature lifecycle, the real-layout GUI
check and a live Painter grouped bake/save/export/import passed. The live fixture
also exercised a group containing an interior role token (`Panel_low_trim`).
This is synthetic workflow validation, not human visual certification or an
exhaustive production-asset test. The preparation benchmark (256×128 sphere,
subdivision level 2) completed in approximately 15.5 seconds active time on this
machine; most time was mesh validation/evaluation, not matching. It is not a
before/after performance comparison or a universal speed guarantee.

**Bake Issues** remains beneath Bake Status and is also used by the validation
dialog. Click a mesh name to reveal, select and activate just that mesh. **Frame**
is separate, so browsing does not move the viewport. **Select All** selects all
affected meshes; **Select Assigned / Candidate Lows** selects the recorded low
objects. Expand the native list filter to search names, reasons or texture sets,
or show blocking issues only. Details show candidate scores/coverage when available
and expose Bake Group / Bake Target corrections. Selection is disabled during baking.

Reports are snapshots: use **Revalidate** after editing. Object and candidate
pointers survive renames and save/load; deleted objects appear missing rather than
selecting a new object with the same name. Revealing deliberately changes hidden,
excluded and selection-locked state. **Select Issue Faces** rechecks current UV
diagnostics and evaluated/source topology before entering Edit Mode. It refuses
changed topology, stale diagnostics and shared mesh data instead of selecting
potentially unrelated source faces.

Automatic target suggestions remain visible but are recomputed on subsequent
bakes. Assigning Bake Target manually pins that choice, including assigning the
same object again. Pre-existing stored targets are treated as manual for compatibility.
Name parsing removes only trailing low/high roles and numeric duplicate suffixes;
interior words such as `vehicle_low_panel` remain part of the asset identity.
New export prefixes escape interior `_low`/`_high` tokens; existing project name
associations remain protected by the original reuse guards.

Surface matching still ranks correspondence, not bakeability. Close candidate
scores trigger a 512-sample refinement. Bounded spatial probes supplement the
128 area samples and report unmatched regions without making raised sculpt
details a hard failure. They are not exhaustive connected-component coverage.
Unresolved fallback now ranks nearest-surface evidence rather than bounding-box
centers. Exact coincident groups still require user intent through Bake Target or
Bake Group; no geometry heuristic can uniquely identify them.

Staged preparation checks all sets, not just the active set, and stops on geometry
dependency updates between steps. This conservative guard may also stop for an
unrelated geometry edit; it deliberately does not hash every vertex every tick.
Automatic matching does not certify ray coverage, AO/thickness secondary-ray
filtering, cage quality, normals, UV overlaps or production-asset visual quality.

## Primary workflow: one Bake button

Choose texture sets, their low/high collections and an output folder, then press **Bake**. The button
validates inputs and material replacement policy, resolves bake pairs, exports fresh
evaluated meshes, connects/launches Painter, creates or opens the associated project,
reloads existing project geometry preserving strokes, bakes, saves, exports textures,
and imports Blender materials. An unrelated open project is never closed/replaced.
The job JSON is internal and is no longer shown in the panel.

The croissant **Bake** button has a **×** cancel control on its right (disabled
while idle). The blue-accented **Bake Status** box directly beneath it shows the
current object/phase in two fixed-height, truncated text rows. A separate **Elapsed**
row stays in place as names change and counts continuously through preparation and
the Painter handoff; it freezes on completion/cancellation. The Details icon opens
the full message, including failure diagnostics, without expanding the sidebar.
Progress-name refreshes are throttled independently of matching work.
**Bake Settings** is collapsed by default and contains
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
confident matches. Bake continues with best-effort assignments for ambiguous, distant,
or unresolved matches: the best scored group is used, or the nearest group by bounding-box
surface distance when none passes the surface checks. All high meshes are exported; lows without
an assigned high may lack detail. Matching issues and fallback choices are saved in the
job and listed in Bake Status Details after the workflow, including failures/cancellation.
Uncertain assignments are not stored as permanent Bake Targets. Validate Setup remains
a strict diagnostic; invalid geometry, export-name collisions and project/material safety
checks still block baking. Select a high
mesh and set **Bake Target** to explicitly choose its low mesh. Resolved targets are
stored as object pointers. Only temporary export names change (`MBTBake_*_low/high`).
Manual targets take priority on subsequent bakes, even after moving a mesh. Clear
the high mesh's **Bake Target** to request name/surface matching again.
Set **Bake Group** on low/high meshes to share any number of lows and highs in one
explicit group. For example, two lows and one high with group `Body` both use that
high; one low and several highs also work. Shared `_low`/`_high` name prefixes are
supported without a group override. Explicit groups take priority over stored targets.
All low meshes share one **Default** texture set unless you add more sets.
The **Texture Set** collection selector is at the top; its **+** creates a parent
collection with Low/High child collections, and **−** removes only the setup entry
(it keeps collections and objects). Choose an existing parent collection to add or
switch sets. Existing Low/High setup is adopted by the default parent on first use.
Each set owns its resolution, requested maps, front/rear distances, relative scale,
antialiasing and ID source. Switching the parent selector switches these controls.
Project name/output/template, normal format and replacement policy remain global.
Matching is scoped to each set, independent of its shared texture material.
Validate Setup uses that same scope. Surface matching compares distinct bake groups,
using the nearest surface across all low members in each group, rather than making
members of one group compete. Area-weighted triangle samples avoid overweighting
densely tessellated sculpt details. Median/75th-percentile distances tolerate minority
raised details instead of requiring 90% of high vertices within a fixed distance.
Only similarly ranked candidates are ambiguous; a clearly better candidate no longer
fails because of a broad additive score floor. These remain correspondence heuristics,
not a ray-projection simulation or proof that a mesh can/cannot bake. Genuine overlapping
groups still require Bake Target or Bake Group; unresolved surface matches are
reported together, with candidate scores or sampled proximity/bounds diagnostics.
Name matching also accepts `.low`/`.high` and `-low`/`-high` role separators.
Objects in a set share the same exported texture files and imported image datablocks;
their UVs therefore share one space and should not overlap unintentionally.
Existing per-object Painter projects require **New Project Next Bake** before
switching to shared sets, as do changes to set/object membership. Existing project
files are never deleted or silently merged. Set collection renames preserve an
associated project's texture-set names. Changing bake groups may also require a
new project to preserve safe name matching.

### Input warnings, hidden collections and offset UVs

Validation collects all mesh/UV issues into one popup with object names and reasons.
Choose **Ignore & Continue** and confirm to acknowledge quality warnings for this
request, or **Select Issue Meshes** to stop and reveal/select the affected objects.
Cancel leaves the scene unchanged. Missing UV maps, non-finite UVs, unusable geometry,
linked data and singular transforms remain blocking; Ignore never silently drops meshes.
Collapsed UV triangles and triangles crossing the bake-tile boundary are warnings.
Quality warnings are checked on the evaluated/export mesh, so faces removed by
modifiers do not cause source-only warnings. Reports include the UV-map name,
triangle count and 1-based evaluated polygon numbers, and distinguish collapsed
UVs on valid geometry from zero-area geometry. Evaluated polygon numbers may not
correspond to source faces after topology-changing modifiers; Select Issue Meshes
still selects objects, not individual evaluated faces.

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