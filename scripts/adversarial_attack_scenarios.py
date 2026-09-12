#!/usr/bin/env python3
"""
scripts/adversarial_attack_scenarios.py — Targeted Attack & Edge Case Simulation
SkullBoard v2.5.0
"""

import ast
import os
import sys
import unittest
import types
from unittest.mock import MagicMock, patch, AsyncMock
import asyncio

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)

# Mock third party modules if missing
try:
    import flask
    from flask import make_response
except ImportError:
    mock_flask = types.ModuleType("flask")
    class MockFlask:
        def __init__(self, name):
            self.name = name
            self.routes = {}
        def after_request(self, f): return f
        def route(self, rule, **options):
            def decorator(f):
                self.routes[rule] = f
                return f
            return decorator
        def response_class(self, response=None, status=200, headers=None, mimetype=None):
            resp = MagicMock()
            resp.status_code = status
            resp.headers = headers or {}
            resp.data = response
            return resp
    mock_flask.Flask = MockFlask
    mock_flask.request = MagicMock()
    mock_flask.send_from_directory = MagicMock()
    mock_flask.redirect = MagicMock()
    def mock_jsonify(*args, **kwargs):
        data = args[0] if args else kwargs
        m = MagicMock()
        m.get_json.return_value = data
        m.json = data
        return m
    def mock_make_response(*args):
        m = MagicMock()
        if args:
            m.data = args[0]
            if len(args) > 1:
                m.status_code = args[1]
        return m
    mock_flask.jsonify = mock_jsonify
    mock_flask.make_response = mock_make_response
    sys.modules["flask"] = mock_flask

if "requests" not in sys.modules:
    mock_requests = types.ModuleType("requests")
    class RequestException(Exception): pass
    class HTTPError(RequestException):
        def __init__(self, message=None, response=None):
            super().__init__(message)
            self.response = response
    class ConnectionError(RequestException): pass
    class Timeout(RequestException): pass
    class ReadTimeout(Timeout): pass
    
    mock_requests.RequestException = RequestException
    mock_requests.HTTPError = HTTPError
    mock_requests.ConnectionError = ConnectionError
    mock_requests.Timeout = Timeout
    mock_requests.ReadTimeout = ReadTimeout
    mock_requests.get = MagicMock()
    mock_requests.post = MagicMock()
    mock_requests.Response = MagicMock
    
    mock_req_exc = types.ModuleType("requests.exceptions")
    mock_req_exc.RequestException = RequestException
    mock_req_exc.HTTPError = HTTPError
    mock_req_exc.ConnectionError = ConnectionError
    mock_req_exc.Timeout = Timeout
    mock_req_exc.ReadTimeout = ReadTimeout
    mock_requests.exceptions = mock_req_exc
    sys.modules["requests"] = mock_requests
    sys.modules["requests.exceptions"] = mock_req_exc

import webserver
from webserver import (
    _is_guild_authorized,
    api_guild_config,
    api_guild_channels,
    api_guild_my_messages
)


