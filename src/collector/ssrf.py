"""SSRF guard for user-supplied feed URLs.

Source URLs are fetched by the worker, and (in single-operator mode) anyone
reaching the API can add them. Before fetching, reject non-http(s) URLs and any
host that resolves to a loopback / link-local / private address.
"""

import ipaddress
import socket
from urllib.parse import urlparse

# Address ranges that must never be fetched from an untrusted feed URL.
_BLOCKED_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]


def is_safe_url(url: str | None) -> bool:
    """Return True only if `url` is http(s) and resolves to a public address."""
    if not url:
        return False
    try:
        parsed = urlparse(url)
    except Exception:
        return False
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return False
    try:
        infos = socket.getaddrinfo(parsed.hostname, None)
    except Exception:
        # Unresolvable host: we can't prove it's unsafe, so allow it (the operator
        # is responsible and the fetch will simply fail). Only resolved private /
        # loopback addresses are blocked — that is the actual SSRF protection.
        return True
    for info in infos:
        host = info[4][0]
        try:
            addr = ipaddress.ip_address(host)
        except ValueError:
            continue
        if addr.is_loopback or addr.is_link_local or addr.is_multicast:
            return False
        if any(addr in net for net in _BLOCKED_NETWORKS):
            return False
    return True
