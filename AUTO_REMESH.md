# Automatic DynaBool and Model to Bake

## Current controls (revision 7)

Automatic Resolution is a shape-driven policy, not a requested polygon count.
There is **no Target Triangles control** in revision 7. Manual mode still uses
Voxel Size and ignores internal processor-resolved values.

The live graph measures the subdivided local surface, including upstream modifiers:

- Baseline voxel: local bounding-box diagonal / 128.
- Smooth-curvature radius: transverse face area / (edge length * dihedral angle),
  aggregated with a length-and-angle-weighted harmonic mean. Hard crease edges
  and nearly flat edges do not drive this estimate; radius / 4 is its voxel candidate.
- Wall thickness and opposing gaps: inward/outward face-center rays, rejecting
  near/self hits and requiring opposing normals. Area-weighted harmonic distances
  provide a distance / 6 candidate, rather than using the single shortest hit.
- The smallest candidate chooses sampling. A lower voxel bound of
  max(diagonal / 4096, sqrt(surface area / 2,000,000)) limits pathological sampling
  work. This is an estimated surface-sampling ceiling, **not a target, triangle cap
  or measured memory allowance**. It can compromise tiny features and does not
  guarantee a particular evaluation time or available RAM.

Automatic extraction uses conservative adaptivity **0.001** to remove redundant
output polygons, especially on flatter regions. Manual mode retains uniform
extraction (adaptivity zero). Sampling cost and final mesh density are separate:
adaptivity does not eliminate the cost of building a fine SDF grid.

The live graph runs without Python handlers, timers, scene scans or iterative
remeshing on edits. It does not change resolution with selection/camera/scene
object count. Its ray/statistics cost scales with the subdivided input mesh.
The `mbt_dynabool_resolution_limited` point attribute marks live automatic output
where the work floor coarsened the desired sampling. **Check Selected DynaBool**
reports it. Inspect small parts visually and use manual mode when necessary.

Checked asset generation mirrors the same shape policy on the subdivided surface,
with an additional Detail Tolerance constraint, existing per-shell/thin-feature
sampled quality checks, bounded refinements and explicit face/work budgets.
Refinement may intentionally exceed the live policy floor to preserve features;
failure preserves the previous high. Standalone automatic mode does not promise
exhaustive component/topology preservation or perform these expensive retries.

### Measured regression results

On the exported Cube.029 Bevel/Solidify stack, revision 7 produces approximately
**149,000 triangles**, versus revision 6's 1,485,112. Its sampled bidirectional
maximum deviation was 0.00020726 local units (acceptance limit 0.000988805), with
finite, closed manifold output. This is not a proof that every bevel or tiny gap
is preserved; inspect the silhouette/shading at the intended viewing distance.

Simple cube/sphere/cylinder/beveled-box fixtures produced approximately
3.9k/31k/28k/33k triangles. Twelve independent cube modifiers produced 47,376
triangles total; the local background smoke test took about 0.22 seconds, not a
cross-machine performance guarantee. Scale stability, tiny-edge insensitivity,
thin solids, separated narrow-gap shells, graph/Python measurement parity and
work-limit signaling have dedicated regressions.

Upgrade stock standalone revisions 1–6 with **Upgrade Selected DynaBool**; old
shared groups are not mutated. Regenerate processor-owned highs. Customized,
animated and linked setups remain protected. Existing revision-6 groups retain
their historical target socket until explicitly upgraded.

## Historical revision 6 (superseded)

Revision 6 replaces the overly coarse revision-5 bounding-box rule with a
surface-area estimate: voxel = sqrt(2.25 * subdivided local area / Target Triangles).
**Target Triangles** is exposed in the modifier and defaults to **1,500,000**.
It is an approximate density target, not a hard cap. On the live Cube.029
calibration fixture (including its Bevel/Solidify stack), automatic output is
**1,485,112 triangles**, rather than the revision-5 result of roughly 2,700.
This estimate is scale-relative and does not let a tiny edge set global density.
Processor-resolved voxels still take priority in automatic mode; manual mode
still ignores both the target and the processor override. Asset generation keeps
its independent quality/refinement and face/work budgets.

