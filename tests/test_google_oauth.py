"""Google OAuth with the library's entry points patched: refresh, write back, bootstrap, and the
token file that must be 0600 and whole."""

from __future__ import annotations

import stat

import google.oauth2.credentials as google_credentials
import google_auth_oauthlib.flow as google_flow
import pytest

from nascommon import google_oauth
from nascommon.google_oauth import NoCredentials, bootstrap, load_credentials, write_token

SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]


class Creds:
    def __init__(self, *, valid=True, expired=False, refresh_token="r"):
        self.valid, self.expired, self.refresh_token = valid, expired, refresh_token
        self.refreshed = False

    def refresh(self, request):
        self.refreshed, self.valid = True, True

    def to_json(self):
        return '{"token": "fresh"}'


def with_file(monkeypatch, tmp_path, creds):
    token = tmp_path / "token.json"
    token.write_text("{}")
    monkeypatch.setattr(
        google_credentials.Credentials,
        "from_authorized_user_file",
        classmethod(lambda cls, path, scopes: creds),
    )
    return token


def test_valid_credentials_are_returned_as_they_are(monkeypatch, tmp_path):
    creds = Creds()
    token = with_file(monkeypatch, tmp_path, creds)
    assert load_credentials(token, SCOPES) is creds and not creds.refreshed
    assert token.read_text() == "{}"


def test_expired_credentials_are_refreshed_and_written_back_0600(monkeypatch, tmp_path):
    creds = Creds(valid=False, expired=True)
    token = with_file(monkeypatch, tmp_path, creds)
    assert load_credentials(token, SCOPES) is creds and creds.refreshed
    assert token.read_text() == '{"token": "fresh"}'
    assert stat.S_IMODE(token.stat().st_mode) == 0o600


def test_a_read_only_mount_keeps_the_refresh_in_memory_and_says_so(monkeypatch, tmp_path):
    creds = Creds(valid=False, expired=True)
    token = with_file(monkeypatch, tmp_path, creds)

    def refuse(path, text):
        raise PermissionError("read-only file system")

    monkeypatch.setattr(google_oauth, "write_token", refuse)
    told = []
    assert load_credentials(token, SCOPES, on_write_error=told.append) is creds
    assert isinstance(told[0], PermissionError)
    quiet = Creds(valid=False, expired=True)
    token = with_file(monkeypatch, tmp_path, quiet)
    assert load_credentials(token, SCOPES) is quiet and quiet.refreshed, "without a listener it stays quiet"


def test_no_token_or_no_refresh_token_asks_for_the_bootstrap(monkeypatch, tmp_path):
    with pytest.raises(NoCredentials, match="run the bootstrap once with"):
        load_credentials(tmp_path / "missing.json", SCOPES, client_secrets=tmp_path / "client.json")
    token = with_file(monkeypatch, tmp_path, Creds(valid=False, expired=True, refresh_token=None))
    with pytest.raises(NoCredentials, match="run the bootstrap once$"):
        load_credentials(token, SCOPES)


class Flow:
    def __init__(self, creds):
        self.creds, self.kwargs = creds, None

    def run_local_server(self, **kwargs):
        self.kwargs = kwargs
        return self.creds


def test_the_bootstrap_forces_consent_and_writes_the_token(monkeypatch, tmp_path):
    secrets = tmp_path / "client.json"
    secrets.write_text("{}")
    flow = Flow(Creds())
    monkeypatch.setattr(
        google_flow.InstalledAppFlow, "from_client_secrets_file", classmethod(lambda cls, path, scopes: flow)
    )
    token = tmp_path / "nested" / "token.json"
    assert bootstrap(secrets, token, SCOPES) is flow.creds
    assert flow.kwargs == {"port": 8765, "access_type": "offline", "prompt": "consent"}
    assert token.read_text() == '{"token": "fresh"}'


def test_a_bootstrap_without_secrets_or_without_a_refresh_token_is_refused(monkeypatch, tmp_path):
    with pytest.raises(FileNotFoundError, match="Desktop app"):
        bootstrap(tmp_path / "missing.json", tmp_path / "token.json", SCOPES)
    secrets = tmp_path / "client.json"
    secrets.write_text("{}")
    monkeypatch.setattr(
        google_flow.InstalledAppFlow,
        "from_client_secrets_file",
        classmethod(lambda cls, path, scopes: Flow(Creds(refresh_token=None))),
    )
    with pytest.raises(NoCredentials, match="revoke the app"):
        bootstrap(secrets, tmp_path / "token.json", SCOPES)
    assert not (tmp_path / "token.json").exists()


def test_a_write_cut_short_leaves_the_old_token_and_no_temp_file(monkeypatch, tmp_path):
    token = tmp_path / "token.json"
    token.write_text("old")

    def crash(src, dst):
        raise OSError("disk gone")

    monkeypatch.setattr(google_oauth.os, "replace", crash)
    with pytest.raises(OSError, match="disk gone"):
        write_token(token, "new")
    assert token.read_text() == "old"
    assert [p.name for p in tmp_path.iterdir()] == ["token.json"]
