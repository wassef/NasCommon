"""The MacServices claude_bridge: its client, its usage readout, and reading what it answers.

`limits`, `json_extract`, `errors` and `worker` import nothing outside the standard library;
`client` and `usage`'s consumer need the `bridge` extra (httpx).
"""

from .errors import BridgeBusy, BridgeError, BridgeRejected, BridgeUnavailable, LimitReached
from .json_extract import extract_json, first_balanced_object
from .limits import is_limit_message, is_limit_text, parse_reset
from .usage import UsageCache
from .worker import BridgeWorker

__all__ = [
    "BridgeBusy",
    "BridgeError",
    "BridgeRejected",
    "BridgeUnavailable",
    "BridgeWorker",
    "LimitReached",
    "UsageCache",
    "extract_json",
    "first_balanced_object",
    "is_limit_message",
    "is_limit_text",
    "parse_reset",
]
