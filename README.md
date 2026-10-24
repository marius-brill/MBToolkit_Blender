# MBToolkit

Hard surface workflow toolkit for Blender 5.2+

## Requirements

- Blender **5.2 or newer**. Earlier Blender versions are not supported.
- No pip packages are required; the add-on uses Blender's Python and its standard library.
- Substance Painter is optional and only needed for the Painter bridge/baking feature.
  See [Painter setup and limitations](SUBSTANCE_PAINTER.md) before enabling it.
- Windows is the primary development environment. Other platforms need validation,
  particularly Painter executable selection and launch behavior.

## Installation

1. Obtain a **built extension ZIP** from this repository's GitHub Releases, if one
   is published. Otherwise build from source using [CONTRIBUTING.md](CONTRIBUTING.md).
   GitHub's **Code > Download ZIP** is a source archive, not an installable extension.
2. In Blender, open **Edit > Preferences > Add-ons**, open the menu at the top
   right, choose **Install from Disk**, and select the built ZIP.
3. Enable **MBToolkit** if it is not already enabled.
4. In the 3D Viewport, press **N** and choose the **MBToolkit** sidebar tab.
   Configure optional features in the add-on's **General** preferences.

For updates, save your work and preferences, close other Blender sessions, and
install the new built ZIP through the same installer. Restart Blender afterward.
Do not enable a legacy checkout and an extension installation simultaneously;
duplicate copies can register conflicting operators, panels, and shortcuts.
To uninstall, disable/remove MBToolkit in Add-ons preferences. Exported Painter
projects and textures are not removed by uninstalling the add-on.

## Documentation and support

- [UV tools guide](UV_SUITE.md)
- [Substance Painter setup and workflow](SUBSTANCE_PAINTER.md)
- [Development, packaging, and release checklist](CONTRIBUTING.md)
- [Test commands and safety precautions](tests/README.md)
- [Changes](CHANGELOG.md)
- [Security and privacy](SECURITY.md)
- [License](LICENSE): GNU GPL v3.0 or later, as declared in the extension manifest

Use this repository's GitHub **Issues** for reproducible bugs and feature requests.
Include Blender/add-on versions, operating system, reproduction steps, and the
complete traceback. Remove private paths and assets before attaching logs or files.
For sensitive vulnerabilities, follow SECURITY.md instead of opening a public issue.

### Troubleshooting and safety

- Missing features: enable their switches in **General** preferences, then check
  the section selector. UV, Painter, Geometry Nodes and Resample start disabled.
- Missing panel: use a 3D Viewport, open its sidebar with **N**, and check whether
  Sidebar Tab Management has hidden the MBToolkit tab.
- Shortcut conflicts: configure MBToolkit's shortcut preferences or Blender's keymap.
- Import/registration errors: check the minimum Blender version, remove duplicate
  installations, restart Blender, and capture the traceback from the system console.
- Save a backup before topology changes, material replacement, or bulk operations.
  Script Runner executes arbitrary Python with Blender's permissions: only run
  scripts you trust. Painter remote scripting should remain local to your machine.

## General preferences / optional features

Open **Edit > Preferences > Add-ons > MBToolkit > General** to choose which
features load. Script Runner, Rename / Clean Up, Align, Sidebar Tab Manager,
Pie Menus, Modifier Tools and Scene Performance are enabled by default.
UV Tools, Substance Painter Bridge / Bake, Geometry Nodes / Low-to-High and
Resample are disabled by default.

Switches apply in the current session, including removal of feature panels,
operators, shortcuts, handlers and timers. Settings are retained when a feature
is disabled. Use **Save Preferences** in General (or Blender's automatic
preference saving) to retain your choices. On the next startup, disabled feature
runtimes are not imported or registered. Lightweight preference storage types
remain available so pie menus, favorites and sidebar arrangements are preserved.
Python modules already imported in a session may remain cached until Blender exits.

The sidebar manager feature switch controls loading the manager; its existing
**Enable Sidebar Tab Management** setting controls applying the saved arrangement.

## Layout

### MBToolkit sidebar sections

