"""URL helpers shared by settings, storage, and ad-hoc input."""
from __future__ import annotations

from urllib.parse import urlparse


def is_http_url(value: str) -> bool:
    """Return True only for syntactically valid http/https URLs with a host."""
    if not isinstance(value, str):
        return False
    s = value.strip()
    if not s or any(ch.isspace() for ch in s):
        return False
    try:
        parsed = urlparse(s)
        host = parsed.hostname
    except ValueError:
        return False
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc and host)


def normalize_http_url(raw: str) -> str | None:
    """Normalize user input to an http/https URL, or return None if invalid."""
    s = raw.strip()
    if not s:
        return None
    if not s.startswith(("http://", "https://")):
        s = "https://" + s
    return s if is_http_url(s) else None


def url_host_label(url: str) -> str:
    """Return the host label used as a human-readable result name."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return url
    return parsed.netloc or url
