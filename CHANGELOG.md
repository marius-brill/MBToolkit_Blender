# Changelog

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