# Changelog

- Move baking to its own MBT Baking sidebar category, separate from MBToolkit
  tools. Replace the Tools/Baking switch with Model/Bake/Export tabs in the baking
  panel, preserving all existing controls and keeping status/cancellation shared.

- Refine the baking sidebar: remove the duplicate Tools Bake icon and viewport
  monitor controls, fix boolean visibility icons, align collection field widths,
  and separate Mesh Matching from map settings. Compact issue summaries retain
  full diagnostics/candidate metrics in a Details dialog without duplicate
  assignment editors.

- Add a Tools / Baking workspace selector above the existing sidebar buttons;
  add collection visibility controls,
  blue low-poly and orange high-poly tags, and collision-safe TextureSet1,
  TextureSet1_low / TextureSet1_high naming for newly created collections.

- Clarify non-averaged projection as mesh normals and estimate its skew using
  evaluated corner normals. Isolate differing per-set Painter common parameters
  before setting values. Add sparse receiver and geometric hard-edge-gap
  prerequisites, read-only backend capability flags and regression coverage;
  automatic local correction remains gated, not enabled.

- Share one imported material per texture set, reuse it on reimport, support
  differently named member UV maps and protect unrelated linked users.
- Estimate front/rear distance-based cage reach automatically from evaluated,
  matched surfaces per texture set. Publish padded absolute-centimeter settings;
  preserve manual overrides and retain exported-geometry estimates on rebake.

- Add guarded live material-ID coverage experiments for flat caps, two bolt
  heights, a boundary witness and joined high meshes. Verify authored local cage
  control preserves boundary rays on a dense synthetic receiver; do not expose it
  as automatic correction. Add read-only planar receiving-patch/boundary primitives
  with transform, curvature and invalid/nonmanifold regression tests.

- Strengthen live skew validation with valid side UVs, non-color normal reads,
  full-image repeat checks and independent placement/shape/detail-recall metrics.
  Prove custom-cage direction control and cage/mode save-reopen persistence in a
  disposable test harness; add a nonempty beveled-edge witness. Production bake
  behavior is unchanged; localized automatic correction remains unavailable.

- Validate skew estimates with real Painter panel/bolt bakes; add explicit per-set
  averaged/perpendicular projection normals to prevent inherited bake state.
  Fix estimator triangle-diagonal weighting and coincident-surface/counting noise;
  add live mode-switch/repeat and save/reopen checks. Local automatic correction
  and general hard-edge coverage remain unverified.

- Let the standalone Painter probe launch a remote-enabled instance with `--launch`;
  guard existing sessions and report startup failures without killing processes.

- Add a connect-only Painter remote preflight with IPv4/IPv6 fallback, isolated
  helper discovery and a JSON report; document the verified IPv6 testing setup.

- Add opt-in projection/skew estimates in output pixels and read-only Painter
  projection-property discovery. Report unassessed samples explicitly; do not
  modify source geometry or advertise unverified automatic skew correction.

- Add persistent, searchable Bake Issues with clickable mesh names, individual
  reveal/select/frame, candidate-low selection, blocking filters and guarded UV
  face selection. Keep object/candidate pointers across rename and save/load;
  deleted objects never rebind by name.
- Refine ambiguous surface matches with 512 samples, use evaluated triangles for
  low BVHs and actual surface distances for unresolved fallbacks. Preserve robust
  sculpt-detail ranking while reporting unmatched spatial regions separately.
- Parse only trailing low/high role tokens; protect generated export prefixes from
  interior role tokens. Distinguish automatic target suggestions from manual
  overrides, accept tiny nonsingular transforms, and guard all texture sets plus
  dependency-graph geometry edits during staged preparation.

- Let Auto Bake proceed through uncertain matching with best-effort assignments;
  retain every high mesh, record unresolved/missing matches and fallback targets in
  the job, and expose the issues in final Bake Status Details. Do not persist
  uncertain Bake Targets; keep validation and project/material safety checks.

- Stabilize Painter Bake Status with two bounded message rows, full-message Details
  and a separate continuous elapsed timer; throttle rapidly changing progress names.
- Replace strict 90% high-vertex matching coverage with area-weighted surface samples
  and robust correspondence scores; stop flagging clear winners as ambiguous while
  preserving genuine ambiguity/distance safeguards. Matching is not a bakeability test.

