# Skullboard Bot — Directivas para Agentes (AGENTS.md)

Este repositorio contiene el bot de Discord **SkullBoard** (Starboard temático de calaveras con filtros avanzados, roles VIP y sistema anti-spam), junto a su servidor web/API en Flask (`webserver.py`), panel de control y frontend estático en `legal/`, y persistencia en Supabase (PostgreSQL).

Cualquier IA o Agente (Antigravity, Claude, Codex, etc.) que opere en este repositorio DEBE acatar estas directivas.

---

## 0. Brain & Memoria Compartida (.agent/)
Este proyecto utiliza el cerebro portátil unificado de **agentic-stack**.
- **Startup**:
  1. `.agent/AGENTS.md` — Mapa y arquitectura del brain.
  2. `.agent/memory/personal/PREFERENCES.md` — Convenciones y estilo.
  3. `.agent/memory/semantic/LESSONS.md` — Lecciones destiladas compartidas.
  4. `.agent/protocols/permissions.md` — Reglas estrictas de ejecución.
  5. `SecondBrain/` — Wiki estructurada de conocimiento y decisiones (`docs/DECISIONS.md`).
- **Recall antes de tareas no triviales**:
  ```bash
  python .agent/tools/recall.py "<descripción de la tarea>"
  ```
- **Registro rápido de aprendizajes**:
  ```bash
  python .agent/tools/learn.py "<regla/lección>" --rationale "<motivo>"
  ```

---

## 0.1 Comunicación Caveman (Always-On)
**Regla de estilo permanente**:
Always respond in Caveman style: terse, direct, technical, no fluff, no pleasantries, no filler. Keep this style unless the user explicitly says ‘normal mode’.
- Elimina artículos innecesarios, saludos, cortesías y rodeos.
- Usa frases cortas, directas y términos técnicos precisos.
- Los bloques de código, comandos CLI, rutas de archivos y cadenas de error NUNCA se alteran ni abrevian inventando tokens.

---

## 1. Filosofía Vibe-Coding & Protocolo `/grill-me`
El usuario practica **vibe-coding** (desarrollo ágil orientado a objetivos sin necesidad de dominar la sintaxis o detalles de bajo nivel).
1. **Ante tareas complejas, confusas o de diseño**:
   - El agente DEBE inspeccionar primero el código relevante para ubicarse en el contexto real.
   - A continuación, debe **preguntar al usuario o recomendar activamente `/grill-me`** para realizar una entrevista breve y clarificar exactamente qué se desea construir antes de programar.
   - Preguntar a tiempo ahorra tokens, evita código desalineado y garantiza que el resultado coincida al 100% con la visión del usuario.
2. **Alcance Completo (Anti-Recortes)**:
   - Resuelve **todos** los requerimientos y puntos solicitados por el usuario.
   - NUNCA omitas, recortes o dejes partes de una petición a medias bajo el pretexto de simplicidad o YAGNI. La simplicidad aplica a la arquitectura del código (menos boilerplate, código limpio), nunca a amputar funcionalidades explícitas.

---

## 2. Comandos de Verificación Local
Antes de dar por finalizada cualquier tarea de código, ejecuta siempre:
```bash
python -m py_compile main.py webserver.py
python scripts/safeguards_test.py
```

Si el frontend fue modificado, valida sintaxis HTML/CSS y coherencia de enlaces limpios (`/dashboard`, `/cambios`, `/privacy`, `/terms`).

---

## 3. Despliegue y Política de Commit + Push
1. **Commit + Push Automático por Defecto**:
   - Una vez que los cambios estén implementados y verificados con las pruebas locales, **haz `git commit` y `git push origin main` automáticamente**.
   - Render despliega automáticamente el backend del bot y Vercel despliega el frontend.
2. **Excepción (Modo Mantenimiento / Pausa)**:
   - Si el usuario indica expresamente: *"no hagas commit/push"*, *"espera"* o menciona que está en *"mantenimiento"*, **NO hagas push**. Mantén los cambios en local o en una rama y solicita confirmación antes de cualquier push remoto.

---

