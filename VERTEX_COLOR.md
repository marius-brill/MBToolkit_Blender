# Vertex Color

## Quick start

1. Enable **Vertex Color** in MBToolkit's General preferences.
2. Select a mesh and choose the pastel triangle/vertices section icon.
3. Choose an existing **Attribute**, or use **+ / Create Color Attribute** in Object Mode.
4. Click **Edit Color…** for Blender's native color picker. Picker changes update
   affected elements live and enable RGB diagnostic preview if preview was off.
   **OK** commits; **Cancel/Esc** restores their exact baseline.
   Opening/accepting the picker without changes does not flatten mixed colors.
5. Alternatively set **Fill Color**, then press **Fill**. Changing the fill swatch
   only changes the tool's remembered color; it does not modify the mesh until Fill.
6. Choose **RGB**, **R**, **G**, **B** or **A** under Preview in Solid shading.

The feature starts disabled and uses no third-party dependencies. Existing material
node graphs, material slots, theme settings and viewport shading choices are not
rewritten. Attribute management and color edits support Blender undo.

## Attributes and components

An **attribute** is a named color layer, for example `Color` or `Masks`.
Its **components** are R, G, B and A. The attribute selector changes the active
editing layer, not the render default; **Set Render Default** is explicit.

New attributes default to **Face Corner / Byte Color** and opaque white.
Creation offers **Vertex / Float Color** too. Vertex storage shares one value
between adjoining faces; Face Corner supports discontinuities across boundaries.
Byte storage quantizes values; Float storage provides higher precision. No existing
attribute is converted automatically. **Convert Domain / Storage…** is explicit and
may merge corner values or reduce precision.

**Attribute Settings** provides rename, duplicate, render default, conversion,
confirmed deletion, Create Missing on Targets, and Make Single User. Management
requires Object Mode. Rename/duplicate/delete/conversion operate on the active mesh;
Create and Create Missing honor Target. Creation rejects name conflicts rather than
silently editing a suffixed or unrelated attribute.

## Color, selection and shared meshes

- **Write R/G/B/A:** only enabled components change. RGB starts enabled and alpha
  starts disabled. New attributes are nevertheless initialized with alpha 1.
- **Active Object:** edits its mesh datablock. Other objects sharing that mesh also
  change; a warning identifies the mesh user count.
- **Selected Objects:** requires matching attribute names, domains and storage on
  all selected mesh targets. All targets are validated before any fill starts.
  Shared mesh datablocks are edited only once.
- **Create Missing on Targets:** explicitly creates opaque-white matching layers;
  it does not silently convert incompatible existing layers.
- **Make Single User:** copies targeted shared meshes in Object Mode, including
  separate instances when Target is Selected Objects.
- **All Geometry:** intentionally includes hidden elements.
- **Selected Geometry:** uses Edit Mode selection or an enabled Vertex Paint face/
  vertex selection mask. In Object Mode it refuses to guess. Empty selection never
  falls back to filling everything.

In Edit Mode, face selection on Face Corner storage changes only selected face
corners. Vertex storage changes shared selected vertices, which can affect adjacent
faces. Edge selection includes endpoint values/corners. Multi-object Edit Mode uses
the meshes participating in that mode. The tools do not switch modes to edit colors.

## Channel Tools

- **Set / Invert:** operate on Channel; its Write component must be enabled.
- **Copy:** copies Channel into To; the destination Write component must be enabled.
- **Swap:** both components must be enabled.
- **Values: Linear / sRGB:** controls numeric RGB operations and component preview.
  Alpha is always a scalar and is never gamma converted. The native color picker
  remains a color editor using scene-linear color properties, like material colors.
- **Sample First Affected:** loads an actual affected element into Fill Color, not
  an average. For an exact element, select it first. This is not a viewport ray picker.
- **Use Material Base Color:** loads an unlinked constant Base Color from a material
  containing exactly one Principled BSDF. It does not evaluate procedural shaders.
- **Inspect Values / Min–Max:** explicitly scans affected elements and reports
  Uniform/Mixed plus component ranges. It is not a continuous expensive mesh scan.

Byte BMesh layers and mesh RNA use different RGB representations internally; the
tools convert them explicitly so Object and Edit Mode agree. Linear numeric byte
values can differ slightly after quantization.

## Diagnostic preview

Preview is scoped to its 3D Viewport and works in **Solid** shading. It does not
automatically change your shading mode. RGB is unlit and ignores stored alpha;
isolated components are grayscale: black = 0 and white = 1. This is a diagnostic
overlay, not a rendered-material/AgX color match or alpha-transparency preview.
Out-of-range float values are clamped for component display, not in stored data.

The overlay uses evaluated geometry, respects object visibility/local view and
depth testing, and frees temporary evaluated meshes. If modifiers remove the
attribute, the viewport label reports it instead of showing an unrelated layer.
Preview uses Target, but shows the full target surfaces rather than only the edited
selection. Preview settings are temporary and reset on undo/redo, file load and
feature disable. No preview color attributes or materials are created.

Large meshes require a full baseline snapshot during live color editing and GPU
buffers for preview. Use Fill for a one-shot edit when repeated live updates are
too expensive. Thin/coincident surfaces, unusual modifier stacks, X-Ray, wireframe
overlays and other add-ons' draw handlers can require visual checking. Rendered
preview, brush painting, palette management and automatic shader wiring are outside
this section's scope.