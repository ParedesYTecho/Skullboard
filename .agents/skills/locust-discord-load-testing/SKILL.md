---
name: locust-discord-load-testing
description: >-
  Methodology and automated scripts for stress-testing, concurrency benchmarking,
  and load testing Discord bots and Supabase PostgreSQL backends.
  Use when validating bot debouncers under high burst loads, testing memory leak
  resilience under 100+ concurrent simulated reactions, or benchmarking PostgREST RPCs.
---

# Locust & Asynchronous Concurrency Load Testing

This skill guides the creation and execution of load and stress tests for high-volume Discord bots and Supabase backends.

## Testing Vectors

### 1. Burst Reaction Simulation (Reaction Storm)
- **Goal:** Verify that a burst of 50–200 reactions on a single message triggers exactly 1 debounced execution and 0 duplicate records.
- **Methodology:** Use `asyncio.gather` with mock `discord.Message` payloads targeting `on_raw_reaction_add`.
- **Validation:** Assert `_counts` in `KeyedAsyncLock` decrements back to 0 and `tracked_messages` receives exactly 1 upsert.

### 2. PostgREST RPC Load Testing
- **Endpoints to Benchmark:**
  - `get_guild_leaderboard(p_guild_id, p_limit)`
  - `get_guild_server_stats(p_guild_id)`
  - `get_top_periodo(p_guild_id, p_min_snowflake, p_limit)`
- **Targets:**
  - P95 latency < 150ms under 50 req/s.
  - Zero connection exhaustion on Supabase pooler.

### 3. Task Cancellation & Deadlock Safety
- **Methodology:** Launch 10 coroutines waiting on the same `message_id` lock, cancel 4 abruptly with `task.cancel()`, and verify the remaining 6 complete cleanly without orphan locks or leaks.