The icon strip at the top controls the sections inside MBToolkit (separately from
the whole-tab Sidebar Tab Manager). Each loaded feature has a distinct colored
pastel symbol, also used in its fixed section heading. Transparent symbol
backgrounds leave native gray buttons and their selected highlight visible.
The MBToolkit title and preferences gear sit in the native collapsible panel
header above the selector. Selector
buttons are double-sized and wrap in narrow sidebars instead of being squeezed.
Blender's native operator glyph size remains fixed; enlarging a button does not
independently scale its glyph. Symbols use bold, high-contrast artwork for clarity.

- **Click** an icon to show only that section.
- **Shift-click** an inactive icon to append its section at the bottom.
- **Shift-click** an active icon to hide it without reordering the others.
- Remove and re-add a section to move it to the bottom. The icon strip stays in
  a consistent order; the cards below follow selection order.
- The gear opens preferences. Disabled features do not appear in the strip;
  hiding a card does not unload its feature. Disabling a feature preserves its
  saved position for re-enabling.

Individual sections are always open, with boxed backgrounds and no collapse arrows. Box
contrast follows Blender's theme. MBToolkit uses the existing native panel
backdrop with a visible native header and one card per selected section, without an additional encompassing
box. The layout grows and shrinks with section selection and scrolls natively.
No theme colors, opacity, sidebar settings, or other Blender UI are modified.
Native panel and box opacity remain controlled by the user's theme.
Selector tooltips contain only the section name
(Blender may append developer information when Python Tooltips are enabled).
The pastel icons include a croissant for Bake, a checker square for UV, and
non-crossing XY arrows for Align.
Internal advanced/options expanders are unchanged. Use Save Preferences (or
automatic preference saving) to retain selection and ordering across restarts.

```
mbtoolkit/
  blender_manifest.toml      extension manifest (version, min Blender)
  __init__.py                minimal core registration, then optional feature loading
  preferences.py             AddonPreferences (stores pie menu definitions)
  core/                      addon id/prefs access, class registry helper, scene props, shared operators
  features/
    pie_menus/               data (prefs storage), runtime (the pie), ops, keymap, ui (prefs editor)
    script_runner.py
    geonodes/               sdf_remesh, crease_by_angle, dynabool (node groups built from code)
    align.py
    rename.py
    resample.py               open wire chains and quad surface strips
    scene_stats.py
  ui/panels.py               N panel
```

Each feature module exposes `classes`, `register()/unregister()` and, if it has N panel UI, a `draw(layout, context)`.

## Modifier list

- Modifier Properties shows compact favorites with at most four buttons per row,
  wrapping additional favorites onto new rows, the stack overview,
  and Blender's native modifier settings, preserving their sections and controls.
  Selecting a modifier in the list expands it and collapses the other modifiers;
  their native headers remain visible. Manual expansion is retained until the
  selection or stack changes.
- Press **Shift + W** over the 3D View to open an in-viewport popup with favorites,
  the modifier list, and compact settings for the selected modifier. No separate
  window is created. The popup uses RNA controls rather than native modifier
  layouts; specialized collection editors and simulation/cache actions remain
  available in the main Modifier Properties panel, which keeps its native UI.
  Change the key, Shift, Ctrl, and Alt in MBToolkit preferences > Modifiers;
  select None to disable it. A conflicting shortcut can be reassigned there.
- The monitor button toggles realtime viewport evaluation and uses Blender's
  theme highlight when enabled. Modifier icons come from Blender's native type enum.
- Last-position pins synchronize with Blender's Pin to Last in both directions.
  Other pins retain their bottom-relative position (second-last, third-last, etc.).
- Modifiers created by Blender or other add-ons are read directly from the stack.
  Geometry Nodes inputs use modern RNA storage when available; Geometry and other
  non-value sockets are skipped, without attempting unsupported IDProperties.

## Sidebar tab manager

Open **Edit > Preferences > Add-ons > MBToolkit > N-Panel** and enable
**Sidebar Tab Manager**. Use the eye toggles to hide/show whole 3D Viewport
sidebar tabs, and the arrows to reorder them. This includes other add-ons and
MBToolkit itself; the manager adds no sidebar panel or individual panel controls.

- **Refresh** discovers tabs from currently registered Python panels. Newly
  enabled add-ons are also detected automatically while the manager is enabled.
- Hidden tabs retain their normal mode/context checks when shown again.
- **Item** stays fixed because it contains native Blender controls that cannot
  be fully hidden or reordered through the Python panel API.
