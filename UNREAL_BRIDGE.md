# Blender to Unreal Bridge

## Setup

1. Enable **Blender to Unreal Bridge** in MBToolkit's General preferences.
2. In the target Unreal project, enable **Python Editor Script Plugin** and
   **Editor Scripting Utilities**, then restart Unreal if prompted.
3. In Unreal Project Settings, search for **Python Remote Execution** and enable
   it. Keep the multicast bind address at `127.0.0.1` and TTL `0`. The default
   multicast group endpoint is `239.0.0.1:6766`; custom ports are supported.
   Only trusted local projects should enable remote
   execution: it permits executing Python code in the editor.
4. Open **N → MBT Unreal** in Blender. Choose your `.uproject` and click
   **Test Connection**. That exact project must already be open in Unreal.
5. With **Engine Directory** blank, the project's EngineAssociation is matched
   against Epic Launcher metadata, both Windows registry views, registered source
   builds, and standard installation directories. The resolved version and path
   appear beneath the engine controls when you select the project or test.
   **Detect Installed Builds** refreshes a list of valid installations and lets
   you choose one explicitly. **Browse Engine** accepts the install root, its
   `Engine` folder, or `UnrealEditor.exe`. Typed and pasted paths are also validated
   immediately (including quoted Explorer paths). Manual selections take precedence;
   clear Engine Directory to restore automatic project matching. Invalid/stale paths
   show a specific error instead of silently falling back to another engine.

**Discovery Endpoint** can be left blank to read the selected project's Python
remote-execution configuration, including `DefaultEngine.ini`, Windows platform
configuration and generated `Saved/Config/WindowsEditor/Engine.ini` overrides.
The bridge displays the resolved endpoint and its source. If Unreal has unsaved,
command-line or other runtime overrides, enter its active multicast endpoint
explicitly (for example `239.0.0.1:6768`). This does not change Unreal settings.
The engine must be open as an **editor**, not a `-game` process. Discovery errors
now distinguish no response, another project, command connection and remote Python
failure. Imported batches are not required to test a connection.

Project, engine, discovery and editor-session controls are grouped in the
**Connection Setup** block. Click its triangle/header to hide or show the setup
without hiding material assignment, export options or connection result messages.

Validated with Blender 5.2 and Unreal Engine 5.7 on Windows. The bridge rejects
editors older than UE 5.7; newer versions still need compatibility testing.
No pip dependencies or custom Unreal plugin are required.

## Send meshes

- Select a root **Empty** in Object Mode. Its mesh descendants, including meshes
  beneath nested Empties, become **one Static Mesh asset**. Evaluated modifiers,
  UV maps, material slots and relative mesh transforms are exported from copies.
- The root Empty's transform is removed: its origin and axes define the asset's
  local frame. Its scale is treated as part of that frame, not baked as an extra
  mesh scale. Apply the root scale first if you want that scale baked into geometry.
- The **Empty name is the asset name**. Names must begin with a letter or
  underscore, use ASCII letters/digits/underscores, and be at most 100 characters.
  Invalid names are rejected, never silently rewritten.
- Multiple selected root Empties produce separate assets. A selected nested
  Empty is included in its selected ancestor rather than exported twice.
- Set **Content Folder**, such as `/Game/Props/Furniture`. The folder button
  browses the selected project's on-disk `Content` directory. You can type a new
  `/Game/...` destination; Unreal creates required asset folders during import.
- Click **Send to Unreal**. Blender export runs on the main thread; connection
  and Unreal import run in a worker, with status shown in the panel.
- Save the `.blend` to persist project, engine and destination choices.

The source objects, transforms and selection are not edited. Meshes outside the
active view layer and empty evaluated meshes are rejected. Collection instances,
Geometry Nodes instances that have not been realized, skeletons, animations,
Blueprint construction and level placement are not supported.

## Standard project import options

### Export Scale

**Export Scale** defaults to **1.0**. Set a positive factor to multiply exported
geometry and child mesh offsets around the root Empty, in addition to normal
scene-unit handling. Source transforms, mesh data and scene units stay unchanged.

### Unreal materials and Blender preview

1. With the project open in Unreal Editor, click **Refresh Material List**.
2. Search **Material** by material name. Full asset paths are retained internally;
   identically named assets have numbered labels to keep their identities distinct.
3. Click **Assign & Preview** once. Assignment happens immediately, and the preview
   fills in automatically when Unreal responds. Changing selection while it loads
   does not change the assignment target. No second click is necessary.
4. Object Mode assigns all faces of selected meshes and mesh descendants of
   selected Empties. Edit Mode assigns only selected faces.
