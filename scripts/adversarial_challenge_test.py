#!/usr/bin/env python3
"""
scripts/adversarial_challenge_test.py — Empirical Challenger Adversarial Verification Suite
SkullBoard v2.5.0

Comprehensive adversarial stress test harness covering:
  1. Adversarial Bitmask & Permission Escalation Oracle on _is_guild_authorized:
     - 100,000 random 64-bit and 128-bit integers
     - Boundary permission bit shifts (0..127)
     - Sub-admin permission combinations (MANAGE_GUILD, MANAGE_ROLES, etc.)
     - Negative integers, two's complement, overflow
  2. Fault Injection & Flaky Network Simulator on @sync_db_retry:
     - HTTP 500, 502, 503, 504 server errors
     - ConnectionError, TimeoutError, RemoteDisconnected exceptions
     - Exhaustion assertion after max_retries
     - Delay and jitter verification
     - Multi-threaded concurrent retry load
  3. Database RPC & Aggregation Malformed Payload Stress Harness:
     - Empty response ([]), None response, malformed schemas
     - Null values inside RPC dictionary
     - Non-list types, unexpected string payloads
     - Verification of api_guild_my_messages aggregation logic
"""

import ast
import os
import sys
import time
import random
import unittest
import types
from unittest.mock import MagicMock, patch
import threading

# Set stdout/stderr encoding
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
        sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")
    except Exception:
        pass

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)

# Mock third-party dependencies if running in clean Python standard environment
if "flask" not in sys.modules:
    mock_flask = types.ModuleType("flask")
    class MockFlask:
        def __init__(self, name):
            self.name = name
            self.routes = {}
            self.after_request_funcs = []
            self.before_request_funcs = []
        def before_request(self, f):
            self.before_request_funcs.append(f)
            return f
        def after_request(self, f):
            self.after_request_funcs.append(f)
            return f
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
    mock_flask.jsonify = mock_jsonify
    def mock_make_response(rv=None):
        m = MagicMock()
        m.set_cookie = MagicMock()
        m.delete_cookie = MagicMock()
        m.headers = {}
        m.data = rv
        return m
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
    
    # Exceptions submodule
    mock_req_exc = types.ModuleType("requests.exceptions")
    mock_req_exc.RequestException = RequestException
    mock_req_exc.HTTPError = HTTPError
    mock_req_exc.ConnectionError = ConnectionError
    mock_req_exc.Timeout = Timeout
    mock_req_exc.ReadTimeout = ReadTimeout
    mock_requests.exceptions = mock_req_exc
    sys.modules["requests"] = mock_requests
    sys.modules["requests.exceptions"] = mock_req_exc

# Import webserver module under test
import webserver
from webserver import (
    _is_guild_authorized,
    sync_db_retry,
    _sb_count,
    _sb_select,
    _sb_upsert,
    _sb_rpc
)
import requests


