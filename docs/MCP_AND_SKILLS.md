# 🧭 Manual Maestro de Skills, Servidores MCP y Comandos Especiales — SkullBoard

Este documento sirve como la **guía de referencia definitiva** para desarrolladores y agentes de IA en el repositorio de **SkullBoard**. Aquí se detalla cada servidor MCP, cada Skill y cada Slash Command disponible en el ecosistema, explicando con precisión **cuándo usarlos, cuándo evitarlos y cómo combinarlos** para lograr la máxima calidad y fiabilidad en el código.

---

## ⚡ 1. PROTOCOLO OBLIGATORIO PARA TAREAS COMPLEJAS: `/grill-me` & `/goal`

Para garantizar que los cambios arquitectónicos y las refactorizaciones complejas se realicen sin fallos ni malentendidos, se establece el siguiente protocolo de dos fases:

```
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│                          FLUJO DE INGENIERÍA PARA TAREAS COMPLEJAS                          │
├─────────────────────────────────────────┬───────────────────────────────────────────────────┤
│ FASE 1: ALINEACIÓN Y DISEÑO             │ FASE 2: EJECUCIÓN AUTÓNOMA Y TESTEO               │
│ 👉 Comando: /grill-me                   │ 👉 Comando: /goal                                 │
│ • Entrevista interactiva de decisiones  │ • Implementación continua sin interrupciones      │
│ • Definición de casos borde y esquemas  │ • Creación de tests unitarios y validación E2E    │
│ • Aprobación del plan técnico           │ • Certificación final del objetivo cumplido       │
└─────────────────────────────────────────┴───────────────────────────────────────────────────┘
```

### 🧠 ¿Cuándo usar `/grill-me`?
* **Propósito:** El agente asume el rol de un Principal Software Architect y te realiza una breve entrevista con preguntas directas para despejar dudas de diseño, validar estructuras de datos y elegir el mejor enfoque antes de modificar el código.
* **Úsalo cuando:**
  * Vayas a diseñar una nueva funcionalidad grande (ej. sistema de niveles, filtros por roles, multi-idioma).
  * Tengas varias opciones de implementación y necesites decidir la más escalable.
  * Vayas a realizar un cambio en el esquema de la base de datos de Supabase.
* **Ejemplo de uso en chat:**
  > `"/grill-me Quiero rediseñar el sistema de notificaciones para que los usuarios puedan elegir entre DMs o menciones en canales específicos."`

### 🚀 ¿Cuándo usar `/goal`?
* **Propósito:** Activa el modo autónomo de larga duración para el agente. El agente no se detiene ante obstáculos menores: investiga, implementa, corrige errores, ejecuta pruebas y no finaliza hasta verificar al 100% que la meta se ha cumplido.
* **Úsalo cuando:**
  * Tengas una tarea pesada o un refactor que tome mucho tiempo (ej. modernizar toda una suite de comandos, auditar 50 archivos o realizar pruebas de estrés completas).
  * Quieras dejar al agente trabajando de forma desatendida (ej. *overnight*).
* **Ejemplo de uso en chat:**
  > `"/goal Implementa soporte completo para auto-resync nocturno con logging en Supabase y añade tests de integración."`

---

## 🎛️ 2. Matriz de Slash Commands (`/`) Disponibles

| Comando Slash | Función Principal | Cuándo Usarlo | Cuándo NO Usarlo |
| :--- | :--- | :--- | :--- |
| **`/grill-me`** | Entrevista interactiva de requerimientos técnicos. | Antes de iniciar cambios grandes o ambiguos en la arquitectura. | Para correcciones simples de una sola línea o preguntas triviales. |
| **`/goal`** | Modo autónomo de larga duración hasta completar la meta. | En refactorizaciones profundas, migraciones o suites de pruebas completas. | En consultas rápidas o tareas que requieran feedback paso a paso. |
| **`/browser`** | Navegación e inspección visual en vivo con capturas. | Para auditar responsive design en móvil/tablet/PC y probar formularios web. | Para tareas que solo afectan al backend en Python (`main.py`). |
| **`/learn`** | Persistir aprendizajes y reglas en `.agents/rules/`. | Tras resolver un error difícil o al descubrir una nueva restricción fija. | Si la conversación no reveló ninguna regla o estándar reutilizable. |
| **`/schedule`** | Programación de timers o tareas cron en segundo plano. | Para monitorizar latencias de Render o polling de bases de datos. | Si la tarea actual es síncrona y termina de inmediato. |
| **`/teamwork-preview`**| Lanzamiento de enjambres de agentes en paralelo. | Cuando un proyecto requiere trabajo simultáneo en Frontend, Backend y DB. | En tareas lineales que un solo agente puede resolver en segundos. |

