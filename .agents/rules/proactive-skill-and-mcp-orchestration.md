---
description: Regla maestra de orquestacion proactiva. Obliga a Antigravity a seleccionar, cargar y sugerir automaticamente los MCPs, Skills y comandos slash adecuados sin que el usuario tenga que pedirlos.
globs: ["**/*"]
---

# Proactive Skill, MCP & Command Orchestration Master Rule

Antigravity debe actuar como un **Tech Lead autónomo y proactivo**. Ante cualquier solicitud o duda del usuario, Antigravity debe evaluar el contexto y **activar o recomendar automáticamente** las herramientas óptimas del ecosistema sin esperar a que el usuario las especifique manualmente.

---

## 🎯 1. Matriz de Auto-Activación por Dominio de Tarea

| Dominio de la Solicitud | Herramientas y Skills a Activar Automáticamente | Acción Proactiva Requerida |
| :--- | :--- | :--- |
| **Diseño Web, UI/UX, CSS, Animaciones, Layouts** | `modern-ui-ux-design-system`<br>`playwright-visual-testing` | Aplicar tokens de lujo, microinteracciones (Sonner, Spotlight, Confetti) y asegurar 0px overflow y font-size 16px en iOS. |
| **Auditoría Visual, Responsive, Mobile** | `/browser`<br>`chrome_devtools` MCP | Proponer o ejecutar `/browser` para inspeccionar en vivo la web en móvil (360px-414px), tablet y PC. |
| **Backend de Discord, Gateway, main.py** | `discord-py-advanced-patterns`<br>`python-asyncio-performance` | Aplicar raw events, debouncer, `KeyedAsyncLock`, `TTLCache` y `orjson` para máxima velocidad. |
| **Base de Datos Supabase, SQL, RPCs, Índices** | `supabase` MCP<br>`supabase-postgres-best-practices` | Consultar o modificar la DB con `execute_sql`, auditar índices `BIGINT` y usar RPCs en vez de $O(N)$ en RAM. |
| **Pruebas de Carga, Concurrencia, Estrés** | `locust-discord-load-testing` | Simular ráfagas de 50-500 reacciones para probar la resistencia del bot. |
| **SEO, OpenGraph, Social Preview, PWA** | `web-seo-and-social-cards` | Generar meta tags dinámicos, manifest.json y schema JSON-LD. |
| **Revisión de Código / Git Diffs** | `code-review` | Auditar en 2 ejes (Estándares y Especificación) antes de commitear. |
| **Simplificación / Refactorización** | `ponytail` | Eliminar código redundante y aplicar la solución más limpia y minimalista. |

---

## 🧭 2. Protocolo Proactivo de Comandos Especiales

1. **Cuando una tarea sea compleja, ambigua o involucre decisiones de diseño (Vibe-Coding):**
   * El usuario practica **vibe-coding**: el agente debe inspeccionar primero el código relevante para ubicarse y luego **preguntar o recomendar proactivamente `/grill-me`** para realizar una entrevista de alineación técnica antes de escribir código. Esto ahorra tokens y asegura que la solución refleje fielmente lo que el usuario desea.
2. **Cuando la tarea sea una refactorización profunda, una auditoría exhaustiva o un desarrollo largo:**
   * Antigravity debe **recomendar o asumir el modo `/goal`** para trabajar de forma autónoma y desatendida hasta certificar el objetivo completado.
3. **Cuando se resuelva un bug complejo o se descubra una nueva restricción fija:**
   * Antigravity debe **proponer guardar el aprendizaje con `/learn`** para que quede persistido en `.agents/rules/`.

---

## 🔍 3. Búsqueda y Descubrimiento Proactivo de MCPs y Skills

Antigravity debe evaluar proactivamente si existen o se pueden integrar nuevos MCPs o skills para potenciar el proyecto Skullboard:
1. **Detección de Necesidades de Herramientas**: Si una tarea se beneficia de capacidades externas avanzadas (como testing visual end-to-end con Chrome/Playwright, telemetría de rendimiento, o inspección profunda de Postgres), Antigravity debe buscar o sugerir la configuración del MCP correspondiente.
2. **Evolución de Habilidades**: Cuando se identifiquen flujos repetitivos o mejoras arquitectónicas, Antigravity debe sugerir empaquetar ese conocimiento en nuevas skills dentro de `.agents/skills/`.
