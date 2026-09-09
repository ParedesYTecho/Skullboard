# SecondBrain: Portable Shared Wiki & LLM Knowledge Base

Welcome to SecondBrain. This directory acts as the centralized, portable knowledge base, decision record, and LLM-maintained wiki for Skullboard, shared across Antigravity, Codex, Cursor, Claude Code, and other AI agents.

## Structure Overview
- `config/`: Operational configuration, source authorization, routing rules, policies, and integrations.
- `inbox/`: Staging area for incoming notes, scratch ideas, and raw materials awaiting processing.
- `raw/`: Immutable provenance archives (`conversations/`, `documents/`, `web/`).
- `catalog/`: Structured JSONL indexes tracking sources (`sources.jsonl`), compiled pages (`pages.jsonl`), and exclusions (`exclusions.jsonl`).
- `wiki/`: Substantive, curated knowledge pages organized by domain:
  - `projects/`: Overview, architecture, and roadmaps for projects.
  - `decisions/`: Architectural Decision Records (ADRs) with rationale and evidence.
  - `concepts/`: Technical deep dives and domain concepts.
  - `workflows/`: Standard operating procedures, deployment guides, and troubleshooting recipes.
  - `lessons/`: Distilled empirical lessons from bugs and production issues.
  - `research/`: Technical research notes and benchmarking.
  - `sources/`: Source metadata summaries and provenance cards.
  - `preferences/`: User preferences, communication styles, and constraints.
  - `skills/`: Installed skills inventory and capabilities.
  - `rules/`: Universal agent behavioral directives.
- `templates/`: Markdown templates for new ADRs, concepts, workflows, and lessons.
- `operations/`: Standard operating manuals (`ingest.md`, `query.md`, `maintain.md`, `restore.md`).
- `staging/`: Isolation buffer for atomic writes and compilations.
- `reports/`: Audit reports, verification logs, and flywheel metrics.
- `logs/`: Operation history and sync audit trails.
- `exports/`: Portable bundle snapshots for cross-system transfers.
- `.runtime/`: Local state, lockfiles, and scratch data (kept outside version control).

## Operating Rules
1. Never import credentials, API tokens, or hidden model reasoning into SecondBrain.
2. Maintain strict provenance: every substantive claim must link to a valid source ID.
3. Keep pages concise, modular, and cross-referenced.
