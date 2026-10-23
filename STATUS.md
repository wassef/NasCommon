---
status_version: 1
phase: operate
health: green
health_note: ""
milestone: "Consumed from the public tag by all three NAS apps"
due: ""
updated: 2026-10-23
---
## Now
- Public at github.com/wassef/NasCommon since 2026-10-23: `main` and the signed `v0.1.0` (82 tests, 100 % line
  and branch coverage; CI green on 3.11 and 3.12 with full-history gitleaks).
- Asturlab consumes it as a vendored wheel (live on NAS stack 48).
- Adopted Project Standard v1.

## Next
- Merge the `nascommon` branches of Job-Search and Local-Ai-App (they pin the public `v0.1.0` tarball), each with
  its image rebuild and a deploy.
- Pin it on the GitHub profile next to MacServices.

## Blocked / risks
- None.

## Recent
- 2026-10-23 · Published (public); first CI run green; adopted Project Standard v1; CI action pins fixed
- 2026-09-24 · v0.1.0 tagged; vendored into Asturlab (plan WP9)
- 2026-09-23 · Package built from what three NAS apps kept copying
