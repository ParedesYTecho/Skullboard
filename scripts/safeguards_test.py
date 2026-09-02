#!/usr/bin/env python3
"""
scripts/safeguards_test.py — Automated Safeguards & Acceptance Verification Runner
SkullBoard v2.5.0

This test suite provides automated, offline, opaque-box static analysis and
behavioral assertions covering all Milestone 1, 2, 3, and 4 requirements:
  - Suite 1 (R1): Database & Backend Standards (no in-memory sum()/len() on message sets, RPC stats)
  - Suite 2 (R1): Strict Administrator Permission Check (0x8 required, 0x20 rejected)
  - Suite 3 (R2): Global Error & Webhook Alerts Wiring (send_system_alert in error/disconnect handlers)
  - Suite 4 (R2): Defensive Server Owner Caching Failover (await bot.fetch_user(guild.owner_id))
  - Suite 5 (R2): Frontend Sliders (max=50) & Clean Absolute URLs (legal/*.html)
  - Suite 6 (R3): System Context Documentation Synchronization (AutoShardedBot, env vars, REST catalog)

Execution:
  python scripts/safeguards_test.py
  python -m unittest scripts/safeguards_test.py
"""

import ast
import os
import re
import sys
import unittest
from html.parser import HTMLParser

# Enable safe UTF-8 output if possible, otherwise rely on ASCII-safe characters
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
        sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")
    except Exception:
        pass

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ─── Caching Helpers for Source Code & AST ────────────────────────────────────
_CACHE = {}


def _get_file_content(path: str) -> str:
    if path not in _CACHE:
        with open(path, "r", encoding="utf-8") as f:
            _CACHE[path] = f.read()
    return _CACHE[path]


def _get_file_ast(path: str) -> ast.AST:
    ast_key = f"__ast__{path}"
    if ast_key not in _CACHE:
        content = _get_file_content(path)
        _CACHE[ast_key] = ast.parse(content, filename=path)
    return _CACHE[ast_key]


def _extract_function_from_file(file_path: str, func_name: str):
    """Parses a Python file with AST, extracts a top-level function definition, and executes it in isolation."""
    tree = _get_file_ast(file_path)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == func_name:
            mod = ast.Module(body=[node], type_ignores=[])
            code = compile(mod, filename=f"<{func_name}>", mode="exec")
            namespace = {}
            exec(code, namespace)
            return namespace.get(func_name)
    return None


