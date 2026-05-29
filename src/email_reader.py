from __future__ import annotations

import base64
import re
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from html import unescape
from typing import Any, Iterable

from .link_extractor import extract_links


class UnsafeMessageError(RuntimeError):
    """Raised when a Gmail message is outside the configured label boundary."""


@dataclass(frozen=True)
class EmailItem:
    message_id: str
    label: str
    label_id: str
    subject: str
    sender: str
    date: str
    body_text: str
    links: tuple[str, ...]
    raw_label_ids: frozenset[str]


def parse_gmail_message(
    raw_message: dict[str, Any],
    *,
    label_name: str,
    label_id: str,
    allowed_label_ids: Iterable[str],
    max_links: int,
) -> EmailItem:
    allowed_ids = set(allowed_label_ids)
    raw_label_ids = frozenset(raw_message.get("labelIds") or [])
    if label_id not in allowed_ids:
        raise UnsafeMessageError(f"Label ID {label_id!r} is not in the allowlist.")
    if label_id not in raw_label_ids:
        raise UnsafeMessageError(
            f"Message {raw_message.get('id')!r} does not contain allowlisted label {label_name!r}."
        )

    payload = raw_message.get("payload") or {}
    headers = _headers_map(payload.get("headers") or [])
    body_text = _payload_to_text(payload)
    message_id = raw_message.get("id")
    if not message_id:
        raise UnsafeMessageError("Gmail message has no ID; refusing to process it.")

    return EmailItem(
        message_id=message_id,
        label=label_name,
        label_id=label_id,
        subject=headers.get("subject", "(no subject)"),
        sender=headers.get("from", "(unknown sender)"),
        date=_normalize_date(headers.get("date", "")),
        body_text=body_text,
        links=tuple(extract_links(body_text, max_links=max_links)),
        raw_label_ids=raw_label_ids,
    )


def _headers_map(headers: list[dict[str, str]]) -> dict[str, str]:
    return {
        header.get("name", "").lower(): header.get("value", "")
        for header in headers
        if header.get("name")
    }


def _normalize_date(raw_date: str) -> str:
    if not raw_date:
        return ""
    try:
        return parsedate_to_datetime(raw_date).isoformat()
    except (TypeError, ValueError):
        return raw_date


def _payload_to_text(payload: dict[str, Any]) -> str:
    plain_parts: list[str] = []
    html_parts: list[str] = []
    _collect_payload_text(payload, plain_parts, html_parts)
    text = "\n".join(part for part in plain_parts if part.strip())
    if text.strip():
        return _clean_text(text)
    return _clean_text("\n".join(_html_to_text(part) for part in html_parts if part.strip()))


def _collect_payload_text(
    payload: dict[str, Any], plain_parts: list[str], html_parts: list[str]
) -> None:
    mime_type = payload.get("mimeType", "")
    body_data = (payload.get("body") or {}).get("data")
    if body_data:
        decoded = _decode_base64url(body_data)
        if mime_type == "text/plain":
            plain_parts.append(decoded)
        elif mime_type == "text/html":
            html_parts.append(decoded)

    for part in payload.get("parts") or []:
        _collect_payload_text(part, plain_parts, html_parts)


def _decode_base64url(data: str) -> str:
    padding = "=" * (-len(data) % 4)
    decoded = base64.urlsafe_b64decode((data + padding).encode("ascii"))
    return decoded.decode("utf-8", errors="replace")


def _html_to_text(html: str) -> str:
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return re.sub(r"<[^>]+>", " ", unescape(html))
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return soup.get_text(" ")


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", unescape(text)).strip()
