import os
import unittest
from unittest.mock import patch

import requests

from telegram import PublishingNotApprovedError, TelegramDeliveryError, send_telegram_message


class TelegramSafetyTests(unittest.TestCase):
    def test_default_environment_fails_closed(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(PublishingNotApprovedError):
                send_telegram_message("candidate")

    def test_dry_run_blocks_even_with_approval_flag(self):
        env = {"DRY_RUN": "true", "PUBLISH_APPROVED": "true"}
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaises(PublishingNotApprovedError):
                send_telegram_message("candidate")

    def test_live_mode_blocks_without_approval_flag(self):
        env = {"DRY_RUN": "false", "PUBLISH_APPROVED": "false"}
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaises(PublishingNotApprovedError):
                send_telegram_message("candidate")

    @patch("telegram.requests.post")
    def test_approved_message_uses_timeout_and_checks_response(self, post):
        env = {
            "DRY_RUN": "false",
            "PUBLISH_APPROVED": "true",
            "TELEGRAM_BOT_TOKEN": "secret",
            "TELEGRAM_CHANNEL_ID": "@channel",
        }
        with patch.dict(os.environ, env, clear=True):
            send_telegram_message("candidate")

        post.assert_called_once()
        self.assertEqual(post.call_args.kwargs["timeout"], 30)
        post.return_value.raise_for_status.assert_called_once_with()

    @patch("telegram.requests.post")
    def test_rejects_oversized_message_before_network(self, post):
        env = {
            "DRY_RUN": "false",
            "PUBLISH_APPROVED": "true",
            "TELEGRAM_BOT_TOKEN": "secret",
            "TELEGRAM_CHANNEL_ID": "@channel",
        }
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaises(ValueError):
                send_telegram_message("x" * 4097)
        post.assert_not_called()

    @patch("telegram.requests.post")
    def test_network_error_is_sanitized_without_bot_token(self, post):
        secret = "super-secret-token"
        post.side_effect = requests.Timeout(f"timeout at https://api.telegram.org/bot{secret}/sendMessage")
        env = {
            "DRY_RUN": "false",
            "PUBLISH_APPROVED": "true",
            "TELEGRAM_BOT_TOKEN": secret,
            "TELEGRAM_CHANNEL_ID": "@channel",
        }
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaises(TelegramDeliveryError) as raised:
                send_telegram_message("candidate")
        self.assertNotIn(secret, str(raised.exception))


if __name__ == "__main__":
    unittest.main()
