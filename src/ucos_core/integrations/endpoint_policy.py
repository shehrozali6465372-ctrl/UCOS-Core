"""Shared strict URL policy for the Agent 01 model endpoint."""

from urllib.parse import urlsplit


def is_safe_analysis_base_url(value: str, *, production: bool) -> bool:
    """Return whether a model endpoint URL is structurally safe for this environment.

    This validates URL syntax and transport policy only. It does not validate DNS
    resolution or establish a network-level SSRF boundary.
    """
    if not value or any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in value):
        return False
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError:
        return False

    local_http = parsed.scheme == "http" and hostname in {
        "localhost",
        "127.0.0.1",
        "::1",
    }
    return bool(
        hostname
        and (parsed.scheme == "https" or (local_http and not production))
        and parsed.username is None
        and parsed.password is None
        and not parsed.query
        and not parsed.fragment
        and port != 0
    )
