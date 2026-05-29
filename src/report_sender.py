from __future__ import annotations

import logging
from dataclasses import dataclass
from email.message import EmailMessage


LOGGER = logging.getLogger(__name__)


class ReportSendError(RuntimeError):
    """Raised when the report cannot be sent or verified."""


@dataclass(frozen=True)
class SendResult:
    sent: bool
    dry_run: bool
    message_id: str | None


def build_report_message(recipient: str, subject: str, body: str) -> EmailMessage:
    message = EmailMessage()
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body)
    return message


def send_report(
    *,
    client,
    recipient: str,
    subject: str,
    body: str,
    dry_run: bool,
) -> SendResult:
    if dry_run:
        LOGGER.info("Dry run: would send summary email to %s with subject %r.", recipient, subject)
        return SendResult(sent=False, dry_run=True, message_id=None)

    response = client.send_message(build_report_message(recipient, subject, body))
    message_id = response.get("id") if isinstance(response, dict) else None
    if not message_id:
        raise ReportSendError("Gmail send did not return a sent message ID.")
    LOGGER.info("Verified summary email sent with Gmail message ID %s.", message_id)
    return SendResult(sent=True, dry_run=False, message_id=message_id)
