# Security baseline

## Runtime

- Secrets exist only in deployment environment variables: `DISCORD_TOKEN`, `DISCORD_CLIENT_SECRET`, `SUPABASE_SERVICE_ROLE_KEY`, `SKULLBOARD_SESSION_ENCRYPTION_KEY`, `RESEND_API_KEY`.
- Browser receives only one opaque session cookie. Production uses `__Host-skullboard_session` with `HttpOnly`, `Secure`, `SameSite=Lax`, `Path=/`, without `Domain`; loopback development uses `skullboard_session` without `Secure` so HTTP testing works. Discord tokens never enter JSON, `localStorage`, or `sessionStorage`; pending OAuth states are stored server-side as HMACs and mirrored transiently in `sessionStorage` for callback UX.
- `SKULLBOARD_SESSION_ENCRYPTION_KEY` is a stable Fernet key held only by Render (and local backend development when explicitly configured). Vercel never receives it. Production fails closed when missing. Session IDs and OAuth states use HMAC hashes; OAuth bundles stay encrypted in `dashboard_sessions`.
- `WEB_ALLOWED_ORIGINS` must contain only deployed frontend origins, comma-separated. Default: `https://skullboard.vercel.app`.
- Supabase `service_role` is server-only. Never expose it as `VITE_*`, `NEXT_PUBLIC_*`, or frontend configuration.
- `dashboard_sessions` and `dashboard_oauth_states` are deny-by-default under RLS; only the backend `service_role` may access them.
- TLS is enforced by deployment (`Strict-Transport-Security`). Supabase provides TLS in transit and encryption at rest. Current tables contain operational IDs/configuration, not application secrets.

## Secrets and dependency checks

```powershell
git grep -n -I -E 'sk_live_|sk-[A-Za-z0-9]{20,}|service_role|BEGIN (RSA|OPENSSH) PRIVATE KEY'
git log --all -S'SUPABASE_SERVICE_ROLE_KEY' --oneline
python -m pip_audit -r requirements.txt
```

If a credential was ever committed: revoke/rotate it first, then purge the affected Git history with an approved repository maintenance window. Removing text from the current tree does not invalidate a leaked credential.

## Database

Applied to production on 2026-09-09: `supabase/migrations/20260909_security_baseline.sql` and `supabase/migrations/20260909_remove_direct_public_rpc_grants.sql`. They enable RLS, revoke direct `anon`/`authenticated` table access, and revoke direct RPC execution. `service_role` retains required access.

RLS policies must be added only after a trusted mapping between Supabase `auth.uid()` and Discord guild ownership exists. Until then, deny-by-default is safer than a guessed policy.
