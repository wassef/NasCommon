# NasCommon — the shared Python package of the NAS apps: auth, web, Claude-bridge client, Web Push, Google OAuth, scheduling, PWA shell

Registry id: `nascommon` · State: @STATUS.md

## Context
- Runs on: nowhere by itself; a library imported inside the NAS apps' containers (Python ≥ 3.11, CI tests
  3.11 and 3.12) · Depends on: nothing at import time; extras `bridge` (httpx), `push` (pywebpush), `google`
  (google-auth), `scheduling` (APScheduler 3) · Talks to, through its consumers: MacServices `claude_bridge`
  (contract in `MacServices/docs/consumers.md`).
- Used by: asturlab (wheel in its `vendor/`, merged on `audit-4`); job-search and local-ai-app have unmerged
  `nascommon` branches that pin the `v0.1.0` tarball from GitHub.

## Commands
- Setup: `uv sync` · Test: `uv run pytest --cov` (100 % line and branch is the gate) · Lint:
  `uv run ruff check . && uv run ruff format --check .`
- Gate: `pre-commit run --all-files` (gitleaks, `hub hygiene .`, ruff check and format, the repo hygiene test);
  the pre-push hook runs the tests with coverage. CI `ci.yml`: 3.11 + 3.12, the bare wheel builds and imports
  with no extras, gitleaks on the full history.
- Release: bump `version` in `pyproject.toml`, signed tag `git tag -s vX.Y.Z`; then Asturlab:
  `bin/vendor.sh ~/WorkSpace/Asturlab vX.Y.Z` and `uv lock --refresh-package nascommon` there; the other two
  bump the tag in their tarball URL.
- Deploy: none here; consumers redeploy through their own `deploy-nas`.

## Docs map
- No nested CLAUDE.md: one package, one stack.
- `README.md` — the module table and the lesson each module carries (the design record)
- `bin/vendor.sh` — builds a wheel from a tag, never the working tree, for consumers that install offline
- `docs/adr/` — decisions · `.claude/plans/` — plans (gitignored: the tree is meant to go public) · `STATUS.md`

## Conventions (deltas from the global rules only)
- Zero import-time dependencies: a module that talks to the outside world pulls its library through an
  extra, and CI proves the bare wheel imports. A new module with a new library gets a new extra.
- Coverage stays at 100 % (`fail_under = 100`); every test is offline (httpx `MockTransport`, a stubbed
  pywebpush, patched Google entry points).
- Python 3.11 is supported (`requires-python >= 3.11`, ruff `target-version = py311`): no 3.12-only syntax.
- The tree is public-ready: `tests/test_repo_hygiene.py` keeps home paths, tailnet addresses, hostnames and
  tokens out without the hub.
- A public API change is an interface change: new semver tag, `hub log nascommon interface "..."`, and a check
  of `used by` in `hub show nascommon`.
- A behaviour fix adds or edits its line in the README's "Lesson built in" column.

## Gotchas
- Asturlab's container runs `uv sync --frozen` with no git in the image: it consumes only the vendored wheel,
  never a git URL.
- The Job-Search and Local-Ai-App `nascommon` branches pin the public `v0.1.0` tarball; merging one means an
  image rebuild there (its pip list lives in the compose), so their checkouts stay on their default branch until
  that deploy is planned, because their deploy scripts rsync the working tree.
- `scheduling.Schedule(tz)` exists because a bare `CronTrigger` in a UTC container fires hours late; consumers
  never build triggers by hand.
- `pytest --cov` writes `.coverage` at the root (ignored).

## Done means
- `uv run pytest --cov` at 100 % and `pre-commit run --all-files` green · an API change tagged and journaled ·
  STATUS.md updated when the change is meaningful · signed commit (and signed tag for a release), no AI
  trailers · pushed, CI green (public repo: github.com/wassef/NasCommon)
