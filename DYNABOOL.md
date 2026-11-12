# DynaBool repair and usage

> **Historical revision-2 notes below.** Revision 3 supersedes the optional remesh,
> manual asset voxel settings and subdivision fallback described here. See
> [Automatic DynaBool and Model to Bake](AUTO_REMESH.md) for current behavior.

DynaBool combines angle-based creases, subdivision and optional SDF remeshing.
Revision 2 fixes disappearing output at small voxel sizes: the old group extracted
at a fixed distance of 0.01 while storing only a three-voxel SDF band. The new group
extracts at zero, the SDF surface. SDFremesh revision 3 likewise removes the old
one-voxel extraction offset. Neither fix changes the source mesh.

## Existing files

Reload the add-on (or restart Blender) after installing the updated code. Enable
**Geometry Nodes / Low-to-High** in preferences if its tools are not visible.

- Select objects using the stock old DynaBool modifier and run **Upgrade Selected
  DynaBool** in Low to High, or search for it with F3. Input settings are preserved;
  the operation is undoable. New modifiers use the repaired group automatically.
- The analogous **Upgrade Selected SDF Remesh** updates stock SDFremesh revision 2.
- Customized graphs, animated objects/groups, linked data and processor-owned highs
  are skipped rather than overwritten. Groups are compared against the stock graph;
  changing layout or node names alone does not prevent upgrade.
- For Model asset components, use **Generate Component / Generate Asset** instead.
  Existing unedited generated highs are refreshed through the normal ownership and
  fingerprint guards. Edited highs still require preservation as Custom High.
- Old shared groups remain intact and keep their names. Updated groups may have a
  numeric suffix; that is intentional and does not indicate an unsuccessful upgrade.

## Failures are not successful remeshes

Standalone DynaBool defaults **Fallback on Failure** to enabled. If remeshing returns
no faces, it displays the subdivided input instead of making the object disappear.
Fallback faces carry the boolean attribute `mbt_dynabool_remesh_failed`.
Run **Check Selected DynaBool** to report empty outputs or this fallback marker.
This check evaluates the final modifier stack; later modifiers can remove the marker.
It detects complete failure, not partial feature loss or every topology defect.

Disable fallback to inspect strict remesh output. Asset generation always disables
fallback: an empty result raises an error, preserves the previous high/low and removes
temporary snapshots. Existing face/voxel budgets remain enforced. Standalone modifiers
do not have the asset processor's resource budgets: start coarse and reduce gradually.

## Getting useful high-poly results

- Voxel Size is measured in **local mesh coordinates**, not world dimensions. Changing
  object scale alone does not change local sampling density. Set mesh dimensions and
  resolution deliberately; the tool does not apply transforms automatically.
- Use a closed solid with meaningful thickness. A flat plane has no enclosed volume;
  give it intentional thickness (for example a Solidify modifier before DynaBool), or
  disable Remesh when a subdivided surface is the desired result.
- Begin with smoothing at zero to inspect detail retention, then increase it as needed.
  Zero iterations was verified as a no-op in Blender 5.2; no extra smoothing switch is
  required. Smoothing is voxel-relative and can shrink or erase thin features.
- Smaller voxels cannot recover detail absent from the source. Remeshing may merge
  nearby surfaces and removes the source topology, UVs and material-face assignments.
- Open boundaries, intersecting or inconsistently oriented faces, degenerate geometry
  and features smaller than the sampling resolution require inspection/preparation.
  There is no automatic hole-filling, normal repair or source cleanup in this patch.

This is not a promise to reconstruct the intended shape from any arbitrary low-poly
input. The repair removes the reproducible threshold bug and makes complete failures
observable; visual inspection remains necessary for partial loss and shape quality.

## Regression checks

Run in a new disposable Blender process, never in an artist's working session:

```powershell
& 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe' --background --factory-startup --python-exit-code 1 --python 'C:\Users\mariu\AppData\Roaming\Blender Foundation\Blender\5.2\scripts\addons\MBToolkit\tests\test_dynabool.py'
```

The test reproduces the legacy failure and covers fine voxel sizes, smoothing 0/1/4,
increasing face counts, finite/manifold geometry, bounds, thin solids, open-surface
fallback, disconnected/overlapping shells, source/transform preservation, protected
upgrades, SDF offset removal, save/reload, processor migration and failure rollback.