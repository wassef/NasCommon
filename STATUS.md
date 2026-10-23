---
status_version: 1
phase: operate
health: amber
health_note: "No remote yet: two of the three consumers cannot take the package until it is published"
milestone: "v0.1.0 published and consumed by all three NAS apps"
due: ""
updated: 2026-10-23
---
## Now
- v0.1.0 (signed tag, 82 tests, 100 % line and branch coverage): auth, web, bridge, webpush, google_oauth,
  scheduling, pwa.
- Asturlab consumes it as a vendored wheel (merged on `audit-4`, live on NAS stack 48).
- Adopted Project Standard v1: CLAUDE.md, STATUS.md, Claude settings, `hub hygiene` in pre-commit, tests on pre-push.

## Next
- Publish: create the GitHub remote (public, as the README and the consumers' tarball pins assume) and push
  `main` plus `v0.1.0`.
- Then merge the `nascommon` branches of Job-Search and Local-Ai-App and rebuild their images.

## Blocked / risks
- Publication is the owner's call (remote and visibility).

## Recent
- 2026-10-23 · Adopted Project Standard v1
- 2026-09-24 · v0.1.0 tagged; vendored into Asturlab (plan WP9)
- 2026-09-23 · Package built from what three NAS apps kept copying