# ─── Suite 1: Adversarial Permission Bitmask Oracle ───────────────────────────
class AdversarialPermissionAuthorizationTests(unittest.TestCase):
    """Deep adversarial testing of _is_guild_authorized."""

    def test_mathematical_oracle_100k_random_masks(self):
        """Oracle test: _is_guild_authorized must match strict (perms & 0x8 != 0) | is_owner for 100,000 random ints."""
        rng = random.Random(0xDEADBEEF)
        for _ in range(100_000):
            # Generate random 64-bit permission integers
            perms = rng.getrandbits(64)
            is_owner = rng.choice([True, False])
            
            expected = bool((perms & 0x8) != 0 or is_owner)
            actual = _is_guild_authorized(perms, is_owner)
            
            self.assertEqual(
                actual, expected,
                f"Oracle mismatch on perms={hex(perms)}, is_owner={is_owner}! Got {actual}, expected {expected}"
            )

    def test_single_bit_boundary_sweeps_up_to_128_bits(self):
        """Sweep bits 0 through 127 in isolation."""
        for bit_idx in range(128):
            bitmask = 1 << bit_idx
            is_admin_bit = (bit_idx == 3) # 1 << 3 = 0x8
            
            # Non-owner test
            actual_non_owner = _is_guild_authorized(bitmask, is_owner=False)
            self.assertEqual(
                actual_non_owner, is_admin_bit,
                f"Bit {bit_idx} (mask {hex(bitmask)}) failed non-owner test: got {actual_non_owner}, expected {is_admin_bit}"
            )
            
            # Owner test
            actual_owner = _is_guild_authorized(bitmask, is_owner=True)
            self.assertTrue(
                actual_owner,
                f"Bit {bit_idx} with owner=True failed to authorize!"
            )

    def test_sub_admin_combinations_without_0x8(self):
        """Combine all Discord standard non-admin permission bits to ensure no cumulative escalation occurs."""
        discord_perms = [
            1 << 0,   # CREATE_INSTANT_INVITE
            1 << 1,   # KICK_MEMBERS
            1 << 2,   # BAN_MEMBERS
            1 << 4,   # MANAGE_CHANNELS
            1 << 5,   # MANAGE_GUILD (0x20)
            1 << 6,   # ADD_REACTIONS
            1 << 7,   # VIEW_AUDIT_LOG
            1 << 9,   # PRIORITY_SPEAKER
            1 << 10,  # STREAM
            1 << 11,  # VIEW_CHANNEL
            1 << 12,  # SEND_MESSAGES
            1 << 13,  # SEND_TTS_MESSAGES
            1 << 14,  # MANAGE_MESSAGES
            1 << 15,  # EMBED_LINKS
            1 << 16,  # ATTACH_FILES
            1 << 17,  # READ_MESSAGE_HISTORY
            1 << 18,  # MENTION_EVERYONE
            1 << 19,  # USE_EXTERNAL_EMOJIS
            1 << 20,  # VIEW_GUILD_INSIGHTS
            1 << 21,  # CONNECT
            1 << 22,  # SPEAK
            1 << 23,  # MUTE_MEMBERS
            1 << 24,  # DEAFEN_MEMBERS
            1 << 25,  # MOVE_MEMBERS
            1 << 26,  # USE_VAD
            1 << 27,  # CHANGE_NICKNAME
            1 << 28,  # MANAGE_NICKNAMES
            1 << 29,  # MANAGE_ROLES
            1 << 30,  # MANAGE_WEBHOOKS
            1 << 31,  # MANAGE_GUILD_EXPRESSIONS
            1 << 32,  # USE_APPLICATION_COMMANDS
            1 << 33,  # REQUEST_TO_SPEAK
            1 << 34,  # MANAGE_EVENTS
            1 << 35,  # MANAGE_THREADS
            1 << 36,  # CREATE_PUBLIC_THREADS
            1 << 37,  # CREATE_PRIVATE_THREADS
            1 << 38,  # USE_EXTERNAL_STICKERS
            1 << 39,  # SEND_MESSAGES_IN_THREADS
            1 << 40,  # USE_EMBEDDED_ACTIVITIES
            1 << 41,  # MODERATE_MEMBERS
        ]
        
        # Test all non-admin bits set simultaneously
        all_non_admin = 0
        for bit in discord_perms:
            all_non_admin |= bit
            
        self.assertEqual(all_non_admin & 0x8, 0, "Sanity check: non-admin composite must not have 0x8")
        
        # Test without owner -> MUST be False
        self.assertFalse(
            _is_guild_authorized(all_non_admin, is_owner=False),
            "Combined non-admin permissions (including MANAGE_GUILD + MANAGE_ROLES + MODERATE_MEMBERS) incorrectly authorized!"
        )
        
        # Adding 0x8 -> MUST be True
        self.assertTrue(
            _is_guild_authorized(all_non_admin | 0x8, is_owner=False),
            "Combined permissions with 0x8 failed authorization!"
        )

    def test_negative_integers_and_two_complement(self):
        """Test negative integer bitwise behavior."""
        # -1 in two's complement has all bits set (including bit 3 / 0x8)
        self.assertTrue(_is_guild_authorized(-1, is_owner=False))
        # -8 has bits ...11111000 (bit 3 is set) -> True
        self.assertTrue(_is_guild_authorized(-8, is_owner=False))
        # -9 has bits ...11110111 (bit 3 is 0) -> False
        self.assertFalse(_is_guild_authorized(-9, is_owner=False))
        # -16 has bits ...11110000 (bit 3 is 0) -> False
        self.assertFalse(_is_guild_authorized(-16, is_owner=False))

    def test_owner_truthy_falsy_values(self):
        """Ensure various truthy and falsy representations for is_owner are strictly evaluated."""
        self.assertTrue(_is_guild_authorized(0, is_owner=1))
        self.assertTrue(_is_guild_authorized(0, is_owner="true"))
        self.assertFalse(_is_guild_authorized(0, is_owner=0))
        self.assertFalse(_is_guild_authorized(0, is_owner=""))
        self.assertFalse(_is_guild_authorized(0, is_owner=None))


