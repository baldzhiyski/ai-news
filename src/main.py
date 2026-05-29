from __future__ import annotations

import logging
import sys

from .cleanup import cleanup_processed_messages
from .config import ConfigError, load_dotenv_file, settings_from_env
from .email_reader import EmailItem, UnsafeMessageError, parse_gmail_message
from .gmail_client import GmailClient, GmailClientError, resolve_allowlisted_labels
from .link_fetcher import ArticleInfo, IgnoredLink, fetch_article
from .report_sender import ReportSendError, send_report
from .summarizer import generate_weekly_report


LOGGER = logging.getLogger(__name__)


def run() -> int:
    load_dotenv_file()
    try:
        settings = settings_from_env()
    except ConfigError as exc:
        _configure_logging("INFO")
        LOGGER.error("Configuration error: %s", exc)
        return 2

    _configure_logging(settings.log_level)
    LOGGER.info("Starting AI news Gmail automation in %s mode.", settings.run_mode)
    LOGGER.info("Configured exact Gmail label allowlist: %s", list(settings.gmail_label_allowlist))

    try:
        client = GmailClient.from_oauth_files(
            settings.gmail_credentials_path,
            settings.gmail_token_path,
        )
        label_map = resolve_allowlisted_labels(settings.gmail_label_allowlist, client.list_labels())
        allowed_label_ids = set(label_map.values())
        window = settings.time_window()
        processed_messages = _fetch_allowlisted_messages(
            client=client,
            label_map=label_map,
            allowed_label_ids=allowed_label_ids,
            gmail_after_query=window.gmail_after_query,
            max_emails=settings.max_emails_per_run,
            max_links=settings.max_links_per_email,
        )
        articles, ignored_links = _fetch_articles(
            processed_messages,
            timeout_seconds=settings.request_timeout_seconds,
            max_bytes=settings.max_article_bytes,
        )
        report = generate_weekly_report(
            emails=processed_messages,
            articles=articles,
            ignored_links=ignored_links,
            date_range=window.display_range,
        )
        if settings.is_dry_run:
            print(report.subject)
            print()
            print(report.body)

        send_result = send_report(
            client=client,
            recipient=settings.summary_recipient_email,
            subject=report.subject,
            body=report.body,
            dry_run=settings.is_dry_run,
        )
        cleanup_processed_messages(
            client=client,
            messages=processed_messages,
            settings=settings,
            send_result=send_result,
            allowed_label_ids=allowed_label_ids,
        )
    except (GmailClientError, UnsafeMessageError, ReportSendError, RuntimeError) as exc:
        LOGGER.exception("Run failed before cleanup. No Gmail messages were deleted: %s", exc)
        return 1

    LOGGER.info("Run completed.")
    return 0


def _fetch_allowlisted_messages(
    *,
    client: GmailClient,
    label_map: dict[str, str],
    allowed_label_ids: set[str],
    gmail_after_query: str,
    max_emails: int,
    max_links: int,
) -> list[EmailItem]:
    processed: list[EmailItem] = []
    for label_name, label_id in label_map.items():
        remaining = max_emails - len(processed)
        if remaining <= 0:
            break
        LOGGER.info("Searching Gmail with exact label_id=%s label_name=%r only.", label_id, label_name)
        message_ids = client.search_message_ids(
            label_id=label_id,
            gmail_after_query=gmail_after_query,
            max_results=remaining,
        )
        LOGGER.info("Found %d candidate messages for label %r.", len(message_ids), label_name)
        for message_id in message_ids:
            raw_message = client.get_message(message_id)
            try:
                item = parse_gmail_message(
                    raw_message,
                    label_name=label_name,
                    label_id=label_id,
                    allowed_label_ids=allowed_label_ids,
                    max_links=max_links,
                )
            except UnsafeMessageError:
                LOGGER.warning("Skipping message %s because it failed the allowlist guard.", message_id)
                raise
            LOGGER.info(
                "Processed message_id=%s label=%r subject=%r links=%d",
                item.message_id,
                item.label,
                item.subject,
                len(item.links),
            )
            processed.append(item)
    return processed


def _fetch_articles(
    messages: list[EmailItem],
    *,
    timeout_seconds: float,
    max_bytes: int,
) -> tuple[list[ArticleInfo], list[IgnoredLink]]:
    articles: list[ArticleInfo] = []
    ignored: list[IgnoredLink] = []
    seen_urls: set[str] = set()

    for message in messages:
        for url in message.links:
            if url in seen_urls:
                ignored.append(IgnoredLink(url=url, reason="duplicate_link"))
                continue
            seen_urls.add(url)
            result = fetch_article(url, timeout_seconds=timeout_seconds, max_bytes=max_bytes)
            if isinstance(result, IgnoredLink):
                ignored.append(result)
            else:
                articles.append(result)
    LOGGER.info("Fetched %d useful links; ignored %d links.", len(articles), len(ignored))
    return articles, ignored


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )


if __name__ == "__main__":
    sys.exit(run())
