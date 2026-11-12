# Changelog

- Group Unreal connection settings in a collapsible Connection Setup block.
- Prevent FBX material-slot markers from creating unwanted MBT_UE material assets:
  use copied project/reimport pipelines with shader/texture creation disabled for
  linked meshes, preserving mesh settings and exact original material bindings.

- Show short Unreal material names while retaining exact-path bindings; make
  Assign & Preview assign on the first click and populate previews asynchronously.
- Deduplicate Unreal discovery node IDs, retain the connected editor for batch
  sends, and allow explicit selection when distinct sessions advertise one project.

- Add Unreal material browsing, approximate texture/parameter previews, mesh/face
  assignment and exact-path material bindings on import/reimport.
- Add source-preserving Unreal Export Scale, defaulting to 1.0.

- Fix Unreal connection discovery on custom multicast ports by reading project
  Python configuration and supporting an explicit Discovery Endpoint override;
  display the endpoint/source and provide connection-stage-specific errors.

- Fix Unreal engine selection with Launcher/registry/standard-path discovery,
  explicit installed-build selection, a dedicated engine browser accepting root,
  Engine folder or editor executable, and immediate resolved-path validation.

- Add optional Blender to Unreal Bridge with a dedicated MBT Unreal sidebar,
  project/Content folder selection, source-preserving evaluated Empty hierarchy
  FBX export, project-default Interchange import, guarded reimport and local-only
  exact-project remote execution. Add Blender and UE 5.7 integration checks.

- Replace DynaBool's triangle-target automatic mode with live weighted curvature,
  wall/gap and dimension measurements, an observable sampling-work safeguard and
  conservative adaptive extraction. Remove Target Triangles from new modifiers;
  preserve manual uniform sampling and protected revision-6 upgrades. Share the
  shape policy with checked asset generation and add shape/normal/gap, scale,
  tiny-edge, work-limit, policy-parity and many-object regressions. Cube.029 now
  evaluates to about 149k triangles while passing sampled fidelity checks.

- Replace DynaBool's overly coarse bounding-box automatic resolution with a
  subdivided-surface-area estimate and exposed Target Triangles (1.5 million
  default). Calibrated on the live Cube.029 stack: 1,485,112 triangles. Preserve
  manual override behavior and add protected upgrades from revision 5.

- Make DynaBool Automatic Resolution editable in the modifier and tool/component
  controls. Manual mode honors Voxel Size without hidden overrides or automatic
  refinement. Reduce default automatic density with four-times-larger voxels and
  remove standalone shortest-edge over-refinement. Add protected revision-4
  upgrades and real-Blender triangle-density, toggle and persistence regressions.

- Unify popup and Properties modifier sections with shared disclosure state and
  matching list row limits. Replace Array's generated layout with native-style
  offset/merge checkbox headers and conditional fit controls. Omit hidden-only
  Additional Settings sections.

- Enlarge selected modifier action buttons to 1.7× and use neutral unpressed
  styling for Search Modifiers instead of the blue selected state.

- Add icon-only Apply, Duplicate and Copy to Selected in selected modifier headers,
  with tooltips and stable object/modifier targeting. Add Properties Ctrl+A over
  modifier settings controls, excluding list fields and unrelated editors/tabs.

- Keep modifier display modes in add-on preferences only, darken the search button
  with theme-compatible depressed styling, and reconcile native panels against a
  private empty template owner in Selected Settings to discard stale native panels.

- Replace the plain selected-modifier property dump with source-ordered native-style
  sections for all 83 Blender 5.2 modifier types. Add collapsible Properties sections,
  popup boxes, conditional controls, specialized widgets and selected-instance actions.
  Bundle offline-generated panel descriptions and retain Native Stack for exact UI.

- Add Selected Settings / Native Stack display preferences below the modifier list.
  Default to the shared selected-only RNA editor, retain the full native UI as a
  fallback, and leave the viewport popup unchanged. No copied per-modifier layouts.

- Default new Triplanar UV modifiers to each mesh's active UV map rather than a
  separate map (UVMap fallback for meshes without UVs). Lower clay bevel radius
  to 0.001 and migrate the old stock 0.01 radius once while preserving custom values.

- Add Tools > Concepting shortcuts: non-destructive per-face Triplanar UV Geometry
  Nodes with transform/map-name controls, and shared grey Bevel-normal clay with
  object-level material overrides. Preserve existing UVs and unselected shared-mesh
  users; show the Cycles-only shading requirement without changing render settings.
  Add real-Blender projection, repeat prevention and material-isolation tests.