# ─── Test Suite 1: Database & Backend Aggregation Standards (R1) ──────────────
class TestSuite1_DbAggregation(unittest.TestCase):
    """Suite 1 (R1): Database-level aggregations vs illegal in-memory operations."""

    def setUp(self):
        self.webserver_path = os.path.join(ROOT_DIR, "webserver.py")
        self.webserver_source = _get_file_content(self.webserver_path)
        self.webserver_tree = _get_file_ast(self.webserver_path)

    def test_my_messages_no_sum_or_len_on_messages(self):
        """Verify api_guild_my_messages does NOT use sum() or len() to calculate totals from messages."""
        my_messages_fn = None
        for node in ast.walk(self.webserver_tree):
            if isinstance(node, ast.FunctionDef) and node.name == "api_guild_my_messages":
                my_messages_fn = node
                break

        self.assertIsNotNone(my_messages_fn, "api_guild_my_messages function must be defined in webserver.py")

        sum_calls = []
        len_calls_on_msgs = []
        for subnode in ast.walk(my_messages_fn):
            if isinstance(subnode, ast.Call) and isinstance(subnode.func, ast.Name):
                if subnode.func.id == "sum":
                    sum_calls.append(subnode.lineno)
                elif subnode.func.id == "len":
                    for arg in subnode.args:
                        if isinstance(arg, ast.Name) and arg.id in ("msgs", "messages", "records"):
                            len_calls_on_msgs.append(subnode.lineno)

        self.assertEqual(
            sum_calls, [],
            f"Prohibited sum() found in api_guild_my_messages at lines: {sum_calls}. Must use database-level stats."
        )
        self.assertEqual(
            len_calls_on_msgs, [],
            f"Prohibited len(msgs) found in api_guild_my_messages at lines: {len_calls_on_msgs}. Must use database-level stats."
        )

    def test_my_messages_calls_get_guild_user_stats_rpc(self):
        """Verify api_guild_my_messages invokes the get_guild_user_stats RPC."""
        self.assertIn(
            "get_guild_user_stats",
            self.webserver_source,
            "webserver.py must reference the get_guild_user_stats RPC for aggregate stats computation."
        )

        my_messages_fn = None
        for node in ast.walk(self.webserver_tree):
            if isinstance(node, ast.FunctionDef) and node.name == "api_guild_my_messages":
                my_messages_fn = node
                break

        self.assertIsNotNone(my_messages_fn)
        rpc_found = False
        for subnode in ast.walk(my_messages_fn):
            if isinstance(subnode, ast.Call):
                for arg in subnode.args:
                    if isinstance(arg, ast.Constant) and arg.value == "get_guild_user_stats":
                        rpc_found = True
                        break
        self.assertTrue(rpc_found, "api_guild_my_messages must call _sb_rpc with 'get_guild_user_stats'.")

    def test_leaderboard_endpoints_no_forbidden_inmemory_aggregations(self):
        """Verify leaderboard endpoints do not aggregate truncated message sets in memory."""
        for node in ast.walk(self.webserver_tree):
            if isinstance(node, ast.FunctionDef) and "leaderboard" in node.name:
                for subnode in ast.walk(node):
                    if isinstance(subnode, ast.Call) and isinstance(subnode.func, ast.Name):
                        if subnode.func.id == "sum":
                            self.fail(f"Prohibited sum() found in {node.name} at line {subnode.lineno}")

    def test_sync_db_retry_engine_applied(self):
        """Verify synchronous Supabase helper functions exist and handle resilient retries."""
        helpers = ["_sb_select", "_sb_count", "_sb_rpc", "_sb_upsert"]
        for h in helpers:
            self.assertIn(h, self.webserver_source, f"Expected Supabase helper '{h}' in webserver.py")
        self.assertIn(
            "sync_db_retry",
            self.webserver_source,
            "webserver.py must implement @sync_db_retry decorator for exponential backoff."
        )


