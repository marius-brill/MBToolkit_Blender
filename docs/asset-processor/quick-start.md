# Quick start

[Asset Processor home](README.md)

## Goal

Create one component from a simple closed mesh, generate its low/high pair, review
UVs and export FBX files without launching Painter.

## Before you start

- Install and enable MBToolkit in Blender 5.2+.
- Enable **Substance Painter** in the add-on preferences; open **MBT Baking** in
  the 3D Viewport sidebar and choose **Model**.
- Use a saved, disposable `.blend` for this first walkthrough. Use a simple closed
  mesh such as a cube, rather than a dense production model or open sheet.
- Stay in Object Mode for processor actions. Do not run these actions during a bake.

## 1. Record the asset

1. Select only your source mesh.
2. Click **From Selection** in **Assets**.
3. Rename the asset and component in their lists if desired.
4. Expand **Component Details** to check the source pointer.

**Expected result:** one asset with one component. Recording it does not duplicate,
move or modify the source. The working low has not been created yet.

## 2. Generate and inspect

1. Keep **High Poly** set to **DynaBool**.
2. Expand **Generation Settings**. Keep the defaults for this simple example.
3. Click **Generate Component** and read its report.
4. Expand **Inspector**, compare **Source**, **Low** and **High**, then click
   **Restore Visibility**.

**Expected result:** an independent working low and a generated high. The pair is
registered in Bake Low/High collections. The source remains unchanged. Generated
highs may be hidden until previewed.

If generation fails, use [troubleshooting](troubleshooting.md) before continuing.
Do not assume a batch report means every component succeeded.

## 3. Review UVs before applying

1. Keep **UV Mode** on **Assisted** and **Protect UV Layout** enabled.
2. Click **Prepare UVs** to create a disposable proposal.
3. Inspect the selected proposal in Edit Mode and the UV Editor. Check seams,
   island shape, padding and distortion. You can inspect or adjust the proposal;
   this is not the working low.
4. Return to Object Mode. If you want to keep the original layout, choose
   **Discard Proposal** instead of applying.
5. To approve the proposal, disable **Protect UV Layout** for the component and
   click **Apply UV Proposal**.
6. Re-enable **Protect UV Layout** after review.

**Expected result:** approved active UV coordinates/pins and seam flags are applied
to the working low, without replacing its object or changing the source geometry.
With multiple components, all shared texture-set members must permit application;
see the [full workflow](workflow.md).

## 4. Validate and export

1. In **Export**, choose an absolute **Output Folder** and enable **Low Poly**
   and **High Poly**.
2. Return to **Model**, expand **Validation**, and click **Validate Asset**.
3. Review findings. Use **Select Mesh** / **Frame** to locate issues, fix problems
   and validate again. Warnings need judgment, not indiscriminate repair.
4. In **Export**, click **Export Active Asset**.

**Expected result:** the report identifies a new asset-named folder containing
`low.fbx`, `high.fbx` and `asset.json`. Existing exports are not overwritten.
Painter is not launched and existing Painter projects are not modified.

## 5. Save and continue

Save the `.blend` to retain asset records and output relationships. UV proposals
are temporary and removed on save/load; apply or discard them before saving.

For baking, switch to **Bake**, inspect the registered texture set and matching,
and follow the [Painter workflow](../../SUBSTANCE_PAINTER.md). A successful
generation or export is not proof of bake readiness.