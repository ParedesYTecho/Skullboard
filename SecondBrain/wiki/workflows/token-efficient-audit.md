# Workflow: Token-Efficient Auditing & Code Exploration

- **ID**: `page_workflow_token_efficient_audit`
- **Scope**: `skullboard`
- **Status**: Confirmed

## Procedure
1. **Change Awareness**:
   ```bash
   git status; git diff --stat
   ```
2. **Graphify Exploration (DO NOT grep full codebase first)**:
   ```bash
   python -m graphify query "<concept or question>"
   python -m graphify path "<symbolA>" "<symbolB>"
   ```
3. **Targeted Inspection**:
   Use selective file viewing (`view_file`) on specific line ranges identified by Graphify.
4. **Shared Recall**:
   ```bash
   python .agent/tools/recall.py "<task description>"
   ```
5. **Compile & Safeguards**:
   ```bash
   python -m py_compile main.py webserver.py
   python scripts/safeguards_test.py
   ```
