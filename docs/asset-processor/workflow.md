# Working with assets

[Asset Processor home](README.md) · [Control reference](reference.md)

## Create or extend an asset

In Object Mode, select source meshes and use **From Selection**, or expand
**Create from Collection**, choose a collection and click **Create from Collection**.
Collection creation includes descendant meshes. Select an existing asset and use
**Add Selected** to add components; duplicate sources within that asset are skipped.

Check the source in **Component Details** before processing. Record creation does
not rename or relocate artist objects. **Remove Record** removes the selected
component metadata; **Remove Asset Record** removes the asset metadata, not meshes.

## Generate multiple components

1. Choose each component's **High Poly** mode and generation settings.
2. Click **Generate Asset**.
3. Read the succeeded/failed/skipped totals and individual failure reports.
4. Use **Select Failed Sources** to inspect failed inputs.
5. Resolve failures and retry the affected component with **Generate Component**.

Components are processed independently: a later failure does not undo earlier
successes. Failed generation preserves the previous high and cleans temporary
snapshots. Disabled high mode is reported as skipped even though a missing low
can be prepared.

Generated/custom pairs are registered in reusable Bake collections, normally one
set per asset unless an explicit assignment already exists. Unrelated sets remain.
An incomplete existing Bake setup or a missing explicit assignment can block
registration; do not delete unrelated sets merely to silence that error.

## Revise a source without losing low-poly work

1. Save the file and edit the source intentionally.
2. Run **Check Outdated** to review source/high/UV/validation/export dependencies.
3. Generate the affected high if it remains eligible for regeneration.
4. Inspect the existing working low against the new high. Adjust the low manually
   if your design change requires it; generation will not rebuild it.
5. Revisit UVs only if necessary, validate again and export to a new folder.

An outdated LOW status describes source provenance, not a command to replace the
low. There is no automatic low refresh or Reprocess Outdated button. If a completely
new low is needed, preserve the old asset and create a separate asset record from
the revised source, then review its new outputs and Bake membership explicitly.

## Preserve an edited generated high

1. Use Inspector **High**, then **Restore Visibility** as needed to locate it.
2. Save a backup before changing relationships.
3. Choose **Custom High** for the component.
4. Select the intended high mesh objects and click **Add Selected Highs**.
5. Check the relationships in **Component Details**, then generate to prepare/register
   the pair without rebuilding the custom geometry.

Sources and working lows cannot be assigned as their own custom highs. **Clear
High Links** clears references only. Switching back to DynaBool does not authorize
overwriting a previously edited generated high; its ownership guard still applies.

## Adopt an existing Bake setup

1. In **Bake**, choose the intended active texture set with its low/high collections.
2. In **Model**, click **Adopt Bake Setup**.
3. Inspect each component and the adoption report.

The lows become source/low references. Only explicit manual targets and Bake
Groups supply high associations; automatic name/surface matching is not run.
Unassigned highs are reported instead of guessed. Repeated adoption of an already
represented low is refused. Adoption itself does not migrate collections or edit
geometry. Adopted original lows are validation-only for processor UV application.

## Prepare a shared UV layout

1. Generate all working lows for the group first.
2. Set all group members to **Assisted**. A Preserve member blocks joint repacking.
3. Keep UV protection enabled while building and reviewing **Prepare UVs** proposals.
4. Inspect the proposals in the UV Editor, then return to Object Mode.
5. Unlock every shared member only when ready, then **Apply UV Proposal**.
6. Re-enable protection and validate the asset.

For **Automatic**, every member must be Automatic and explicitly unlocked before
Prepare UVs builds and applies. Use Assisted when approval is important.

The strictest island gap/border across members is used at the assigned texture-set
resolution, falling back to global Bake resolution. Existing seams and pins are
constraints. A Boolean edge-domain attribute named `mbt_uv_protected` marks edges
that must not receive new seams. Proposals violating protected edges are refused.

Applying requires independent local single-user lows, unchanged dependencies and
valid proposal geometry/padding/overlap. If inputs changed after preview, rebuild
rather than trying to force application. Apply updates active UV coordinates/pins
and seam flags, not topology, other UV maps or material assignments.

**Acknowledge Reviewed UVs** accepts the current working layout as the reviewed
reference without editing UVs; use it only after inspection. It is not a repair or
a replacement for a successful UV-application dependency baseline.

## Deliver files or bake

For files, select **Export**, set Output Folder and Low Poly/High Poly, then
**Export Active Asset**. Low-only and high-only exports are supported; Disabled
components contribute no highs. Review `asset.json` for exported names/material groups.

For baking, inspect the registered set in **Bake** and follow the
[Painter guide](../../SUBSTANCE_PAINTER.md). Generation does not launch Painter,
unwrap protected lows, or resolve unrelated incomplete sets. Bake diagnostics
remain necessary even after Model validation.