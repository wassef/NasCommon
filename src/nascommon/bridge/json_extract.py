"""The JSON object inside what a tool-less model actually returns.

`claude -p` has no JSON mode, so an answer that is supposed to be an object arrives wrapped in a
```json fence, with commentary before or after it, or both. Nothing here executes anything: it
finds a brace-balanced object and hands it to `json.loads`.
"""

from __future__ import annotations

import json
import re
from typing import Any

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def extract_json(text: str) -> dict[str, Any]:
    """The first reading of `text` that is a JSON object: whole, fenced, or the first balanced
    `{...}`. `ValueError` when none is — a list or a bare string is not the object asked for."""
    candidates: list[str] = [text.strip()]
    fence = _FENCE_RE.search(text)
    if fence:
        candidates.append(fence.group(1).strip())
    brace = first_balanced_object(text)
    if brace is not None:
        candidates.append(brace)
    for candidate in candidates:
        try:
            value = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    raise ValueError("no parseable JSON object found in response")


def first_balanced_object(text: str) -> str | None:
    """The first brace-balanced `{...}` substring, ignoring braces inside strings."""
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    in_str = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None