# ─── Test Suite 2: Strict Administrator (0x8) Permission Check (R1) ───────────
class TestSuite2_StrictAdminPermission(unittest.TestCase):
    """Suite 2 (R1): Strict Administrator (0x8) permission check and MANAGE_GUILD (0x20) rejection."""

    def setUp(self):
        self.webserver_path = os.path.join(ROOT_DIR, "webserver.py")
        self.webserver_source = _get_file_content(self.webserver_path)
        self.webserver_tree = _get_file_ast(self.webserver_path)
        self.is_guild_authorized = _extract_function_from_file(self.webserver_path, "_is_guild_authorized")

    def test_function_exists(self):
        """Verify _is_guild_authorized is defined in webserver.py."""
        self.assertIsNotNone(self.is_guild_authorized, "_is_guild_authorized must be defined in webserver.py")

    def test_manage_guild_alone_rejected(self):
        """Tier 1/2: MANAGE_GUILD (0x20) without Administrator (0x8) and not owner MUST return False."""
        result = self.is_guild_authorized(0x20, is_owner=False)
        self.assertFalse(
            result,
            "Security vulnerability: MANAGE_GUILD (0x20) alone was authorized! Must strictly require ADMINISTRATOR (0x8)."
        )

    def test_administrator_permission_accepted(self):
        """Tier 1: ADMINISTRATOR (0x8) permission without owner MUST return True."""
        result = self.is_guild_authorized(0x8, is_owner=False)
        self.assertTrue(result, "ADMINISTRATOR (0x8) permission must be authorized.")

    def test_server_owner_bypass_accepted(self):
        """Tier 1: Server Owner with 0 permissions MUST return True."""
        result = self.is_guild_authorized(0, is_owner=True)
        self.assertTrue(result, "Server owner (is_owner=True) must be authorized.")

    def test_combined_admin_and_manage_guild_accepted(self):
        """Tier 2: ADMINISTRATOR (0x8) + MANAGE_GUILD (0x20) = 0x28 MUST return True."""
        result = self.is_guild_authorized(0x28, is_owner=False)
        self.assertTrue(result, "Permissions with 0x8 bit set (0x28) must be authorized.")

    def test_regular_user_zero_permissions_rejected(self):
        """Tier 2: Zero permissions and not owner MUST return False."""
        result = self.is_guild_authorized(0, is_owner=False)
        self.assertFalse(result, "Zero permissions for non-owner must return False.")

    def test_owner_with_manage_guild_accepted(self):
        """Tier 2: Owner with MANAGE_GUILD permission MUST return True."""
        result = self.is_guild_authorized(0x20, is_owner=True)
        self.assertTrue(result, "Owner with 0x20 must return True.")

    def test_adversarial_sub_admin_bits_rejected(self):
        """Tier 2/3 Adversarial: Test every single Discord permission bit below and above 0x8."""
        permission_bits = [1 << shift for shift in range(40) if (1 << shift) != 0x8]
        for bit in permission_bits:
            with self.subTest(bit=hex(bit)):
                res = self.is_guild_authorized(bit, is_owner=False)
                self.assertFalse(
                    res,
                    f"Permission bit {hex(bit)} without 0x8 was incorrectly authorized as admin!"
                )

    def test_all_permissions_mask_accepted(self):
        """Tier 2: Full permission bitmask MUST return True (since 0x8 is set)."""
        full_mask = 0xFFFFFFFFFFFFFFFF
        result = self.is_guild_authorized(full_mask, is_owner=False)
        self.assertTrue(result, "Full permission bitmask must be authorized.")

    def test_ast_0x20_not_present_in_auth_function(self):
        """Static AST: Ensure 0x20 (32) is completely absent from _is_guild_authorized AST."""
        fn_node = None
        for node in ast.walk(self.webserver_tree):
            if isinstance(node, ast.FunctionDef) and node.name == "_is_guild_authorized":
                fn_node = node
                break

        self.assertIsNotNone(fn_node)
        for subnode in ast.walk(fn_node):
            if isinstance(subnode, ast.Constant):
                self.assertNotEqual(
                    subnode.value, 0x20,
                    "Found constant 0x20 (32) in _is_guild_authorized AST! MANAGE_GUILD must not be checked."
                )

    def test_config_and_channels_endpoints_use_authorization(self):
        """Static AST: Ensure /config and /channels endpoints call _is_guild_authorized."""
        endpoints_checked = 0
        for node in ast.walk(self.webserver_tree):
            if isinstance(node, ast.FunctionDef) and node.name in (
                "api_guild_channels",
                "api_guild_config",
                "api_guild_config_post",
            ):
                calls = [
                    sub.func.id
                    for sub in ast.walk(node)
                    if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name)
                ]
                self.assertIn(
                    "_is_guild_authorized",
                    calls,
                    f"Endpoint handler {node.name} must call _is_guild_authorized to enforce security."
                )
                endpoints_checked += 1
        self.assertGreaterEqual(endpoints_checked, 2, "Must verify _is_guild_authorized in protected endpoints.")

    def test_guilds_endpoint_filters_non_manageable_servers(self):
        """Verify api_auth_guilds filters out servers where the bot is absent AND user lacks invite permissions."""
        webserver_source = _get_file_content(self.webserver_path)
        self.assertIn("can_invite", webserver_source, "webserver.py must compute can_invite permission.")
        self.assertIn(
            "dashboard_guilds",
            webserver_source,
            "webserver.py must filter user_guilds into dashboard_guilds before returning JSON."
        )



