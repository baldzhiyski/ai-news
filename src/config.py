from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Mapping


class ConfigError(ValueError):
    """Raised when required configuration is missing or unsafe."""


@dataclass(frozen=True)
class TimeWindow:
    raw: str
    start: datetime
    end: datetime

    @property
    def gmail_after_query(self) -> str:
        return self.start.strftime("%Y/%m/%d")

    @property
    def display_range(self) -> str:
        return f"{self.start.date().isoformat()} to {self.end.date().isoformat()}"


@dataclass(frozen=True)
class Settings:
    gmail_label_allowlist: tuple[str, ...]
    summary_recipient_email: str
    run_mode: str = "dry_run"
    delete_after_success: bool = False
    max_emails_per_run: int = 50
    max_links_per_email: int = 5
    summary_time_window: str = "last 7 days"
    gmail_credentials_path: str = "credentials.json"
    gmail_token_path: str = "token.json"
    request_timeout_seconds: float = 10.0
    max_article_bytes: int = 1_000_000
    log_level: str = "INFO"

    @property
    def is_dry_run(self) -> bool:
        return self.run_mode == "dry_run"

    @property
    def live_deletion_enabled(self) -> bool:
        return self.run_mode == "live" and self.delete_after_success

    def validate(self) -> None:
        if not self.gmail_label_allowlist:
            raise ConfigError("GMAIL_LABEL_ALLOWLIST is empty; refusing to run.")
        if any(not label.strip() for label in self.gmail_label_allowlist):
            raise ConfigError("GMAIL_LABEL_ALLOWLIST contains an empty label.")
        if len(set(self.gmail_label_allowlist)) != len(self.gmail_label_allowlist):
            raise ConfigError("GMAIL_LABEL_ALLOWLIST contains duplicate labels.")
        if self.run_mode not in {"dry_run", "live"}:
            raise ConfigError("RUN_MODE must be dry_run or live.")
        if not self.summary_recipient_email:
            raise ConfigError("SUMMARY_RECIPIENT_EMAIL is required.")
        if self.max_emails_per_run < 1:
            raise ConfigError("MAX_EMAILS_PER_RUN must be at least 1.")
        if self.max_links_per_email < 0:
            raise ConfigError("MAX_LINKS_PER_EMAIL cannot be negative.")

    def time_window(self, now: datetime | None = None) -> TimeWindow:
        now = now or datetime.now(timezone.utc)
        raw = self.summary_time_window.strip()
        lower = raw.lower()
        match = re.search(r"last\s+(\d+)\s+days?", lower) or re.fullmatch(r"(\d+)d", lower)
        if not match:
            raise ConfigError(
                "SUMMARY_TIME_WINDOW must use a supported format such as 'last 7 days' or '7d'."
            )
        days = int(match.group(1))
        if days < 1 or days > 90:
            raise ConfigError("SUMMARY_TIME_WINDOW must be between 1 and 90 days.")
        return TimeWindow(raw=raw, start=now - timedelta(days=days), end=now)


def load_dotenv_file(path: str | Path = ".env") -> None:
    env_path = Path(path)
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def settings_from_env(env: Mapping[str, str] | None = None) -> Settings:
    env = env or os.environ
    settings = Settings(
        gmail_label_allowlist=_parse_label_allowlist(_env_value(env, "GMAIL_LABEL_ALLOWLIST", "")),
        summary_recipient_email=_env_value(env, "SUMMARY_RECIPIENT_EMAIL", "").strip(),
        run_mode=_env_value(env, "RUN_MODE", "dry_run").strip().lower(),
        delete_after_success=_parse_bool(_env_value(env, "DELETE_AFTER_SUCCESS", "false")),
        max_emails_per_run=_parse_int(
            _env_value(env, "MAX_EMAILS_PER_RUN", "50"), "MAX_EMAILS_PER_RUN"
        ),
        max_links_per_email=_parse_int(
            _env_value(env, "MAX_LINKS_PER_EMAIL", "5"), "MAX_LINKS_PER_EMAIL"
        ),
        summary_time_window=_env_value(env, "SUMMARY_TIME_WINDOW", "last 7 days").strip(),
        gmail_credentials_path=_env_value(env, "GMAIL_CREDENTIALS_PATH", "credentials.json").strip(),
        gmail_token_path=_env_value(env, "GMAIL_TOKEN_PATH", "token.json").strip(),
        request_timeout_seconds=float(_env_value(env, "REQUEST_TIMEOUT_SECONDS", "10")),
        max_article_bytes=_parse_int(
            _env_value(env, "MAX_ARTICLE_BYTES", "1000000"), "MAX_ARTICLE_BYTES"
        ),
        log_level=_env_value(env, "LOG_LEVEL", "INFO").strip().upper(),
    )
    settings.validate()
    return settings


def _parse_label_allowlist(raw: str) -> tuple[str, ...]:
    raw = raw.strip()
    if not raw:
        return ()
    if raw.startswith("["):
        try:
            labels = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ConfigError("GMAIL_LABEL_ALLOWLIST JSON is invalid.") from exc
        if not isinstance(labels, list) or not all(isinstance(label, str) for label in labels):
            raise ConfigError("GMAIL_LABEL_ALLOWLIST JSON must be a list of strings.")
        return tuple(label.strip() for label in labels if label.strip())
    return tuple(label.strip() for label in raw.split(",") if label.strip())


def _env_value(env: Mapping[str, str], name: str, default: str) -> str:
    value = env.get(name)
    if value is None or value.strip() == "":
        return default
    return value


def _parse_bool(raw: str) -> bool:
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "y", "on"}:
        return True
    if value in {"0", "false", "no", "n", "off"}:
        return False
    raise ConfigError(f"Invalid boolean value: {raw!r}")


def _parse_int(raw: str, name: str) -> int:
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer.") from exc
