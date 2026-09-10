# Workspace (live task state)

> Replace this template on your first real task. The dream cycle auto-archives
> this file after 2 days of inactivity — don't keep long-lived notes here.

## Current task
Finish Skullboard dashboard runtime hardening and UI/status polish.

## Open files
- `webserver.py`, `dashboard_sessions.py`, `legal/dashboard.html`, `legal/sw.js`, Vercel config, migrations

## Active hypotheses
- Supabase project `tjmcclgyirqjatezkqgr` verified; dashboard migration `20260910210424` is applied.
- Backend uses one opaque HttpOnly session cookie; OAuth states are HMAC-persisted server-side and mirrored only as bounded sessionStorage UX state.

## Checkpoints
- [x] Backend/session/frontend implementation and local checks
- [x] One-use OAuth state, honest status states, channel validation, explicit Discord disconnect
- [x] Production migration, Render/Vercel deployment, anonymous API/UI verification
- [ ] OAuth consent + authenticated browser smoke test

## Next step
Obtain action-time confirmation for Discord OAuth `Authorize`; then verify authenticated dashboard reload, guilds, config, and logout/disconnect paths. Do not clean legacy `web_sessions` without explicit production mutation approval.