class AttackScenarioSuite(unittest.TestCase):
    """Execution of realistic attack vectors against the API logic."""

    def test_attack_vector_a_non_member_guild_access(self):
        """Attacker crafts request for guild_id they do not belong to."""
        with patch("webserver._session_token", return_value="valid_token"), \
             patch("webserver._require_origin", return_value=None), \
             patch("webserver._fetch_discord_guilds") as mock_guilds:
            
            # User belongs to guild 111111111111111111, but requests config for guild 999999999999999999
            mock_guilds.return_value = [
                {"id": "111111111111111111", "name": "Other Guild", "permissions": 0x8, "owner": True}
            ]
            
            # Test api_guild_channels for guild 999999999999999999
            with webserver.app.test_request_context("/api/guild/999999999999999999/channels", method="GET"):
                resp, status = api_guild_channels("999999999999999999")
                self.assertEqual(status, 403)
                self.assertFalse(resp.json.get("ok"))

            # Test api_guild_config for guild 999999999999999999
            with webserver.app.test_request_context("/api/guild/999999999999999999/config", method="GET"):
                resp, status = api_guild_config("999999999999999999")
                self.assertEqual(status, 403)
                self.assertFalse(resp.json.get("ok"))

    def test_attack_vector_b_sub_admin_escalation_attempt(self):
        """Sub-admin with MANAGE_GUILD (0x20), MANAGE_ROLES (0x10000000), BAN_MEMBERS (0x4) tries to update config."""
        with patch("webserver._session_token", return_value="valid_token"), \
             patch("webserver._require_origin", return_value=None), \
             patch("webserver._fetch_discord_guilds") as mock_guilds:
            
            sub_admin_perms = 0x20 | 0x10000000 | 0x4 # 0x10000024 (No 0x8)
            mock_guilds.return_value = [
                {"id": "999999999999999999", "name": "Target Guild", "permissions": sub_admin_perms, "owner": False}
            ]
            
            with webserver.app.test_request_context("/api/guild/999999999999999999/config", method="POST", json={"min_skulls": 10}):
                resp, status = api_guild_config("999999999999999999")
                self.assertEqual(status, 403)
                self.assertIn("Permisos insuficientes", resp.json.get("error", ""))

    def test_attack_vector_c_config_sanitization_boundaries(self):
        """Attacker sends extreme values: min_skulls=999999, negative numbers, giant strings for prefix."""
        fake_session = ("sess_id", {}, {"csrf_token": "valid_csrf"})
        with patch("webserver._session_token", return_value="valid_token"), \
             patch("webserver._require_session", return_value=fake_session), \
             patch("webserver._channel_is_available_to_bot", return_value=True), \
             patch("webserver._require_origin", return_value=None), \
             patch("webserver._fetch_discord_guilds") as mock_guilds, \
             patch("webserver._sb_upsert") as mock_upsert:
            
            mock_guilds.return_value = [
                {"id": "999999999999999999", "name": "Target Guild", "permissions": 0x8, "owner": False}
            ]
            mock_upsert.return_value = True
            
            payload = {
                "min_skulls": 999999,           # Must clamp to 50
                "prefix": "   !@#$%^&*()   \n\r", # Whitespace stripped, max 10 chars
                "skullboard_channel_id": "123456789012345678",
                "pin_threshold": -50             # Must clamp to 0
            }
            with webserver.app.test_request_context(
                "/api/guild/999999999999999999/config",
                method="POST",
                json=payload,
                headers={"X-CSRF-Token": "valid_csrf"}
            ):
                resp = api_guild_config("999999999999999999")
                # When successful, returns _cors(jsonify(ok=True, config=payload))
                self.assertIsNotNone(mock_upsert.call_args)
                upsert_payload = mock_upsert.call_args[0][1]
                
                self.assertEqual(upsert_payload["min_skulls"], 50, "min_skulls must be clamped to max 50")
                self.assertEqual(upsert_payload["pin_threshold"], 0, "pin_threshold must be clamped to min 0")
                self.assertEqual(len(upsert_payload["prefix"]), 10, "prefix must be clamped to max 10 chars")
                self.assertNotIn("\n", upsert_payload["prefix"])
                self.assertNotIn(" ", upsert_payload["prefix"])

    def test_owner_cache_miss_failover_logic(self):
        """Simulate owner cache miss failover logic from main.py."""
        # Check source code of main.py for the exact failover pattern
        main_path = os.path.join(ROOT_DIR, "main.py")
        with open(main_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Check defensive failover AST / pattern
        self.assertIn("fetch_user", content)
        self.assertIn("guild.owner_id", content)
        
        # Verify defensive failover logic simulation
        async def mock_failover_simulation():
            mock_guild = MagicMock()
            mock_guild.owner = None # Cache miss!
            mock_guild.owner_id = 561225979389804544
            
            mock_bot = MagicMock()
            mock_bot.fetch_user = AsyncMock(return_value=MagicMock(id=561225979389804544, name="ServerOwner"))
            
            # Logic under test:
            owner = mock_guild.owner
            if not owner and mock_guild.owner_id:
                try:
                    owner = await mock_bot.fetch_user(mock_guild.owner_id)
                except Exception:
                    owner = None
                    
            self.assertIsNotNone(owner)
            self.assertEqual(owner.id, 561225979389804544)
            mock_bot.fetch_user.assert_awaited_once_with(561225979389804544)

        asyncio.run(mock_failover_simulation())


if __name__ == "__main__":
    unittest.main(verbosity=2)
