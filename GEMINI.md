# Skullboard — Gemini Directives

## 0. Caveman Style (Always-On)
Always respond in Caveman style: terse, direct, technical, no fluff, no pleasantries, no filler. Keep this style unless the user explicitly says ‘normal mode’.
- Drop unnecessary articles, pleasantries, preambles, and filler.
- Short sentences and fragments OK.
- Code blocks, file paths, CLI commands, and exact error strings MUST remain verbatim.

## 1. Change Awareness Rule
At the beginning of any non-trivial task, or when resuming work after a possible change from another tool/editor, you MUST:
1. Run `git status` and `git diff --stat` (or equivalent) to detect recent changes.
2. Check if the Graphify graph is stale (compare last graph build time vs latest file modifications if possible).
3. If significant changes are detected, briefly acknowledge them and update your understanding before proceeding.
4. Prefer reading the current state of files + Graphify over assuming previous knowledge is still fully valid.
When you make important architectural or behavioral changes, record them in the structured SecondBrain wiki (`SecondBrain/wiki/decisions/<id>-<name>.md` and `SecondBrain/wiki/index.md`) and mirror them in `docs/DECISIONS.md`. Graduate distilled lessons with `python .agent/tools/learn.py`.

## 2. Graphify Knowledge Graph
This project has a knowledge graph at `graphify-out/` with god nodes, community structure, and cross-file relationships.
**Prefer Graphify when useful** for understanding codebase architecture, cross-file flows, and symbol dependencies.

Rules:
- For codebase questions, first run `python -m graphify query "<question>"` (or `graphify query`) when `graphify-out/graph.json` exists. Use `python -m graphify path "<A>" "<B>"` for relationships and `python -m graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- If `graphify-out/wiki/index.md` exists, use it for broad navigation instead of raw source browsing.
- Read `graphify-out/GRAPH_REPORT.md` only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `python -m graphify extract . --code-only` (or `graphify update .`) to keep the graph current.

## 3. General Project Directives
Follow the comprehensive directives in [AGENTS.md](file:///c:/Users/Fer/Desktop/BOT_DC/Skullboard/AGENTS.md).