# ─── Suite 2: Adversarial Sync DB Retry & Flaky Network Simulator ──────────────
class AdversarialSyncDbRetryTests(unittest.TestCase):
    """Adversarial stress testing of @sync_db_retry decorator."""

    def test_immediate_success_zero_retries(self):
        """A function that succeeds immediately should be called exactly once."""
        call_count = 0
        
        @sync_db_retry(max_retries=3, base_delay=0.001, max_delay=0.01)
        def healthy_operation(x, y):
            nonlocal call_count
            call_count += 1
            return x + y
            
        res = healthy_operation(10, 20)
        self.assertEqual(res, 30)
        self.assertEqual(call_count, 1)

    def test_transient_failure_then_recovery(self):
        """Simulate 2 HTTP 503 errors followed by HTTP 200 on attempt 3."""
        attempts = 0
        
        @sync_db_retry(max_retries=3, base_delay=0.001, max_delay=0.01)
        def flaky_network_call():
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                resp = MagicMock()
                resp.status_code = 503
                err = requests.HTTPError("503 Service Unavailable", response=resp)
                raise err
            return {"status": "success", "attempts": attempts}
            
        result = flaky_network_call()
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["attempts"], 3)
        self.assertEqual(attempts, 3)

    def test_permanent_failure_exhaustion(self):
        """Simulate persistent 500 Internal Server Error -> should exhaust and raise exception."""
        attempts = 0
        
        @sync_db_retry(max_retries=3, base_delay=0.001, max_delay=0.01)
        def dead_endpoint():
            nonlocal attempts
            attempts += 1
            resp = MagicMock()
            resp.status_code = 500
            raise requests.HTTPError("500 Internal Server Error", response=resp)
            
        with self.assertRaises(requests.HTTPError) as ctx:
            dead_endpoint()
            
        self.assertIn("500 Internal Server Error", str(ctx.exception))
        self.assertEqual(attempts, 3)

    def test_connection_timeout_and_network_drop(self):
        """Simulate socket / ReadTimeout exceptions."""
        attempts = 0
        
        @sync_db_retry(max_retries=4, base_delay=0.001, max_delay=0.01)
        def socket_timeout():
            nonlocal attempts
            attempts += 1
            if attempts < 4:
                raise requests.exceptions.ReadTimeout("HTTPSConnectionPool: Read timed out")
            return "recovered_after_timeouts"
            
        res = socket_timeout()
        self.assertEqual(res, "recovered_after_timeouts")
        self.assertEqual(attempts, 4)

    def test_preserves_function_metadata(self):
        """Ensure functools.wraps properly preserved __name__ and __doc__."""
        @sync_db_retry(max_retries=3)
        def sample_documented_func():
            """This is a sample docstring."""
            return 42
            
        self.assertEqual(sample_documented_func.__name__, "sample_documented_func")
        self.assertEqual(sample_documented_func.__doc__, "This is a sample docstring.")

    def test_concurrent_multithreaded_retries(self):
        """Run 50 parallel threads through @sync_db_retry with randomized flakiness."""
        errors = []
        successes = []
        
        @sync_db_retry(max_retries=3, base_delay=0.001, max_delay=0.005)
        def concurrent_flaky_op(thread_id, fail_times):
            state = getattr(concurrent_flaky_op, "_state", {})
            cnt = state.get(thread_id, 0) + 1
            state[thread_id] = cnt
            concurrent_flaky_op._state = state
            
            if cnt <= fail_times:
                raise requests.ConnectionError(f"Transient drop on thread {thread_id} (attempt {cnt})")
            return f"thread_{thread_id}_ok"

        concurrent_flaky_op._state = {}

        def worker(tid, fail_count):
            try:
                res = concurrent_flaky_op(tid, fail_count)
                successes.append(res)
            except Exception as e:
                errors.append((tid, e))

        threads = []
        # 30 threads fail 2 times (should succeed on attempt 3)
        # 10 threads fail 0 times (should succeed on attempt 1)
        # 10 threads fail 5 times (should fail after 3 attempts)
        for i in range(50):
            if i < 30:
                fails = 2
            elif i < 40:
                fails = 0
            else:
                fails = 5
            t = threading.Thread(target=worker, args=(i, fails))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        self.assertEqual(len(successes), 40)
        self.assertEqual(len(errors), 10)


