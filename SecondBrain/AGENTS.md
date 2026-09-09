# SecondBrain Operating Contract (AGENTS.md)

This document is the operating contract for any AI agent interacting with SecondBrain.

## Rules for Agents
1. **Selective Retrieval**: Never read the entire wiki into conversation context. Query `wiki/index.md` or targeted topics first.
2. **Provenance**: When creating or modifying a page, reference the exact source ID in `catalog/sources.jsonl`.
3. **Immutability of Raw Data**: Never edit files in `raw/`.
4. **Dispute Handling**: If two sources conflict, retain both claims with dates and source citations. Do not silently overwrite disputed claims.
5. **Decisions & Lessons**:
   - Architectural decisions belong in `wiki/decisions/`.
   - Bug/debug lessons belong in `wiki/lessons/` and mirrored to `.agent/memory/semantic/LESSONS.md`.
