# Registro de Decisiones y Cambios Arquitectónicos (Decisions & Lessons)

Este documento actúa como registro persistente (SecondBrain / Architectural Decision Records) compartido entre todos los agentes de IA (Antigravity, Claude Code, Cursor, Codex, OpenCode, Gemini, etc.) y desarrolladores humanos para rastrear cambios clave en Skullboard.

---

## Directrices para Agentes de IA
Al implementar cambios arquitectónicos, nuevas dependencias, mutaciones de base de datos o alteraciones de comportamiento del bot o API:
1. Registra una nueva entrada breve al final de este archivo siguiendo la plantilla.
2. Mantén la descripción concisa, directa y con enlaces a los archivos modificados.
3. No dupliques detalles triviales de código; documenta el **por qué**, **qué** cambió y cualquier **lección/advertencia** para futuros agentes.

---

### Plantilla de Entrada
```markdown
### [YYYY-MM-DD] <Título del Cambio>
- **Herramienta / Agente**: <Nombre del agente o editor>
- **Contexto & Decisión**: <Por qué se hizo el cambio>
- **Archivos Clave**: <Rutas de archivos tocados>
- **Impacto / Lección para futuros agentes**: <Detalle crítico o advertencia>
```

---

## Historial de Decisiones

### [2026-09-09] Integración de Graphify, Caveman Always-On y Change Awareness
- **Herramienta / Agente**: Antigravity
- **Contexto & Decisión**: Configuración de reglas universales multiplataforma para sincronización de contexto entre agentes (Antigravity, Claude, Codex, Cursor, Gemini, OpenCode), activación permanente de modo Caveman (token-efficient) y protocolo Change Awareness.
- **Archivos Clave**: `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, `.cursor/rules/`, `.agents/rules/`, `.git/hooks/`, `docs/DECISIONS.md`
- **Impacto / Lección para futuros agentes**: Antes de cualquier tarea no trivial, ejecutar `git status` / `git diff --stat` y verificar si el grafo de Graphify está desactualizado (`graphify-out/graph.json`). Registrar decisiones mayores en este documento.

### [2026-09-09] Sesión OAuth opaca y baseline RLS
- **Herramienta / Agente**: Codex
- **Contexto & Decisión**: El access token de Discord deja de viajar al navegador y se guarda solo en una sesión opaca server-side; CORS queda limitado a orígenes permitidos y la API valida IDs/entradas y limita tasa.
- **Archivos Clave**: `webserver.py`, `legal/dashboard.html`, `supabase/migrations/20260909_security_baseline.sql`, `docs/SECURITY.md`
- **Impacto / Lección para futuros agentes**: RLS queda deny-by-default para clientes públicos. La migración requiere revisión, backup y aprobación antes de ejecutarse en producción. Sesiones actuales son process-locales; usar Redis si se escalan workers.

### [2026-09-10] Preset local Plus Luna-max
- **Herramienta / Agente**: Codex
- **Contexto & Decisión**: Aislar ahorro de tokens por proyecto sin alterar configuración global: root Luna `max`, subagentes Luna `medium`, reviewer Astra `low` solo bajo riesgo material, máximo 3 hilos.
- **Archivos Clave**: `.codex/config.toml`, `.codex/agents/*.toml`, `AGENTS.md`
- **Impacto / Lección para futuros agentes**: Tareas pequeñas siguen `root-only`/`routine`; Graphify, Change Awareness, pruebas obligatorias y confirmación explícita para mutaciones Supabase permanecen intactos.

### [2026-09-10] Sesiones persistentes cifradas de dashboard
- **Herramienta / Agente**: Codex
- **Contexto & Decisión**: Reemplazar sesiones process-locales y credenciales legibles por `dashboard_sessions`, HMAC del identificador, bundle OAuth Fernet cifrado, state de un solo uso y CSRF en escrituras.
- **Archivos Clave**: `webserver.py`, `dashboard_sessions.py`, `legal/dashboard.html`, `legal/sw.js`, `supabase/migrations/20260910_*sessions*.sql`
- **Impacto / Lección para futuros agentes**: Producción exige `SKULLBOARD_SESSION_ENCRYPTION_KEY`; migración remota y limpieza de `web_sessions` legado siguen pendientes de aprobación e inventario.
