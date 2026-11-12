# Asset Processor

The Asset Processor organizes source meshes into assets and components, prepares
working lows and generated or custom highs, supports protected UV preparation,
and exports low/high FBX files. It lives in **3D Viewport > Sidebar (N) > MBT Baking > Model**;
standalone file export is in **Export**.

Enable **Substance Painter** in MBToolkit's add-on preferences to show this panel.
Painter does not need to be running for asset records, generation, UV preparation,
validation, or standalone export. Blender 5.2+ is required by this add-on.

## Start here

1. [Quick start](quick-start.md) — create a simple asset and export it.
2. [Concepts and safety](concepts.md) — understand sources, lows, highs and ownership.
3. [Working with assets](workflow.md) — revise sources, preserve custom work and adopt a Bake setup.
4. [Control reference](reference.md) — controls, defaults and dependency states.
5. [Troubleshooting](troubleshooting.md) — failures, protection guards and recovery.

For contributors:

- [Developer guide](developer-guide.md) — architecture, invariants and tests.
- [Documentation maintenance](documentation.md) — source-of-truth policy and future wiki publishing.

## Workflow at a glance

**Source meshes → Asset/component records → Generate → Review low/high → Prepare
UVs → Validate → Export or Bake**

Generation with a generated/custom high registers its low/high inputs in Bake
collections. This is not a bake: it does not launch Painter or update a project.
Standalone export is a separate operation that writes a new folder.

> **The central safety rule:** generation never refreshes an existing working low.
> Source changes can make its provenance outdated without replacing its geometry or UVs.
> UV proposals are disposable; applying them requires explicit permission.

## Scope and limitations

- This is not automatic retopology: the initial low is an evaluated source snapshot.
- Remesh quality checks are sampled, not a guarantee that every thin feature survives.
- UV preparation packs one tile (1001), jointly within the component's texture set.
- Generation and UV preparation are synchronous. Save before expensive work.
- Validation and dependency status are snapshots; rerun them after edits.
- There is no automatic **Reprocess Outdated** operation.

These pages describe the current checkout, not a promise that a released ZIP has
identical behavior. The processor code was reviewed for this documentation; the
quick start still needs an interactive UI walkthrough on release.

## Related guides

- [Painter setup, baking and texture import](../../SUBSTANCE_PAINTER.md)
- [DynaBool remeshing implementation notes](../../AUTO_REMESH.md)
- [Standalone UV tools](../../UV_SUITE.md)
- [Development and packaging](../../CONTRIBUTING.md)

Use this wiki as the entry point for the processor. Older remeshing notes contain
superseded behavior; this reference describes optional Remesh and the configurable
work allowance used by the current processor.