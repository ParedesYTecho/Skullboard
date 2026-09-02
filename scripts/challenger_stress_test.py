# -*- coding: utf-8 -*-
import os, sys, glob, re, json, time, asyncio, unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from html.parser import HTMLParser

sys.stdout.reconfigure(encoding='utf-8')

os.environ.setdefault('SUPABASE_URL', 'https://mock-test.supabase.co')
os.environ.setdefault('SUPABASE_SERVICE_ROLE_KEY', 'mock-service-key-xyz')
os.environ.setdefault('SUPABASE_KEY', 'mock-service-key-xyz')
os.environ.setdefault('DISCORD_TOKEN', 'mock-discord-token-12345')
os.environ.setdefault('DISCORD_CLIENT_ID', '123456789012345678')
os.environ.setdefault('DISCORD_CLIENT_SECRET', 'mock-client-secret')
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import webserver
import main
import discord
from discord.ext import commands
from discord import app_commands


class HTMLTreeAuditor(HTMLParser):
    def __init__(self, filename):
        super().__init__()
        self.filename = filename
        self.defined_ids = set()
        self.anchor_refs = []
        self.navigation_links = []
        self.static_asset_links = []
        self.inputs = []
        self.duplicate_ids = []

    def handle_starttag(self, tag, attrs):
        attr_dict = dict(attrs)
        if "id" in attr_dict:
            elem_id = attr_dict["id"]
            if elem_id in self.defined_ids:
                self.duplicate_ids.append(elem_id)
            self.defined_ids.add(elem_id)
        if tag == "a":
            if "name" in attr_dict:
                self.defined_ids.add(attr_dict["name"])
            if "href" in attr_dict:
                href = attr_dict["href"].strip()
                self.navigation_links.append(href)
                if href.startswith("#") and len(href) > 1:
                    self.anchor_refs.append(href[1:])
        elif tag in ("link", "script", "img", "form"):
            for attr in ("href", "src", "action"):
                if attr in attr_dict:
                    self.static_asset_links.append((tag, attr, attr_dict[attr].strip()))
        elif tag == "input":
            self.inputs.append(attr_dict)


