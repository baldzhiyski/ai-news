from __future__ import annotations

import base64
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Iterable


GMAIL_SCOPES = (
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.send",
)


class GmailClientError(RuntimeError):
    """Raised when Gmail API operations fail."""


def resolve_allowlisted_labels(
    allowlist: Iterable[str], available_labels: Iterable[dict[str, Any]]
) -> dict[str, str]:
    """Resolve exact Gmail label names to IDs.

    This intentionally performs exact string matching only. Prefix, substring,
    folder-like parent, and fuzzy matches are not accepted.
    """

    by_name: dict[str, str] = {}
    for label in available_labels:
        name = label.get("name")
        label_id = label.get("id")
        if isinstance(name, str) and isinstance(label_id, str):
            by_name[name] = label_id

    resolved: dict[str, str] = {}
    missing: list[str] = []
    for label_name in allowlist:
        if label_name in by_name:
            resolved[label_name] = by_name[label_name]
        else:
            missing.append(label_name)
    if missing:
        raise GmailClientError(f"Configured Gmail labels were not found exactly: {missing}")
    return resolved


class GmailClient:
    def __init__(self, service: Any):
        self.service = service

    @classmethod
    def from_oauth_files(
        cls,
        credentials_path: str,
        token_path: str,
        allow_interactive_auth: bool = True,
    ) -> "GmailClient":
        try:
            from google.auth.exceptions import RefreshError
            from google.auth.transport.requests import Request
            from google.oauth2.credentials import Credentials
            from google_auth_oauthlib.flow import InstalledAppFlow
            from googleapiclient.discovery import build
        except ImportError as exc:
            raise GmailClientError(
                "Google API dependencies are not installed. Run `pip install -r requirements.txt`."
            ) from exc

        credentials_file = Path(credentials_path)
        token_file = Path(token_path)
        creds = None
        if token_file.exists():
            creds = Credentials.from_authorized_user_file(str(token_file), GMAIL_SCOPES)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except RefreshError as exc:
                    raise GmailClientError(
                        "Gmail token refresh failed (token may be expired or revoked). "
                        "Regenerate token.json locally and update the GMAIL_TOKEN_JSON secret "
                        "before running in CI."
                    ) from exc
            else:
                if not allow_interactive_auth:
                    raise GmailClientError(
                        "Gmail token is missing or cannot be refreshed and interactive OAuth is "
                        "disabled (ALLOW_INTERACTIVE_AUTH=false). Generate a valid token.json "
                        "locally and provide it (e.g. via the GMAIL_TOKEN_JSON secret) before "
                        "running in a non-interactive environment such as CI."
                    )
                if not credentials_file.exists():
                    raise GmailClientError(f"Missing OAuth credentials file: {credentials_file}")
                flow = InstalledAppFlow.from_client_secrets_file(str(credentials_file), GMAIL_SCOPES)
                creds = flow.run_local_server(port=0)
            token_file.write_text(creds.to_json(), encoding="utf-8")

        service = build("gmail", "v1", credentials=creds)
        return cls(service)

    def list_labels(self) -> list[dict[str, Any]]:
        response = self.service.users().labels().list(userId="me").execute()
        return list(response.get("labels", []))

    def search_message_ids(
        self,
        *,
        label_id: str,
        gmail_after_query: str,
        max_results: int,
    ) -> list[str]:
        if not label_id:
            raise GmailClientError("Refusing to search Gmail without an exact label ID.")
        if max_results < 1:
            return []

        message_ids: list[str] = []
        page_token: str | None = None
        query = f"after:{gmail_after_query}"

        while len(message_ids) < max_results:
            remaining = max_results - len(message_ids)
            request = (
                self.service.users()
                .messages()
                .list(
                    userId="me",
                    labelIds=[label_id],
                    q=query,
                    maxResults=min(remaining, 500),
                    includeSpamTrash=False,
                    pageToken=page_token,
                )
            )
            response = request.execute()
            message_ids.extend(message["id"] for message in response.get("messages", []))
            page_token = response.get("nextPageToken")
            if not page_token:
                break
        return message_ids

    def get_message(self, message_id: str) -> dict[str, Any]:
        return (
            self.service.users()
            .messages()
            .get(userId="me", id=message_id, format="full")
            .execute()
        )

    def send_message(self, message: EmailMessage) -> dict[str, Any]:
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")
        return (
            self.service.users()
            .messages()
            .send(userId="me", body={"raw": raw})
            .execute()
        )

    def trash_message(self, message_id: str) -> dict[str, Any]:
        return self.service.users().messages().trash(userId="me", id=message_id).execute()