Run **Upgrade Selected DynaBool** for stock revision-5 modifiers too. Existing
groups stay intact; only explicitly upgraded modifiers use the new target.

### Historical revision-5 controls and calibration

Automatic Resolution is now editable, enabled by default, and exposed in the
DynaBool modifier as well as component Generation Settings. Disable it to use
**Voxel Size (local)**. Manual mode ignores the hidden processor-resolved voxel
input and never silently refines the requested voxel size. Failed processor
quality checks preserve the previous high and report that manual resolution needs
adjustment. Changes to either setting are included in high dependency tracking.

Revision 5 used local bounding-box diagonal / 36 instead of
diagonal / 144, and tiny sharp edges no longer force globally excessive density.
On the cube regression this reduces triangle count to about 6.4% (26 million
would scale to about 1.66 million). This cube-only calibration proved unsuitable
for thin/elongated geometry and is superseded by revision 6. This was a relative density target, not a
guaranteed triangle cap for arbitrary geometry. Processor automatic generation
starts four times coarser too, but may refine to meet its sampled quality checks.

For existing standalone modifiers, run **Upgrade Selected DynaBool** to upgrade
stock revisions 1–4 while preserving input settings. Regenerate processor-owned
highs instead. Customized, linked and animated setups remain protected.

The Low to High tools expose a default toggle for new modifiers and, when present,
a separate toggle for the active object's current DynaBool modifier.

### Work allowance and source feature sizing

The processor now starts from dimensions/detail tolerance. Shortest sharp edges
and opposing-wall distances are diagnostic hints, not unconditional initial voxel
constraints. Opposing-wall samples require opposing normals and nonadjacent faces;
their local distance limits and per-connected-shell limits drive bounded refinement.
These remain sampled fidelity checks, not exhaustive topology preservation proofs.
Reports include the previous failed local/global check when refinement is required.

Disposable-high cleanup attempts a boundary-only weld at source diagonal * 1e-7
(minimum 1e-12 local units), accepting it only if every edge becomes manifold.
Unresolved openings report boundary groups, edge counts and extents. No holes are
automatically capped and no sheet thickness is invented. Existing lows and sources
are not welded. This supersedes the initial minimum-feature selection described below.

The fixed 2-GiB cutoff has been replaced by **Work Allowance (GiB estimate)** in
Generation Settings (default 8 GiB). This is an explicitly configurable heuristic,
not measured RAM or a promise that evaluation fits available memory. A value of zero
disables this estimate guard and can cause excessive memory use. Face Budget remains
independent and is checked against evaluated geometry. The 8-GiB default is not
automatically selected from installed RAM; choose it conservatively for your machine.

Initial resolution is selected from the prepared source before subdivision, avoiding
artificially tiny feature lengths introduced by subdivision edge splitting. Remesh
quality still targets the subdivided surface. Reports identify the source resolution
driver and candidate voxel sizes, actual attempt/refinement, work estimate and output
face count. Work-estimate errors include the configured allowance and do not claim
that Blender actually ran out of memory. The older fixed-2-GiB statements below are
historical and superseded by this section.

Revision 4 forced Automatic Resolution on; revision 5 supersedes that behavior
with an editable toggle. Processor-resolved resolution uses a separate internal
socket, honored only in automatic mode. **Remesh is optional again**, enabled by
default. Turn it off to generate the crease/subdivision high without SDF restrictions,
including open surfaces. Existing component Remesh values are respected.

Generate Asset processes every component independently, stores fresh per-component
Succeeded/Failed/Skipped status, and reports counts plus named errors. **Select Failed
Sources** reveals failed inputs. Failures preserve the previous high. Errors separate
source topology, subdivision/remesh output, measured face limits, sampled quality,
and estimated memory work. The old dense 24-million-cell box cutoff was removed;
a sparse-band work estimate retains a separate 2-GiB safety threshold. Increasing
Face Budget does not change that memory estimate threshold.