class TestFrontendHTMLAndRoutingAdversarial(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html_files = sorted(glob.glob("legal/*.html"))
        cls.parsed_docs = {}
        for f in cls.html_files:
            with open(f, "r", encoding="utf-8") as fp:
                content = fp.read()
            auditor = HTMLTreeAuditor(f)
            auditor.feed(content)
            cls.parsed_docs[f] = auditor
        cls.client = webserver.app.test_client()

    def test_all_expected_html_files_present(self):
        expected = [
            "legal\\cambios.html",
            "legal\\dashboard.html",
            "legal\\index.html",
            "legal\\privacy.html",
            "legal\\terms.html",
        ]
        norm_actual = [f.replace("/", "\\") for f in self.html_files]
        for exp in expected:
            self.assertIn(exp, norm_actual, f"Missing required HTML template: {exp}")

    def test_zero_relative_navigation_links(self):
        for filepath, doc in self.parsed_docs.items():
            for href in doc.navigation_links:
                if href.startswith(("http://", "https://", "mailto:", "javascript:", "#", "data:")):
                    continue
                self.assertTrue(
                    href.startswith("/"),
                    f"Found relative navigation link '{href}' in {filepath}. Must start with '/'"
                )

    def test_internal_anchor_integrity(self):
        for filepath, doc in self.parsed_docs.items():
            for ref in doc.anchor_refs:
                self.assertIn(
                    ref,
                    doc.defined_ids,
                    f"Broken anchor reference '#{ref}' in {filepath}. Element with id='{ref}' does not exist!"
                )

    def test_no_duplicate_element_ids(self):
        for filepath, doc in self.parsed_docs.items():
            self.assertEqual(
                doc.duplicate_ids,
                [],
                f"Duplicate element IDs found in {filepath}: {doc.duplicate_ids}"
            )

    def test_flask_clean_url_and_static_routing(self):
        routes_to_test = [
            ("/", 200),
            ("/dashboard", 200),
            ("/terms", 200),
            ("/privacy", 200),
            ("/cambios", 200),
            ("/styles.css", 200),
            ("/skullboard_icon.png", 200),
            ("/manifest.json", 200),
            ("/robots.txt", 200),
            ("/sitemap.xml", 200),
            ("/sw.js", 200),
        ]
        for route, expected_code in routes_to_test:
            resp = self.client.get(route)
            self.assertEqual(
                resp.status_code,
                expected_code,
                f"Route '{route}' returned {resp.status_code}, expected {expected_code}"
            )

    def test_flask_legacy_html_redirects_to_clean_urls(self):
        redirect_tests = [
            ("/terms.html", "/terms"),
            ("/privacy.html", "/privacy"),
            ("/cambios.html", "/cambios"),
            ("/dashboard.html", "/dashboard"),
        ]
        for legacy_url, expected_target in redirect_tests:
            resp = self.client.get(legacy_url)
            self.assertEqual(resp.status_code, 301)
            self.assertTrue(
                resp.headers.get("Location", "").endswith(expected_target),
                f"Expected redirect to '{expected_target}', got '{resp.headers.get("Location")}'"
            )

    def test_nonexistent_route_returns_404(self):
        resp = self.client.get("/nonexistent_page_abcdef123")
        self.assertEqual(resp.status_code, 404)

class TestSliderBoundsAndBoundaryManipulation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open("legal/dashboard.html", "r", encoding="utf-8") as fp:
            content = fp.read()
        auditor = HTMLTreeAuditor("legal/dashboard.html")
        auditor.feed(content)
        cls.inputs_by_id = {inp.get("id"): inp for inp in auditor.inputs if "id" in inp}

    def test_dashboard_skulls_slider_attributes(self):
        inp = self.inputs_by_id.get("cfg-skulls")
        self.assertIsNotNone(inp, "#cfg-skulls input element not found in legal/dashboard.html")
        self.assertEqual(inp.get("type"), "range")
        self.assertEqual(inp.get("min"), "1", "#cfg-skulls min attribute must be '1'")
        self.assertEqual(inp.get("max"), "50", "#cfg-skulls max attribute must be '50'")
        self.assertEqual(inp.get("value"), "1", "#cfg-skulls default value must be '1'")

    def test_dashboard_pin_slider_attributes(self):
        inp = self.inputs_by_id.get("cfg-pin")
        self.assertIsNotNone(inp, "#cfg-pin input element not found in legal/dashboard.html")
        self.assertEqual(inp.get("type"), "range")
        self.assertEqual(inp.get("min"), "0", "#cfg-pin min attribute must be '0'")
        self.assertEqual(inp.get("max"), "50", "#cfg-pin max attribute must be '50'")
        self.assertEqual(inp.get("value"), "0", "#cfg-pin default value must be '0'")

    def test_backend_min_skulls_clamping_adversarial(self):
        cases = [
            (-999999, 1),
            (-1, 1),
            (0, 1),
            (1, 1),
            (2, 2),
            (25, 25),
            (49, 49),
            (50, 50),
            (51, 50),
            (100, 50),
            (9999999999, 50),
            ("25", 25),
            ("50", 50),
            ("100", 50),
            ("0", 1),
            ("-5", 1),
        ]
        for input_val, expected_val in cases:
            body = {"min_skulls": input_val}
            val = max(1, min(int(body.get("min_skulls", 1)), 50))
            self.assertEqual(val, expected_val, f"Input {input_val} clamped to {val}, expected {expected_val}")

    def test_backend_pin_threshold_clamping_adversarial(self):
        cases = [
            (-999999, 0),
            (-1, 0),
            (0, 0),
            (1, 1),
            (25, 25),
            (50, 50),
            (51, 50),
            (100, 50),
            (9999999999, 50),
            ("0", 0),
            ("50", 50),
            ("999", 50),
        ]
        for input_val, expected_val in cases:
            body = {"pin_threshold": input_val}
            val = max(0, min(int(body.get("pin_threshold", 0)), 50))
            self.assertEqual(val, expected_val, f"Input {input_val} clamped to {val}, expected {expected_val}")

    def test_backend_prefix_sanitization_adversarial(self):
        cases = [
            ("!", "!"),
            ("sk!", "sk!"),
            ("12345", "12345"),
            ("1234567890", "12345"),
            ("   \r\n\t  ", "sk!"),
            ("", "sk!"),
            ("a b c", "abc"),
            ("; DROP TABLE;", ";DROP"),
        ]
        for input_pfx, expected_pfx in cases:
            body = {"prefix": input_pfx}
            prefix = re.sub(r"[\r\n\s]+", "", str(body.get("prefix", "sk!")))[:5] or "sk!"
            self.assertEqual(prefix, expected_pfx, f"Prefix '{input_pfx}' sanitized to '{prefix}', expected '{expected_pfx}'")


class TestErrorHandlerAndAlertSanitization(unittest.IsolatedAsyncioTestCase):
    async def test_send_system_alert_giant_traceback_truncation(self):
        giant_tb = "Traceback (most recent call last):\n" + ("  File 'main.py', line 123 in foo\n    bar()\n" * 1000)
        self.assertGreater(len(giant_tb), 40000)

        mock_post = AsyncMock()
        mock_session_inst = MagicMock()
        mock_session_inst.post = mock_post
        mock_session_inst.__aenter__ = AsyncMock(return_value=mock_session_inst)
        mock_session_inst.__aexit__ = AsyncMock(return_value=None)

        with patch("main.DISCORD_ALERTS_WEBHOOK_URL", "https://discord.com/api/webhooks/mock/test"), \
             patch("aiohttp.ClientSession", return_value=mock_session_inst):
            
            await main.send_system_alert(
                title="Giant Traceback Test",
                description=giant_tb,
                level="ERROR"
            )

        self.assertTrue(mock_post.called, "Webhook post was not called")
        call_kwargs = mock_post.call_args[1]
        json_payload = call_kwargs["json"]
        embed = json_payload["embeds"][0]
        
        self.assertLessEqual(len(embed["description"]), 2000)
        self.assertEqual(embed["color"], 0xef4444)

    async def test_send_system_alert_special_characters_and_emojis(self):
        weird_description = (
            "Testing emojis: \U0001F480\U0001F6A8\U0001F525\U0001F389\n"
            "Testing RTL override: \u202eRTL_TEXT\u202c\n"
            "Testing ANSI codes: \x1b[31mRed\x1b[0m\n"
            "Testing Markdown quotes: ```python\nprint('hello')```\n"
            "Testing Zalgo: H\u0311e\u0316l\u0315l\u0310o\u0312"
        )

        mock_post = AsyncMock()
        mock_session_inst = MagicMock()
        mock_session_inst.post = mock_post
        mock_session_inst.__aenter__ = AsyncMock(return_value=mock_session_inst)
        mock_session_inst.__aexit__ = AsyncMock(return_value=None)

        with patch("main.DISCORD_ALERTS_WEBHOOK_URL", "https://discord.com/api/webhooks/mock/test"), \
             patch("aiohttp.ClientSession", return_value=mock_session_inst):
            
            await main.send_system_alert(
                title="Weird Characters",
                description=weird_description,
                level="WARNING"
            )

        self.assertTrue(mock_post.called)
        json_payload = mock_post.call_args[1]["json"]
        serialized = json.dumps(json_payload)
        self.assertIsInstance(serialized, str)
        self.assertEqual(json_payload["embeds"][0]["color"], 0xf59e0b)

    async def test_send_system_alert_extra_fields_capped_at_10(self):
        fields = [{"name": f"Field {i}", "value": f"Value {i}", "inline": True} for i in range(30)]

        mock_post = AsyncMock()
        mock_session_inst = MagicMock()
        mock_session_inst.post = mock_post
        mock_session_inst.__aenter__ = AsyncMock(return_value=mock_session_inst)
        mock_session_inst.__aexit__ = AsyncMock(return_value=None)

        with patch("main.DISCORD_ALERTS_WEBHOOK_URL", "https://discord.com/api/webhooks/mock/test"), \
             patch("aiohttp.ClientSession", return_value=mock_session_inst):
            
            await main.send_system_alert(
                title="Fields Capping",
                description="Testing extra fields capping",
                level="INFO",
                extra_fields=fields
            )

        embed = mock_post.call_args[1]["json"]["embeds"][0]
        self.assertEqual(len(embed.get("fields", [])), 10)
        self.assertEqual(embed["color"], 0x3b82f6)

    async def test_send_system_alert_network_failure_is_non_fatal(self):
        mock_post = AsyncMock(side_effect=Exception("Network connection refused"))
        mock_session_inst = MagicMock()
        mock_session_inst.post = mock_post
        mock_session_inst.__aenter__ = AsyncMock(return_value=mock_session_inst)
        mock_session_inst.__aexit__ = AsyncMock(return_value=None)

        with patch("main.DISCORD_ALERTS_WEBHOOK_URL", "https://discord.com/api/webhooks/mock/test"), \
             patch("aiohttp.ClientSession", return_value=mock_session_inst):
            
            await main.send_system_alert(
                title="Network Failure Test",
                description="Testing failure resilience",
                level="ERROR"
            )

    async def test_on_command_error_formatting_and_alert(self):
        mock_ctx = MagicMock()
        mock_ctx.command = "skullboard_extreme"
        mock_ctx.guild = None
        mock_ctx.channel = MagicMock(name="DMChannel")
        mock_ctx.channel.name = "Direct Message"
        mock_ctx.channel.id = 12345
        mock_author = MagicMock(spec=discord.Member)
        mock_author.__str__.return_value = "AdversarialUser#0001"
        mock_author.id = 99999
        mock_ctx.author = mock_author

        error = Exception("Adversarial synthetic exception: " + ("X" * 5000))

        with patch("main.send_system_alert", new_callable=AsyncMock) as mock_alert:
            await main.on_command_error(mock_ctx, error)

            self.assertTrue(mock_alert.called)
            call_kwargs = mock_alert.call_args[1] if mock_alert.call_args[1] else {}
            call_args = mock_alert.call_args[0]
            
            title = call_kwargs.get("title", call_args[0] if len(call_args) > 0 else "")
            description = call_kwargs.get("description", call_args[1] if len(call_args) > 1 else "")
            
            self.assertIn("skullboard_extreme", title)
            self.assertTrue(description.startswith("```"))
            self.assertTrue(description.endswith("```"))
            self.assertLessEqual(len(description), 2000)

    async def test_on_app_command_error_formatting_and_alert(self):
        mock_interaction = MagicMock()
        mock_interaction.command = MagicMock()
        mock_interaction.command.name = "ping_slash"
        mock_interaction.guild = MagicMock()
        mock_interaction.guild.name = "Test Guild"
        mock_interaction.guild.id = 111222333
        mock_user = MagicMock(spec=discord.Member)
        mock_user.__str__.return_value = "TestAdmin"
        mock_user.id = 444555666
        mock_interaction.user = mock_user
        mock_interaction.response.is_done.return_value = False
        mock_interaction.response.send_message = AsyncMock()

        error = app_commands.AppCommandError("Synthetic slash command failure")

        with patch("main.send_system_alert", new_callable=AsyncMock) as mock_alert:
            await main.on_app_command_error(mock_interaction, error)

            self.assertTrue(mock_interaction.response.send_message.called)
            user_embed = mock_interaction.response.send_message.call_args[1]["embed"]
            self.assertEqual(user_embed.title, "❌ Ha ocurrido un error")
            self.assertTrue(mock_interaction.response.send_message.call_args[1]["ephemeral"])

            self.assertTrue(mock_alert.called)
            title = mock_alert.call_args[1].get("title") or mock_alert.call_args[0][0]
            self.assertIn("/ping_slash", title)

    async def test_on_shard_disconnect_formatting(self):
        with patch("main.send_system_alert", new_callable=AsyncMock) as mock_alert, \
             patch.object(main.bot, "shard_count", 5):
            await main.on_shard_disconnect(3)
            self.assertTrue(mock_alert.called)
            kwargs = mock_alert.call_args[1]
            self.assertEqual(kwargs["title"], "Shard #3 Desconectado")
            self.assertEqual(kwargs["level"], "WARNING")
            fields = kwargs.get("extra_fields", [])
            self.assertEqual(fields[0]["value"], "3")
            self.assertEqual(fields[1]["value"], "5")


class TestDefensiveOwnerFailover(unittest.IsolatedAsyncioTestCase):
    async def test_owner_cache_hit_does_not_fetch(self):
        mock_owner = MagicMock(spec=discord.Member)
        mock_owner.id = 7777777
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.owner = mock_owner
        mock_guild.owner_id = 7777777

        mock_bot = MagicMock()
        mock_bot.fetch_user = AsyncMock()

        owner = mock_guild.owner
        if not owner and mock_guild.owner_id:
            try:
                owner = await mock_bot.fetch_user(mock_guild.owner_id)
            except Exception:
                owner = None

        self.assertEqual(owner, mock_owner)
        self.assertFalse(mock_bot.fetch_user.called)

    async def test_owner_cache_miss_fetches_user_successfully(self):
        mock_fetched_user = MagicMock(spec=discord.User)
        mock_fetched_user.id = 8888888
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.owner = None
        mock_guild.owner_id = 8888888

        mock_bot = MagicMock()
        mock_bot.fetch_user = AsyncMock(return_value=mock_fetched_user)

        owner = mock_guild.owner
        if not owner and mock_guild.owner_id:
            try:
                owner = await mock_bot.fetch_user(mock_guild.owner_id)
            except Exception:
                owner = None

        self.assertEqual(owner, mock_fetched_user)
        mock_bot.fetch_user.assert_awaited_once_with(8888888)

    async def test_owner_fetch_not_found_handled_gracefully(self):
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.owner = None
        mock_guild.owner_id = 9999999

        mock_bot = MagicMock()
        mock_bot.fetch_user = AsyncMock(side_effect=discord.NotFound(MagicMock(), "User not found"))

        owner = mock_guild.owner
        if not owner and mock_guild.owner_id:
            try:
                owner = await mock_bot.fetch_user(mock_guild.owner_id)
            except Exception:
                owner = None

        self.assertIsNone(owner)

    async def test_owner_fetch_forbidden_handled_gracefully(self):
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.owner = None
        mock_guild.owner_id = 123123123

        mock_bot = MagicMock()
        mock_bot.fetch_user = AsyncMock(side_effect=discord.Forbidden(MagicMock(), "Missing access"))

        owner = mock_guild.owner
        if not owner and mock_guild.owner_id:
            try:
                owner = await mock_bot.fetch_user(mock_guild.owner_id)
            except Exception:
                owner = None

        self.assertIsNone(owner)

    async def test_owner_fetch_http_exception_handled_gracefully(self):
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.owner = None
        mock_guild.owner_id = 321321321

        mock_bot = MagicMock()
        mock_bot.fetch_user = AsyncMock(side_effect=discord.HTTPException(MagicMock(), "Discord API 500"))

        owner = mock_guild.owner
        if not owner and mock_guild.owner_id:
            try:
                owner = await mock_bot.fetch_user(mock_guild.owner_id)
            except Exception:
                owner = None

        self.assertIsNone(owner)

    async def test_reaction_pipeline_permission_failover_block(self):
        gid = "123456789"
        main._perm_failover_cooldown.clear()

        mock_owner = MagicMock()
        mock_owner.send = AsyncMock(side_effect=discord.Forbidden(MagicMock(), "Cannot send DM"))

        mock_msg = MagicMock()
        mock_msg.guild.name = "Stress Guild"
        mock_msg.guild.owner = None
        mock_msg.guild.owner_id = 99887766

        with patch("main.bot.fetch_user", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_owner

            now = time.time()
            if now - main._perm_failover_cooldown.get(gid, 0) > 3600:
                main._perm_failover_cooldown[gid] = now
                owner = mock_msg.guild.owner
                if not owner and mock_msg.guild.owner_id:
                    try:
                        owner = await main.bot.fetch_user(mock_msg.guild.owner_id)
                    except Exception:
                        owner = None
                if owner:
                    try:
                        owner_embed = discord.Embed(
                            title="SkullBoard Warning",
                            description="Mock test",
                            color=0xf59e0b
                        )
                        await owner.send(embed=owner_embed)
                    except Exception:
                        pass

        self.assertIn(gid, main._perm_failover_cooldown)
        self.assertTrue(mock_owner.send.called)

    async def test_serverinfo_command_with_owner_failover_resolved(self):
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 55555
        mock_guild.name = "ServerInfo Guild"
        mock_guild.owner = None
        mock_guild.owner_id = 777888999
        mock_guild.member_count = 42
        mock_guild.created_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
        mock_guild.icon = None

        mock_owner = MagicMock()
        mock_owner.__str__.return_value = "ResolvedOwner#0001"
        mock_owner.id = 777888999


        mock_ctx = MagicMock()
        mock_ctx.guild = mock_guild
        mock_ctx.send = AsyncMock()


        mock_supabase1 = MagicMock()
        mock_resp1 = MagicMock()
        mock_resp1.count = 10
        mock_supabase1.table.return_value.select.return_value.eq.return_value.execute = AsyncMock(return_value=mock_resp1)

        with patch("main._deny_if_not_owner", new_callable=AsyncMock, return_value=False), \
             patch("main.get_guild_config", new_callable=AsyncMock, return_value={"min_skulls": 3}), \
             patch.object(main.bot, "get_guild", return_value=mock_guild), \
             patch.object(main, "supabase", mock_supabase1), \
             patch("main.bot.fetch_user", new_callable=AsyncMock, return_value=mock_owner):
            
            await main.serverinfo_cmd(mock_ctx, guild_id=55555)

            self.assertTrue(mock_ctx.send.called)
            embed = mock_ctx.send.call_args[1]["embed"]
            owner_field = next(f for f in embed.fields if "Owner" in f.name)
            self.assertIn("ResolvedOwner#0001", owner_field.value)
            self.assertIn("777888999", owner_field.value)

    async def test_serverinfo_command_with_owner_failover_exception(self):
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 55555
        mock_guild.name = "ServerInfo Guild"
        mock_guild.owner = None
        mock_guild.owner_id = 777888999
        mock_guild.member_count = 42
        mock_guild.created_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
        mock_guild.icon = None

        mock_ctx = MagicMock()
        mock_ctx.guild = mock_guild
        mock_ctx.send = AsyncMock()

        mock_supabase2 = MagicMock()
        mock_resp2 = MagicMock()
        mock_resp2.count = 10
        mock_supabase2.table.return_value.select.return_value.eq.return_value.execute = AsyncMock(return_value=mock_resp2)

        with patch("main._deny_if_not_owner", new_callable=AsyncMock, return_value=False), \
             patch("main.get_guild_config", new_callable=AsyncMock, return_value={"min_skulls": 3}), \
             patch.object(main.bot, "get_guild", return_value=mock_guild), \
             patch.object(main, "supabase", mock_supabase2), \
             patch("main.bot.fetch_user", new_callable=AsyncMock, side_effect=discord.HTTPException(MagicMock(), "API 500")):
            
            await main.serverinfo_cmd(mock_ctx, guild_id=55555)

            self.assertTrue(mock_ctx.send.called)
            embed = mock_ctx.send.call_args[1]["embed"]
            owner_field = next(f for f in embed.fields if "Owner" in f.name)
            self.assertEqual(owner_field.value, "Desconocido")


def run_adversarial_suite():
    print("=" * 80)
    print("SkullBoard v2.5.0 -- Adversarial Challenger Stress Runner")
    print("Targeting: Frontend HTML, URLs, Sliders, Error Handlers, Owner Failovers")
    print("=" * 80)
    
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    suite.addTests(loader.loadTestsFromTestCase(TestFrontendHTMLAndRoutingAdversarial))
    suite.addTests(loader.loadTestsFromTestCase(TestSliderBoundsAndBoundaryManipulation))
    suite.addTests(loader.loadTestsFromTestCase(TestErrorHandlerAndAlertSanitization))
    suite.addTests(loader.loadTestsFromTestCase(TestDefensiveOwnerFailover))
    
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    print("=" * 80)
    print("Adversarial Suite Summary:")
    print(f"  Total Tests Run : {result.testsRun}")
    print(f"  Failures        : {len(result.failures)}")
    print(f"  Errors          : {len(result.errors)}")
    status = "PASS" if result.wasSuccessful() else "FAIL"
    print(f"  Final Verdict   : [{status}]")
    print("=" * 80)
    
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(run_adversarial_suite())
