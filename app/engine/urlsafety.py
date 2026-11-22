"""Guards partner webhook URLs against being pointed at our own network (SSRF)."""
import ipaddress
import socket
from urllib.parse import urlparse


def is_safe_webhook_url(url: str, allow_insecure: bool = False, resolver=socket.getaddrinfo):
    """Returns (ok, reason). https only, and the host must resolve to public addresses."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return False, "not a valid URL"
    if parsed.scheme != "https" and not (allow_insecure and parsed.scheme == "http"):
        return False, "webhook URL must use https"
    host = parsed.hostname
    if not host:
        return False, "webhook URL has no host"
    if parsed.username or parsed.password:
        return False, "webhook URL must not contain credentials"
    try:
        infos = resolver(host, parsed.port or (443 if parsed.scheme == "https" else 80))
    except OSError:
        return False, "webhook host could not be resolved"
    for info in infos:
        ip = ipaddress.ip_address(str(info[4][0]).split("%", 1)[0])  # drop IPv6 scope id
        if not allow_insecure and (
            ip.is_private or ip.is_loopback or ip.is_link_local
            or ip.is_multicast or ip.is_reserved or ip.is_unspecified
        ):
            return False, "webhook host resolves to a non-public address"
    return True, None
