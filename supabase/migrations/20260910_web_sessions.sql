create table if not exists public.web_sessions (
    session_id text primary key,
    discord_token text not null,
    expires_at timestamptz not null,
    created_at timestamptz not null default now()
);

create index if not exists web_sessions_expires_at_idx
    on public.web_sessions (expires_at);

alter table public.web_sessions enable row level security;
revoke all on table public.web_sessions from anon, authenticated;
grant all on table public.web_sessions to service_role;
