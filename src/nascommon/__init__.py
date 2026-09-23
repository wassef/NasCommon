"""NasCommon: what three NAS-hosted apps kept copying from each other.

Each module stands alone and imports its third-party library only through its extra:
`auth`, `web`, `pwa` and `bridge` (bar its client) need nothing; `bridge.client` needs
`nascommon[bridge]`, `webpush` needs `[push]`, `google_oauth` needs `[google]`, `scheduling`
needs `[scheduling]`.
"""

__version__ = "0.1.0"
