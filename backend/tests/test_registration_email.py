import os
import sys
import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


fake_resend = MagicMock()
fake_resend.Emails.send.return_value = {"id": "email_123"}
sys.modules.setdefault("resend", fake_resend)

from services.registration_email import send_registration_request


class RegistrationEmailTests(unittest.TestCase):
    def test_sends_admin_approval_link_with_configured_sender(self):
        user = SimpleNamespace(
            id=42,
            email="staff@example.com",
            provider_name="Test Commander",
            game_start_date=date(2024, 1, 2),
            play_server="JP",
        )
        env = {
            "RESEND_API_KEY": "re_test",
            "EMAIL_FROM": "noreply@sendmail.nikkeari.cc",
            "ADMIN_NOTIFICATION_EMAIL": "amatsukasa@gmail.com",
            "APP_BASE_URL": "https://nikkeari.cc",
        }
        with patch.dict(os.environ, env, clear=False):
            email_id = send_registration_request(user, "approval-token")

        self.assertEqual(email_id, "email_123")
        payload = fake_resend.Emails.send.call_args.args[0]
        self.assertEqual(payload["from"], env["EMAIL_FROM"])
        self.assertEqual(payload["to"], [env["ADMIN_NOTIFICATION_EMAIL"]])
        self.assertIn(
            "https://nikkeari.cc/approve-registration?user=42&token=approval-token",
            payload["text"],
        )
        self.assertIn("Test Commander", payload["text"])


if __name__ == "__main__":
    unittest.main()
