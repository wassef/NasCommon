"""The PWA shell's one hard problem: a service worker that must never serve a stale screen.

The worker caches the shell under a version string. If the version did not change when the files
did, a phone would keep an old screen until someone cleared its site data. So the version is a
digest of the files themselves — change any of them and every client refetches on its next load
— and the worker's source carries a placeholder the server stamps it into when it serves it.

It is served from `/`, not `/static/`, because a worker controls only its own path and below; and
never cached itself, because a cached worker cannot be replaced by a newer one.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from pathlib import Path

PLACEHOLDER = "__ASSET_VERSION__"
WORKER_HEADERS = {"Cache-Control": "no-cache", "Service-Worker-Allowed": "/"}
WORKER_MEDIA_TYPE = "application/javascript"


def asset_version(directories: Iterable[Path], *, length: int = 12) -> str:
    """A short digest over every file under `directories` (names and bytes; dotfiles skipped).

    Computed once at start-up by the caller: a deploy restarts the process anyway.
    """
    digest = hashlib.sha256()
    for directory in directories:
        if not directory.exists():
            continue
        for path in sorted(directory.rglob("*")):
            if path.is_file() and not path.name.startswith("."):
                digest.update(path.relative_to(directory).as_posix().encode())
                digest.update(path.read_bytes())
    return digest.hexdigest()[:length]


def render_worker(source: str, version: str) -> str:
    """The worker's source with its version stamped in."""
    return source.replace(PLACEHOLDER, version)
