-- Security baseline. Apply in Supabase SQL editor after backup and review.
-- The bot uses service_role server-side; this blocks direct public REST access.

alter table if exists public.settings enable row level security;
alter table if exists public.tracked_messages enable row level security;
alter table if exists public.ignored_channels enable row level security;
alter table if exists public.notify_settings enable row level security;

revoke all on table public.settings from anon, authenticated;
revoke all on table public.tracked_messages from anon, authenticated;
revoke all on table public.ignored_channels from anon, authenticated;
revoke all on table public.notify_settings from anon, authenticated;

-- No client-side Supabase access is part of this application. Keep policies
-- absent until Supabase Auth identities are mapped to Discord guild ownership.
-- service_role bypasses RLS for the server-side bot/API only.
