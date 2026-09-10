import os
import sys
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dashboard_sessions import SessionCipher, SessionSecurityError, new_session
from cryptography.fernet import Fernet


class DashboardAuthTests(unittest.TestCase):
    def test_malformed_session_key_is_rejected_as_security_error(self):
        with self.assertRaises(SessionSecurityError):
            SessionCipher("not-a-fernet-key")

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
        self.assertNotIn('_oauth_cookie_name', source)
        self.assertNotIn('browser_hash', source)
        self.assertNotIn('Sec-Fetch-Site', source)
        self.assertNotIn('skb_cached_user', frontend)
        self.assertNotIn('skb_cached_guilds', frontend)
        self.assertNotIn('discord_token', source)

    def test_cookie_storage_and_frontend_reload_contract(self):
        import webserver
        source = (ROOT / "webserver.py").read_text(encoding="utf-8")
        frontend = (ROOT / "legal/dashboard.html").read_text(encoding="utf-8")
        self.assertIn('httponly=True', source)
        self.assertIn('_session_cookie_secure()', source)
        self.assertIn('samesite="Lax"', source)
        self.assertEqual(webserver._session_cookie_name("production"), "__Host-skullboard_session")
        self.assertTrue(webserver._session_cookie_secure("production"))
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
        import webserver
        cipher = SessionCipher(Fernet.generate_key().decode())
        with patch.object(webserver, "_session_cipher", cipher), \
             patch.object(webserver, "SUPABASE_URL", "https://db.invalid"), \
             patch.object(webserver, "SUPABASE_KEY", "service-role-placeholder"), \
             patch.object(webserver, "DISCORD_CLIENT_SECRET", "client-secret-placeholder"), \
             patch.object(webserver, "_consume_dashboard_state", return_value=False):
            with webserver.app.test_client() as client:
                response = client.post("/api/auth/token", json={
                    "code": "safe-code", "state": "not-issued", "redirect_uri": "http://localhost:8080/dashboard"
                }, headers={"Origin": "http://localhost:8080"})
        self.assertEqual(response.status_code, 400)

    def test_oauth_state_is_consumed_once(self):
        import webserver

        cipher = SessionCipher(Fernet.generate_key().decode())
        state = "s" * 43
        row = {
            "state_hash": cipher.hash_state(state),
            "expires_at": "2099-01-01T00:00:00+00:00",
        }
        with patch.object(webserver, "_session_cipher", cipher), \
             patch.object(webserver, "_sb_select_required", side_effect=[[row], []]), \
             patch.object(webserver, "_sb_delete", return_value=True) as delete_mock:
            self.assertTrue(webserver._consume_dashboard_state(state))
            self.assertFalse(webserver._consume_dashboard_state(state))
        delete_mock.assert_called_once()

    def test_auth_start_persists_hashed_state_without_origin_header(self):
        import webserver
        cipher = SessionCipher(Fernet.generate_key().decode())
        persisted = {}
        with patch.object(webserver, "_session_cipher", cipher), \
             patch.object(webserver, "SUPABASE_URL", "https://db.invalid"), \
             patch.object(webserver, "SUPABASE_KEY", "service-role-placeholder"), \
             patch.object(webserver, "_sb_upsert", side_effect=lambda table, data: persisted.update(data) or True), \
             patch.object(webserver, "_purge_expired_sessions"):
            with webserver.app.test_client() as client:
                response = client.get("/api/auth/start")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("Set-Cookie", response.headers)
        state = response.get_json()["auth_url"].split("state=", 1)[1]
        self.assertNotEqual(persisted["state_hash"], state)
        self.assertEqual(persisted["state_hash"], cipher.hash_state(state))

    def test_refresh_rotates_access_and_refresh_tokens_in_encrypted_bundle(self):
        import webserver

        class FakeResponse:
            status_code = 200

            def json(self):
                return {"access_token": "new-access-secret", "refresh_token": "new-refresh-secret", "expires_in": 3600}

        cipher = SessionCipher(Fernet.generate_key().decode())
        session_id, row = new_session(cipher, "123", "old-access-secret", "old-refresh-secret",
                                      datetime.now(timezone.utc).replace(microsecond=0), "valid-csrf")
        row["expires_at"] = datetime.fromtimestamp(time.time() + 3600, timezone.utc).isoformat()
        bundle = cipher.decrypt(row["token_bundle"])
        bundle["token_expires_at"] = datetime.fromtimestamp(time.time() + 30, timezone.utc).isoformat()
        row["token_bundle"] = cipher.encrypt(bundle)
        with patch.object(webserver, "_session_cipher", cipher), \
             patch.object(webserver, "DISCORD_CLIENT_SECRET", "client-secret-placeholder"), \
             patch.object(webserver, "_require_session", return_value=(session_id, row, bundle)), \
             patch.object(webserver, "_claim_refresh_lock", return_value="lock-id"), \
             patch.object(webserver, "_sb_patch", return_value=[{"updated": True}]), \
             patch.object(webserver.requests, "post", return_value=FakeResponse()):
            refreshed = webserver._session_credentials()
        self.assertEqual(refreshed["access_token"], "new-access-secret")
        self.assertEqual(refreshed["refresh_token"], "new-refresh-secret")

    def test_refresh_invalidation_is_bound_to_lock_owner_and_version(self):
        import webserver
        with patch.object(webserver, "_sb_delete", return_value=True) as delete_mock:
            self.assertTrue(webserver._invalidate_refresh_owned_session("hash", "lock", 3))
        delete_mock.assert_called_once_with("dashboard_sessions", {
            "session_hash": "eq.hash", "refresh_lock_id": "eq.lock", "token_version": "eq.3"
        }, require_match=True)

    def test_cookie_flags_and_frontend_response_have_no_oauth_tokens(self):
        import webserver

        class FakeResponse:
            status_code = 200

            def __init__(self, payload):
                self.payload = payload

            def json(self):
                return self.payload

        cipher = SessionCipher(Fernet.generate_key().decode())
        with patch.object(webserver, "_session_cipher", cipher), \
             patch.object(webserver, "SUPABASE_URL", "https://db.invalid"), \
             patch.object(webserver, "SUPABASE_KEY", "service-role-placeholder"), \
             patch.object(webserver, "DISCORD_CLIENT_SECRET", "client-secret-placeholder"), \
             patch.object(webserver, "SESSION_COOKIE", "__Host-skullboard_session"), \
             patch.object(webserver, "_session_cookie_secure", return_value=True), \
             patch.object(webserver, "_consume_dashboard_state", return_value=True), \
             patch.object(webserver, "_sb_upsert", return_value=True), \
             patch.object(webserver.requests, "post", return_value=FakeResponse({"access_token": "access-secret", "refresh_token": "refresh-secret", "expires_in": 3600, "scope": "identify guilds"})), \
             patch.object(webserver.requests, "get", return_value=FakeResponse({"id": "123", "username": "tester"})):
            with webserver.app.test_client() as client:
                response = client.post("/api/auth/token", json={
                    "code": "safe-code", "state": "s" * 43, "redirect_uri": "http://localhost:8080/dashboard"
                }, headers={"Origin": "http://localhost:8080"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.headers.getlist("Set-Cookie")), 1)
        cookie = response.headers["Set-Cookie"]
        self.assertIn(f"{webserver.SESSION_COOKIE}=", cookie)
        self.assertIn("HttpOnly", cookie)
        self.assertIn("Secure", cookie)
        self.assertIn("SameSite=Lax", cookie)
        self.assertIn("Path=/", cookie)
        self.assertNotIn("Domain=", cookie)
        response_text = response.get_data(as_text=True)
        self.assertNotIn("access-secret", response_text)
        self.assertNotIn("refresh-secret", response_text)
        frontend = (ROOT / "legal/dashboard.html").read_text(encoding="utf-8")
        self.assertNotIn("access_token", frontend)
        self.assertNotIn("refresh_token", frontend)
        self.assertNotIn("localStorage.setItem('skb_oauth", frontend)

    def test_oauth_token_accepts_scopes_superset_and_rejects_missing(self):
        import webserver

        class FakeResponse:
            def __init__(self, payload, status_code=200):
                self.payload = payload
                self.status_code = status_code

            def json(self):
                return self.payload

        cipher = SessionCipher(Fernet.generate_key().decode())

        # 1. Superset with role_connections.write should be accepted (even uppercase/whitespace)
        with patch.object(webserver, "_session_cipher", cipher), \
             patch.object(webserver, "SUPABASE_URL", "https://db.invalid"), \
             patch.object(webserver, "SUPABASE_KEY", "service-role-placeholder"), \
             patch.object(webserver, "DISCORD_CLIENT_SECRET", "client-secret-placeholder"), \
             patch.object(webserver, "SESSION_COOKIE", "__Host-skullboard_session"), \
             patch.object(webserver, "_session_cookie_secure", return_value=True), \
             patch.object(webserver, "_consume_dashboard_state", return_value=True), \
             patch.object(webserver, "_sb_upsert", return_value=True), \
             patch.object(webserver.requests, "post", return_value=FakeResponse({
                 "access_token": "access-secret",
                 "refresh_token": "refresh-secret",
                 "expires_in": 3600,
                 "scope": " IDENTIFY  guilds role_connections.write "
             })), \
             patch.object(webserver.requests, "get", return_value=FakeResponse({"id": "123", "username": "tester"})):
            with webserver.app.test_client() as client:
                response = client.post("/api/auth/token", json={
                    "code": "safe-code", "state": "s" * 43, "redirect_uri": "http://localhost:8080/dashboard"
                }, headers={"Origin": "http://localhost:8080"})
            self.assertEqual(response.status_code, 200)

        # 2. Missing guilds should be rejected
        with patch.object(webserver, "_session_cipher", cipher), \
             patch.object(webserver, "SUPABASE_URL", "https://db.invalid"), \
             patch.object(webserver, "SUPABASE_KEY", "service-role-placeholder"), \
             patch.object(webserver, "DISCORD_CLIENT_SECRET", "client-secret-placeholder"), \
             patch.object(webserver, "_consume_dashboard_state", return_value=True), \
             patch.object(webserver.requests, "post", return_value=FakeResponse({
                 "access_token": "access-secret",
                 "refresh_token": "refresh-secret",
                 "expires_in": 3600,
                 "scope": "identify"
             })):
            with webserver.app.test_client() as client:
                response = client.post("/api/auth/token", json={
                    "code": "safe-code", "state": "s" * 43, "redirect_uri": "http://localhost:8080/dashboard"
                }, headers={"Origin": "http://localhost:8080"})
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.get_json()["error"], "Scopes OAuth no permitidos")

    def test_csrf_invalid_is_rejected(self):
        import webserver
        with patch.object(webserver, "_session_token", return_value="access-placeholder"), \
             patch.object(webserver, "_fetch_discord_guilds", return_value=[{"id": "123456789012345", "permissions": 8, "owner": False}]), \
             patch.object(webserver, "_require_session", return_value=("session", {}, {"csrf_token": "valid-csrf"})):
            with webserver.app.test_client() as client:
                response = client.post("/api/guild/123456789012345/config", json={}, headers={
                    "Origin": "http://localhost:8080", "X-CSRF-Token": "wrong-csrf"
                })
        self.assertEqual(response.status_code, 403)

    def test_config_rejects_channel_the_bot_cannot_access(self):
        import webserver

        guild_id = "123456789012345"
        with patch.object(webserver, "_session_token", return_value="access-placeholder"), \
             patch.object(webserver, "_fetch_discord_guilds", return_value=[{"id": guild_id, "permissions": 8, "owner": False}]), \
             patch.object(webserver, "_require_session", return_value=("session", {}, {"csrf_token": "valid-csrf"})), \
             patch.object(webserver, "_fetch_bot_channels", return_value=[{"id": "999999999999999", "type": 0}]), \
             patch.object(webserver, "_sb_upsert", return_value=True) as upsert_mock:
            with webserver.app.test_client() as client:
                response = client.post(f"/api/guild/{guild_id}/config", json={
                    "skullboard_channel_id": "888888888888888",
                    "min_skulls": 1,
                    "pin_threshold": 0,
                    "prefix": "sk!",
                }, headers={"Origin": "http://localhost:8080", "X-CSRF-Token": "valid-csrf"})

        self.assertEqual(response.status_code, 400)
        self.assertIn("canal", response.get_json()["error"].lower())
        upsert_mock.assert_not_called()

    def test_expired_session_is_rejected_without_fallback(self):
        import webserver
        with patch.object(webserver, "_session_credentials", return_value=None), \
             patch.object(webserver, "_session_cipher", SessionCipher(Fernet.generate_key().decode())), \
             patch.object(webserver, "SUPABASE_URL", "https://db.invalid"), \
             patch.object(webserver, "SUPABASE_KEY", "service-role-placeholder"):
            with webserver.app.test_client() as client:
                client.set_cookie(webserver.SESSION_COOKIE, "expired-session-id")
                response = client.get("/api/auth/me")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.get_json()["error"], "Sesión expirada")

    def test_supabase_failure_returns_503_and_never_creates_session(self):
        import webserver
        with patch.object(webserver, "_session_cipher", SessionCipher(Fernet.generate_key().decode())), \
             patch.object(webserver, "SUPABASE_URL", "https://db.invalid"), \
             patch.object(webserver, "SUPABASE_KEY", "service-role-placeholder"), \
             patch.object(webserver, "_sb_select_required", side_effect=SessionSecurityError("store unavailable")):
            with webserver.app.test_client() as client:
                client.set_cookie(webserver.SESSION_COOKIE, "a" * 43)
                response = client.get("/api/auth/me")
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("Set-Cookie", response.headers)

    def test_logout_invalidates_persisted_session_and_clears_cookie(self):
        import webserver
        cipher = SessionCipher(Fernet.generate_key().decode())
        session_id, row = new_session(cipher, "123", "access-secret", "refresh-secret",
                                      datetime.now(timezone.utc), "valid-csrf")
        bundle = cipher.decrypt(row["token_bundle"])
        with patch.object(webserver, "_session_cipher", cipher), \
             patch.object(webserver, "_require_session", return_value=(session_id, row, bundle)), \
             patch.object(webserver, "_sb_delete", return_value=True) as delete_mock, \
             patch.object(webserver.requests, "post", return_value=type("Response", (), {"status_code": 204})()), \
             patch.object(webserver, "_clear_discord_cache"):
            with webserver.app.test_client() as client:
                client.set_cookie(webserver.SESSION_COOKIE, session_id)
                response = client.post("/api/auth/logout", headers={
                    "Origin": "http://localhost:8080", "X-CSRF-Token": "valid-csrf"
                })
        self.assertEqual(response.status_code, 200)
        delete_mock.assert_called_once()
        self.assertIn("Max-Age=0", response.headers["Set-Cookie"])

    def test_disconnect_revokes_grant_and_removes_all_user_sessions(self):
        import webserver

        cipher = SessionCipher(Fernet.generate_key().decode())
        session_id, row = new_session(cipher, "123", "access-secret", "refresh-secret",
                                      datetime.now(timezone.utc), "valid-csrf")
        bundle = cipher.decrypt(row["token_bundle"])
        revoke_response = type("Response", (), {"status_code": 204})()
        with patch.object(webserver, "_session_cipher", cipher), \
             patch.object(webserver, "DISCORD_CLIENT_SECRET", "client-secret"), \
             patch.object(webserver, "_require_session", return_value=(session_id, row, bundle)), \
             patch.object(webserver, "_sb_delete", return_value=True) as delete_mock, \
             patch.object(webserver.requests, "post", return_value=revoke_response) as revoke_mock, \
             patch.object(webserver, "_clear_discord_cache"):
            with webserver.app.test_client() as client:
                client.set_cookie(webserver.SESSION_COOKIE, session_id)
                response = client.post("/api/auth/disconnect", headers={
                    "Origin": "http://localhost:8080", "X-CSRF-Token": "valid-csrf"
                })

        self.assertEqual(response.status_code, 200)
        revoke_mock.assert_called_once()
        delete_mock.assert_called_once_with("dashboard_sessions", {"discord_user_id": "eq.123"}, require_match=True)
        self.assertIn("Max-Age=0", response.headers["Set-Cookie"])

    def test_dashboard_reload_checks_cookie_session_before_guilds(self):
        frontend = (ROOT / "legal/dashboard.html").read_text(encoding="utf-8")
        self.assertLess(frontend.index("/api/auth/me"), frontend.index("/api/auth/guilds"))
        self.assertIn("rememberOAuthState(state)", frontend)
        self.assertIn("forgetOAuthState(state)", frontend)
        self.assertIn("slice(-4)", frontend)
        self.assertIn("history.replaceState", frontend)

    def test_frontend_exposes_explicit_oauth_failure_states(self):
        frontend = (ROOT / "legal/dashboard.html").read_text(encoding="utf-8")
        self.assertIn("access_denied", frontend)
        self.assertIn("Abriendo Discord", frontend)
        self.assertIn("pageshow", frontend)

    def test_frontend_exposes_explicit_discord_disconnect_action(self):
        frontend = (ROOT / "legal/dashboard.html").read_text(encoding="utf-8")
        self.assertIn("btn-dropdown-disconnect", frontend)
        self.assertIn("/api/auth/disconnect", frontend)

    def test_settings_save_waits_for_dirty_loaded_form(self):
        frontend = (ROOT / "legal/dashboard.html").read_text(encoding="utf-8")
        self.assertIn("settingsDirty", frontend)
        self.assertIn("Cambios sin guardar", frontend)
        self.assertIn("!settingsDirty", frontend)

    def test_production_frontend_uses_same_origin_api_proxy(self):
        legal = "".join(path.read_text(encoding="utf-8") for path in (ROOT / "legal").glob("*.html"))
        self.assertNotIn("skullboard-fqf1.onrender.com/api", legal)
        self.assertIn('"/api/:path*"', (ROOT / "vercel.json").read_text(encoding="utf-8"))
        self.assertIn("url.pathname.startsWith('/api/')", (ROOT / "legal/sw.js").read_text(encoding="utf-8"))

    def test_local_session_cookie_is_usable_without_https(self):
        import webserver

        self.assertEqual(webserver._session_cookie_name("development"), "skullboard_session")
        self.assertFalse(webserver._session_cookie_secure("development"))
        self.assertEqual(webserver._session_cookie_name("production"), "__Host-skullboard_session")
        self.assertTrue(webserver._session_cookie_secure("production"))

    def test_status_does_not_fabricate_bot_health_without_provider(self):
        import webserver

        with patch.object(webserver, "_bot_status_provider", None), \
             patch.object(webserver, "SUPABASE_URL", None), \
             patch.object(webserver, "SUPABASE_KEY", None), \
             patch.object(webserver, "_system_status_cache", {"ts": 0.0, "data": {}}):
            with webserver.app.test_client() as client:
                response = client.get("/api/status")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["bot"]["status"], "unknown")
        self.assertFalse(payload["bot"]["online"])
        self.assertEqual(payload["bot"]["uptime_seconds"], None)

    def test_frontend_autoredirects_to_discord_oauth_when_unauthenticated(self):
        frontend = (ROOT / "legal/dashboard.html").read_text(encoding="utf-8")
        self.assertIn("userRes.status === 401", frontend)
        self.assertIn("triggerDiscordAuth()", frontend)
        self.assertIn("urlParams.has('logged_out')", frontend)
        self.assertIn("authResult.exchanged", frontend)
        self.assertIn("heading.textContent = title", frontend)


if __name__ == "__main__":
    unittest.main()
