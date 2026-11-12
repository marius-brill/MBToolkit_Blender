# Maintaining and publishing this wiki

[Asset Processor home](README.md)

## Source of truth

The repository Markdown is authoritative. A future Notion wiki should be a
published copy, not a second independently maintained manual. Update documentation
alongside user-visible code changes, review it in the same change, then refresh
the published copy deliberately. No synchronization service is configured here.

These pages describe current checkout behavior. For a release, record which
add-on/Blender versions were actually checked; do not imply an unreleased feature
is available in an older ZIP. Avoid invented test dates or verification claims.

## Page conventions

- One topic and one top-level heading per file; begin with a home link.
- Use ordinary Markdown headings, lists, blockquotes, fenced code and simple tables.
- Link to sibling pages with relative paths. Keep essential content in text, not
  only in screenshots. Avoid custom HTML, proprietary callouts and plugin syntax.
- Use exact UI labels. Separate expected behavior, known limitations and future ideas.
- For procedures, explain prerequisites, steps, expected results and preservation risks.
- Link specialist material instead of copying it across several guides.
- Use absolute paths in executable examples; explain machine-specific values.

## Screenshots

Store real captured images in the `images` folder next to these pages when available.
Use descriptive filenames and alt text, crop irrelevant UI, and remove private paths
and assets. Capture the UI state that the instructions describe. Do not add broken
image links or fabricated screenshots merely to fill a layout.

Useful first captures: Model asset/component overview, a generated pair in Inspector,
an Assisted UV proposal beside its working low, and the Export result folder.
The current guide is text-complete and does not require images to follow it.

## Future Notion publication checklist

This is a publishing checklist, not a guaranteed automatic conversion procedure:

1. Review Notion's import capabilities at publication time.
2. Test a representative Markdown page containing a table, image and relative links.
3. Publish the landing page as the parent and map each guide to a child page.
4. Upload/verify images and repair cross-page links as needed after import.
5. Check headings, tables, warnings and code blocks in the resulting pages.
6. Add a source-repository reference and identify the release/commit being published.
7. Repeat from reviewed Markdown for updates; avoid untracked edits only in Notion.

Use manual publishing initially. Only introduce one-way automation if repeat
publishing becomes costly; decide how page identity, images and removed pages are
handled before implementing it.

## Review checklist

- Follow [quick start](quick-start.md) in a disposable UI session when behavior changes.
- Verify labels/defaults against settings and drawing code, not old release notes alone.
- Check low preservation, custom-high ownership and group-wide UV approval wording.
- Update troubleshooting for new guards or failure reports.
- Run the repository tests: they check wiki page presence and relative file links.
  Anchor targets, screenshot accuracy and Notion conversion still need manual review.
- Keep historical implementation notes marked as such; do not silently copy their
  superseded limits into the current reference.