Disposable high snapshots remove loose elements/degenerate edges and recalculate
normals without altering artist sources or existing lows. Open/nonmanifold surfaces
that remain cannot be inferred into an intended solid: they get topology counts and
the option to disable Remesh or repair/add intentional thickness. Thickness rays now
start on the actual surface and filter near/self hits. Fidelity is checked against
the prepared subdivided surface, not against an incompatible pre-subdivision shape.
Subdivision's intentional shape changes are not included in that remesh error figure.

The sections below describe the revision-3 introduction; the controls and limits in
this revision-4 section supersede its always-remesh/manual-override wording.

## Workflow

Restart Blender/reload the updated add-on. In Model, create an asset from sources
and run **Generate Asset** or **Generate Component**. DynaBool always remeshes: stored
legacy Remesh switches and manual voxel sizes no longer control asset generation.
Source geometry and existing working lows/UVs remain unchanged.

Successful generation creates/reuses an asset texture-set parent with Low/High child
collections, registers them in Bake, sets generated high-to-low targets and activates
the texture set. No output selection or manual collection creation is required.
Switch to Bake; UV validity, output-folder/project choices and the normal Bake
preparation still apply. Registration does not launch Painter, unwrap protected lows
or replace projects automatically.

Components share one asset set by default; explicit existing assignments are respected.
Regeneration reuses output objects and collections. Unrelated sets are preserved, not
removed/merged. Bake validates all registered sets, so unrelated incomplete sets still
need attention. Custom highs register without geometry changes. Disabled components
prepare a low only, without creating an incomplete Bake set.

## Resolution and quality

The processor analyses an evaluated source snapshot for dimensions, sharp-edge
lengths, estimated wall thickness/gaps and **Detail Tolerance** (a fraction of the
local source diagonal). Output must be finite/manifold and pass sampled bidirectional
surface-distance checks, including sharp-edge samples. Failed checks trigger finer
retries, up to four attempts. Face/voxel-volume budgets reject excessive work, never
silently coarsen it. Reports show the chosen voxel size, face count and sampled error.

Smoothing defaults to zero; existing components retain saved smoothing. Subdivision
and smoothing can alter the source shape and must fit the quality tolerance too.
Processor input must be a closed, nondegenerate solid; open surfaces require intentional
thickness or boundary repair. Artist geometry is not cleaned or modified automatically.
Failed generation preserves the previous high; subdivision fallback is not success.

**Checks are sampled, not exhaustive guarantees.** Tiny unsampled features and narrow
holes still need visual review. This release does not reproject sharp edges: a simple
shrinkwrap can collapse/fold cells and is not a reliable edge-reconstruction solution.
Lower Detail Tolerance for tighter sampled agreement; split sources or explicitly raise
budgets when needed. No finite uniform voxel grid preserves arbitrary geometry exactly.

## Standalone modifier

Revision 3 always routes output through remeshing; obsolete bypass/fallback sockets are
hidden and ignored. **Automatic Resolution** defaults on and updates inside Geometry
Nodes from dimensions and sharp-edge lengths. It is a live estimate, not the processor's
ray-based analysis/retries/acceptance checks. Use Model for bounded checked generation.
Manual voxel resolution remains an explicit standalone override. The standalone add
operator checks initial validity/budget; later live edits do not enforce processor budgets.
All voxel sizes are local-space, not world-space.

Run **Upgrade Selected DynaBool** (F3 or Low to High) for stock revision 1/2 modifiers.
Customized/animated/linked/processor-owned setups are skipped. Model highs upgrade by
regeneration. Shared old groups keep their names; numeric suffixes are intentional.
**Check Selected DynaBool** detects empty final output/old fallback markers, not all
geometry defects. The separate SDFremesh zero-surface fix remains available.

## Validation

Run tests only in a new disposable Blender process with
`--background --factory-startup --python-exit-code 1 --python` and an absolute script
path. `test_auto_generation.py` covers mandatory/automatic remesh, scale, registration,
Bake validation/matching without output selection, stable refresh, multiple components,
failure cleanup, quality rejection and save/reload. Existing DynaBool, generation,
UV and tracking tests cover preservation and upgrade behavior.