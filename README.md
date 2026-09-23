# NasCommon

The pieces three self-hosted apps kept copying from each other, lifted into one small,
tested package.

The apps run on a Synology NAS behind Tailscale: a job-search pipeline, a media transcriber and a
personal "life compass". Each has a browser-facing PWA, a JSON API a script may drive, and calls
out to a Mac that hosts the GPU and the Claude CLI (see
[MacServices](https://github.com/wassef/MacServices)). Each had grown its own copy of the same
auth check, the same Claude-bridge client, the same Web Push sender, the same scheduler
boilerplate — and each copy had learned a different lesson the others had not. This package is
the copy that learned all of them.

```
            ┌───────────── NAS (Docker, Tailscale sidecar) ─────────────┐
 phone ───► │  app (FastAPI + APScheduler + PWA)                          │ ───► Mac: claude_bridge,
  (tailnet) │    nascommon.web      CSRF, security headers, tailnet check │      whisper, embed …
            │    nascommon.auth     X-Api-Key in, X-Service-Key out  ─────┼───►  (X-Service-Key)
            │    nascommon.bridge   client, limits, usage, one-line worker│
            │    nascommon.webpush  VAPID send, subscription check  ──────┼───► FCM / Mozilla / Apple
            │    nascommon.scheduling  zone-safe cron, windows, grace     │
            │    nascommon.google_oauth  headless refresh, 0600 tokens ───┼───► Google APIs
            │    nascommon.pwa      service-worker cache busting          │
            └─────────────────────────────────────────────────────────────┘
```

## What each module is for

| Module | What it does | Lesson built in |
|---|---|---|
| `auth` | `inbound_verdict` for an `X-Api-Key` surface; `service_headers` for the Mac services | A key that is *not configured* refuses everything (503) rather than silently opening the API |
| `web` | `security_headers`, `csrf_verdict`, `outside_tailnet` | Origins are compared by host name: a proxy that forwards `$host` drops the port the browser keeps |
| `bridge.client` | Async client for the tool-less `claude -p` bridge | Never post while `busy`; only connect errors, 503 and 504 are worth a retry |
| `bridge.limits` | Tells a usage limit from any other failure, and when it resets | A limit arrives as HTTP 502 with the CLI's stderr; the same words in a CV are not a limit |
| `bridge.json_extract` | The JSON object inside a model's prose and fences | A list or a bare string is not the object asked for |
| `bridge.usage` | A 60 s cache over `/usage` | A failed fetch is cached too, so a sleeping Mac costs one timeout a minute |
| `bridge.worker` | One line in front of the bridge: priorities, no key twice, a hold | Two reactions that both saw the bridge free must not both post |
| `webpush` | `send_one` → `(ok, gone, error)`; `subscription_from` | pywebpush's default TTL of 0 drops a message to a phone in Doze; 401/403 means re-subscribe |
| `google_oauth` | Consent once on a laptop, silent refresh on the server | `prompt=consent`, or a re-grant returns no refresh token; tokens written 0600, atomically |
| `scheduling` | `Schedule(tz)`: `cron`, `cron_at`, `interval`, `window`, `scheduler` | A bare `CronTrigger` in a UTC container fires two hours late in summer; a hibernating NAS needs grace |
| `pwa` | `asset_version` (digest of the shell), `render_worker`, `WORKER_HEADERS` | A cached worker can never be replaced; a version that does not move with the files serves stale screens |

## Install

Nothing is needed to import the package; each module that talks to the outside world pulls its
library in through an extra:

```
pip install "nascommon[bridge,push,google,scheduling] @ git+https://github.com/wassef/NasCommon@v0.1.0"
```

A consumer that must install offline (a container that runs `uv sync --frozen` at start-up, with
no `git` in its image) can carry the wheel instead: `bin/vendor.sh <consumer repo>` builds it
from a tag and drops it into the consumer's `vendor/`.

## Develop

```
uv sync
uv run pytest --cov          # 100 % line and branch coverage is the gate
uv run ruff check . && uv run ruff format --check .
```

Every test runs offline: httpx's `MockTransport` for the bridge, a stubbed `pywebpush`, patched
Google entry points. `tests/test_repo_hygiene.py` keeps home paths, tailnet addresses and tokens
out of the tree, and gitleaks runs in pre-commit and CI.

## License

MIT
