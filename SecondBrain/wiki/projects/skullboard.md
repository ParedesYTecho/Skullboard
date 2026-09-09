# Project: Skullboard

- **ID**: `page_project_skullboard`
- **Scope**: `skullboard`
- **Status**: Confirmed
- **Sources**: `src_skullboard_core_docs`

## Architecture Summary
- **Bot**: Python 3.11+, `discord.py` 2.x `AutoShardedBot`. Gateway reactions debounced with `MessageDebouncer` (1.5s - 2.0s) and `KeyedAsyncLock`.
- **Database**: Supabase PostgreSQL. Critical aggregates computed via PostgreSQL RPCs (`get_guild_user_stats`, `get_guild_leaderboard`), never in-memory.
- **Web API**: Flask + Gunicorn, admin authorization requires `Administrator` bit (`0x8`) or guild ownership.
- **Frontend**: Responsive static HTML/CSS with Sapphire status modal and clean URLs.
