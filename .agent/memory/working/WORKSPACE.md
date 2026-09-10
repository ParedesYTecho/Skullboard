# Workspace (live task state)

> Replace this template on your first real task. The dream cycle auto-archives
> this file after 2 days of inactivity — don't keep long-lived notes here.

## Current task
Finish Skullboard dashboard runtime hardening and UI/status polish.

## Open files
- `webserver.py`, `dashboard_sessions.py`, `legal/dashboard.html`, `legal/sw.js`, Vercel config, migrations

## Active hypotheses
- Supabase project `tjmcclgyirqjatezkqgr` verified; required dashboard tables absent.
- Backend now requires additive `dashboard_sessions` / `dashboard_oauth_states` schema before deploy.

## Checkpoints
- [x] Backend/session/frontend implementation and local checks
- [x] Browser-bound OAuth state and honest status states
- [ ] Exact production migration approval and deployment verification

## Next step
Request approval before applying additive migration or cleaning legacy `web_sessions`; then push and verify Render/Vercel browser flow.
