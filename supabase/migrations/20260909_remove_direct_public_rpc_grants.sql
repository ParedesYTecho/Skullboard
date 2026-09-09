-- Explicit grants existed on anon/authenticated, so revoking PUBLIC alone
-- was insufficient. Keep all RPC access server-side through service_role.
revoke execute on function public.get_guild_leaderboard(text, integer) from anon, authenticated;
revoke execute on function public.get_guild_server_stats(text) from anon, authenticated;
revoke execute on function public.get_guild_user_stats(text, text) from anon, authenticated;
revoke execute on function public.get_random_tracked_message(text) from anon, authenticated;
revoke execute on function public.get_top_periodo(text, bigint, integer) from anon, authenticated;
