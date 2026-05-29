import unittest

from src.cleanup import cleanup_processed_messages
from src.config import Settings
from src.email_reader import UnsafeMessageError, parse_gmail_message
from src.gmail_client import resolve_allowlisted_labels
from src.report_sender import SendResult


def _settings(run_mode="dry_run", delete_after_success=False):
    return Settings(
        gmail_label_allowlist=("Programming Newsletter",),
        summary_recipient_email="me@example.com",
        run_mode=run_mode,
        delete_after_success=delete_after_success,
        max_emails_per_run=10,
        max_links_per_email=5,
        summary_time_window="last 7 days",
    )


def _gmail_message(message_id="msg-1", labels=None, subject="AI launch"):
    return {
        "id": message_id,
        "labelIds": labels or ["Label_AI"],
        "payload": {
            "headers": [
                {"name": "Subject", "value": subject},
                {"name": "From", "value": "newsletter@example.com"},
                {"name": "Date", "value": "Fri, 29 May 2026 10:00:00 +0000"},
            ],
            "mimeType": "text/plain",
            "body": {"data": "QUkgbmV3czogaHR0cHM6Ly9leGFtcGxlLmNvbS9haQ=="},
        },
    }


class FakeGmailClient:
    def __init__(self):
        self.trashed = []

    def trash_message(self, message_id):
        self.trashed.append(message_id)
        return {"id": message_id, "labelIds": ["TRASH"]}


class GmailSafetyTests(unittest.TestCase):
    def test_resolves_only_exact_allowlisted_label_names(self):
        labels = [
            {"id": "Label_AI", "name": "AI News"},
            {"id": "Label_AI_Archive", "name": "AI News/Archive"},
            {"id": "Label_Other", "name": "Personal"},
        ]

        resolved = resolve_allowlisted_labels(("AI News",), labels)

        self.assertEqual(resolved, {"AI News": "Label_AI"})

    def test_rejects_message_missing_exact_allowlisted_label_id(self):
        with self.assertRaises(UnsafeMessageError):
            parse_gmail_message(
                _gmail_message(labels=["Label_Other"]),
                label_name="AI News",
                label_id="Label_AI",
                allowed_label_ids={"Label_AI"},
                max_links=5,
            )

    def test_dry_run_mode_never_deletes_processed_messages(self):
        client = FakeGmailClient()
        item = parse_gmail_message(
            _gmail_message(),
            label_name="AI News",
            label_id="Label_AI",
            allowed_label_ids={"Label_AI"},
            max_links=5,
        )
        send_result = SendResult(sent=False, dry_run=True, message_id=None)

        results = cleanup_processed_messages(
            client=client,
            messages=[item],
            settings=_settings(run_mode="dry_run", delete_after_success=True),
            send_result=send_result,
            allowed_label_ids={"Label_AI"},
        )

        self.assertEqual(client.trashed, [])
        self.assertEqual(results[0].action, "dry_run_skip")

    def test_deletes_only_after_successful_live_send(self):
        client = FakeGmailClient()
        item = parse_gmail_message(
            _gmail_message(message_id="msg-safe"),
            label_name="AI News",
            label_id="Label_AI",
            allowed_label_ids={"Label_AI"},
            max_links=5,
        )
        send_result = SendResult(sent=True, dry_run=False, message_id="sent-1")

        results = cleanup_processed_messages(
            client=client,
            messages=[item],
            settings=_settings(run_mode="live", delete_after_success=True),
            send_result=send_result,
            allowed_label_ids={"Label_AI"},
        )

        self.assertEqual(client.trashed, ["msg-safe"])
        self.assertEqual(results[0].action, "trashed")

    def test_does_not_delete_when_send_fails(self):
        client = FakeGmailClient()
        item = parse_gmail_message(
            _gmail_message(message_id="msg-safe"),
            label_name="AI News",
            label_id="Label_AI",
            allowed_label_ids={"Label_AI"},
            max_links=5,
        )
        send_result = SendResult(sent=False, dry_run=False, message_id=None)

        results = cleanup_processed_messages(
            client=client,
            messages=[item],
            settings=_settings(run_mode="live", delete_after_success=True),
            send_result=send_result,
            allowed_label_ids={"Label_AI"},
        )

        self.assertEqual(client.trashed, [])
        self.assertEqual(results[0].action, "send_not_confirmed_skip")


if __name__ == "__main__":
    unittest.main()
