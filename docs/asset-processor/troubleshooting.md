# Troubleshooting

[Asset Processor home](README.md) · [Control reference](reference.md)

Save a backup before changing geometry, relationships or resource limits. Read the
full operation report; a previous valid output can remain visible after a failure.

## Panel missing or controls disabled

- Enable Substance Painter in MBToolkit preferences and open **MBT Baking**, not
  the separate MBToolkit tools category. Check Sidebar Tab Manager visibility.
- Return to Object Mode. For a running bake, wait or use its Cancel control.
- Choose the intended asset/component before processing or exporting.

## Missing source after deletion

Records store pointers. A same-named replacement is not automatically substituted.
Inspect **Component Details** and explicitly assign the intended source or remove
the obsolete record. Removing a record keeps its mesh objects and Bake setup.

## Generated high refuses to refresh

An edited, linked, shared or foreign high is protected. Preserve intended work by
choosing **Custom High** and **Add Selected Highs**. Do not remove ownership tags
or fake a fingerprint. Switching modes alone does not reset the guard.

## Source changed but the low did not

This is intentional. Generation never refreshes an existing low, even when LOW
provenance is Outdated. Compare it against the revised source/high and adjust it
explicitly. See [revising sources](workflow.md).

## Remesh fails or loses detail

- Inspect the named failure and failed source, not just the batch total.
- For topology errors, review open boundaries, nonmanifold edges and intended
  thickness. Disposable-high cleanup does not cap holes or invent a solid.
- For an intentionally open surface, disable **Remesh** for subdivision-only
  output, or add appropriate thickness/repair to the source deliberately.
- For quality failures, inspect thin walls, small shells, smoothing and subdivision.
  Lower tolerance can require finer resolution and more resources, not guarantee success.
- Do not infer success from a visible old high. Failed generation preserves it.

The processor can remove loose/degenerate elements, recalculate normals and attempt
a conservative boundary weld on a disposable high, not on artist sources or lows.
Sampled quality checks can still miss defects; inspect the result visually.

## Face/work budget exceeded

Reduce subdivision, split the input into deliberate components, or simplify source
detail where appropriate. Raise a budget only after assessing machine capacity.
The work allowance is a heuristic, not actual memory usage; it is independent of
Face Budget. Zero disables that guard and risks excessive memory use. There is no
mid-evaluation processor cancel for synchronous generation.

## Generation fails while registering Bake collections

Review incomplete legacy Low/High fields, missing assigned texture sets, linked
collections, role overlap or membership in another set. Complete/correct the intended
setup explicitly. Registration rolls back its collection changes on failure.
Unrelated sets are preserved and can still cause Bake validation failures.

## UV proposal cannot be built/applied

| Symptom | Check or action |
| --- | --- |
| Apply disabled/protected | Unlock every shared member only after review |
| Preserve member blocks packing | Keep its layout and do not repack, or deliberately change the whole group policy |
| Original/adopted low is validation-only | Processor application requires an independent derived low; do not force edits onto a source |
| Linked/shared mesh data | Use deliberate local single-user derived lows; verify ownership first |
| Inputs changed after preview | Rebuild and inspect the proposal |
| Shared set crosses assets | Consolidate the intended components before joint prep |
| Protected edge/pin constraint fails | Review constraints; do not clear artist intent indiscriminately |
| More than 50,000 low faces | Use an appropriate lower-complexity working low or manual UV workflow |
| Proposal disappeared after saving | Proposals are intentionally temporary; apply/discard before save |

**Acknowledge Reviewed UVs** changes the reviewed reference, not the layout. Use
only after checking intentional edits. It cannot repair collapsed or missing UVs.

## Validation and dependency status seem contradictory

They answer different questions. Current means matching dependencies; validation
can still report errors. Blocked UV status is expected for protected/Preserve groups.
Unknown is expected for old files without compatible successful-operation baselines.
Rerun both after edits. The legacy BAKE_HANDOFF status row does not describe current
generation-time registration; inspect the actual Bake set.

## Export refused or files missing

Check that requested lows/highs exist in the active scene, transforms are nonsingular,
and requested low UVs are valid. Low/high objects must be separate. A low cannot
belong to multiple exported components; custom highs shared across components are
refused. Choose an absolute output path or save the blend before using `//`.

Export writes a fresh folder each time. Check the reported path, not an earlier
folder. Check Outdated does not verify exported-file existence; export again if
files were moved/deleted. Map/texture export is part of Painter's workflow, not this
standalone FBX operation.

## Report a reproducible issue

Include Blender/add-on versions, OS, operation, settings, full report/traceback,
expected versus actual result, and a minimal non-private example if possible.
Remove private asset paths and content. Follow the repository's
[support guidance](../../README.md) and [security policy](../../SECURITY.md).