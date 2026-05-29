from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Iterable

from .config import Settings
from .email_reader import EmailItem
from .report_sender import SendResult


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class DeletionResult:
    message_id: str
    subject: str
    label: str
    action: str
    detail: str


def cleanup_processed_messages(
    *,
    client,
    messages: Iterable[EmailItem],
    settings: Settings,
    send_result: SendResult,
    allowed_label_ids: set[str],
) -> list[DeletionResult]:
    results: list[DeletionResult] = []
    for message in messages:
        if settings.is_dry_run:
            result = _result(message, "dry_run_skip", "Dry run never modifies Gmail.")
        elif not settings.delete_after_success:
            result = _result(message, "delete_disabled_skip", "DELETE_AFTER_SUCCESS is false.")
        elif not send_result.sent:
            result = _result(message, "send_not_confirmed_skip", "Summary send was not verified.")
        elif message.label_id not in allowed_label_ids or message.label_id not in message.raw_label_ids:
            result = _result(message, "guard_skip", "Message is outside the exact label allowlist.")
        else:
            client.trash_message(message.message_id)
            result = _result(message, "trashed", "Moved to Gmail Trash after verified send.")

        LOGGER.info(
            "cleanup message_id=%s label=%r subject=%r action=%s detail=%s",
            result.message_id,
            result.label,
            result.subject,
            result.action,
            result.detail,
        )
        results.append(result)
    return results


def _result(message: EmailItem, action: str, detail: str) -> DeletionResult:
    return DeletionResult(
        message_id=message.message_id,
        subject=message.subject,
        label=message.label,
        action=action,
        detail=detail,
    )