5. Use **Material Preview** shading. **Refresh Preview** reloads changes from
   Unreal; fetched images are packed into the blend.
6. Sending binds slots to the original exact Unreal material paths, including on
   reimport. Materials linked to another project are rejected.

Previews are **approximations**, not shader conversions or baked renders. Common
BaseColor/Albedo/Diffuse/Color/Tint, Roughness, Metallic/Metalness and Normal/NormalMap
parameters are recognized. Unrecognized/non-parameterized graphs use neutral
defaults. Texture parameters export as TGA to
`Saved/MBToolkit/UnrealBridge/MaterialPreviews`; export failures are reported.
Packed ORM, UV tiling logic, world-aligned materials, layers, procedural effects,
displacement, transparency and arbitrary graph connections are not reconstructed.
Fetching previews writes cache files but does not modify Unreal materials.

Successful connections retain the editor node for subsequent requests, including
multi-asset batches. Duplicate discovery replies with the same node ID count as
one editor. If distinct sessions advertise the same project, use the refresh icon
beside **Editor**, choose the intended session ID, and retry. The bridge never
arbitrarily chooses among distinct editors; exact-project and loopback checks
still apply. An editor restart with only one matching session reconnects normally.

The bridge uses UE's synchronous **Interchange asset import**. Your project's
configured default asset pipeline stack controls Nanite,
collision, LOD, lightmap, material, texture and other mesh options. This is an
automated import: no import-options dialog opens. The bridge supplies only the
source FBX, asset name, destination and overwrite/reimport intent for unlinked meshes.

For meshes with linked Unreal materials, the bridge copies the project pipeline
stack (or the mesh's saved stack on reimport) and disables material/texture asset
creation on the copies. This prevents FBX slot markers named `MBT_UE_...` from
becoming unwanted Unreal material instances. Mesh import settings are retained;
project defaults are not edited. Existing Unreal materials are assigned by path
after import. For mixed linked/unlinked slots on the same mesh, no new shaders or
textures are imported; link all slots that need existing Unreal materials. Custom
stacks without a supported Generic Assets/Material pipeline are rejected rather
than importing unwanted marker assets.

The fix prevents new placeholder assets; it does **not** automatically delete
`MBT_UE_...` assets left by older sends. Inspect their references in Unreal before
manually removing any unused ones.

Mesh copies are joined before export, so the project need not enable Combine
Meshes. A custom project pipeline that changes names or excludes Static Mesh
import can prevent the expected asset from being created; the bridge reports
that failure instead of replacing your pipeline.

**Replace Existing** is off by default. When enabled, only existing Interchange
Static Meshes can be reimported; their saved Interchange settings are retained.
Legacy FBX assets and assets of other types are rejected. Imported mesh packages
are saved; source-control checkout permissions must allow this. The bridge does
not save unrelated editor packages. Materials/textures follow project import rules
and may require saving in Unreal separately.

## Sources, errors and limits

FBX sources and a request manifest are retained in the target project's
`Saved/MBToolkit/UnrealBridge/<send-id>/` directory. Keep sources referenced by
Unreal for future reimports; `Saved` is often excluded from source control, so
back them up or relocate sources through Unreal before sharing the project.
Old send folders are not automatically deleted.

A batch is **not atomic**. Earlier imports may succeed before a later failure.
Check the Unreal Output Log before retrying. Closing/disabling the Blender feature
does not cancel an import already running in Unreal. A timed-out command may
still finish. Do not launch duplicate editors for the same project.

Only loopback connections are accepted, the project is verified again inside
Unreal before any import, and assets cannot be sent to another open project by
name alone. The bridge uses Epic's `remote_execution.py` shipped with the selected
engine and one private client socket attribute to enforce a bounded command timeout.

## Development checks

Run `tests/test_unreal_bridge.py` in a **new disposable background Blender** with
factory startup. It validates naming/paths, lifecycle, nested hierarchy collection,
source preservation, evaluated FBX round-trip, pivot, scale, UV/material retention
and failure cleanup. It prints a disposable project path under the system temp
directory. `tests/test_unreal_bridge_editor.py` runs inside **that disposable UE
project only**, using `-run=pythonscript -script="<absolute forward-slash path>"`,
and tests real import, asset dimensions, saving, reimport and safety guards.
Never run destructive integration checks in an artist's working session.

`tests/test_unreal_bridge_connection.py` additionally tests discovery and remote
import against the generated project opened in a separate Unreal editor with
remote execution enabled; it quits only that disposable editor afterward.
`tests/test_unreal_bridge_ui_live.py` runs in disposable GUI Blender and exercises
the panel builder in a real Blender layout, then quits automatically. It does not
simulate OS file-picker interaction.