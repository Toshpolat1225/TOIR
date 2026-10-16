import unittest
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException

from app.services.auth import (
    LOGIN_FAILURE_WINDOW,
    _raise_login_rate_limit,
    login_attempt_key_hash,
)


class LoginAttemptLimiterTests(unittest.TestCase):
    def test_key_hash_normalizes_email_without_storing_it(self):
        normalized = login_attempt_key_hash("192.0.2.1", "Admin@Example.com")
        equivalent = login_attempt_key_hash("192.0.2.1", " admin@example.COM ")
        different_ip = login_attempt_key_hash("192.0.2.2", "admin@example.com")

        self.assertEqual(normalized, equivalent)
        self.assertNotEqual(normalized, different_ip)
        self.assertNotIn("admin", normalized)
        self.assertNotIn("@", normalized)

    def test_rate_limit_returns_remaining_sliding_window(self):
        now = datetime.now(timezone.utc)
        started_at = now - timedelta(minutes=5)

        with self.assertRaises(HTTPException) as raised:
            _raise_login_rate_limit(now, started_at)

        self.assertEqual(raised.exception.status_code, 429)
        self.assertEqual(
            int(raised.exception.headers["Retry-After"]),
            int((LOGIN_FAILURE_WINDOW - timedelta(minutes=5)).total_seconds()),
        )


if __name__ == "__main__":
    unittest.main()