## 4. Salvaguardas Críticas en Base de Datos (Supabase)
La base de datos en producción es extensa y crítica para los servidores que usan Skullboard:
1. **Operaciones de Lectura (`SELECT`) e Inserciones Idempotentes**:
   - Son seguras y pueden ejecutarse de forma autónoma.
2. **Mutaciones y Modificaciones (`UPDATE`, `DELETE`, `ALTER TABLE`, `DROP`, `TRUNCATE`)**:
   - **MÁXIMA PRECAUCIÓN**: Toda operación que altere o elimine registros existentes requiere una parada obligatoria.
   - El agente DEBE explicar detalladamente al usuario:
     * **Qué** va a modificar o borrar (tabla, columnas, condiciones `WHERE`).
     * **Por qué** es necesario y qué impacto tendrá en los datos existentes.
     * Solicitar confirmación explícita del usuario antes de ejecutar la mutación.

---

## 5. Búsqueda y Descubrimiento Proactivo de MCPs y Skills
El agente debe actuar como un Tech Lead proactivo y explorar constantemente maneras de mejorar el proyecto:
1. **Ecosistema de MCPs**:
   - Usar activamente MCPs existentes (`supabase`, `windows-computer-use`, etc.) y sugerir o buscar nuevos servidores MCP (ej. Chrome DevTools, Playwright, analizadores de rendimiento) cuando aporten valor directo a la tarea.
2. **Ecosistema de Skills**:
   - Evaluar las habilidades disponibles en `.agents/skills/` y en la configuración global (`modern-ui-ux-design-system`, `discord-py-advanced-patterns`, `python-asyncio-performance`, `locust-discord-load-testing`, etc.).
   - Si se detecta una necesidad recurrente no cubierta, proponer la creación de una nueva skill especializada o la integración de herramientas adicionales.

---

## 6. Arquitectura y Reglas Técnicas Invariables
- **Discord Bot**: Python 3.11+, `discord.py` 2.x utilizando `AutoShardedBot`.
- **Eventos Gateway**: Priorizar eventos crudos (`on_raw_reaction_add`, `on_raw_reaction_remove`) con `MessageDebouncer` (1.5s - 2.0s) y `KeyedAsyncLock` por `message_id`.
- **Permisos**: Los comandos administrativos y endpoints de configuración deben verificar estrictamente el permiso de `Administrator` (`0x8`) o la propiedad del servidor (`guild.owner_id`).
- **Web API**: Flask + Gunicorn, consumo de endpoints `/api/guild/<guild_id>/...` mediante RPCs optimizados en PostgreSQL, nunca agregaciones $O(N)$ en memoria.

---

## 7. Change Awareness Rule (Conciencia de Cambios entre Editores e IAs)
At the beginning of any non-trivial task, or when resuming work after a possible change from another tool/editor, you MUST:
1. Run `git status` and `git diff --stat` (or equivalent) to detect recent changes.
2. Check if the Graphify graph is stale (compare last graph build time vs latest file modifications if possible).
3. If significant changes are detected, briefly acknowledge them and update your understanding before proceeding.
4. Prefer reading the current state of files + Graphify over assuming previous knowledge is still fully valid.
When you make important architectural or behavioral changes, briefly record them in the shared wiki/SecondBrain (`docs/DECISIONS.md`) so other tools and agents can find them later.

---

## 8. Uso de Graphify (Knowledge Graph)
This project has a knowledge graph at `graphify-out/` with god nodes, community structure, and cross-file relationships.
**Prefer Graphify when useful** for understanding codebase architecture, cross-file flows, and symbol dependencies.

When the user types `/graphify`, use the installed graphify skill or instructions before doing anything else.

Rules:
- For codebase questions, first run `python -m graphify query "<question>"` (or `graphify query`) when `graphify-out/graph.json` exists. Use `python -m graphify path "<A>" "<B>"` for relationships and `python -m graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- Dirty `graphify-out/` files are expected after hooks or incremental updates; dirty graph files are not a reason to skip graphify. Only skip graphify if the task is about stale or incorrect graph output, or the user explicitly says not to use it.
- If `graphify-out/wiki/index.md` exists, use it for broad navigation instead of raw source browsing.
- Read `graphify-out/GRAPH_REPORT.md` only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `python -m graphify extract . --code-only` or git commit (git hooks auto-update) to keep the graph current.
