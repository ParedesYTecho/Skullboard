# Security baseline

## Runtime

- Secrets exist only in deployment environment variables: `DISCORD_TOKEN`, `DISCORD_CLIENT_SECRET`, `SUPABASE_SERVICE_ROLE_KEY`, `RESEND_API_KEY`.
- Browser receives an opaque `HttpOnly`, `Secure`, `SameSite=Lax` session cookie. Discord access tokens never enter JSON, `localStorage`, or `sessionStorage`.
- `WEB_ALLOWED_ORIGINS` must contain only deployed frontend origins, comma-separated. Default: `https://skullboard.vercel.app`.
- Supabase `service_role` is server-only. Never expose it as `VITE_*`, `NEXT_PUBLIC_*`, or frontend configuration.
- TLS is enforced by deployment (`Strict-Transport-Security`). Supabase provides TLS in transit and encryption at rest. Current tables contain operational IDs/configuration, not application secrets.

## Secrets and dependency checks

```powershell
git grep -n -I -E 'sk_live_|sk-[A-Za-z0-9]{20,}|service_role|BEGIN (RSA|OPENSSH) PRIVATE KEY'
git log --all -S'SUPABASE_SERVICE_ROLE_KEY' --oneline
python -m pip_audit -r requirements.txt
```

If a credential was ever committed: revoke/rotate it first, then purge the affected Git history with an approved repository maintenance window. Removing text from the current tree does not invalidate a leaked credential.

## Database

Review and apply `supabase/migrations/20260909_security_baseline.sql` in Supabase. It enables RLS and revokes direct `anon`/`authenticated` table access. Do not run it against production without backup and explicit approval.

RLS policies must be added only after a trusted mapping between Supabase `auth.uid()` and Discord guild ownership exists. Until then, deny-by-default is safer than a guessed policy.
