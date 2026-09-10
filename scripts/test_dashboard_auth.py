import os
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dashboard_sessions import SessionCipher, SessionSecurityError, new_session


class DashboardAuthTests(unittest.TestCase):
    def test_bundle_encrypts_and_rejects_tampering(self):
        from cryptography.fernet import Fernet
        cipher = SessionCipher(Fernet.generate_key().decode())
        session_id, row = new_session(cipher, "123", "access-secret", "refresh-secret",
                                      datetime.now(timezone.utc), "csrf")
        self.assertNotIn("access-secret", row["token_bundle"])
        self.assertEqual(cipher.decrypt(row["token_bundle"])["discord_user_id"], "123")
        with self.assertRaises(SessionSecurityError):
            cipher.decrypt(row["token_bundle"][:-1] + "x")
        self.assertNotIn(session_id, row["token_bundle"])

    def test_security_contract_is_present(self):
        source = (ROOT / "webserver.py").read_text(encoding="utf-8")
        frontend = (ROOT / "legal/dashboard.html").read_text(encoding="utf-8")
        self.assertIn('__Host-skullboard_session', source)
        self.assertIn('samesite="Lax"', source)
        self.assertIn('X-CSRF-Token', source)
        self.assertNotIn('skb_cached_user', frontend)
        self.assertNotIn('skb_cached_guilds', frontend)
        self.assertNotIn('discord_token', source)

    def test_cookie_storage_and_frontend_reload_contract(self):
        source = (ROOT / "webserver.py").read_text(encoding="utf-8")
        frontend = (ROOT / "legal/dashboard.html").read_text(encoding="utf-8")
        self.assertIn('httponly=True', source)
        self.assertIn('secure=APP_ENV == "production"', source)
        self.assertIn('samesite="Lax"', source)
        self.assertIn("/api/auth/me", frontend)
        self.assertIn("credentials: 'include'", frontend)
        self.assertNotIn("localStorage.setItem('skb_cached", frontend)

    def test_csrf_expiry_persistence_and_logout_guards(self):
        source = (ROOT / "webserver.py").read_text(encoding="utf-8")
        self.assertIn('X-CSRF-Token', source)
        self.assertIn('CSRF inválido', source)
        self.assertIn('expires_at', source)
        self.assertIn('dashboard_sessions', source)
        self.assertIn('No se pudo invalidar la sesión', source)
        self.assertNotIn('_sessions[', source)

    def test_invalid_oauth_state_is_rejected(self):
        os.environ.pop("SKULLBOARD_SESSION_ENCRYPTION_KEY", None)
        import webserver
        with webserver.app.test_client() as client:
            response = client.post("/api/auth/token", json={
                "code": "safe-code", "state": "not-issued", "redirect_uri": "http://localhost:8080/dashboard"
            }, headers={"Origin": "http://localhost:8080"})
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