---

## 🔌 3. Catálogo Completo de Servidores MCP (Model Context Protocol)

Los servidores MCP dotan al agente de herramientas nativas de conexión con servicios externos y APIs del sistema:

### 1. 🗄️ `supabase` MCP Server
* **Herramientas Clave:** `execute_sql`, `list_tables`, `list_migrations`, `apply_migration`, `query_logs`, `get_advisors`, `list_edge_functions`.
* **Cuándo Usarlo:**
  * Para inspeccionar o crear tablas, índices o funciones RPC en PostgreSQL (`settings`, `tracked_messages`, `notify_settings`).
  * Para consultar logs de PostgREST y analizar consultas lentas o bloqueos de conexión.
  * Para aplicar migraciones y validar políticas RLS (*Row Level Security*).
* **Cuándo NO Usarlo:**
  * Para cambios de diseño en el frontend HTML/CSS o lógica interna de `discord.py` en RAM.

### 2. 🐙 `github` MCP Server
* **Herramientas Clave:** `create_issue`, `create_pull_request`, `get_pull_request`, `list_issues`, `list_repositories`.
* **Cuándo Usarlo:**
  * Para automatizar la apertura de Pull Requests tras completar una feature o refactor.
  * Para consultar issues abiertos, bugs reportados y sincronizar hitos de desarrollo.
* **Cuándo NO Usarlo:**
  * Para comandos locales de git rutinarios (`git add`, `git commit`) que se resuelven más rápido por terminal.

### 3. ▲ `vercel` MCP Server
* **Herramientas Clave:** `list_deployments`, `get_deployment`, `get_project_logs`, `get_env_vars`, `list_projects`.
* **Cuándo Usarlo:**
  * Para verificar el estado de despliegue de `skullboard.vercel.app` tras actualizar `legal/styles.css` o `legal/index.html`.
  * Para inspeccionar logs de compilación o errores 404/500 en las URLs limpias del portal.
* **Cuándo NO Usarlo:**
  * Para depurar el bot de Discord en Render.

### 4. 🌐 `chrome_devtools` / Browser MCP Server
* **Herramientas Clave:** `navigate_page`, `take_screenshot`, `resize_page`, `evaluate_script`, `click`, `fill`, `lighthouse_audit`.
* **Cuándo Usarlo:**
  * Para pruebas automatizadas E2E de la interfaz en cualquier resolución (iPhone 390px, Android 360px, Tablet 768px, PC 1440px).
  * Para auditar accesibilidad (A11y), contrastes WCAG en modo claro/oscuro y prevenir el bug de auto-zoom en iOS.
  * Para simular interacción de usuarios en el formulario de contacto y comprobar el filtrado de comandos.
* **Cuándo NO Usarlo:**
  * Cuando no hay cambios visuales en el frontend.

### 5. 🖥️ `windows-computer-use` MCP Server
* **Herramientas Clave:** `cua_computer_use_screenshot`, `automation_mouse`, `automation_keyboard`, `get_desktop_state`.
* **Cuándo Usarlo:**
  * Para interacción visual directa con la interfaz del sistema operativo Windows cuando no hay API o CLI disponible.
* **Cuándo NO Usarlo:**
  * Cuando la tarea se pueda resolver mediante comandos de terminal PowerShell o llamadas a APIs.

---

## 🛠️ 4. Catálogo Completo de Agent Skills (Habilidades)

Las skills son bibliotecas de procedimientos especializados que guían al agente paso a paso:

```
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│                                   CATÁLOGO DE SKILLS ACTIVAS                                │
├─────────────────────────────────────────┬───────────────────────────────────────────────────┤
│ 💀 discord-py-advanced-patterns         │ 🧪 locust-discord-load-testing                    │
│ Arquitectura de bots a gran escala,     │ Pruebas de estrés, simulación de tormentas de     │
│ raw events, locks y debouncing.         │ reacciones y benchmarking de RPCs de Supabase.    │
├─────────────────────────────────────────┼───────────────────────────────────────────────────┤
│ 📱 playwright-visual-testing            │ 🗄️ supabase-postgres-best-practices               │
│ Auditoría visual responsive, viewports  │ Reglas de oro en Postgres: índices compuestos,    │
│ móviles y contraste Dark/Light.         │ advisory locks, RLS y prevención de deadlocks.    │
├─────────────────────────────────────────┼───────────────────────────────────────────────────┤
│ ⚡ ponytail                              │ 🔍 code-review                                    │
│ Filosofía YAGNI: la solución más        │ Revisión estricta de diffs en 2 ejes: estándares  │
│ simple, limpia y sin sobreingeniería.   │ del repositorio y fidelidad a la especificación.  │
└─────────────────────────────────────────┴───────────────────────────────────────────────────┘
```

