"""SSRF guard for user-supplied URLs (feed URLs and article URLs).

Two layers of protection:

1. `is_safe_url` — cheap parse-time check used when operators add a source. It
   rejects non-http(s) URLs, URLs with credentials, and any host that resolves to
   a private / loopback / link-local / reserved address. Unresolvable hosts are
   rejected (fail closed).

2. `safe_fetch` — used when fetching article content (untrusted URLs from feeds).
   It resolves the host up front, pins the connection to that IP (so DNS rebinding
   cannot redirect the socket to an internal address), validates *every* redirect
   hop against the same blocklist, and never follows redirects automatically.
"""

import dataclasses
import http.client
import ipaddress
import socket
import ssl
import urllib.parse
from typing import List, Tuple

# Address ranges that must never be fetched from an untrusted URL.
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

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (compatible; NewsIntelligence/0.1; +https://github.com/news-intelligence)"
)


@dataclasses.dataclass
class FetchResult:
    status: int
    headers: List[Tuple[str, str]]
    body: bytes
    final_url: str


def _ip_is_blocked(addr: str) -> bool:
    try:
        ip = ipaddress.ip_address(addr)
    except ValueError:
        return False
    if (
        ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_unspecified
        or ip.is_private
    ):
        return True
    return any(ip in net for net in _BLOCKED_NETWORKS)


def _host_is_safe(hostname: str) -> bool:
    """Resolve `hostname` and reject it if any address is blocked.

    Returns False on resolution failure (fail closed: an unresolvable host is not
    provably safe to fetch).
    """
    try:
        infos = socket.getaddrinfo(hostname, None)
    except Exception:
        return False
    for info in infos:
        if _ip_is_blocked(info[4][0]):
            return False
    return True


def is_safe_url(url: str | None) -> bool:
    """Parse-time check for operator-supplied URLs (e.g. news sources).

    Rejects non-http(s), credentialed URLs, and hosts that resolve to a blocked
    address. Unresolvable hosts are rejected (fail closed): a host we cannot
    prove is safe must not be fetched.
    """
    if not url:
        return False
    try:
        parsed = urllib.parse.urlparse(url)
    except Exception:
        return False
    if parsed.scheme not in ("http", "https"):
        return False
    if parsed.username or parsed.password:
        return False
    if not parsed.hostname:
        return False
    try:
        infos = socket.getaddrinfo(parsed.hostname, None)
    except Exception:
        return False
    for info in infos:
        if _ip_is_blocked(info[4][0]):
            return False
    return True


def safe_fetch(
    url: str,
    *,
    timeout: float = 15.0,
    max_redirects: int = 5,
    max_size: int = 5_000_000,
    user_agent: str = DEFAULT_USER_AGENT,
) -> FetchResult:
    """Fetch a URL with SSRF protection.

    - Validates the host against the blocklist on every hop.
    - Pins the TCP/TLS connection to the pre-resolved IP (defeats DNS rebinding).
    - Does NOT follow redirects automatically; each Location is re-validated.
    """
    current = url
    for _ in range(max_redirects + 1):
        parsed = urllib.parse.urlparse(current)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            raise ValueError(f"unsupported URL: {current}")
        if not _host_is_safe(parsed.hostname):
            raise ValueError(f"blocked host: {parsed.hostname}")

        try:
            infos = socket.getaddrinfo(parsed.hostname, None)
        except Exception as e:
            raise ValueError(f"unresolved host: {parsed.hostname} ({e})")
        ip = next(
            (info[4][0] for info in infos if not _ip_is_blocked(info[4][0])), None
        )
        if ip is None:
            raise ValueError(f"no safe address for host: {parsed.hostname}")

        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        path = parsed.path or "/"
        if parsed.query:
            path += "?" + parsed.query

        try:
            if parsed.scheme == "https":
                ctx = ssl.create_default_context()
                raw = socket.create_connection((ip, port), timeout=timeout)
                ssock = ctx.wrap_socket(raw, server_hostname=parsed.hostname)
                conn = http.client.HTTPSConnection(parsed.hostname, port, timeout=timeout)
                conn.sock = ssock
            else:
                raw = socket.create_connection((ip, port), timeout=timeout)
                conn = http.client.HTTPConnection(parsed.hostname, port, timeout=timeout)
                conn.sock = raw
            conn.request(
                "GET",
                path,
                headers={"Host": parsed.hostname, "User-Agent": user_agent},
            )
            resp = conn.getresponse()
        except (socket.timeout, ssl.SSLError, OSError) as e:
            raise ValueError(f"connection failed: {e}")

        if resp.status in (301, 302, 303, 307, 308):
            location = resp.getheader("Location")
            resp.read()
            conn.close()
            if not location:
                raise ValueError("redirect with no Location header")
            current = urllib.parse.urljoin(current, location)
            continue

        body = resp.read(max_size)
        conn.close()
        return FetchResult(
            status=resp.status, headers=resp.getheaders(), body=body, final_url=current
        )

    raise ValueError("too many redirects")