- Preserve add-on ownership during deferred registration and sidebar panel rebuilds
  (verified with real sidebar instances and workspace owner filtering). Keep pie
  and modifier shortcut initialization alive across file loads, add narrow runtime
  repair and Copy Lifecycle Diagnostics, and roll back partial class/UV/Geometry
  Nodes/Pie registration. Do not resurrect externally hidden panels or reset scenes.

- Recover deferred feature initialization after startup, File New and blend loads;
  add Retry Initialization and hidden-tab diagnostics in General preferences.
  Isolate feature teardown/rollback failures, stop unrelated feature toggles from
  rebuilding sidebar panels, and recover surviving panels independently when a
  third-party registration fails. Preserve intentional tab visibility settings.

- Add a repository-owned Asset Processor wiki with quick start, concepts, workflows,
  control reference, troubleshooting, developer notes and future publishing policy.
  Include wiki presence and relative links in dependency-free repository checks.

- Start processor remeshing from tolerance/dimensions instead of minimum sharp-edge
  length or ray distance. Add opposing-normal/nonadjacent ray filtering, local
  shell/thin-feature acceptance limits, conservative all-closed seam welding,
  boundary-group diagnostics and refinement reasons. Validate copied scene meshes:
  Object_001/021/026/033 now pass; Object_025/027 still exceed the tested 1M face
  allowance during preservation-driven refinement; actual open boundaries remain explicit.

- Replace the fixed DynaBool 2-GiB estimate rejection with configurable Work Allowance
  (8 GiB default, zero disables). Size source features before subdivision, retain
  subdivided-surface quality checks, and report resolution drivers/refinement attempts.
  Regression-test the reported 6.50-GiB rejection without allocating that memory.

- Restore optional DynaBool Remesh while keeping automatic resolution enabled.
  Fix curved-surface thickness self hits and subdivision-incompatible quality checks;
  prepare disposable highs, replace the dense-box cutoff with a sparse work estimate,
  and show named per-object failures/counts with Select Failed Sources.

- Make DynaBool always remesh with automatic resolution and processor feature/thickness
  analysis, sampled quality checks and bounded refinement. Register generated pairs
  in reusable Bake texture-set Low/High collections without output selection.
  Preserve existing lows/UVs and roll back failed registration. See AUTO_REMESH.md.

- Fix DynaBool disappearing at fine voxel sizes by extracting the zero SDF surface.
  Remove the standalone SDFremesh extraction offset, add explicit protected upgrades,
  marked standalone empty-remesh fallback/checks and strict processor failure handling.
  Preserve old group names/fingerprints and add real-Blender geometry/rollback tests.
  See DYNABOOL.md for existing-file upgrade steps and input limitations.

- Add explicit Check Outdated dependency snapshots for low provenance, generated
  highs, shared UV layouts, validation and standalone export. Record versioned
  baselines only after successful operations; legacy outputs remain Unknown.
  No automatic low refresh, UV application, export or Bake handoff is performed.
  Centralize rename-stable texture-set identity; reject pinned-UV proposal edits
  and lows shared by component records. Restore UV-preview selection and disclose
  base-mesh-only topology validation for modifier outputs.

- Add protected asset-stage UV preparation using the existing UV suite: Preserve,
  Assisted proposals and explicit unlocked Automatic mode. Jointly pack derived lows
  per texture set; preserve artist seams, pins, other UV maps, geometry and materials.
  Guard stale/edited proposals, support protected edge attributes, and discard
  temporary proposals on save/load, record removal or feature disable. Add read-only
  stage diagnostics with object-pointer selection/framing and reviewed-UV baselines.
  Original/adopted source lows remain validation-only; cross-asset UV groups are refused.

- Connect Model assets to bounded DynaBool generation and Custom High assignment.
  Preserve sources and existing lows/UVs; refresh owned, unedited highs with stable
  object pointers. Add reversible visibility preview, subdivision/voxel budgets,
  independent per-component batch outcomes, and standalone Painter-ready low/high
  FBX export in new folders using the existing snapshot exporter. No Painter launch,
  bake-set reassignment or project replacement is performed.

- Add metadata-only assets/components to MBT Baking's Model tab: selection and
  collection creation, explicit adoption of existing bake setups, stable IDs,
  source/low/high pointers and UV-protection intent. Keep source objects and Bake
  controls unchanged; generation/UV automation remain unavailable at this milestone.
  Keep cancellation accessible across tabs and exclude tab selection from bake
  preparation input signatures.

- Consolidate the complete Painter workflow in the Baking panel's default Bake
  tab, restoring the original setup/output/maps/matching/bake/status/advanced order.
  Keep Model and Export empty for future tools; retain collection and responsive UI.

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