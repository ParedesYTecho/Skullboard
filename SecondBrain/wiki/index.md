# SecondBrain Wiki Index

Shared knowledge index for Skullboard and AI coding agents.

## Projects
- [Skullboard Core Project](projects/skullboard.md) — Architecture, tech stack, and components.

## Decisions (ADRs)
- [ADR-001: Agentic Stack & Shared Memory Integration](decisions/001-agentic-stack-setup.md) — Unified portable memory bridge between Antigravity, Codex, and Cursor.
- [ADR-002: OAuth Scope Superset, Werewolf Flow & Supabase Audit](decisions/002-oauth-werewolf-and-security-audit.md) — Solución de scopes OAuth, redirección directa Werewolf, simplificación de logout y auditoría read-only de Supabase.

## Workflows
- [Token-Efficient Auditing](workflows/token-efficient-audit.md) — How to verify and explore code without wasting context tokens.

## Operations Manuals
- [Ingestion Procedure](../operations/ingest.md)
- [Querying Guide](../operations/query.md)
- [Maintenance Guide](../operations/maintain.md)
- [Restoration Guide](../operations/restore.md)

## Lessons
- [LSN-001: Tolerancia de Scopes OAuth y Patrón Werewolf](lessons/001-oauth-scope-tolerance.md) — Lecciones aprendidas en el flujo de autenticación, scopes acumulativos y bucles de cookies.
