"""Shared syntax validation for untrusted research citation URLs."""

from urllib.parse import urlsplit


def is_valid_evidence_url(value: object) -> bool:
    """Return whether a citation URL has a valid, credential-free HTTP(S) authority.

    This function validates string syntax only. It does not fetch the URL or
    provide DNS/IP, redirect-chain, or network-egress SSRF protection.
    """
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 2048
        or any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in value)
        or "\\" in value
    ):
        return False
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
        port = parsed.port
        authority = parsed.netloc.rsplit("@", maxsplit=1)[-1]
    except ValueError:
        return False
    return bool(
        parsed.scheme in {"http", "https"}
        and hostname
        and parsed.username is None
        and parsed.password is None
        and not authority.endswith(":")
        and not authority.startswith(":")
        and port != 0
    )
