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
- **Impacto / Lección para futuros agentes**: Producción exige `SKULLBOARD_SESSION_ENCRYPTION_KEY`; migración `dashboard_sessions`/`dashboard_oauth_states` aplicada el 2026-09-10. `web_sessions` legado sigue fuera del escritor nuevo.

### [2026-09-10] Estado OAuth persistente y renovación distribuida
- **Herramienta / Agente**: Codex
- **Contexto & Decisión**: El estado OAuth del dashboard pasa a `dashboard_oauth_states` con HMAC y consumo confirmado de un solo uso. La renovación usa reserva condicional en `dashboard_sessions` y nunca hace upsert tras logout.
- **Archivos Clave**: `webserver.py`, `dashboard_sessions.py`, `legal/dashboard.html`, `legal/sw.js`, `supabase/migrations/20260910_dashboard_sessions_transition.sql`

### 2026-09-10 — Estado OAuth ligado al navegador (supersedida)

- **Decisión anterior**: Se propuso ligar cada state a un nonce HttpOnly por flujo (`browser_hash` en Supabase).
- **Estado actual**: Supersedida por el requisito de que el navegador reciba una sola cookie. El backend persiste únicamente el HMAC del state y lo consume una vez; el frontend conserva solo una lista limitada de states transitorios en `sessionStorage`.
- **Motivo**: Mantener una única cookie opaca de sesión y evitar cualquier cookie OAuth adicional. El state sigue siendo aleatorio, persistente, de un solo uso y no contiene tokens.
- **Archivos Clave**: `webserver.py`, `legal/dashboard.html`, `supabase/migrations/20260910_*.sql`
- **Impacto / Lección para futuros agentes**: Producción usa `__Host-skullboard_session` con `Secure`; desarrollo loopback usa variante no-Secure. La clave Fernet nunca llega a Vercel. Migración aplicada; no añadir cookie OAuth secundaria sin cambiar requisito.

### [2026-09-10] Estado operativo honesto y cargas de dashboard aisladas
- **Herramienta / Agente**: Codex
- **Contexto & Decisión**: El endpoint de estado informa `unknown` cuando ningún proveedor del bot está registrado; modal de estado deja de afirmar uptime/SLA inventados. Dashboard mantiene generaciones separadas para leaderboard, mensajes y ajustes; errores tardíos no pisan otro servidor ni habilitan guardado tras carga fallida.
- **Archivos Clave**: `webserver.py`, `legal/dashboard.html`, `legal/styles.css`, cinco páginas públicas y `scripts/test_dashboard_auth.py`
- **Impacto / Lección para futuros agentes**: Los estados visuales deben representar evidencia real; el footer permanece estable durante cargas y el foco del modal vuelve a su disparador.

### [2026-09-10] Logout local y desconexión Discord explícita
- **Herramienta / Agente**: Codex
- **Contexto & Decisión**: `Cerrar sesión` elimina solo sesión local. `Desconectar Discord` revoca grant OAuth y elimina todas las sesiones persistidas del usuario. La configuración valida que el canal elegido sea visible para el bot antes de escribir.
- **Archivos Clave**: `webserver.py`, `legal/dashboard.html`, `scripts/test_dashboard_auth.py`, `docs/SYSTEM_CONTEXT.md`, `docs/SECURITY.md`
- **Impacto / Lección para futuros agentes**: No mezclar cierre de sesión con revocación global. Nunca aceptar Snowflake de canal sin comprobarlo contra Discord.

### [2026-09-11] OAuth Scope Superset y Entrada Directa Dashboard (Patrón Werewolf)
- **Herramienta / Agente**: Antigravity
- **Contexto & Decisión**: Discord OAuth2 conserva los scopes autorizados previamente por el usuario para el cliente (ej. `role_connections.write` de `/verify`). La verificación estricta `set(scopes) == {"identify", "guilds"}` fallaba con "Scopes OAuth no permitidos". Se ajustó a `{"identify", "guilds"}.issubset(granted)`. Además, en paridad con Werewolf, al acceder a `/dashboard` sin sesión activa se redirige automáticamente al flujo de Discord sin mostrar tarjeta intermedia previa; `#view-unauthenticated` se mantiene para errores explícitos, cancelaciones o tras logout.
- **Archivos Clave**: `webserver.py`, `legal/dashboard.html`, `scripts/test_dashboard_auth.py`, `docs/DECISIONS.md`
- **Impacto / Lección para futuros agentes**: Nunca asumir que Discord devuelve únicamente los scopes de la petición actual; validar que los requeridos estén presentes. Al entrar al dashboard sin autenticar, redirigir directo salvo logout explícito o error de intercambio.
