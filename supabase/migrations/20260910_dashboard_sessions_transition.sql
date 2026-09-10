-- Additive transition for databases where 20260910_web_sessions.sql was already applied.
-- The backend never reads the legacy table. Do not copy plaintext credentials in SQL.
create table if not exists public.dashboard_sessions (
    session_hash text primary key,
    discord_user_id text not null,
    expires_at timestamptz not null,
    revoked_at timestamptz,
    token_bundle text not null,
    token_expires_at timestamptz not null,
    created_at timestamptz not null default now(),
    last_seen_at timestamptz not null default now(),
    refresh_lock_id text,
    refresh_lock_until timestamptz,
    token_version integer not null default 0
);
alter table public.dashboard_sessions add column if not exists refresh_lock_id text;
alter table public.dashboard_sessions add column if not exists refresh_lock_until timestamptz;
alter table public.dashboard_sessions add column if not exists token_version integer not null default 0;
create index if not exists dashboard_sessions_expires_at_idx on public.dashboard_sessions (expires_at);
alter table public.dashboard_sessions enable row level security;
revoke all on table public.dashboard_sessions from public;
revoke all on table public.dashboard_sessions from anon, authenticated;
grant all on table public.dashboard_sessions to service_role;

create table if not exists public.dashboard_oauth_states (
    state_hash text primary key,
    expires_at timestamptz not null,
    created_at timestamptz not null default now()
);
create index if not exists dashboard_oauth_states_expires_at_idx on public.dashboard_oauth_states (expires_at);
alter table public.dashboard_oauth_states enable row level security;
revoke all on table public.dashboard_oauth_states from public;
revoke all on table public.dashboard_oauth_states from anon, authenticated;
grant all on table public.dashboard_oauth_states to service_role;

-- Legacy web_sessions needs an explicitly approved cleanup after inventory.
-- Existing plaintext rows must be discarded or re-encrypted by a controlled backend
-- procedure using SKULLBOARD_SESSION_ENCRYPTION_KEY; never expose them to clients.