- Fix false Painter surface ambiguity between members of the same bake group;
  match combined low surfaces with spatial samples and robust distance scores.
- Scope Validate Setup to texture sets and aggregate unresolved surface matches
  with candidate diagnostics. Accept dot/hyphen low/high role separators.
- Report evaluated UV triangle counts, map names and face numbers; distinguish
  zero-area geometry and avoid warnings for source faces removed by modifiers.

- Add collection-backed Painter texture sets: shared default textures, Low/High
  children, per-set resolution/maps/projection settings, scoped matching and shared
  imported images. Protect existing per-object painting with an explicit new-project guard.

## Painter input and automation improvements

- Aggregate mesh/UV issues in a warning dialog with investigate/select and per-job
  quality-warning override; structurally unusable inputs remain blocking.
- Evaluate hidden objects and excluded collection ancestors with state restoration.
- Preserve intentional offset mirrored UVs without requiring every island in 0–1.
- Add shared bake groups for multiple low/high inputs and unique temporary export names.
- Protect unattended baking by disabling/hiding Painter's main window with recovery
  watchdog; add Open Painter Project beneath Bake for the texturing handoff.
- Add input, popup-action, window-guard and safe-opening regression coverage.

## Unreleased

### Vertex Color

- Add an optional Vertex Color sidebar section with a procedural pastel mesh icon,
  native live color dialog with cancel restoration, masked fills and channel tools.
- Support point/corner byte/float colors, Edit Mode and Vertex Paint selections,
  batch preflight, explicit missing-attribute creation and shared-mesh safeguards.
- Add viewport-local Solid RGB/R/G/B/A diagnostic overlays without material edits,
  attribute management, sampling, mixed/min-max inspection and regression tests.

### Bake panel and preparation responsiveness

- Harden restoration for deleted inputs and renamed collections, restore exact
  surviving selection, clear completed runtime scene references, and reacquire
  dependency graphs between staged operations.
- Guard interactive ticks against structural input/settings changes and expose
  active preparation stage timings with a synthetic benchmark fixture. Full
  coordinate/node/dependency tracking and production profiling remain follow-ups.

- Reuse the croissant on Bake, identify Open Painter Project with the Painter app
  icon, and place a compact cancel cross immediately to the right of Bake.
- Promote wrapped status messages beneath Bake with a blue information badge;
  collapse secondary options into Bake Settings without changing their values.
- Stage interactive preparation across main-thread timer ticks with per-object
  status and cancellation cleanup. Individual mesh evaluation and FBX export
  calls still cannot be interrupted mid-call.
- Avoid building a high-poly BVH for automatic matching; use bounds and sampled
  vertices, retaining low-poly BVHs for nearest-surface queries.
- Check missing persisted job manifests before mesh preparation and show safe
  restore/reset guidance with a confirmed New Project Next Bake recovery action.

### Automatic baking reliability

- Fix live automatic rebaking after mesh reload: return the associated project
  path and texture-set names on completion rather than failing before baking.
- Add explicit opt-in GUI Painter matrix/custom-export tests and document their
  passed synthetic live coverage and remaining production/OS-input limitations.
- Clarify stored Bake Target priority in the tooltip and Bake UI.
- Cancel/invalidate pending Painter work and remove its polling timer before blend
  file loads and feature teardown; clean up failed worker startup as well.
- Reject duplicate final mesh/texture-set names after associated-project name reuse,
  before exporting snapshots.
- Add controlled AUTO orchestration tests covering worker/main-thread boundaries,
  cancellation, failures, scene/job changes, teardown/restart and real file reload.
- Extend project-reuse regression tests and reconcile legacy Painter documentation
  with the current automatic workflow; record staged validation and next steps.

### Repository setup

- Add installation, troubleshooting, contribution, packaging, and release guidance.
- Add license text, security guidance, GitHub issue/PR templates, and Python CI.
- Synchronize the extension manifest to the existing add-on version `0.3.0`.
- Declare filesystem and local Painter network usage and exclude development
  metadata and build output from extension archives.

This file starts with the repository setup work; it is not a reconstructed release
history. See Git history for earlier changes. No release date is implied.