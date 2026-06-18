import unittest
from unittest.mock import patch

from src.config import Settings
from src.gmail_client import GmailClientError
from src.main import run


def _settings() -> Settings:
    return Settings(
        gmail_label_allowlist=("Programming Newsletter",),
        summary_recipient_email="me@example.com",
        run_mode="dry_run",
        delete_after_success=False,
    )


class MainTests(unittest.TestCase):
    @patch("src.main._configure_logging")
    @patch("src.main.load_dotenv_file")
    @patch("src.main.settings_from_env")
    @patch("src.main.GmailClient.from_oauth_files")
    def test_returns_exit_code_3_when_gmail_auth_is_unavailable(
        self,
        mock_from_oauth_files,
        mock_settings_from_env,
        _mock_load_dotenv,
        _mock_configure_logging,
    ):
        mock_settings_from_env.return_value = _settings()
        mock_from_oauth_files.side_effect = GmailClientError("invalid_grant")

        exit_code = run()

        self.assertEqual(exit_code, 3)


if __name__ == "__main__":
    unittest.main()