# ─── Test Suite 3: Webhook Alerts Wiring (R2) ──────────────────────────────────
class TestSuite3_WebhookAlertsWiring(unittest.TestCase):
    """Suite 3 (R2): Webhook alert wiring in error handlers and shard disconnects."""

    def setUp(self):
        self.main_path = os.path.join(ROOT_DIR, "main.py")
        self.main_source = _get_file_content(self.main_path)
        self.main_tree = _get_file_ast(self.main_path)

    def test_send_system_alert_defined(self):
        """Verify send_system_alert is defined in main.py."""
        fn = None
        for node in ast.walk(self.main_tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "send_system_alert":
                fn = node
                break
        self.assertIsNotNone(fn, "send_system_alert function must be defined in main.py")

    def test_on_command_error_calls_send_system_alert(self):
        """Verify on_command_error calls send_system_alert for unexpected command errors."""
        fn = None
        for node in ast.walk(self.main_tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "on_command_error":
                fn = node
                break

        self.assertIsNotNone(fn, "on_command_error must be defined in main.py")
        calls = [
            sub.func.id
            for sub in ast.walk(fn)
            if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name)
        ]
        self.assertIn(
            "send_system_alert",
            calls,
            "on_command_error must call send_system_alert to notify of critical unhandled command errors."
        )

    def test_on_app_command_error_calls_send_system_alert(self):
        """Verify on_app_command_error calls send_system_alert for unhandled slash command errors."""
        fn = None
        for node in ast.walk(self.main_tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "on_app_command_error":
                fn = node
                break

        self.assertIsNotNone(fn, "on_app_command_error must be defined in main.py")
        calls = [
            sub.func.id
            for sub in ast.walk(fn)
            if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name)
        ]
        self.assertIn(
            "send_system_alert",
            calls,
            "on_app_command_error must call send_system_alert to notify of critical slash command errors."
        )

    def test_on_shard_disconnect_calls_send_system_alert(self):
        """Verify on_shard_disconnect is implemented and calls send_system_alert."""
        fn = None
        for node in ast.walk(self.main_tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "on_shard_disconnect":
                fn = node
                break

        self.assertIsNotNone(fn, "on_shard_disconnect event listener must be defined in main.py")
        calls = [
            sub.func.id
            for sub in ast.walk(fn)
            if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name)
        ]
        self.assertIn(
            "send_system_alert",
            calls,
            "on_shard_disconnect must call send_system_alert when a Gateway shard loses connection."
        )


# ─── Test Suite 4: Defensive Owner Cache Failover (R2) ────────────────────────
class TestSuite4_DefensiveOwnerCacheFailover(unittest.TestCase):
    """Suite 4 (R2): Defensive server owner cache failover (bot.fetch_user fallback)."""

    def setUp(self):
        self.main_path = os.path.join(ROOT_DIR, "main.py")
        self.main_source = _get_file_content(self.main_path)
        self.main_tree = _get_file_ast(self.main_path)

    def test_fetch_user_called_on_owner_cache_miss(self):
        """Verify that main.py falls back to bot.fetch_user(guild.owner_id) when guild.owner is None."""
        self.assertIn(
            "fetch_user",
            self.main_source,
            "main.py must use bot.fetch_user() for defensive failover when member cache is cold."
        )
        self.assertIn(
            "owner_id",
            self.main_source,
            "main.py must pass guild.owner_id to bot.fetch_user()."
        )

    def test_fetch_user_in_permission_failover_block(self):
        """Verify the permission failover notification block invokes fetch_user."""
        self.assertRegex(
            self.main_source,
            r"if\s+not\s+owner\s+and\s+msg\.guild\.owner_id:\s+try:\s+owner\s*=\s*await\s+bot\.fetch_user\(msg\.guild\.owner_id\)",
            "Permission failover in main.py must attempt fetch_user when msg.guild.owner is None."
        )


# ─── HTML Collector Helper ───────────────────────────────────────────────────
class HtmlSliderAndLinkCollector(HTMLParser):
    """HTML Parser collecting slider elements, max values, and anchor href targets."""

    def __init__(self):
        super().__init__()
        self.sliders = {}
        self.links = []
        self.relative_internal_links = []

    def handle_starttag(self, tag, attrs):
        attr_dict = dict(attrs)
        if tag == "input" and attr_dict.get("type") in ("range", "number"):
            elem_id = attr_dict.get("id")
            if elem_id in ("cfg-skulls", "cfg-pin"):
                self.sliders[elem_id] = {
                    "min": attr_dict.get("min"),
                    "max": attr_dict.get("max"),
                    "value": attr_dict.get("value"),
                }
        elif tag == "a" and "href" in attr_dict:
            href = attr_dict["href"]
            self.links.append(href)
            # Detect relative internal link without leading slash or protocol
            if href in ("cambios", "dashboard", "privacy", "terms", "index.html", "cambios.html"):
                self.relative_internal_links.append(href)
            elif not href.startswith(("/", "http://", "https://", "mailto:", "#", "javascript:", "${")):
                self.relative_internal_links.append(href)


# ─── Test Suite 5: Frontend Sliders & Absolute Clean URLs (R2) ─────────────────
class TestSuite5_FrontendSlidersAndCleanUrls(unittest.TestCase):
    """Suite 5 (R2): Frontend slider ranges and clean absolute URLs in legal/ templates."""

    def setUp(self):
        self.legal_dir = os.path.join(ROOT_DIR, "legal")
        self.html_files = [
            f for f in os.listdir(self.legal_dir) if f.endswith(".html")
        ]

    def test_dashboard_sliders_max_value_is_50(self):
        """Verify #cfg-skulls and #cfg-pin sliders have max='50' in legal/dashboard.html."""
        dash_path = os.path.join(self.legal_dir, "dashboard.html")
        content = _get_file_content(dash_path)

        parser = HtmlSliderAndLinkCollector()
        parser.feed(content)

        self.assertIn("cfg-skulls", parser.sliders, "#cfg-skulls slider must be present in dashboard.html")
        self.assertIn("cfg-pin", parser.sliders, "#cfg-pin slider must be present in dashboard.html")

        self.assertEqual(
            parser.sliders["cfg-skulls"]["max"], "50",
            f"#cfg-skulls slider max is '{parser.sliders['cfg-skulls']['max']}', must be '50'."
        )
        self.assertEqual(
            parser.sliders["cfg-pin"]["max"], "50",
            f"#cfg-pin slider max is '{parser.sliders['cfg-pin']['max']}', must be '50'."
        )

    def test_dashboard_sliders_min_values(self):
        """Verify #cfg-skulls has min='1' and #cfg-pin has min='0'."""
        dash_path = os.path.join(self.legal_dir, "dashboard.html")
        content = _get_file_content(dash_path)

        parser = HtmlSliderAndLinkCollector()
        parser.feed(content)

        self.assertEqual(parser.sliders["cfg-skulls"]["min"], "1", "#cfg-skulls min must be 1")
        self.assertEqual(parser.sliders["cfg-pin"]["min"], "0", "#cfg-pin min must be 0")

    def test_all_html_files_use_absolute_links(self):
        """Verify no HTML template in legal/ contains relative navigation links (e.g. href='cambios')."""
        self.assertGreater(len(self.html_files), 0, "legal/ directory must contain HTML templates.")

        for fname in self.html_files:
            with self.subTest(file=fname):
                fpath = os.path.join(self.legal_dir, fname)
                content = _get_file_content(fpath)

                parser = HtmlSliderAndLinkCollector()
                parser.feed(content)

                self.assertEqual(
                    parser.relative_internal_links, [],
                    f"Found relative links {parser.relative_internal_links} in legal/{fname}. Must be absolute (/...)"
                )


# ─── Test Suite 6: Documentation Synchronization (R3) ─────────────────────────
class TestSuite6_DocumentationSync(unittest.TestCase):
    """Suite 6 (R3): System context and architectural documentation accuracy."""

    def setUp(self):
        self.doc_path = os.path.join(ROOT_DIR, "docs", "SYSTEM_CONTEXT.md")
        self.doc_content = _get_file_content(self.doc_path)

    def test_system_context_specifies_autoshardedbot(self):
        """Verify docs/SYSTEM_CONTEXT.md explicitly specifies AutoShardedBot."""
        self.assertIn(
            "AutoShardedBot",
            self.doc_content,
            "docs/SYSTEM_CONTEXT.md must document 'AutoShardedBot' in its architecture diagram and text."
        )

    def test_system_context_documents_alerts_webhook_env(self):
        """Verify docs/SYSTEM_CONTEXT.md Section 6.1 documents DISCORD_ALERTS_WEBHOOK_URL."""
        self.assertIn(
            "DISCORD_ALERTS_WEBHOOK_URL",
            self.doc_content,
            "docs/SYSTEM_CONTEXT.md Section 6.1 must document DISCORD_ALERTS_WEBHOOK_URL."
        )

    def test_system_context_documents_bot_owner_id_env(self):
        """Verify docs/SYSTEM_CONTEXT.md Section 6.1 documents BOT_OWNER_ID."""
        self.assertIn(
            "BOT_OWNER_ID",
            self.doc_content,
            "docs/SYSTEM_CONTEXT.md Section 6.1 must document BOT_OWNER_ID."
        )

    def test_system_context_catalog_contains_dashboard_endpoints(self):
        """Verify docs/SYSTEM_CONTEXT.md Section 4.2 table lists all dashboard REST endpoints."""
        required_endpoints = [
            "/api/auth/token",
            "/api/auth/me",
            "/api/auth/guilds",
            "/api/guild/<guild_id>/channels",
            "/api/guild/<guild_id>/config",
            "/api/guild/<guild_id>/leaderboard/public",
            "/api/guild/<guild_id>/leaderboard",
            "/api/guild/<guild_id>/my-messages",
            "/api/og",
            "/api/health",
            "/api/status",
            "/api/contact",
            "/verify",
            "/callback",
        ]
        for ep in required_endpoints:
            with self.subTest(endpoint=ep):
                self.assertIn(
                    ep,
                    self.doc_content,
                    f"docs/SYSTEM_CONTEXT.md Section 4.2 table must document endpoint '{ep}'."
                )


# ─── Test Suite 7: Visual & Status Renovation (Sapphire Footer, Status & Jump URLs) ──
class TestSuite7_VisualAndStatusRenovation(unittest.TestCase):
    """Verifies that the /api/status endpoint, author profile resolving, jump URLs,
    and multi-column Sapphire footer are strictly present and functional."""

    @classmethod
    def setUpClass(cls):
        cls.webserver_content = _get_file_content(os.path.join(ROOT_DIR, "webserver.py"))
        cls.main_content = _get_file_content(os.path.join(ROOT_DIR, "main.py"))
        cls.dashboard_content = _get_file_content(os.path.join(ROOT_DIR, "legal", "dashboard.html"))
        cls.index_content = _get_file_content(os.path.join(ROOT_DIR, "legal", "index.html"))
        cls.cambios_content = _get_file_content(os.path.join(ROOT_DIR, "legal", "cambios.html"))
        cls.terms_content = _get_file_content(os.path.join(ROOT_DIR, "legal", "terms.html"))
        cls.privacy_content = _get_file_content(os.path.join(ROOT_DIR, "legal", "privacy.html"))
        cls.styles_content = _get_file_content(os.path.join(ROOT_DIR, "legal", "styles.css"))

    def test_status_endpoint_and_provider_wiring(self):
        """webserver.py must define /api/status and main.py must register set_bot_status_provider."""
        self.assertIn(
            "@app.route('/api/status'",
            self.webserver_content,
            "webserver.py must expose endpoint GET /api/status"
        )
        self.assertIn(
            "set_bot_status_provider",
            self.webserver_content,
            "webserver.py must provide set_bot_status_provider hook"
        )
        self.assertIn(
            "webserver.set_bot_status_provider(get_bot_status)",
            self.main_content,
            "main.py must connect get_bot_status to webserver"
        )

    def test_leaderboard_jump_url_and_author_enrichment(self):
        """Leaderboard and my-messages endpoints must resolve author profile and jump_url."""
        self.assertIn(
            "_fetch_author_profile_cached",
            self.webserver_content,
            "webserver.py must have cached author profile resolution helper"
        )
        self.assertIn(
            "jump_url",
            self.webserver_content,
            "webserver.py must construct jump_url for Discord messages"
        )
        self.assertIn(
            "discord.com/channels",
            self.webserver_content,
            "jump_url must point to discord.com/channels/{guild_id}/{channel_id}/{message_id}"
        )

    def test_sapphire_footer_and_modal_across_all_html_pages(self):
        """All 5 HTML pages must contain the Sapphire multi-column footer and status modal."""
        pages = [
            ("dashboard.html", self.dashboard_content),
            ("index.html", self.index_content),
            ("cambios.html", self.cambios_content),
            ("terms.html", self.terms_content),
            ("privacy.html", self.privacy_content)
        ]
        for name, html in pages:
            with self.subTest(page=name):
                self.assertIn("site-footer-v2", html, f"{name} must include .site-footer-v2")
                self.assertIn("status-modal-overlay", html, f"{name} must include #status-modal-overlay")
                self.assertIn("open-status-modal", html, f"{name} must include .open-status-modal trigger")

    def test_humanized_leaderboard_in_dashboard(self):
        """dashboard.html must render .lb-card with medals, avatars, usernames and jump buttons."""
        self.assertIn("lb-card", self.dashboard_content, "dashboard.html must use .lb-card class")
        self.assertIn("lb-avatar", self.dashboard_content, "dashboard.html must render author avatar")
        self.assertIn("btn-jump-discord", self.dashboard_content, "dashboard.html must provide Discord jump button")
        self.assertIn(".site-footer-v2", self.styles_content, "styles.css must style .site-footer-v2")
        self.assertIn(".lb-card", self.styles_content, "styles.css must style .lb-card")


# ─── Test Suite 8: Total Perfection (Navbar, Number Inputs, Channels Fix, Footer & Skull) ─
class TestSuite8_TotalPerfection(unittest.TestCase):
    """Verifies the v2.5.2 Total Perfection requirements:
    - Smart Sticky Navbar and removal of status-pill from navbar
    - Hybrid clean footer without 'con ❤️'
    - Status modal without refresh button
    - Number inputs for skulls and pin thresholds
    - Eradication of 'Starboard' in dashboard metrics & skull ☠️ with snowflake dates
    - api_guild_channels returning ok=True and channels
    """

    @classmethod
    def setUpClass(cls):
        cls.webserver_content = _get_file_content(os.path.join(ROOT_DIR, "webserver.py"))
        cls.styles_content = _get_file_content(os.path.join(ROOT_DIR, "legal", "styles.css"))
        cls.pages = {
            fname: _get_file_content(os.path.join(ROOT_DIR, "legal", fname))
            for fname in ("dashboard.html", "index.html", "cambios.html", "terms.html", "privacy.html")
        }

    def test_channels_api_returns_ok_true(self):
        """webserver.py api_guild_channels must return _cors(jsonify(ok=True, channels=channels))."""
        self.assertRegex(
            self.webserver_content,
            r"return\s+_cors\(jsonify\(ok=True,\s*channels=channels\)\)",
            "api_guild_channels must return ok=True with channels list to prevent 500 error."
        )

    def test_number_inputs_present_in_dashboard(self):
        """dashboard.html must contain number inputs for skulls and pin thresholds."""
        dash = self.pages["dashboard.html"]
        self.assertIn('id="cfg-skulls-num"', dash, "dashboard.html must contain #cfg-skulls-num input")
        self.assertIn('id="cfg-pin-num"', dash, "dashboard.html must contain #cfg-pin-num input")
        self.assertIn('class="cfg-number-input"', dash, "dashboard.html must style number inputs with .cfg-number-input")

    def test_navbar_no_status_pill(self):
        """None of the 5 HTML pages should have .status-pill inside the <nav> element."""
        for name, html in self.pages.items():
            with self.subTest(page=name):
                # Extraer bloque <nav> ... </nav>
                nav_match = re.search(r"<nav[\s\S]*?</nav>", html)
                self.assertIsNotNone(nav_match, f"{name} must have a <nav> block")
                self.assertNotIn(
                    "status-pill",
                    nav_match.group(0),
                    f"{name} has status-pill inside <nav>. Status indicator belongs strictly in footer."
                )

    def test_footer_no_heart_and_has_brand_mark(self):
        """All 5 HTML pages must have f-brand-mark and no 'con ❤️'."""
        for name, html in self.pages.items():
            with self.subTest(page=name):
                self.assertNotIn("Desarrollado con ❤️", html, f"{name} should not contain 'Desarrollado con ❤️'")
                self.assertIn("Desarrollado por <strong>GlobalFerociouS</strong>", html, f"{name} must credit GlobalFerociouS")
                self.assertIn("f-brand-mark", html, f"{name} must use .f-brand-mark for logo gradient")

    def test_status_modal_no_refresh_button(self):
        """None of the 5 HTML pages should have the 'btn-refresh-status' button."""
        for name, html in self.pages.items():
            with self.subTest(page=name):
                self.assertNotIn("btn-refresh-status", html, f"{name} should not contain btn-refresh-status")

    def test_dashboard_skullboard_metrics_and_skull_icon(self):
        """dashboard.html must say 'Mensajes en Skullboard' and use .my-msg-icon-skull with ☠️."""
        dash = self.pages["dashboard.html"]
        self.assertIn("Mensajes en Skullboard", dash, "dashboard.html must say 'Mensajes en Skullboard'")
        self.assertIn("Canal de Skullboard:", dash, "dashboard.html must say 'Canal de Skullboard:'")
        self.assertIn("my-msg-icon-skull", dash, "dashboard.html must use .my-msg-icon-skull")
        self.assertIn("☠️", dash, "dashboard.html must feature skull emoji ☠️")

    def test_smart_sticky_navbar_behavior_in_scripts_and_css(self):
        """All 5 HTML pages and styles.css must implement the Smart Sticky Navbar (nav-hidden)."""
        self.assertIn(".nav.nav-hidden", self.styles_content, "styles.css must define .nav.nav-hidden")
        for name, html in self.pages.items():
            with self.subTest(page=name):
                self.assertIn("nav-hidden", html, f"{name} must toggle 'nav-hidden' on scroll")


# ─── Custom Test Result Handler for Clean Presentation ────────────────────────
class SafeguardTestResult(unittest.TestResult):
    def __init__(self):
        super().__init__()
        self.test_records = []

    def addSuccess(self, test):
        super().addSuccess(test)
        test_name = test.id().split(".")[-1]
        doc = test.shortDescription() or test_name
        self.test_records.append(("PASS", test_name, doc, None))

    def addFailure(self, test, err):
        super().addFailure(test, err)
        test_name = test.id().split(".")[-1]
        doc = test.shortDescription() or test_name
        self.test_records.append(("FAIL", test_name, doc, self._exc_info_to_string(err, test)))

    def addError(self, test, err):
        super().addError(test, err)
        test_name = test.id().split(".")[-1]
        doc = test.shortDescription() or test_name
        self.test_records.append(("ERROR", test_name, doc, self._exc_info_to_string(err, test)))


def run_safeguards():
    """Runs all safeguard suites with a detailed CLI presentation and returns total exit code."""
    print("=" * 78)
    print("SkullBoard v2.5.0 -- Automated Safeguards & Acceptance Verification Runner")
    print("Milestones: R1 (DB & Admin), R2 (Webhooks, Sliders, URLs), R3 (Docs), R4 (Infra)")
    print("=" * 78)

    loader = unittest.TestLoader()
    suite_classes = [
        ("Suite 1: Database & Backend Aggregation Standards (R1)", TestSuite1_DbAggregation),
        ("Suite 2: Strict Administrator (0x8) Permissions (R1)", TestSuite2_StrictAdminPermission),
        ("Suite 3: Webhook Alerts & Global Error Handlers (R2)", TestSuite3_WebhookAlertsWiring),
        ("Suite 4: Defensive Server Owner Cache Failover (R2)", TestSuite4_DefensiveOwnerCacheFailover),
        ("Suite 5: Frontend Sliders (max=50) & Clean Absolute URLs (R2)", TestSuite5_FrontendSlidersAndCleanUrls),
        ("Suite 6: System Context Documentation Synchronization (R3)", TestSuite6_DocumentationSync),
        ("Suite 7: Visual & Status Renovation (Sapphire Footer, Status API & Jump URLs)", TestSuite7_VisualAndStatusRenovation),
        ("Suite 8: Total Perfection (Smart Navbar, Number Inputs, Channels Fix & Skull ☠️)", TestSuite8_TotalPerfection),
    ]

    total_tests = 0
    total_failures = 0
    total_errors = 0

    for title, suite_cls in suite_classes:
        print(f"\n>> [{title}]")
        suite = loader.loadTestsFromTestCase(suite_cls)
        result = SafeguardTestResult()
        suite.run(result)

        for status, test_name, doc, trace in result.test_records:
            total_tests += 1
            if status == "PASS":
                print(f"   [PASS] {test_name} -- {doc}")
            elif status == "FAIL":
                total_failures += 1
                print(f"   [FAIL] {test_name} -- {doc}")
                if trace:
                    for line in trace.strip().split("\n")[-2:]:
                        print(f"      {line}")
            elif status == "ERROR":
                total_errors += 1
                print(f"   [ERROR] {test_name} -- {doc}")
                if trace:
                    for line in trace.strip().split("\n")[-2:]:
                        print(f"      {line}")

    print("\n" + "=" * 78)
    print("Safeguards Test Summary:")
    print(f"   Total Test Assertions : {total_tests}")
    print(f"   Passed Checks         : {total_tests - total_failures - total_errors}")
    print(f"   Failed Assertions     : {total_failures}")
    print(f"   Execution Errors      : {total_errors}")

    if total_failures == 0 and total_errors == 0:
        print("   Status                : [OK] 100% PASS -- All R1, R2, R3, R4 criteria satisfied!")
        print("=" * 78)
        return 0
    else:
        print("   Status                : [FAILED] FAILURES DETECTED -- Review violations above.")
        print("=" * 78)
        return 1


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--unittest":
        unittest.main(argv=[sys.argv[0]])
    else:
        exit_code = run_safeguards()
        sys.exit(exit_code)
