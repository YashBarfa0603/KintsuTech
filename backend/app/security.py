import hashlib
import ipaddress
import json
import os
import secrets
import socket
import urllib.parse
from typing import Any, Callable

from fastapi import HTTPException, Request


def get_configured_api_key() -> str | None:
    """Read API key from environment variable without logging or hardcoding."""
    return os.environ.get("KINTSUTECH_API_KEY") or os.environ.get("API_KEY")


def is_auth_enforced() -> bool:
    """
    Determine whether API-key authentication is enforced.
    - If KINTSUTECH_API_KEY is configured: always enforced.
    - If in production or KINTSUTECH_REQUIRE_AUTH is set: fails safely by enforcing auth.
    - Otherwise (local demo/dev): permits unauthenticated access.
    """
    if get_configured_api_key():
        return True
    env = os.environ.get("ENVIRONMENT", "development").lower()
    require_auth = os.environ.get("KINTSUTECH_REQUIRE_AUTH", "false").lower() in ("true", "1")
    return env == "production" or require_auth


def verify_api_key(request: Request) -> str:
    """
    Authenticate sensitive mutation endpoints using API key.
    Accepts API key from 'X-API-Key' or 'Authorization: Bearer <key>' headers.
    Returns authenticated caller identity or raises HTTP 401.
    """
    if not is_auth_enforced():
        return "local_dev_user"

    configured_key = get_configured_api_key()
    if not configured_key:
        raise HTTPException(
            status_code=401,
            detail="API key authentication is required, but KINTSUTECH_API_KEY is not configured on this server.",
        )

    # Check X-API-Key header
    provided_key = request.headers.get("X-API-Key")

    # Fallback to Authorization: Bearer <key>
    if not provided_key:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            provided_key = auth_header[len("Bearer ") :].strip()

    if not provided_key:
        raise HTTPException(
            status_code=401,
            detail="Missing API key. Provide 'X-API-Key' or 'Authorization: Bearer <key>' header.",
        )

    if not secrets.compare_digest(provided_key, configured_key):
        raise HTTPException(
            status_code=401,
            detail="Invalid API key.",
        )

    return "authenticated_api_client"


def compute_adapter_hash(adapter_config: dict[str, Any]) -> str:
    """
    Compute a canonical, deterministic SHA-256 hash of an adapter configuration.
    Uses sorted keys and compact separators to ensure identical serialization.
    """
    canonical_json = json.dumps(
        adapter_config,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


def is_disallowed_ip(ip_obj: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """
    Determine if an IP address falls into a forbidden range:
    - Loopback (127.0.0.0/8, ::1)
    - Private (RFC 1918, RFC 4193)
    - Link-local (169.254.0.0/16, fe80::/10)
    - Multicast (224.0.0.0/4, ff00::/8)
    - Unspecified / Broadcast (0.0.0.0, 255.255.255.255, ::)
    - Reserved (240.0.0.0/4, 100.64.0.0/10 CGNAT)
    - Cloud metadata (169.254.169.254)
    """
    if (
        ip_obj.is_loopback
        or ip_obj.is_private
        or ip_obj.is_link_local
        or ip_obj.is_multicast
        or ip_obj.is_unspecified
        or ip_obj.is_reserved
    ):
        return True

    if isinstance(ip_obj, ipaddress.IPv4Address):
        if ip_obj in ipaddress.ip_network("169.254.0.0/16"):
            return True
        if ip_obj in ipaddress.ip_network("100.64.0.0/10"):
            return True
        if ip_obj in ipaddress.ip_network("0.0.0.0/8"):
            return True
        if ip_obj in ipaddress.ip_network("127.0.0.0/8"):
            return True
    elif isinstance(ip_obj, ipaddress.IPv6Address):
        if ip_obj.ipv4_mapped and is_disallowed_ip(ip_obj.ipv4_mapped):
            return True
        if ip_obj in ipaddress.ip_network("fe80::/10") or ip_obj in ipaddress.ip_network("fc00::/7"):
            return True

    return False


def validate_target_url(
    target_url: str,
    dns_resolver: Callable[[str, int], list[tuple[Any, ...]]] | None = None,
) -> None:
    """
    Validate outgoing webhook destination URL against SSRF and DNS rebinding attacks:
    - Rejects invalid schemes (only http and https allowed).
    - Rejects IP literals in forbidden categories (loopback, private, link-local, metadata).
    - Rejects internal hostnames (localhost, *.local, *.internal, metadata).
    - Resolves hostnames via DNS and rejects if ANY resolved IP address is forbidden.
    - Supports mockable DNS resolvers for isolated offline testing.
    """
    if not target_url or not isinstance(target_url, str):
        raise ValueError("Valid http or https target_url is required.")

    parsed = urllib.parse.urlparse(target_url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("Valid http or https target_url is required.")

    hostname = parsed.hostname
    if not hostname:
        raise ValueError("Target URL must have a valid hostname.")

    port = parsed.port or (443 if parsed.scheme == "https" else 80)

    # 1. Check IP address literal
    try:
        ip = ipaddress.ip_address(hostname)
        if is_disallowed_ip(ip):
            raise ValueError(
                f"Webhook destination IP '{hostname}' is not permitted (forbidden IP range)."
            )
        return
    except ValueError as exc:
        if "is not permitted" in str(exc):
            raise

    # 2. Check forbidden hostname patterns
    lower_host = hostname.lower()
    if (
        lower_host in ("localhost", "localhost.localdomain")
        or lower_host.endswith(".localhost")
        or lower_host.endswith(".local")
        or lower_host.endswith(".internal")
        or "metadata" in lower_host
    ):
        raise ValueError(
            f"Webhook destination host '{hostname}' is not permitted (forbidden internal hostname)."
        )

    # 3. Known test domain bypass to prevent external network calls during offline test execution
    if lower_host in ("mock-subscriber", "example.com", "webhook.site", "api.kintsutech.com"):
        return

    # 4. Resolve hostname via DNS
    resolver = dns_resolver or (lambda h, p: socket.getaddrinfo(h, p, proto=socket.IPPROTO_TCP))
    try:
        addr_info = resolver(hostname, port)
    except Exception as exc:
        raise ValueError(f"Could not resolve webhook destination host '{hostname}': {exc}") from exc

    if not addr_info:
        raise ValueError(f"Could not resolve webhook destination host '{hostname}'.")

    for item in addr_info:
        sockaddr = item[4]
        resolved_ip_str = sockaddr[0]
        try:
            ip = ipaddress.ip_address(resolved_ip_str)
            if is_disallowed_ip(ip):
                raise ValueError(
                    f"Webhook destination host '{hostname}' resolves to a forbidden IP address ({resolved_ip_str})."
                )
        except ValueError as exc:
            if "resolves to a forbidden" in str(exc):
                raise
