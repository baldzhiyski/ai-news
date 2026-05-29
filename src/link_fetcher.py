from __future__ import annotations

import logging
import re
from collections import Counter
from dataclasses import dataclass
from urllib.parse import urlparse

from .link_extractor import AI_RELEVANCE_TERMS, is_probably_useful_link


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class ArticleInfo:
    url: str
    title: str
    source: str
    publish_date: str
    main_topic: str
    key_claims: tuple[str, ...]
    relevance: str
    relevance_score: int
    excerpt: str


@dataclass(frozen=True)
class IgnoredLink:
    url: str
    reason: str


TOPIC_TERMS = {
    "AI engineering and developer tools": {
        "developer",
        "coding",
        "copilot",
        "ide",
        "tool",
        "tools",
        "sdk",
        "api",
        "engineering",
        "eval",
        "observability",
    },
    "AI agents and automation": {
        "agent",
        "agents",
        "workflow",
        "automation",
        "autonomous",
        "tool-use",
        "orchestration",
    },
    "Startups, products, and business opportunities": {
        "startup",
        "funding",
        "product",
        "launch",
        "pricing",
        "business",
        "enterprise",
        "revenue",
    },
    "Research or technical breakthroughs": {
        "research",
        "benchmark",
        "paper",
        "model",
        "training",
        "inference",
        "llm",
        "reasoning",
        "multimodal",
    },
    "Market signals and trends": {
        "market",
        "adoption",
        "regulation",
        "policy",
        "trend",
        "spend",
        "capex",
        "infrastructure",
    },
}


def fetch_article(
    url: str,
    *,
    timeout_seconds: float,
    max_bytes: int,
) -> ArticleInfo | IgnoredLink:
    if not is_probably_useful_link(url):
        return IgnoredLink(url=url, reason="unsafe_or_irrelevant_url")

    try:
        import requests
        from bs4 import BeautifulSoup
    except ImportError as exc:
        raise RuntimeError("Install requests and beautifulsoup4 before fetching links.") from exc

    headers = {
        "User-Agent": "ai-news-weekly-brief/1.0 (+read-only article fetcher)",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,text/plain;q=0.8,*/*;q=0.5",
    }
    try:
        with requests.get(
            url,
            headers=headers,
            timeout=timeout_seconds,
            allow_redirects=True,
            stream=True,
        ) as response:
            final_url = response.url
            if not is_probably_useful_link(final_url):
                return IgnoredLink(url=url, reason="redirected_to_unsafe_or_irrelevant_url")
            response.raise_for_status()
            content_type = response.headers.get("content-type", "").lower()
            if "html" not in content_type and "text/plain" not in content_type:
                return IgnoredLink(url=url, reason=f"unsupported_content_type:{content_type[:60]}")
            content = _read_limited(response, max_bytes)
    except requests.RequestException as exc:
        LOGGER.warning("Ignoring broken link %s: %s", url, exc)
        return IgnoredLink(url=url, reason="request_failed")

    soup = BeautifulSoup(content, "html.parser")
    for tag in soup(["script", "style", "noscript", "form", "button", "nav", "footer"]):
        tag.decompose()

    title = _extract_title(soup, final_url)
    publish_date = _extract_meta(
        soup,
        (
            "article:published_time",
            "datePublished",
            "pubdate",
            "publish_date",
            "date",
        ),
    )
    text = _extract_main_text(soup)
    combined = f"{title}\n{text}"
    if not _is_ai_relevant(combined):
        return IgnoredLink(url=url, reason="irrelevant_content")

    topic = _classify_topic(combined)
    claims = _extract_key_claims(combined)
    score = _relevance_score(combined)
    source = urlparse(final_url).hostname or "unknown source"

    return ArticleInfo(
        url=final_url,
        title=title,
        source=source,
        publish_date=publish_date,
        main_topic=topic,
        key_claims=tuple(claims),
        relevance=_explain_relevance(topic, score),
        relevance_score=score,
        excerpt=text[:1200],
    )


def _read_limited(response, max_bytes: int) -> str:
    chunks: list[bytes] = []
    total = 0
    for chunk in response.iter_content(chunk_size=8192):
        if not chunk:
            continue
        total += len(chunk)
        if total > max_bytes:
            break
        chunks.append(chunk)
    encoding = response.encoding or "utf-8"
    return b"".join(chunks).decode(encoding, errors="replace")


def _extract_title(soup, fallback_url: str) -> str:
    for selector in [
        ("property", "og:title"),
        ("name", "twitter:title"),
        ("name", "title"),
    ]:
        tag = soup.find("meta", attrs={selector[0]: selector[1]})
        if tag and tag.get("content"):
            return _clean_text(tag["content"])
    if soup.title and soup.title.string:
        return _clean_text(soup.title.string)
    return fallback_url


def _extract_meta(soup, names: tuple[str, ...]) -> str:
    for name in names:
        tag = soup.find("meta", attrs={"property": name}) or soup.find("meta", attrs={"name": name})
        if tag and tag.get("content"):
            return _clean_text(tag["content"])
    return ""


def _extract_main_text(soup) -> str:
    root = soup.find("article") or soup.find("main") or soup.body or soup
    paragraphs = [_clean_text(node.get_text(" ")) for node in root.find_all(["h1", "h2", "p", "li"])]
    meaningful = [paragraph for paragraph in paragraphs if len(paragraph) >= 40]
    return "\n".join(meaningful[:30])


def _extract_key_claims(text: str) -> list[str]:
    sentences = [
        _clean_text(sentence)
        for sentence in re.split(r"(?<=[.!?])\s+", text)
        if 60 <= len(sentence.strip()) <= 260
    ]
    ranked = sorted(sentences, key=_sentence_score, reverse=True)
    claims: list[str] = []
    seen: set[str] = set()
    for sentence in ranked:
        normalized = sentence.lower()
        if normalized in seen:
            continue
        claims.append(sentence)
        seen.add(normalized)
        if len(claims) >= 4:
            break
    return claims or [_clean_text(text[:220])]


def _classify_topic(text: str) -> str:
    lower = text.lower()
    scores = {
        topic: sum(1 for term in terms if term in lower)
        for topic, terms in TOPIC_TERMS.items()
    }
    topic, score = max(scores.items(), key=lambda item: item[1])
    if score == 0:
        return "Market signals and trends"
    return topic


def _relevance_score(text: str) -> int:
    lower = text.lower()
    counts = Counter(term for term in AI_RELEVANCE_TERMS if term in lower)
    return min(100, 20 + sum(counts.values()) * 8)


def _sentence_score(sentence: str) -> int:
    lower = sentence.lower()
    score = sum(4 for term in AI_RELEVANCE_TERMS if term in lower)
    score += min(len(sentence) // 40, 5)
    if any(term in lower for term in {"announced", "launched", "released", "raised", "benchmark"}):
        score += 3
    return score


def _is_ai_relevant(text: str) -> bool:
    lower = text.lower()
    return any(term in lower for term in AI_RELEVANCE_TERMS)


def _explain_relevance(topic: str, score: int) -> str:
    if score >= 70:
        strength = "high"
    elif score >= 45:
        strength = "medium"
    else:
        strength = "emerging"
    return f"{strength} relevance to {topic.lower()}"


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()
