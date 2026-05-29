from __future__ import annotations

import ipaddress
import re
from html import unescape
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse


URL_RE = re.compile(r"https?://[^\s<>'\"]+", re.IGNORECASE)

AI_RELEVANCE_TERMS = {
    "ai",
    "agent",
    "agents",
    "automation",
    "artificial-intelligence",
    "business",
    "copilot",
    "developer",
    "engineering",
    "gpt",
    "inference",
    "infrastructure",
    "llm",
    "machine-learning",
    "model",
    "openai",
    "product",
    "rag",
    "research",
    "startup",
    "vector",
}

UNSAFE_PATH_TERMS = {
    "billing",
    "cart",
    "checkout",
    "login",
    "logout",
    "payment",
    "preferences",
    "purchase",
    "signin",
    "subscribe",
    "unsubscribe",
}

IRRELEVANT_PATH_TERMS = {
    "celebrity",
    "coupon",
    "gambling",
    "gaming",
    "horoscope",
    "recipe",
    "shopping",
    "sports",
    "weather",
}

TRACKING_HOST_PARTS = (
    "click.",
    "clicks.",
    "email.",
    "link.mail",
    "lnk.",
    "tracking.",
    "trk.",
)

REDIRECT_ONLY_HOSTS = {
    "bit.ly",
    "buff.ly",
    "cutt.ly",
    "goo.gl",
    "lnkd.in",
    "rebrand.ly",
    "t.co",
    "tinyurl.com",
}

TRACKING_QUERY_PREFIXES = ("utm_",)
TRACKING_QUERY_KEYS = {
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "mkt_tok",
    "spm",
}


def extract_links(text: str, max_links: int) -> list[str]:
    if max_links <= 0:
        return []

    links: list[str] = []
    seen: set[str] = set()
    for raw_url in URL_RE.findall(text or ""):
        normalized = normalize_url(raw_url)
        if not normalized or normalized in seen:
            continue
        if not is_probably_useful_link(normalized):
            continue
        links.append(normalized)
        seen.add(normalized)
        if len(links) >= max_links:
            break
    return links


def normalize_url(raw_url: str) -> str | None:
    cleaned = unescape(raw_url).strip().rstrip(").,;!]'\"")
    parsed = urlparse(cleaned)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return None

    hostname = (parsed.hostname or "").lower()
    if not hostname:
        return None

    query_pairs = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=False):
        lower_key = key.lower()
        if lower_key in TRACKING_QUERY_KEYS:
            continue
        if any(lower_key.startswith(prefix) for prefix in TRACKING_QUERY_PREFIXES):
            continue
        query_pairs.append((key, value))

    normalized = parsed._replace(
        scheme=parsed.scheme.lower(),
        netloc=hostname + (f":{parsed.port}" if parsed.port else ""),
        path=parsed.path.rstrip("/") or "/",
        params="",
        query=urlencode(sorted(query_pairs)),
        fragment="",
    )
    return urlunparse(normalized)


def is_probably_useful_link(url: str) -> bool:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in {"http", "https"} or not host:
        return False
    if _is_local_or_private_host(host):
        return False
    if host in REDIRECT_ONLY_HOSTS:
        return False
    if any(part in host for part in TRACKING_HOST_PARTS):
        return False

    searchable = f"{host} {parsed.path} {parsed.query}".lower()
    if any(term in searchable for term in UNSAFE_PATH_TERMS):
        return False
    if any(term in searchable for term in IRRELEVANT_PATH_TERMS):
        return False
    return True


def _is_local_or_private_host(host: str) -> bool:
    if host in {"localhost", "0.0.0.0"} or host.endswith(".local"):
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast
