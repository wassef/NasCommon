"""Google OAuth for an app that runs headless: one consent on a laptop, silent refreshes after.

The consent flow runs once where there is a browser (`bootstrap`), writes a token file, and that
file is copied to the server, which refreshes it on its own (`load_credentials`). Two lessons are
built in:

* `prompt=consent` on every bootstrap. Re-authorising a grant Google already has returns an
  access token with no refresh token, which dies within the hour. And a consent screen left in
  **Testing** kills the refresh token after seven days: set it to **In production**.
* The token is written 0600 and all or nothing. Written 0644 it was readable by every account on
  the NAS; a write cut short by a restart left half a JSON document no refresh could read again.
  A read-only mount is fine: the refreshed token lives in memory for the process's lifetime.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

BOOTSTRAP_PORT = 8765


class NoCredentials(RuntimeError):
    """No usable token: the bootstrap has to be run (again)."""


def load_credentials(
    token_file: Path,
    scopes: Sequence[str],
    *,
    client_secrets: Path | None = None,
    on_refresh: Callable[[], None] | None = None,
    on_write_error: Callable[[OSError], None] | None = None,
) -> Any:
    """Valid credentials from `token_file`, refreshed and written back when they had expired.

    `on_refresh` is told after a refresh was written back, `on_write_error` when it could not be:
    the caller's log says which, where this module logs nothing of its own.
    """
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    creds = (
        Credentials.from_authorized_user_file(str(token_file), list(scopes)) if token_file.exists() else None
    )
    if creds and creds.valid:
        return creds
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        try:
            write_token(token_file, creds.to_json())
        except OSError as exc:  # a read-only mount: refreshed in memory for this process
            if on_write_error is not None:
                on_write_error(exc)
        else:
            if on_refresh is not None:
                on_refresh()
        return creds
    where = f" with {client_secrets}" if client_secrets else ""
    raise NoCredentials(f"no valid Google credentials in {token_file}; run the bootstrap once{where}")


def bootstrap(
    client_secrets: Path, token_file: Path, scopes: Sequence[str], *, port: int = BOOTSTRAP_PORT
) -> Any:
    """The consent flow, in a browser on this machine, once. Returns the credentials it wrote."""
    from google_auth_oauthlib.flow import InstalledAppFlow

    if not client_secrets.exists():
        raise FileNotFoundError(
            f"missing OAuth client secrets at {client_secrets} "
            "(Cloud Console → APIs & Services → Credentials → OAuth client, Desktop app → Download JSON)"
        )
    flow = InstalledAppFlow.from_client_secrets_file(str(client_secrets), list(scopes))
    creds = flow.run_local_server(port=port, access_type="offline", prompt="consent")
    if not creds.refresh_token:
        raise NoCredentials(
            "Google returned no refresh_token, so the token would die within the hour; revoke the app "
            "at https://myaccount.google.com/permissions and run the bootstrap again"
        )
    token_file.parent.mkdir(parents=True, exist_ok=True)
    write_token(token_file, creds.to_json())
    return creds


def write_token(token_file: Path, text: str) -> None:
    """Write `text` to `token_file` 0600, atomically: a temp file beside it, then a rename."""
    fd, tmp = tempfile.mkstemp(dir=token_file.parent, prefix=f".{token_file.name}.", suffix=".tmp")
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, token_file)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
