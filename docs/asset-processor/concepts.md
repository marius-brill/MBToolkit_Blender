# Concepts and safety

[Asset Processor home](README.md)

## Asset and component

An **asset** is a named record containing **components**. Each component refers to
one source mesh, a working low and generated/custom high relationships. Stable
asset/component IDs support export names; the records live in the `.blend`.

**From Selection** creates one component per selected mesh. Collection creation
also includes child collections. Records use object pointers, not name lookups:
deleting an object and creating another with the same name does not reconnect it.
Renaming a record is not renaming its source object.

## Source, working low and high

| Role | Meaning | What the processor may change |
| --- | --- | --- |
| Source | Artist-owned mesh used as generation input | Recording/generation do not alter its mesh or modifier stack |
| Working low | Existing/adopted low, or independent evaluated source snapshot created on first generation | Generation never refreshes it; approved UV application can update an eligible derived low |
| Generated high | Processor-owned source snapshot with DynaBool | Regeneration may refresh an unedited, local, single-user, owned high while keeping its object pointer |
| Custom high | Explicitly assigned artist mesh | Geometry remains artist-owned; generation can register it in Bake collections |
| UV proposal | Disposable copy used to preview a shared layout | Can be rebuilt/discarded; never exported as a working low |

The initial working low is a snapshot, not a decimation or retopology result.
Source modifiers are evaluated for snapshots. An adopted low can also be its
component's source; those original/source lows are validation-only for processor UVs.

## Ownership is different from freshness

A generated high has ownership tags and a recorded fingerprint. Editing its mesh,
transform, materials or modifier setup can make regeneration refuse to overwrite it.
Shared or foreign highs are also protected. Preserve intentional edits as
**Custom High**, rather than trying to reset ownership metadata.

**Check Outdated** compares dependencies with successful-operation baselines. It
does not grant overwrite permission. An output can be outdated and protected at
the same time; a current signature does not certify visual quality.

## UV protection and shared layouts

**Protect UV Layout** defaults on. Assisted preview is allowed while protected;
application requires all shared members explicitly unlocked. Preserve mode prevents
joint repacking. Protection gates processor application, not Blender's native UV
editing tools or other UV operators.

Components with the same texture-set identity share a packed layout. Unassigned
components use an asset-level fallback group. Changes to one member may require a
new proposal for the entire group. Cross-asset shared sets are refused for UV prep.
Packing currently targets tile 1001, not a multi-tile UDIM layout.

## Generation, export and Bake are separate operations

- **Record creation/adoption:** metadata only; no generation or automatic matching.
- **Generation:** creates missing lows, generates/checks highs, and registers valid
  low/high pairs in Bake collections. Disabled high mode prepares only a low.
- **Standalone export:** writes requested FBX files and a manifest into a new folder.
  It does not register collections, launch Painter or replace a project.
- **Bake:** uses the existing Painter workflow, including its own diagnostics,
  project/output choices and matching checks.

## Preservation and removal

Removing a component or asset record does not delete its source, low or high
objects and does not dismantle the Bake setup. Disposable proposals are cleaned
up. Clearing custom high links keeps the high objects.

Inspector previews temporarily change referenced objects' view-layer hidden state;
they do not unexclude collections or isolate the entire scene. Restore visibility
before judging whether an object is missing.

> Save before expensive operations. Generation and UV preparation are synchronous;
> an individual geometry evaluation cannot be cancelled mid-operation through the
> processor. Resource limits reduce risk but are not memory/time guarantees.