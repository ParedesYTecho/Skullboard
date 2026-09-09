# ADR-001: Agentic Stack & Shared Brain Integration

- **ID**: `page_adr_001_agentic_stack`
- **Date**: 2026-09-09
- **Status**: Accepted
- **Sources**: `src_skullboard_decisions`, `src_agentic_stack_config`

## Context
Multiple AI agents (Antigravity, Codex, Cursor, Claude Code) interact with this codebase. Previously, context was lost when switching tools.

## Decision
1. Deploy `codejunkie99/agentic-stack` portable `.agent/` brain.
2. Wire both Antigravity (`ANTIGRAVITY.md`) and Codex (`AGENTS.md`) to the same shared memory.
3. Establish `SecondBrain/` as the shared portable wiki directory.
4. Integrate Graphify knowledge graph (`graphify-out/`) for token-efficient code navigation.
5. Enforce Caveman style always-on for maximum token compression.

## Consequences
- Cross-agent recall enabled via `python .agent/tools/recall.py`.
- Shared lessons distilled in `.agent/memory/semantic/LESSONS.md`.
- Token consumption reduced by 60%+ through Caveman style and Graphify AST queries.
