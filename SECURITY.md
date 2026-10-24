# Security and privacy

## Reporting vulnerabilities

Do not post exploit details, credentials, proprietary .blend files, or sensitive
logs in public issues. If GitHub shows **Security > Report a vulnerability** for
this repository, use that private reporting channel. Its availability depends on
the maintainer enabling private vulnerability reporting in repository settings.

If that option is unavailable, open a public issue containing only a request for
a private contact channel, with no vulnerability details, and wait for the
maintainer to establish one. No private email address or response-time guarantee
is currently published by this repository.

Include the affected commit/version, Blender version, OS, impact, and a minimal
reproduction in the private report. Security fixes target the current development
version; older releases have no guaranteed maintenance window.

## Trust boundaries

- Script Runner executes the chosen Python file with Blender's process permissions.
  It is not a sandbox. A script can access files, launch programs, or use the network.
- Pie menu commands can also execute configured Python. Review commands before use.
- The optional Painter bridge sends Python to Painter's remote-scripting endpoint
  over loopback (`127.0.0.1` or `::1`). It can launch Painter and write exported
  meshes, job JSON, projects, and textures to the selected output directory.
  Do not expose remote scripting through port forwarding or to untrusted networks.
- Bake/material operations can replace integration-owned material graphs and, when
  explicitly enabled, existing material slots. Back up work before using them.
- The reviewed runtime has no analytics or automatic update downloader. This is
  not a restriction on user-selected scripts or on Blender/Painter themselves.
- Logs and job manifests may contain absolute file paths and object/project names.
  Review and redact them before sharing.