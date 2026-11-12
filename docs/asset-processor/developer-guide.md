# Developer guide

[Asset Processor home](README.md) · [Documentation maintenance](documentation.md)

## Ownership and lifecycle

The processor package is `features/asset_processing` (paths here are relative to
the repository root). It is registered through the existing Substance Painter
feature lifecycle, not as a separate preference toggle. Registration installs
settings, operators and preview handling; teardown reverses that order.

`Scene.mbt_assets` stores asset/component records and schema version. Object and
collection pointers represent relationships. Asset/component UUIDs and canonical
texture-set identities support stable export grouping. Stage baseline JSON is
versioned separately from the settings schema. Displayed dependency rows are not saved.

## Module map

| Source | Responsibility |
| --- | --- |
| [settings.py](../../features/asset_processing/settings.py) | Property groups, defaults and active-record helpers |
| [operators.py](../../features/asset_processing/operators.py) | Record editing, adoption and explicit processing actions |
| [generation.py](../../features/asset_processing/generation.py) | Snapshots, fingerprints, bounds, high refresh and low preservation |
| [bake_setup.py](../../features/asset_processing/bake_setup.py) | Transactional collection/texture-set registration |
| [uv.py](../../features/asset_processing/uv.py) | Group eligibility, proposals, application guards and cleanup |
| [validation.py](../../features/asset_processing/validation.py) | Stage diagnostics and validation baselines |
| [tracking.py](../../features/asset_processing/tracking.py) | Explicit dependency signatures and state publication |
| [identity.py](../../features/asset_processing/identity.py) | Canonical set identity helpers |
| [export.py](../../features/asset_processing/export.py) | Export planning, FBX reuse and asset manifest |
| [preview.py](../../features/asset_processing/preview.py) | Temporary visibility and lifecycle cleanup |
| [ui.py](../../features/asset_processing/ui.py) | Model/Export drawing; no geometry signature scans on redraw |
| [resolution.py](../../features/geonodes/resolution.py) | Prepared-high analysis, work estimates and sampled remesh acceptance |

The processor reuses Substance Painter evaluation/export/texture-set helpers,
DynaBool node groups and the existing UV suite. No additional pip dependencies
are needed. Keep standalone modifier behavior distinct from processor acceptance.

## Invariants to preserve

1. Record edits/adoption are metadata-only; do not guess automatic high matches.
2. Existing lows never refresh during generation, regardless of UV lock state.
3. Sources/custom high geometry remain artist-owned. Generated highs require
   ownership, editability/single-user checks and fingerprint agreement before refresh.
4. Validate staged output before replacing a previous high; retain stable object
   pointers and clean temporary data on failure.
5. Registration must roll back collection links, set selection and assignments
   if processing fails. Independent batch successes remain committed.
6. UV application requires unchanged eligible lows and group-wide approval. Never
   bypass Preserve/protection, source-sharing, local/single-user or scope guards.
7. UV proposals and previews are disposable; save/load/undo/teardown cleanup must
   not leave hidden artist objects or export preview meshes.
8. Only successful operations establish stage baselines. Checks do not adopt old
   outputs, silently reprocess, or run during panel redraw.
9. Export uses a fresh folder, temporary naming/material overrides and failure cleanup.

## Known documentation-sensitive limitation

Tracking still emits an unimplemented BAKE_HANDOFF message, while generation now
registers pairs through `bake_setup.prepared`. Do not use that status row as proof
of missing collections. A future tracking fix needs its own behavior/test change;
this documentation does not change runtime semantics.

## Validation

Read the [test safety guide](../../tests/README.md) first. Never use blanket test
discovery or run scene-mutating tests in an artist's working Blender session.

Ordinary-Python checks, using an absolute checkout path:

```powershell
$root = 'C:\Users\mariu\AppData\Roaming\Blender Foundation\Blender\5.2\scripts\addons\MBToolkit'
python "$root\tests\verify_structure.py"
python "$root\tests\test_repository.py"
python "$root\tests\test_sidebar_sections.py"
```

For runtime changes, run affected scripts individually in new disposable Blender
processes with `--background --factory-startup --python-exit-code 1 --python` and
an absolute script path. Use disposable configurations where required by the test guide.

| Test script | Focus |
| --- | --- |
| test_asset_processing.py | Records and adoption |
| test_asset_generation.py | Source/low preservation, custom highs and export |
| test_asset_uv.py | Protected proposals, application and diagnostics |
| test_asset_tracking.py | Dependency baselines, invalidation and protection |
| test_auto_generation.py | Automatic resolution, registration and stable refresh |
| test_generation_failures.py | Mixed batches, optional remesh and work allowances |
| test_resolution_policy.py | Boundary welding and local/shell acceptance |
| test_dynabool.py | Node-group regressions, upgrade and failure behavior |

Some tests encode earlier revision policies; inspect their assertions before
interpreting failures against newer optional-remesh behavior. Do not change tests
just to hide a mismatch. Panel layout, actual clicks, undo/redo and the quick start
still require an interactive smoke test. Documentation-only checks do not prove
runtime correctness.