- Unavailable tabs retain their saved settings for when their add-ons return.
- Disable the manager to restore original panel behavior without losing settings;
  **Restore Defaults** also clears the saved arrangement and visibility.
- Save Preferences (or enable Blender's automatic preference saving) to retain
  settings across restarts. Disabling MBToolkit restores managed panel classes.
- The manager re-registers Python sidebar panels to change tab order. Add-ons
  that independently rebuild those panels can conflict; refresh or disable the
  manager if a particular add-on is incompatible. Existing per-editor panel
  expansion/pinning state may be reset by re-registration.

## Substance Painter foundation

The **Bake** panel has one primary **Bake** action: validate, pair meshes, export
fresh snapshots, connect/launch Painter, create or update the associated project,
bake, save, export textures and update Blender materials. Internal job files are
managed automatically. Collection assignment moves meshes rather than adding links.
Name matching uses explicit Bake Targets, existing names, or conservative sampled
surface matching; ambiguous inputs stop with an actionable error. Project templates
can be set globally or per scene. The default export definition is automatic;
advanced custom unpacked PNG mappings and painting-only texture updates are supported.
See [SUBSTANCE_PAINTER.md](SUBSTANCE_PAINTER.md) for the workflow, supported texture
filenames, limitations, and background-Blender tests.

## Adding a feature (registration)
1. Create `features/<name>.py` with operators and `register()/unregister()`.
2. Add a key, label, default and lazy module path to `core/feature_manager.py`'s `FEATURES`. Register property groups before their consumers. Do not import optional runtimes from core modules.
3. Expose `draw(layout, context)` and lazily import it inside a `_SubPanel` subclass in `ui/panels.py`; add the panel to `classes` and map it to its feature in `_features`.
4. Use `MBT_OT_*` classes, `mbt.*` operator IDs, and the helpers in `core/registry.py`. Unregistration runs in reverse order.

Registration is explicit. Lightweight storage types register before preferences;
only enabled feature runtimes register afterwards. Sidebar panels follow their
feature switches. Runtime modules unregister in reverse order, with managed
sidebar classes restored before panel changes.

## Installation Instructions

### Method 1: Development with VS Code (Recommended)
1. Install the "Blender Development" extension for VS Code (by Jacques Lucke)
2. Open this folder in VS Code
3. Run the command "Blender: Start" and select this folder
4. This symlinks the add-on into Blender and reloads on save

### Method 2: Manual Installation via Blender Preferences
1. Close Blender completely
2. Navigate to your Blender addons directory:
   - Windows: `C:\Users\<YourUsername>\AppData\Roaming\Blender Foundation\Blender\5.2\scripts\addons`
   - macOS: `/Users/<YourUsername>/Library/Application Support/Blender/5.2/scripts/addons`
   - Linux: `/home/<YourUsername>/.config/blender/5.2/scripts/addons`
3. Copy the entire `mbtoolkit` folder into this directory
4. Start Blender
5. Go to Edit > Preferences > Add-ons
6. Search for "MBToolkit" 
7. Enable the add-on by checking the box next to it

### Method 3: Using Blender's Extension System (Blender 5.2+)
1. Open Blender 5.2+
2. Go to Edit > Preferences > Add-ons > Get Extensions
3. Click on "Repositories" tab
4. Add this folder as a local extension repository
5. Find MBToolkit in the list and install it

## Troubleshooting

### If you don't see the N panel:
1. Make sure the addon is enabled in Edit > Preferences > Add-ons
2. Open the 3D Viewport sidebar with N; Resample requires mesh Edit Mode
3. The N panel should appear on the right side of the 3D viewport
4. Look for a tab labeled "MBToolkit" - if it's not there, try restarting Blender

### Common Issues:
- Check the tool's required mode; Resample runs in mesh Edit Mode
- Check that all required modules are properly imported
- Verify that your Blender version matches the requirements (5.2+)
- Make sure no other add-ons are conflicting with MBToolkit

### If problems persist:
1. Check the System Console (Window > Toggle System Console)
2. Look for error messages when loading the add-on
3. Try reinstalling the add-on
4. Ensure all Python dependencies are properly installed

## Features

### UV Suite

The UV suite is available in the 3D Viewport and UV Editor MBToolkit sidebars:
Auto UV with seam repair and unwrap-method comparison; topology-aware straighten,
quadrify, rectify and relax; native shape search and constrained rectangle packing;
pixel gaps/borders, fixed-density UDIM layouts, locks and existing exact stacks;
px/m or px/cm density tools; selection diagnostics; UV transforms and map management.
Operations protect selection and roll back UV/seam changes on failure (selection
tools intentionally change selection). See `UV_SUITE.md` for exact behavior,
remaining planned features, conservative algorithm limits and test instructions.


## Modifier List

The **Properties editor > Modifiers (wrench tab)** has a fixed, headerless favorites toolbar and compact modifier list above Blender's native settings. It is not a separate collapsible panel or an N-panel section. Selection follows the context object, including pinned Properties objects. Drawing never initializes or modifies datablocks.

- Rename modifiers and use the small cage, Edit Mode, viewport, and render buttons on the right of each row. The old separate visibility overview box has been removed.
- **Add Modifier** opens a category-column menu overview for editable supported objects in Object Mode. Selecting an entry uses normal menu dismissal rather than leaving an operator-properties popup open. Compatible entries are derived from the installed Blender menu definitions, including explicit built-in node assets. Native category asset catalogs remain accessible within the popup. Missing external assets may still report Blender's own availability error.
- **Preferences > Add-ons > MBToolkit > Modifiers:** select favorites by category and drag the compact icon-and-name tiles directly to reorder them in the four-column preview. The preview snaps to the new position while dragging; release commits, Escape or right-click cancels. No separate reorder popup, handles, or arrow/remove controls are needed. Toggle category buttons below to add/remove favorites. Favorites are disabled in incompatible object contexts. Use Blender's Save Preferences if automatic saving is disabled.
- Favorites use compact labeled, icon-and-name buttons, wrapping after four entries. Both modifier-popup and pie shortcuts use a clickable capture field: press the combination, Escape cancels, Backspace or the X clears it. Ctrl, Shift, Alt and OS-key combinations are supported.
- The row pin stores the modifier's **distance from the bottom**: last stays last, second-last stays second-last, and so on. Newly added modifiers are placed above a pinned tail. Pins use persistent modifier IDs and survive renaming. Previous exact-index records are converted once using the current modifier positions, outside drawing. Adding through the toolbar immediately restores pins; external changes are corrected on a deferred safe update. Multiple pins preserve unlocked modifiers' relative order. When a stack becomes too short, pins use the nearest available slots while retaining their requested bottom offsets.
- The up/down controls beside the list reorder the selected modifier among unpinned slots and preserve selection. Unpin a modifier before moving it. Each row's X deletes that modifier, including pinned modifiers, and removes stale pin records. Reorder/delete require an editable Object Mode object and support undo; Blender's own modifier restrictions still apply.
- Disable native Pin to Last before using bottom-relative pins. Native ordering restrictions can prevent restoration; conflicts are reported in the UI/console and are not endlessly retried for the same stack state. Updates are deferred during renders. Undo/redo and file-load notifications rebuild enforcement state; actual interactive undo timing requires a UI smoke test.
- Full native modifier settings remain available in the same wrench tab; the list does not replace Blender's built-in modifier panels or change editor pins.
- Linked/read-only objects are inspection-only. Individual read-only controls are disabled; the Add button is unavailable in unsupported contexts.
- The native Modifier Properties draw function is temporarily replaced so there is one Add button and no movable list header. It is restored on disable. Other add-ons that replace the same native draw function may conflict; MBToolkit will not overwrite a later replacement during cleanup.

## Scene Performance

Open **3D Viewport > Sidebar > MBToolkit > Scene Performance** in Object Mode.

- Choose **Visible in View Layer**, **Selected Objects**, or **Active Collection**, then **Scan**. Collection scope optionally includes child collections; selected/collection scopes can include hidden objects but stay within the current view layer. Visible scope respects viewport Local View.
- Scans read evaluated mesh triangles and optionally native last-evaluation modifier timings. They never toggle modifier visibility or alter the stack. A scan is not a forced cold-cache benchmark. Timings are diagnostic, not object/frame/render time; parallel modifier execution can make them unreliable. No frame-time or FPS claim is made from their sum.
- Triangle totals are **per-object evaluated mesh** counts. Shared meshes count for each object; collection instances and Geometry Nodes instances are not expanded, and non-mesh components are not converted into an invented total. Objects with modifiers but unsupported mesh output can still show modifier timings. A dash means disabled, unavailable, or unmeasured; measured zero remains distinct.
- **Auto**, enabled by default and located left of **Scan**, uses an editor-owned session and a single revision-based controller. Changes debounce for 0.4 seconds with a 1.5-second maximum postponement. Ordinary changes never cancel scans: a bounded full-scope capture finishes and commits, stays marked stale if newer changes arrived, then receives a follow-up capture. Dependency-aware incremental collection is deliberately disabled until separately validated. Previous results remain visible during soft refreshes; hard context changes clear incompatible data. Closed sidebars, playback/rendering and non-Object modes pause measurement, not selection reconciliation. Opening the tool acquires its viewport session; collapsing the panel does not stop an acquired session. Cancel turns Auto off.
- Two compact buttons sort by **Tris** (left) or modifier **ms** (right), highest first, with unavailable values last. All objects remain accessible in the scrollable list. **Preferences > Add-ons > MBToolkit > Scene Performance** contains native timing and triangle/timing budget settings. Search, filters, metric help, baseline comparison, and export have been removed.
- Each viewport has its own rows, scan revisions, Local View/view-layer binding and selection projection. Clicking an object name queues an explicit activation command; Shift adds to selection. UIList index changes from background clicks/keyboard navigation are reconciled outside drawing; they do not invoke scene changes from an RNA property callback. A concurrent viewport active-object change takes priority. Changing viewport selection highlights the matching row and preserves multi-selection even with stale results, Auto off or a scan running. Deselect-all clears the active highlight. Hidden/unselectable objects are not unhidden or unlocked. The wrench uses an existing unpinned Properties editor and never changes editor pins.
- Interactive scans run in main-thread batches capped at 32 objects and an approximately 8 ms shared controller budget. One expensive dependency-graph evaluation or mesh conversion cannot be interrupted mid-call. Explicit **Cancel** preserves partial manual results, while cancelled automatic work preserves its previous committed snapshot. Scene/view-layer/Local View/frame/scope changes are hard boundaries; ordinary geometry updates queue a new revision without discarding work. Background automation runs synchronously under an explicit viewport override.
- Snapshots include scene/view-layer/scope/frame metadata and use session object identities rather than names. Renaming does not retarget a result to a different object. File loads and undo/redo clear transient results; results are not saved into the blend file.

## Development tests

Development checks live in `tests/`, separate from the add-on runtime. See
`tests/README.md` for coverage, safe execution commands, GUI checks and persistence
testing. Extension builds exclude this directory; omit it from manually made
distribution ZIPs as well.

### Scene Performance validation

Run `tests/test_scene_performance.py` in a **disposable background Blender process with `--factory-startup --python-exit-code 1`**. It creates/deletes objects and must never be run in a working scene. Run `tests/test_registration.py` separately for the existing Modifier List/Resample regression suite. Interactive appearance, sidebar widths, Local View, and actual UI responsiveness still need a viewport smoke test.

`tests/test_scene_performance_live.py` runs in a disposable **interactive** factory-startup Blender with `--enable-event-simulate` and checks scheduled multi-batch collection, Blender-native viewport hit selection, explicit list activation, soft-change follow-up, idle behavior, editor/window isolation and file-load recovery. It quits its own process. OS-delivered mouse events and keyboard focus still need a manual smoke test. The background suite also covers Local View, view-layer rebinds, rename identity, selection guards, partial cancellation and the legacy starvation sequence.

For diagnosis, `features.scene_performance.runtime.diagnostics()` returns controller registration/heartbeat, each editor's context, requested/committed/scanning revisions, progress, last reason/error, and a bounded 200-event trace. Handler callbacks only record Python revisions; Blender UI storage is updated by the controller, never from dependency-graph handlers. Unregister removes the controller and message-bus subscription; file load and undo/redo rebuild transient sessions.

## Preference editors

- **UV** has its own preferences tab and retains the existing angle threshold.
- **Pie Menus** uses a compact list, name/shortcut header, directional slot preview, and one selected-slot editor. Add, duplicate (without duplicating its hotkey), remove, and the starter example remain available. Existing definitions are preserved.
- Choose **Operator** and **Choose Blender Command** to search registered commands by name or ID, including native commands that are unavailable in the Preferences context. **Options** edits boolean, number, text, and ordinary enum overrides without executing the command. Arrays, enum flags, pointers and collections remain in the Advanced literal-argument field; unsupported overrides are preserved. Native menus also have a search picker. Nested MBToolkit pies and explicit Python actions remain supported. Commands execute using the viewport invocation context and retain Blender's mode/selection restrictions.
- `tests/test_preferences.py` exercises data, picker discovery, options, duplication, shortcut storage and preference drawing in a disposable background Blender. `tests/test_preferences_live.py` runs with `--factory-startup --enable-event-simulate --python` in a disposable GUI process and checks real shortcut capture, GPU tile drawing, drag reorder, and Escape rollback. Never run these tests inside a working scene.

## Resample

Open **3D Viewport > Sidebar > MBToolkit > Resample** and enter Edit Mode on one mesh object.

- **Resample Edge Chain:** select an open edge chain. Choose the target vertex count and Linear or Smooth interpolation. Changing count requires isolated wire geometry. Face-connected chains support same-count redistribution only. Endpoints stay fixed.
- **Resample Surface Strip:** select consecutive, non-touching cross edges in Edge Select mode, or a one-quad-wide open band of quad faces in Face Select mode. Cross Edges includes both fixed ends: 4 cross edges produces 3 quads. Roundness 0 samples the original polyline; higher values smooth the profile. When a single face has an ambiguous direction, the shorter transverse edges are preferred.
- Both tools support multiple independent selected components. Settings appear in a dialog and in Adjust Last Operation (F9).
- Closed loops, branching selections, degenerate segments, shape-key meshes, and multi-object Edit Mode are rejected. Connected strip rails are supported: same-count resampling moves existing shared vertices without rebuilding topology. Count changes merge immediate side-face fans into n-gons and resample their shared boundary, keeping the mesh attached and the outer perimeter fixed. This intentionally removes side-face spokes; it does not preserve an all-quad surrounding mesh. Hidden/non-manifold side connections, loose spokes, and merges across marked seams or material boundaries are rejected with a specific message. UVs and other attributes on merged faces follow Blender's dissolve/interpolation rules.
- Operations are staged on a private BMesh. Failure before commit leaves the edit mesh untouched; a serialized backup restores it if commit fails. Existing BMesh-supported custom data is carried through serialization; subdivision/dissolution uses Blender's interpolation rules, not exact preservation of removed UV seams or arbitrary per-face values. New wire elements interpolate vertex data and copy edge data from their source segment.

### Validation

Run `tests/verify_structure.py` using Python for syntax checks or Blender for import checks. Run `tests/test_registration.py` in a **disposable background Blender process with `--factory-startup --python-exit-code 1`**. It creates/deletes test objects and must not be run in a working scene.

The integration tests exercise registration cycles, count changes, selection, interpolation, custom data, invalid inputs, and injected failure recovery. Interactive panel appearance, dialogs, F9, and undo/redo still require a UI smoke test.


## Features

- **Align Tools**: Drop objects to ground or move to target location
- **Incremental Rename**: Rename selected objects with a base name and sequential numbering
- **Scene Performance**: Monitor triangle count and modifier evaluation times with automatic updates and viewport-synced selection
- **Script Runner**: Execute external Python scripts directly from the N panel
- **Pie Menu Editor**: Custom pie menu creator setup
- **Clean Up Mesh**:
- **Modifier List**: Change modifier stack to list view with favorites
- **Organize UI**: Hide N-Panel segments


## Future Features Ideas

- **Focus**: Machin3Tools type focus with hotkey on object or multiple objects
- **Double Click Select**: Bind ctrl + l (select linked by type) to double click
- **Resample Mesh**: Like the existing addon resample mesh
- **Automatic Unwrap**: Heavy on math and complex operations could be difficult
- **Smart Face**:
- **Boolean Tools**: General setup
- **Bolts from Plane**: Add plane for where want to add a bolt. Select from dropdown list of bolts. On click highpoly of bolts get generated
- **Script Shelf**: Shelf to load and store your most used scripts. Drop down list
