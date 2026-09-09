---
name: discord-py-advanced-patterns
description: >-
  Expert guidance and patterns for high-scale Discord.py bot development.
  Covers raw Gateway event pipelines, asynchronous debouncing, message locks,
  interaction handling (Slash commands, buttons, select menus, modals),
  safe member caching, REST rate limit protection, and Supabase integration.
  Use whenever modifying main.py, implementing new Discord bot commands,
  handling reactions, or optimizing concurrency.
---

# Discord.py Advanced Patterns & High-Scale Architecture

This skill provides production-grade architectural patterns for building and maintaining high-scale Discord bots using `discord.py` (v2.x) with asynchronous databases (Supabase/PostgreSQL).

## Core Principles

1. **Always Prefer Raw Events for Scaled Gateways:**
   - Use `on_raw_reaction_add` and `on_raw_reaction_remove` over `on_reaction_add`. Raw events fire regardless of whether messages are cached in memory.
   - Extract `payload.guild_id`, `payload.channel_id`, `payload.message_id`, `payload.user_id`, and `payload.emoji` directly.

2. **Asynchronous Debouncing & Event Coalescing:**
   - Burst reactions on viral messages must be coalesced to prevent duplicate database writes or duplicate webhook/embed posts.
   - Use a generational timer handle (`loop.call_later`) with a 1.5s - 2.0s debounce window.

3. **Keyed Locks for Per-Message Mutual Exclusion:**
   - Always wrap message update workflows in a keyed lock (`KeyedAsyncLock`) per `message_id`.
   - Prevent race conditions where two simultaneous reactions trigger concurrent reposts.

4. **Safe Member and Nickname Resolution:**
   - Attempt local cache resolution first (`guild.get_member(uid)`).
   - Fall back to `guild.fetch_member(uid)` only when uncached.
   - Fall back to `bot.get_user(uid)` / `bot.fetch_user(uid)` if the user left the server.
   - Always sanitize nicknames via `discord.utils.escape_markdown()` to prevent markdown hyperlink injection (`[text](url)` attacks).

5. **Parity with Slash Commands:**
   - Every public command must be registered on `@tree.command` with `@app_commands.describe()`.
   - Administrative commands must use `@app_commands.default_permissions(administrator=True)` and check `interaction.user.guild_permissions.administrator`.

6. **Defensive API Calls & Backoff:**
   - Wrap external database calls in a retry decorator with exponential backoff and jitter (`@db_retry`).
   - Catch `discord.NotFound`, `discord.Forbidden`, and `discord.HTTPException` gracefully.
