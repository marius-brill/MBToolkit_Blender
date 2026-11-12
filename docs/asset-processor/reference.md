# Control reference

[Asset Processor home](README.md)

Defaults below apply to newly created component records. Saved components retain
their settings. Model/Export controls require Object Mode and no active bake job.

## Assets and components

| Control | Action |
| --- | --- |
| From Selection | Create an asset with one component per selected mesh |
| Create from Collection | Reference meshes in the chosen collection and descendants |
| Adopt Bake Setup | Record the active Bake set's lows and explicit high associations |
| Add Selected | Add selected source meshes to the active asset |
| Remove Record / Remove Asset Record | Remove metadata, not low/high/source objects |
| Component Details | Inspect/change the source pointer; inspect low/high/set references |

## Processing

| Setting | Default | Meaning |
| --- | --- | --- |
| High Poly | DynaBool | DynaBool generates a high; Custom High references assigned meshes; Disabled prepares only a low |
| Automatic Resolution | On, editable | Processor chooses/refines resolution when on; off uses Voxel Size (local) without automatic refinement |
| Automatic policy | Shape-driven | Weighted curvature, opposing walls/gaps and dimensions; conservative adaptive extraction. No user triangle target. Generation also enforces sampled quality and face/work budgets |
| Voxel Size (local) | 0.008 | Manual remesh resolution when Automatic Resolution is off; smaller values increase density |
| Remesh | On | SDF remesh after crease/subdivision; off permits subdivision-only highs, including open surfaces |
| Subdivision | 2 | Subdivision level, supported range 0–5 |
| Crease Angle | 50 | Angle input for DynaBool crease generation |
| Detail Tolerance | 0.01 | Sampled remesh deviation allowance as a fraction of local source diagonal; smaller can require more work |
| Smooth Iterations | 0 | Smoothing iterations, supported range 0–20 |
| Face Budget | 1,000,000 | Subdivision estimate and evaluated face limits; maximum setting 10,000,000 |
| Work Allowance (GiB estimate) | 8 | Heuristic sparse-band work guard, not measured RAM; zero disables the guard |

The default work allowance is not selected from installed RAM. Face Budget and
work allowance are separate guards. Increasing one does not remove the other.
Processor remesh resolution is local-space. Sampling/refinement is bounded and
does not prove exact preservation of every shell, gap or edge.

- **Generate Component:** process only the active component.
- **Generate Asset:** process components independently and report fresh counts/failures.
- **Select Failed Sources:** reveal/select sources with failed generation status.
- **Add Selected Highs / Clear High Links:** edit custom references without deleting meshes.

## UV Preparation

| Setting/action | Default or effect |
| --- | --- |
| UV Mode | Assisted: disposable preview; Preserve validates; Automatic prepares/applies eligible unlocked groups |
| Protect UV Layout | On; application is blocked until every shared member is unlocked |
| Seam Angle | 66 |
| Island Gap (px) | 8; interpreted at the group's texture resolution |
| Tile Border (px) | 8 |
| Allow UV Overlap | Off; deliberate stacks need permission across the group; generated proposals still pack without overlaps |
| Prepare UVs / Validate UVs | Mode-dependent action; Preserve never repacks |
| Show UV Proposal | Reveal the current proposal without rebuilding |
| Apply UV Proposal | Validate and apply to eligible, unchanged derived lows |
| Discard Proposal | Remove disposable previews; keep working UVs |
| Acknowledge Reviewed UVs | Update the artist-reviewed layout reference without editing UVs |

UV preparation has a 50,000-face per-low safety limit plus the UV suite's detailed
check budgets. Source-sharing, linked, multi-user or multiply referenced lows are
not writable. Proposals are removed before save/load and feature disable.

## Inspector and validation

**Source / Low / High** preview referenced objects' hidden state. **Restore
Visibility** restores that preview; excluded collections remain excluded.

**Validate Asset** reports ANALYZE, GENERATE, GEOMETRY, UV and EXPORT findings.
Select a finding for its reason/action and **Select Mesh / Frame** controls.
Warnings can describe intentional open geometry, stacks or non-unit scale.
Large meshes can skip detailed scans with an explicit limitation. Base-mesh
topology checks do not certify final modifier-output topology or bake projection.

## Dependency Status

**Check Outdated** explicitly compares current inputs against versioned successful
operation baselines. It does not regenerate, unlock, apply, export or launch Painter.

| State | Interpretation |
| --- | --- |
| Current | Inputs match the last successful operation; not a quality certificate |
| Outdated | Tracked dependencies changed; choose the next operation explicitly |
| Not Processed | Required output/baseline operation has not occurred |
| Blocked | Artist intent or an ownership/protection guard prevents processing |
| Unknown | No compatible baseline or a dependency could not be inspected |

LOW tracks source provenance; HIGH tracks evaluated source/settings and ownership;
UV tracks shared low/layout/settings dependencies; VALIDATION and EXPORT are
asset-wide snapshots. Baselines persist in the blend; displayed checks do not.
Checking does not adopt legacy outputs or check that exported files still exist.

**Known status limitation:** the `BAKE_HANDOFF` row currently says handoff is not
implemented. That row is older than automatic generation-time collection
registration and is not a reliable registration indicator. Inspect actual Bake
collections/targets. There is no separate handoff freshness baseline or automatic bake.

## Export

Choose **Output Folder**, **Low Poly** and/or **High Poly**, then **Export Active
Asset**. Both output toggles default on. Relative `//` paths require a saved blend.

Each successful export creates a fresh asset-named folder:

| File | Content |
| --- | --- |
| low.fbx | Requested working lows with temporary export material grouping |
| high.fbx | Requested generated/custom highs; Disabled components contribute none |
| asset.json | Schema version, asset/component IDs/names, normal format, FBX filenames, name mapping and texture-set material identifiers |

Mesh export names use stable asset/component UUIDs with `_low` / `_high` suffixes;
additional custom highs get numbered suffixes. Original materials are not reassigned.
Collection-backed export groups use canonical identities, not just mutable names.
Failed export folders are cleaned up. Export does not launch Painter or update a project.