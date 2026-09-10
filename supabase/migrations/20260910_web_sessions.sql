-- Safe replacement for the original plaintext session schema.
create table if not exists public.dashboard_sessions (
    session_hash text primary key,
    discord_user_id text not null,
    expires_at timestamptz not null,
    revoked_at timestamptz,
    token_bundle text not null,
    token_expires_at timestamptz not null,
    created_at timestamptz not null default now(),
    last_seen_at timestamptz not null default now()
);

create index if not exists dashboard_sessions_expires_at_idx
    on public.dashboard_sessions (expires_at);

alter table public.dashboard_sessions enable row level security;
revoke all on table public.dashboard_sessions from anon, authenticated;
grant all on table public.dashboard_sessions to service_role;
