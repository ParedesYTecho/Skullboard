# ADR-002: OAuth Scope Superset, Werewolf Flow & Supabase Audit

- **ID**: `page_adr_002_oauth_security_audit`
- **Date**: 2026-09-11
- **Status**: Accepted
- **Sources**: `src_skullboard_decisions`, `src_supabase_audit_20260911`

## Context
1. Users experienced "Scopes OAuth no permitidos" during dashboard login when Discord returned scopes accumulated from prior authorizations (e.g. `role_connections.write`).
2. The unauthenticated state displayed an unnecessary intermediate card, diverging from the direct-redirect pattern of Werewolf.
3. Profile dropdown contained a duplicate/destructive "Desconectar Discord" action that confused users compared to standard "Cerrar sesión".
4. Multiple database and backend refactors occurred, requiring a full read-only security and data integrity audit of Supabase and token lifecycle.

## Decisions

### 1. OAuth Scope Superset & Normalization
- In `webserver.py`, replaced strict equality `set(scopes) == {"identify", "guilds"}` with `{"identify", "guilds"}.issubset(granted_set)`.
- Applied case-insensitive normalization: `{s.strip().lower() for s in granted_scopes if isinstance(s, str) and s.strip()}`.

### 2. Direct Discord OAuth Redirection (Werewolf Pattern)
- In `legal/dashboard.html`, unauthenticated visits (`401` on `/api/auth/me` or `/api/auth/guilds`) immediately call `triggerDiscordAuth()`, redirecting directly to Discord OAuth without intermediate cards.
- Introduced `authResult.exchanged` flag: if a 401 occurs immediately after token exchange (e.g. browser blocks cookies), the dashboard halts and displays a clear cookie error instead of an infinite redirect loop.
- Reserved `#view-unauthenticated` strictly for explicit logout (`/?logged_out=1`), cancellations, and errors.

### 3. User Dropdown Simplification
- Removed `Desconectar Discord` from the user profile dropdown in `legal/dashboard.html`.
- Retained only `Cerrar sesión` (local session invalidation via `/api/auth/logout` with 30-day cookie TTL). Kept `/api/auth/disconnect` in backend for API compatibility.

### 4. Token Security & Discord Policies
- Tokens (`access_token`, `refresh_token`) remain strictly backend-only, encrypted at rest with Fernet (AES-128-CBC + HMAC SHA-256) in `dashboard_sessions`.
- Browser only receives opaque HttpOnly cookie (`__Host-skullboard_session`).
- Client data filtered via `_public_discord_user` (`id`, `username`, `global_name`, `avatar`).
- Logs sanitized via `_LOG_SECRET_RE`.
- Discord developer policies satisfied: minimal scopes (`identify`, `guilds`) and non-elevated bot invite bitmask (`277025508352`).

### 5. Supabase Read-Only Audit Results
- Tables verified: `public.settings` (72 servers), `public.tracked_messages` (1,558 rows), `public.notify_settings` (3 rows), `public.ignored_channels` (1 row), `public.dashboard_sessions` (1 active session), `public.dashboard_oauth_states` (0 rows).
- Zero data corruption, zero negative skulls, zero orphaned foreign key rows (`ON DELETE CASCADE` intact).
- 1,342 historic rows in `tracked_messages` with `channel_id = NULL` are resolved via fallback to `skullboard_channel_id` in `settings`.
- Public privileges locked down: `anon`, `authenticated`, and `public` have 0 table privileges and 0 RPC execute grants.
- 5/5 RPCs in `SECURITY INVOKER` restricted to `service_role` executing in sub-millisecond range.
- 8/8 migrations match database state.

## Consequences
- Frictionless 1-click login for returning users.
- Immune to unexpected scope additions by Discord.
- Zero risk of token leakage in client-side storage or logs.
- Safe database baseline confirmed across all production tables.
