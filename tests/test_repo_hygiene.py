"""The tree may go public: no secret, home path, tailnet address or hostname in it, ever."""

from __future__ import annotations

import os
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SKIP_DIRS = {".git", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache", "htmlcov", "dist", ".claude"}
SKIP_FILES = {"uv.lock", ".git", Path(__file__).name}
FORBIDDEN = [
    # Spelled as an alternation so this file does not contain what it looks for.
    (re.compile(r"/(?:Users|home)/[A-Za-z0-9._-]+"), "absolute home path"),
    # CGNAT 100.64.0.0/10 is where tailnet addresses live; the range itself and 100.64.0.1, the
    # documentation example, may be written down.
    (
        re.compile(
            r"\b100\.(6[4-9]|[7-9]\d|1[01]\d|12[0-7])\.\d{1,3}\.\d{1,3}\b(?<!100\.64\.0\.1)(?<!100\.64\.0\.0/10)(?<!100\.64\.0\.0)"
        ),
        "tailnet IP",
    ),
    (re.compile(r"\b(?!example\b)[a-z0-9-]+\.ts\.net\b"), "tailnet hostname"),
    (re.compile(r"\b(gho|ghp|ghu|ghs)_[A-Za-z0-9]{20,}"), "GitHub token"),
    (re.compile(r"sk-ant-[A-Za-z0-9-]{10,}"), "Anthropic API key"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "private key"),
]


def files() -> list[Path]:
    found = []
    for root, dirs, names in os.walk(REPO):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        found.extend(Path(root) / n for n in names if n not in SKIP_FILES)
    return found


def test_nothing_personal_or_secret_in_the_tree():
    offenders = []
    for path in files():
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            for pattern, what in FORBIDDEN:
                if pattern.search(line):
                    offenders.append(f"{path.relative_to(REPO)}:{lineno}: {what}")
    assert offenders == [], "\n".join(offenders)
