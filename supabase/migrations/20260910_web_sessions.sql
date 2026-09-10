-- Safe replacement for the original plaintext session schema.
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

create index if not exists dashboard_sessions_expires_at_idx
    on public.dashboard_sessions (expires_at);

alter table public.dashboard_sessions enable row level security;
revoke all on table public.dashboard_sessions from public;
revoke all on table public.dashboard_sessions from anon, authenticated;
grant all on table public.dashboard_sessions to service_role;

create table if not exists public.dashboard_oauth_states (
    state_hash text primary key,
    browser_hash text,
    expires_at timestamptz not null,
    created_at timestamptz not null default now()
);
alter table public.dashboard_oauth_states add column if not exists browser_hash text;

create index if not exists dashboard_oauth_states_expires_at_idx
    on public.dashboard_oauth_states (expires_at);

alter table public.dashboard_oauth_states enable row level security;
revoke all on table public.dashboard_oauth_states from public;
revoke all on table public.dashboard_oauth_states from anon, authenticated;
grant all on table public.dashboard_oauth_states to service_role;