### 1. `discord-py-advanced-patterns`
* **Qué hace:** Proporciona patrones de ingeniería para `discord.py` v2.x: uso de eventos raw (`on_raw_reaction_add`), coalescencia de eventos con debouncer, exclusión mutua por `KeyedAsyncLock`, decorador `@db_retry` y resolución segura de apodos contra inyecciones markdown.
* **Cuándo se activa:** Al modificar `main.py`, añadir comandos slash o cambiar la lógica del Starboard.

### 2. `locust-discord-load-testing`
* **Qué hace:** Guía la creación de simulaciones de carga concurrente (50-500 reacciones simultáneas) para verificar que el bot no sufra fugas de memoria (*memory leaks*), condiciones de carrera ni sature los límites de PostgREST.
* **Cuándo se activa:** Al auditar la resiliencia del bot o preparar el bot para servidores con miles de miembros activos.

### 3. `playwright-visual-testing`
* **Qué hace:** Establece la matriz de viewports (360px a 1440px), checklists de desbordamiento horizontal (`scrollWidth > innerWidth`), validación de `font-size: 16px` para evitar zoom en iOS y verificación de contrastes WCAG AAA.
* **Cuándo se activa:** Al hacer cambios en `legal/styles.css` o en cualquiera de las páginas HTML del portal.

### 4. `supabase-postgres-best-practices`
* **Qué hace:** Compendio de mejores prácticas oficiales de Supabase para Postgres: tipos de datos eficientes (`BIGINT` para snowflakes), índices en foreign keys con `ON DELETE CASCADE`, uso de `COALESCE` en agregaciones y prevención de consultas $O(N)$ en RAM.
* **Cuándo se activa:** Al crear o modificar tablas, RPCs o consultas a la base de datos.

### 5. `ponytail` (Lazy & Minimalist Engineer)
* **Qué hace:** Aplica el principio YAGNI (*You Aren't Gonna Need It*). Exige la solución más corta, simple y legible posible antes de instalar dependencias innecesarias o escribir código redundante.
* **Cuándo se activa:** En cualquier tarea de refactorización o cuando el usuario pide la solución más limpia y directa.

### 6. `code-review`
* **Qué hace:** Ejecuta una revisión paralela en dos ejes: **Estándares** (buenas prácticas del repo) y **Especificación** (si cumple lo pedido por el usuario), reportando hallazgos antes de commitear.
* **Cuándo se activa:** Cuando el usuario pide auditar una rama o revisar los cambios pendientes.

### 7. `modern-ui-ux-design-system`
* **Qué hace:** Sistema de diseño estético avanzado inspirado en Magic UI, Aceternity UI y Shadcn: tokens cromáticos de lujo en modo oscuro/claro, micro-interacciones físicas con curvas de resorte (`cubic-bezier`), toasts flotantes y simuladores interactivos de Discord en vivo.
* **Cuándo se activa:** Al crear o mejorar componentes visuales, animaciones o interfaces de usuario.

---

## 🎯 5. Matriz de Decisión Rápida

| Si lo que quieres hacer es... | La mejor combinación de herramientas es: |
| :--- | :--- |
| **Diseñar una feature compleja nueva** | Escribe **`/grill-me`** para la entrevista inicial $\to$ Usa **`/goal`** para implementarla. |
| **Comprobar el diseño móvil en iPhone/Android** | Usa **`/browser`** junto con la skill **`playwright-visual-testing`**. |
| **Optimizar una consulta lenta de Supabase** | Usa el MCP **`supabase`** (`execute_sql`, `query_logs`) + la skill **`supabase-postgres-best-practices`**. |
| **Simular 200 personas reaccionando a la vez** | Usa la skill **`locust-discord-load-testing`** con scripts de estrés asíncronos en scratch. |
| **Persistir una regla fija para futuros chats** | Usa **`/learn`** y la directriz quedará grabada en `.agents/rules/`. |
| **Publicar una nueva versión en Vercel/GitHub** | MCP **`vercel`** para logs de deploy + MCP **`github`** para Pull Request / Release. |