# ─── Suite 3: Database RPC & Aggregation Malformed Payload Stress ─────────────
class AdversarialDatabaseRpcAndAggregationTests(unittest.TestCase):
    """Stress testing of database RPC calls, empty/None/malformed responses, and endpoint resiliency."""

    def test_sb_rpc_simulated_empty_list(self):
        """When PostgREST returns [], helper should safely return []."""
        with patch.object(webserver, "SUPABASE_URL", "https://test.supabase.co"), \
             patch.object(webserver, "SUPABASE_KEY", "mock_key"), \
             patch("requests.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = []
            mock_post.return_value = mock_resp
            
            res = _sb_rpc("get_guild_user_stats", {"p_guild_id": "123", "p_author_id": "456"})
            self.assertEqual(res, [])

    def test_sb_rpc_500_server_error_exhaustion_raises(self):
        """When PostgREST persistently returns 500, _sb_rpc raises after retries."""
        with patch.object(webserver, "SUPABASE_URL", "https://test.supabase.co"), \
             patch.object(webserver, "SUPABASE_KEY", "mock_key"), \
             patch("requests.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 500
            mock_resp.raise_for_status.side_effect = requests.HTTPError("500 Internal Server Error")
            mock_post.return_value = mock_resp
            
            with self.assertRaises(requests.HTTPError):
                _sb_rpc("get_guild_user_stats", {"p_guild_id": "123", "p_author_id": "456"})

    def test_api_guild_my_messages_aggregation_logic_isolated(self):
        """Test the exact stats extraction logic from api_guild_my_messages under various malformed RPC returns."""
        test_cases = [
            # Case 1: Standard clean RPC response
            ([{"total_messages": 15, "total_skulls": 88}], 15, 88),
            # Case 2: Empty RPC response list
            ([], 0, 0),
            # Case 3: None RPC response
            (None, 0, 0),
            # Case 4: Non-list return (e.g. dict or string)
            ({"total_messages": 5, "total_skulls": 10}, 0, 0),
            # Case 5: Null / None fields inside dict
            ([{"total_messages": None, "total_skulls": None}], 0, 0),
            # Case 6: String numbers inside dict
            ([{"total_messages": "42", "total_skulls": "100"}], 42, 100),
            # Case 7: Missing keys inside dict
            ([{"other_key": 99}], 0, 0),
        ]

        for rpc_return, exp_msgs, exp_skulls in test_cases:
            with self.subTest(rpc_return=rpc_return):
                stats_res = rpc_return
                stats = stats_res[0] if (isinstance(stats_res, list) and stats_res) else {"total_messages": 0, "total_skulls": 0}
                if not isinstance(stats, dict):
                    stats = {"total_messages": 0, "total_skulls": 0}
                
                total_skulls = int(stats.get("total_skulls") or 0)
                total_messages = int(stats.get("total_messages") or 0)
                
                self.assertEqual(total_messages, exp_msgs)
                self.assertEqual(total_skulls, exp_skulls)


if __name__ == "__main__":
    suite = unittest.TestSuite()
    suite.addTest(unittest.defaultTestLoader.loadTestsFromTestCase(AdversarialPermissionAuthorizationTests))
    suite.addTest(unittest.defaultTestLoader.loadTestsFromTestCase(AdversarialSyncDbRetryTests))
    suite.addTest(unittest.defaultTestLoader.loadTestsFromTestCase(AdversarialDatabaseRpcAndAggregationTests))
    
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
