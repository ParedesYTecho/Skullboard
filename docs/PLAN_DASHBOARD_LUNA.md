# SkullBoard: plan de recuperación de sesión y renovación web para Luna

Fecha: 2026-09-10. Base inspeccionada: `9abaa74` en `main`.
Estado: **plan propuesto; implementación pendiente**. No certifica despliegue ni migraciones aplicadas.

## 1. Objetivo y límites

Entregar una web coherente y una dashboard donde iniciar sesión una vez permita recargar, abrir otra pestaña y volver después de reiniciar el backend. Proteger las credenciales OAuth, conservar permisos administrativos estrictos y evitar pérdida de ajustes. Renovar login, servidores, rankings, mensajes, ajustes y elementos comunes de las cinco páginas.

Mantener HTML/CSS/JS vanilla, Flask, Discord OAuth y Supabase. Preservar IDs del DOM y rutas existentes. Se pueden añadir endpoints auxiliares y archivos pequeños con responsabilidad concreta. No migrar a React/Tailwind, crear otro backend en Vercel ni modificar los eventos del bot.

Este documento es el encargo de implementación que se debe aprobar/iniciar después. Su redacción no autoriza ejecutar SQL de producción, mover credenciales, borrar sesiones existentes o desplegar cambios. Las autorizaciones previas de la conversación siguen aplicándose en su alcance concreto; no pedir de nuevo permiso para trabajo ya autorizado.

## 2. Hechos verificados y corrección del diagnóstico anterior

La revisión del 10 de septiembre incluyó inspección de código, consulta Graphify, ejecución de los 50 safeguards y reproducción aislada de dos funciones JavaScript mediante Node VM y respuestas simuladas. No se inició OAuth real ni se consultaron filas de sesiones de producción.

| ID | Prioridad | Hallazgo real | Ubicación base / evidencia |
|---|---|---|---|
| B01 | P0 | Recargar `/dashboard` sin `?code` devuelve `authToken=null`; `init()` termina antes de comprobar la cookie con `/api/auth/me`. | `legal/dashboard.html`, `getOrExchangeAuthToken` alrededor de 402 e `init` alrededor de 1264. Reproducido: cero consultas de sesión. |
| B02 | P0 | `loadMyMessages()` lanza error cuando la petición sí pertenece al servidor activo. | `legal/dashboard.html`, alrededor de 678–680: `else { throw ... }` asociado al guard. Reproducido con `{ok:true}`. |
| B03 | P1 | Solo `vercel.json` de raíz tiene rewrite `/api/:path*`; `legal/vercel.json` no. | El resultado depende del Root Directory configurado realmente en Vercel; no verificado en esta tarea. |
| B04 | P1 | `SESSION_TTL` sigue siendo 3600, no 30 días. Se ignoran `expires_in` y `refresh_token`. | `webserver.py`, `SESSION_TTL`, `api_auth_token`. |
| B05 | P1 | Sesiones guardan ID reutilizable y token Discord en texto legible. Al fallar inserción se usan sesiones de memoria silenciosamente. | `_new_session`, `_session_token`, migración `20260910_web_sessions.sql`. Existencia remota de tabla desconocida. |
| B06 | P1 | OAuth de dashboard no vincula `state` al navegador. El flujo `/verify` es diferente y no protege esta ruta. | `triggerDiscordAuth`, `/api/auth/token`. |
| B07 | P1 | POST de configuración sin JSON puede convertirse en `{}` y guardar valores por defecto; no hay control de origen/CSRF en esa mutación. | `api_guild_config`. Cookie actual `SameSite=None`; CORS no impide que llegue un POST. |
| B08 | P1 | Logout ignora un DELETE fallido y frontend navega sin esperarlo. | `api_auth_logout`, `_sb_delete`, listener `btn-dropdown-logout`. |
| B09 | P1 | Fallos temporales de Discord/BD pueden convertirse en 401, listas vacías, ajustes por defecto o 500 sin contrato útil. | `_fetch_discord_user`, `_fetch_discord_guilds`, `_sb_select` y consumidores. |
| B10 | P1 | Fallar al cargar ajustes vuelve a habilitar Guardar. Guardado tardío puede modificar estado visual de otro servidor. | `setSettingsFormState`, `loadGuildConfig`, submit del formulario. |
| B11 | P2 | Dos contadores globales de cargas, estados de canal compartidos y caché local pueden producir invalidaciones cruzadas o contexto viejo. | `requestSerial`, `currentGuildLoadId`, `currentGuildChannels`, `init`. |
| B12 | P2 | Subtabs eliminan outline después de reglas de foco; reglas móviles se añaden antes de reglas base y se pisan. Falta `--surface-hover`. | `legal/styles.css`, `.lb-sub-tab`, media query 540px y bloque final. |
| B13 | P2 | Footer se oculta en cada petición; estados de carga, error, vacío y búsqueda incompletos. | `hideFooter`, loaders, listas y formularios. |
| B14 | P2 | Modal muestra Online/Operacional/99.9% estáticos. Backend inventa bot activo si falta proveedor y confunde SELECT fallido con BD operativa. | `fetchSystemStatus`, `api_status`, HTML de cinco páginas. |
| B15 | P2 | Service worker puede cachear navegación `/dashboard?code=...`; no tiene restricción de origen/allowlist para otras respuestas. | `legal/sw.js`. Ya excluye `/api/`, lo que debe conservarse. |
| B16 | P1 | Tests existentes no ejercitan restauración, cookies, CSRF ni logout real. Tests adversariales antiguos usan bearer/IDs inválidos y dobles incompletos. | `scripts/safeguards_test.py`, `adversarial_*`. Los 50 pasan con B01 y B02 presentes. |
| B17 | P2 | Privacy/landing no explican sesiones OAuth; «Zero-Data» puede inducir a error. | `legal/privacy.html`, `legal/index.html`, `docs/SECURITY.md`. |

P0: recorrido principal roto. P1: seguridad, integridad o sesión no fiable. P2: UX, accesibilidad, consistencia y operación. Estas prioridades son de trabajo, no una clasificación CVSS.

Ya hay mejoras útiles: nombres de servidores escapados, toast escapado, dropdown claro, skeletons, ARIA parcial y números tabulares. Conservarlas y verificar comportamiento; no volver a añadirlas como si faltaran.

### Correcciones que deben guiar toda implementación

- Vercel sirve interfaz y puede actuar como proxy. `webserver.py` en Render sigue procesando autenticación y datos. Un proxy no traslada la ejecución de Flask a Vercel.
- La cookie contiene un identificador de sesión; el token Discord reside en el backend/almacenamiento. No describir ambos como lo mismo.
- `identify` y `guilds` conceden perfil básico y lista de servidores. No conceden control completo de cuenta ni lectura de DMs. Quien posea el token sí puede utilizar los permisos concedidos. [Discord OAuth2](https://docs.discord.com/developers/topics/oauth2).
- RLS limita roles de BD; `service_role` y administradores privilegiados no quedan aislados por RLS. [Supabase RLS](https://supabase.com/docs/guides/database/postgres/row-level-security).
- Cifrado de tokens con clave separada protege frente a filtración de BD sin clave. El operador que controla backend y clave sigue pudiendo descifrarlos. No prometer que Fer carece de acceso técnico.
- Una cookie Flask firmada protege integridad, pero su contenido puede leerse. No introducir tokens allí como sustituto de cifrado. [Flask: sesiones](https://flask.palletsprojects.com/en/stable/quickstart/#sessions).
- Una cookie cifrada con clave persistente puede sobrevivir a reinicios. No es automáticamente más segura y complica revocación centralizada; no será la arquitectura elegida aquí.
- Guardar OAuth para prestar el servicio no equivale por sí solo a acceso ilícito. Deben definirse finalidad, base jurídica, transparencia, retención y seguridad; autorización OAuth no resuelve por sí sola todo el RGPD. No emitir certificación legal. [RGPD](https://eur-lex.europa.eu/eli/reg/2016/679/oj), [política de desarrolladores Discord](https://support-dev.discord.com/hc/en-us/articles/8563934450327-Discord-Developer-Policy).

## 3. Arquitectura elegida para este plan

```text
Navegador
  cookie HttpOnly con ID aleatorio
       │ HTTPS mismo origen /api/*
       ▼
Vercel: HTML/CSS/JS + proxy de API, sin cachear respuestas privadas
       │ HTTPS
       ▼
Flask en Render: valida sesión, origen, CSRF y permisos
       ├── Discord: perfil, servidores, intercambio/renovación OAuth
       └── Supabase: hash del ID + credenciales cifradas + caducidad
               Clave de cifrado: solo entorno secreto del backend
```

La propuesta conserva Supabase para sesiones y sustituye el almacenamiento de credenciales legibles por cifrado autenticado. No introducir simultáneamente Redis, Supabase Auth y cookies con tokens. Si el usuario exige que su infraestructura nunca pueda usar tokens OAuth, detener esa decisión de producto: esta propuesta no ofrece esa propiedad y requeriría replantear integración y confianza.

### 3.1 Contrato de cookie y expiraciones

| Elemento | Valor objetivo |
|---|---|
| Cookie producción | `__Host-skb_session`, valor `secrets.token_urlsafe(32)`; validar formato antes de consultar BD |
| Atributos | `HttpOnly; Secure; SameSite=Lax; Path=/`; sin `Domain` |
| Caducidad de sesión | 30 días absolutos desde login, sin extensión indefinida por actividad |
| Caducidad Discord | La devuelta en `expires_in`; renovar al acercarse a expirar, margen objetivo 120 s |
| Fin anticipado | Logout, desconexión/revocación del proveedor, error de credencial permanente o rotación de emergencia |
| Entorno local | Cookie separada sin prefijo `__Host-`, `Secure=False` solo en desarrollo explícito y loopback; jamás inferir producción a partir de un header manipulable |
| Navegador | Solo preferencia de tema y último servidor en storage; nunca access/refresh token ni ID de cookie copiado a JS |

`SameSite=Lax` es apropiado después de comprobar proxy de mismo origen. No basta con cambiar ese atributo mientras el cliente sigue llamando a otro sitio. [Atributos de cookie](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie).

El objetivo de 30 días exige renovación y revocación probadas; cambiar solo `SESSION_TTL` no lo cumple. Si Discord revoca acceso, pedir login aunque resten días. No prometer sesión permanente.

### 3.2 Almacenamiento seguro, sin arrastrar credenciales antiguas

Crear una migración nueva y aditiva para `public.dashboard_sessions`; no reescribir una migración potencialmente aplicada. Mantener `web_sessions` sin uso en el código nuevo y preparar su retirada por separado. No convertir tokens antiguos en masa durante el despliegue; pedir login una vez para crear sesión nueva.

Esquema objetivo:

| Campo | Tipo / regla | Finalidad |
|---|---|---|
| `session_hash` | `text primary key`, SHA-256 hexadecimal del ID | Buscar/revocar sin guardar cookie reutilizable |
| `user_id` | `text not null`, Snowflake validado | Vincular sesión a identidad |
| `token_bundle` | `text not null` | Cifrado autenticado de access token, refresh token, scopes e identidad |
| `token_expires_at` | `timestamptz not null` | Renovación basada en Discord |
| `session_expires_at` | `timestamptz not null` | Vencimiento absoluto |
| `created_at` | `timestamptz not null` | Retención y trazabilidad mínima |
| `refresh_lock_until` | `timestamptz null` | Reserva temporal para renovar entre workers |
| `refresh_lock_id` | `text null` | Identificar propietario de reserva |
| `token_version` | `integer not null default 0` | Impedir que un renovador atrasado sobrescriba o invalide credenciales nuevas |

Índice adicional en `session_expires_at`; clave primaria ya indexa búsquedas. No guardar IP, user-agent, lista de servidores ni contenido de mensajes por defecto.

Usar `cryptography` con Fernet/MultiFernet, versión estable verificada y fijada como dependencia directa si se utiliza. Comprobar primero disponibilidad real: ausencia en `requirements.txt` no demuestra ausencia en el entorno. No diseñar cifrado casero, derivar clave del token del bot ni guardar clave junto a BD. [Fernet](https://cryptography.io/en/latest/fernet/).

El contenido autenticado del bundle incluirá versión, `session_hash`, `user_id`, scopes y caducidad absoluta; verificar coincidencia con la fila. Esto evita aceptar un blob copiado de otra sesión. Validar tipos, tamaños y fechas al descifrar. Nunca loguear blob, token, cookie ni cuerpos OAuth.

Clave estable `WEB_SESSION_KEYS` en gestor de secretos del backend; primera clave cifra, claves anteriores permiten transición. Falta/clave inválida: autenticación responde 503 identificable y alerta sanitizada; no generar clave al arrancar ni detener el bot por un fallo exclusivo del panel. Una rotación planificada conserva clave anterior hasta migrar/expirar sesiones; una rotación de emergencia invalida sesiones y se comunica.

RLS habilitado y revocación de privilegios a `PUBLIC`, `anon`, `authenticated`; conceder solo operaciones necesarias a `service_role`. Verificar también ausencia de accesos indirectos por vistas, RPC y grants heredados. Nada de políticas `using (true)` para esta tabla. Probar desde los roles reales en BD desechable.

No usar el fallback a `_sessions` en producción. Una sesión nueva solo se considera creada tras confirmar persistencia. Distinguir fila inexistente (401) de almacenamiento no disponible (503).

### 3.3 OAuth, origen y renovación

Conservar `/api/auth/token`, `/me`, `/guilds`, `/logout`. Añadir `POST /api/auth/start` para iniciar el flujo desde el backend. Mantener callback en `/dashboard` para no obligar a cambiar URL registrada en Discord.

Secuencia prevista:

1. Cliente pide `/api/auth/start` con JSON y origen permitido.
2. Backend genera state aleatorio y nonce de navegador en una cookie HttpOnly independiente para ese flujo. Guarda hashes y expiración en tabla temporal `dashboard_oauth_states`.
3. Devuelve exclusivamente URL de autorización con scopes `identify guilds`, state y redirect permitido.
4. Discord vuelve a `/dashboard?code=...&state=...` o con error de cancelación.
5. JS captura parámetros, limpia URL del historial inmediatamente y envía code/state a `/api/auth/token`.
6. Backend consume state atómicamente condicionado a hash de nonce y `expires_at > now()`. Ausente, ajeno, caducado o reutilizado: rechazar antes del intercambio.
7. Intercambia code una vez, comprueba identidad/scopes y guarda bundle cifrado. Devuelve cookie y perfil mínimo, nunca credenciales.
8. Cliente comprueba `/api/auth/me` y después carga servidores.

`dashboard_oauth_states`: `state_hash` PK, `browser_hash`, `expires_at`; TTL 10 minutos e índice de expiración. Consumo mediante DELETE condicionado con resultado confirmado. Cookie por flujo: `__Host-skb_oauth_<sha256(state)>`, nonce aleatorio como valor, `HttpOnly; Secure; SameSite=Lax; Path=/`, sin Domain, Max-Age 600. Usar variante local explícita como con la cookie de sesión. Validar formato/longitud de state antes de calcular nombre y borrar solo esa cookie al consumir/cancelar el flujo. Cada `/start` crea su propia cookie: dos primeras solicitudes sin cookie y con respuestas invertidas no se pisan. Limitar tasa de `/start` y vida de state/cookies para evitar acumulación; no alargar indefinidamente al reintentar. No tocar `_oauth_states` de Linked Roles ni romper `/verify` y `/callback`.

Control CSRF: origen exacto permitido + Content-Type JSON en POST de inicio/intercambio; token CSRF ligado a sesión en configuración/logout/desconexión. `/me` puede entregar ese token separado, derivado con HMAC de clave y sesión, sin revelar ID ni OAuth. Añadir `X-CSRF-Token` a cabeceras permitidas donde proceda. Comparación constante y validación backend obligatorias. CORS no es autorización.

Renovación distribuida:

- Adquirir reserva mediante actualización atómica condicionada a reserva vencida y sesión vigente. Una sola petición obtiene la fila.
- Renovador llama a Discord una vez, timeout acotado. Escribe nuevo bundle solo si conserva `refresh_lock_id`, `token_version` leído y sesión sigue existiendo/vigente; incrementa versión al guardar. Nunca hacer upsert que resucite sesión eliminada.
- Otros workers releen o responden error temporal reintentable, sin renovar en paralelo. Máximo de espera/peticiones definido; no bucles infinitos.
- `invalid_grant`/revocación permanente invalidan sesión únicamente si el resultado corresponde todavía al propietario de reserva y versión vigentes. Un renovador atrasado no puede borrar una sesión recién renovada: releer y usar resultado vigente o devolver error temporal. Timeout, 429 y 5xx conservan sesión y devuelven 503/429.
- La reserva coordina workers en operación normal; no garantiza exactamente una llamada externa si un proceso queda suspendido más allá de su vencimiento. Probar esa ventana, aplicar condiciones también al liberar reserva/invalidate y nunca asumir que timeout implica que Discord no procesó la renovación.
- Si Discord renovó y el proceso cae antes de persistir, la próxima renovación puede requerir login. Documentar esta ventana; no inventar recuperación de un token que no llegó a almacenarse.
- No mantener un bloqueo global Python durante llamadas HTTP. Probar dos workers sobre almacenamiento compartido simulado.

### 3.4 Logout, eliminación y errores

Logout elimina únicamente fila de la sesión actual por hash y limpia cookie con mismo nombre/path. Debe ser idempotente: con origen válido y sesión inexistente devuelve éxito y limpia cookie, sin exigir un CSRF que ya no se puede recuperar; con sesión existente exige CSRF válido. Una indisponibilidad de BD no equivale a sesión inexistente. Si BD falla, no anunciar revocación completada: conservar posibilidad de reintentar, ocultar datos sensibles y mostrar error. UI navega solo después de confirmación. Probar repetición después de perder la respuesta de un DELETE exitoso.

Añadir acción explícita «Desconectar Discord» para revocar autorización OAuth mediante endpoint de Discord y finalizar sesiones de ese usuario según resultado real. Explicar posible efecto entre sesiones; no presentarla como un simple cierre de pestaña. No confundir eliminación de fila con revocación del grant OAuth.

Purga automática diaria de filas con expiración vencida, solo tablas de sesión/state; trabajo programado de BD si está disponible. Crear configuración revisable y comprobar ejecución con datos de prueba. No crear una automatización de Codex para cumplir retención del producto. Regla objetivo: filas activas eliminadas al logout, vencidas retiradas en ≤24 h; backups según retención real del proveedor, sin promesa de borrado instantáneo de copias.

Contrato común, preservando `ok` y `error`:

| HTTP | `code` sugerido | UI |
|---|---|---|
| 200 | — | Aplicar datos validados |
| 400/415 | `invalid_input` | Error de campo; ninguna escritura |
| 401 | `session_expired` | Login claro, una sola transición |
| 403 | `forbidden` / `csrf_rejected` | Permiso insuficiente; no borrar sesión por defecto |
| 429 | `rate_limited` | Espera según Retry-After; sin recarga automática |
| 503 | `service_unavailable` / `session_not_configured` | Reintentar conservando sesión y borrador |

No cachear `/api/auth/*`, respuestas privadas de guild ni respuestas con `Set-Cookie`: `Cache-Control: no-store`. Revisar comportamiento CDN del proxy, no asumirlo. Mantener caché pública solo para información realmente pública.

## 4. Contrato de UX y diseño

### 4.1 Dirección visual fijada

Identidad SkullBoard: carbón, blanco suave, calavera de marca y acento Discord contenido. Componentes quietos, bordes finos, foco evidente y contenido legible. Referencias Linear/Raycast sirven como orientación estética; no agregar librerías de sus ecosistemas ni copiar estilos completos. No se ha auditado una URL real de Werewolf; no afirmar paridad ni asumir su arquitectura.

Reutilizar nombres actuales de tokens. Modificar reglas originales/consolidarlas, evitando apilar otra tanda de overrides con `!important`.

| Token/medida | Oscuro | Claro |
|---|---|---|
| `--bg` | `#0a0a0c` | `#f3f4f6` |
| `--surface` | `#141418` | `#ffffff` |
| `--surface-2` | `#1c1c22` | `#e9ecf2` |
| `--surface-hover` | `#24242c` | `#e0e5ee` |
| `--ink` | `#f2f2f5` | `#151821` |
| `--ink-soft` | `#b8b8c4` | `#4b5563` |
| `--ink-dim` | `#9797a6` | `#5b6472` |
| Borde | blanco al 10–12% | negro al 12–14% |
| Acento de acción/foco | `#a5b4fc` | `#4338ca` |
| Radio | tarjetas 16px, controles 10px, login 20px | Igual |
| Espaciado | escala 4/8/12/16/24/32/48px | Igual |

Los colores son propuesta inicial; medir contraste en cada combinación, incluidos disabled, placeholders y estados. Texto normal ≥4.5:1, texto grande ≥3:1 y controles/foco distinguibles ≥3:1 donde corresponda. No afirmar AA solo por seleccionar un hex.

Inter para UI, Manrope para títulos. Body/control 16px en móvil, secundarios 13–14px, título panel 24–28px desktop y 22–24px móvil. Contadores con `tabular-nums` y formato `Intl.NumberFormat('es-ES')`. Foco 2px y offset 2px. Objetivos táctiles 44×44px. Movimiento 120–180ms en opacity/color; respetar reduced-motion. Sin shimmer permanente en barra ni animaciones de números que distraigan.

### 4.2 Estructura general

Desktop: contenedor máximo 1180px, margen lateral 24px. Móvil: margen 16px y padding interior de panel 16px; 24px desktop. Navbar con altura previsible y espacio reservado en contenido. En dashboard debe permanecer localizable; no ocultar controles mientras tienen foco. Navbar y menú móvil conservan Inicio, Cambios, Panel, tema y cuenta.

Login: tarjeta máximo 480px, icono 56px, título breve, texto de dos/tres líneas, CTA Discord dominante de ancho completo y acción secundaria discreta. No renderizar una tarjeta de login durante una comprobación válida de sesión.

```text
┌ marca · navegación · tema · cuenta ┐
│                                   │
│       [icono SkullBoard]           │
│       Tu comunidad, en un lugar   │
│       Continúa con Discord        │
│       [ Continuar con Discord ]   │
│       Solo perfil y servidores    │
│       Privacidad · Volver         │
└ footer compacto y estable ────────┘
```

Dashboard: barra de contexto del servidor, navegación de tres pestañas, cabecera del panel con buscador/filtros y contenido. El footer conserva altura/posición durante cargas. No introducir sidebar fija en móvil.

### 4.3 Estados de login (sin framework)

Una función `showAuthState(...)` será dueña de qué vista se muestra. Estados simples: `checking`, `anonymous`, `redirecting`, `authenticated`, `expired`, `error`. No biblioteca de máquinas de estado.

| Situación | Resultado esperado |
|---|---|
| Primera visita sin cookie | Checking breve → login normal, sin mensaje de sesión expirada |
| Recarga con cookie válida y sin code | `/me` valida → perfil/servidores, sin pedir Discord |
| Inicio OAuth | Deshabilitar botón y «Abriendo Discord…»; pageshow restablece botón al volver |
| Callback cancelado | «Has cancelado el acceso» + botón para intentarlo otra vez |
| Callback inválido/reutilizado | Error claro; no reutilizar código ni crear bucle |
| Sesión revocada | Limpiar contexto, cancelar loaders y presentar login |
| Red lenta | Estado de comprobación; tras espera mostrar información útil; timeout finito y botón Reintentar |
| 503/429 | Error temporal; no afirmar que la sesión caducó |
| Storage bloqueado | Tema/último servidor pueden no persistir; sesión por cookie debe funcionar |
| Otra pestaña cierra sesión | Evento BroadcastChannel o storage sin datos secretos → invalidación de UI; siguiente API verifica igualmente |

El backend determina autenticación. No usar `authToken='server-session'`, presencia de caché o permisos guardados como prueba de login. Prefetch de datos de usuario solo después de validarlo. No persistir la lista completa de servidores en localStorage; caché en memoria por sesión basta.

### 4.4 Servidores, rankings, mensajes y ajustes

- Servidores: búsqueda siempre disponible, contador de resultados y distinción «Bot añadido»/«Invitar bot». Mantener filtrado de servidores autorizados. Tarjetas con icono, nombre truncado accesible y una acción dominante. Respetar búsqueda al volver, o limpiarla junto con lista: nunca campo filtrado + lista completa.
- Rankings: conservar subpestañas usuarios/mensajes. Filas con posición, avatar, nombre, métricas alineadas; en móvil segunda línea para acciones. No convertir todo en una rejilla de tarjetas grandes. Enlaces Discord con destino validado, handler de eventos y texto claro. Intentar abrir app no debe abrir a la vez app y web obligatoriamente.
- Búsqueda de mensajes: filtrar datos ya cargados por autor, canal o ID. Etiqueta «Buscar entre estos resultados» y cantidad cargada; no prometer búsqueda global ni contenido completo, que no se almacena. Reutilizar límites de API. No cargar N registros para filtrar millones en memoria ni añadir agregaciones a Python.
- Mis mensajes: métricas propias y lista, estados vacíos con acción útil. Reset visual al cambiar guild, no mostrar cifras anteriores mientras carga. No incluir contenido privado ni inventar previews.
- Ajustes: agrupar Canal → Umbrales → Comandos, explicaciones breves y desactivación explícita de Auto-Pin con cero. Mantener inputs numéricos actuales y sus IDs; no introducir sliders como requisito nuevo. Prefijo con límite único frontend/backend (propuesta 10 caracteres, preservando valores existentes).
- Guardado: `loading/error/ready/dirty/saving/saved`; botón activo solo con config válida cargada, permiso y cambios. Mostrar «Cambios sin guardar», «Guardando…», «Guardado» o error concreto. No habilitar por un `finally` si cambió servidor o falló carga. Reconciliar formulario con respuesta normalizada del backend.
- Borradores: conservar en memoria por guild mientras navega entre pestañas. Al cambiar servidor con cambios, permitir continuar con borrador conservado; aviso antes de salir/recargar cuando corresponda. Ninguna respuesta tardía sobrescribe edición más reciente.
- Cargas: skeletons con `aria-busy`, tamaño próximo al contenido final y una transición discreta. No vaciar listas visibles por cualquier actualización en segundo plano.
- Vacíos: distinguir ningún servidor, búsqueda sin coincidencias, ningún mensaje, permiso insuficiente y fallo de red. Cada error recuperable incluye Reintentar; vacío no se pinta como error.

### 4.5 Accesibilidad y páginas públicas

Tabs con `tablist/tab/tabpanel`, `aria-controls`, `aria-selected`, tabindex móvil y flechas/Home/End. Activación manual con Enter/Espacio cuando dispare red; flechas no deben lanzar cargas en cascada. [Patrón tabs WAI](https://www.w3.org/WAI/ARIA/apg/patterns/tabs/).

Canales: completar combobox existente con nombre accesible, lista, opción activa, flechas, Enter y Escape; mantener select oculto/IDs si se usan para compatibilidad. Input con label, texto de ayuda conectado mediante `aria-describedby` y errores de campo. Menu de cuenta: disclosure de botones simple o menú completo, nunca semántica parcial de menú.

Modal estado: foco inicial, Escape, cierre accesible, foco de retorno y fondo no interactivo. Preferir `<dialog>` si conserva IDs y permite pruebas; si se conserva overlay, implementar el patrón completo. [Patrón modal WAI](https://www.w3.org/WAI/ARIA/apg/patterns/dialog-modal/).

Inicio: conservar hero «Lo mejor de tu servidor, destacado», dos CTA jerarquizados (Añadir a Discord / Abrir panel), métricas reales, beneficios y buscador de comandos. Reducir ornamentación que compite con CTA. Sustituir afirmaciones ambiguas «Zero-Data» por descripción verificable del tratamiento mínimo.

Cambios: mantener historial; mejorar ritmo tipográfico, fechas y etiquetas. Privacy/Terms: columna de lectura de 70–75 caracteres, títulos claros, fecha real de actualización y enlaces coherentes. Footer, tema y modal deben verse iguales en todas las páginas. Conservar formulario de contacto, validación y feedback; no enviar mensajes reales durante pruebas.

Matriz visual obligatoria: 360, 390, 414, 768 y 1440px; oscuro/claro; zoom 200%; teclado y reduced-motion. Medir contenido fuera del viewport, no solo ausencia de scrollbar: `overflow-x:hidden` puede esconder fallos. Desbordamiento horizontal permitido: 0px fuera de tolerancia de redondeo ≤1px.

## 5. Plan de ejecución por paquetes

Cada paquete indica dependencias, archivos y cierre verificable. Luna debe terminar implementación y verificación local de un paquete antes de editar el siguiente dependiente. Separar ese cierre local de validación remota: gates de OAuth real, migración y despliegue pueden quedar pendientes hasta P11 sin bloquear trabajo local independiente. Nunca convertir pendiente remoto en completado. Los nombres de tests siguientes son objetivos a crear, no archivos ya existentes.

### P00 — Inventario y baseline

Archivos a leer: AGENTS/brain, este plan, `webserver.py`, `legal/dashboard.html`, `legal/styles.css`, ambos `vercel.json`, `legal/sw.js`, migraciones y tests existentes.

1. Ejecutar status/diff/log y comparar fechas de Graphify. Si HEAD cambió, actualizar hallazgos B01–B17 antes de editar.
2. Consultar Graphify por concepto concreto; usar símbolos para localizar callers. No volcar el grafo completo.
3. Comprobar Root Directory y último despliegue de Vercel con lectura de configuración, nunca mostrar secretos. Verificar con GET anónimo que `/api/health` y `/api/auth/me` son JSON, no HTML.
4. Consultar solo metadatos de migraciones/RLS/grants y presencia de `web_sessions`; nunca SELECT de tokens ni imprimir cookies. Si no hay acceso, anotarlo como pendiente de verificación, no asumir tabla aplicada.
5. Registrar versiones Python/Node y dependencias de pruebas disponibles. Capturas baseline del login y páginas públicas; para dashboard usar datos sintéticos locales.

Cierre: matriz de comprobado/pendiente, sin cambios a producción. Reproducciones B01/B02 y salida inicial de safeguards guardadas de forma sanitizada.

### P01 — Regresiones mínimas y arranque correcto

Depende P00. Archivos: `legal/dashboard.html`, `scripts/dashboard_regression.test.cjs`.

1. Añadir tests Node que ejecuten JS real con dobles mínimos de DOM/fetch; no comprobar solo que existe una cadena.
2. Reproducir B01/B02 en rojo. Extraer funciones con rangos delimitados/parseo robusto; no regex frágil que ignore llaves anidadas.
3. Quitar bifurcación que niega login por no haber code. Siempre verificar cookie vía `/me`; intercambio de code es un paso opcional distinto.
4. Eliminar `else throw` incorrecto de mensajes. No eliminar la comprobación de respuesta `ok:false` legítima.
5. Renderizar usuario validado una sola vez; errores de sesión/red separados. Capturar code/error/state y limpiar URL pronto.

Cierre: ambos tests pasan, respuesta 200 muestra mensajes y recarga válida no presenta login. IDs/rutas conservados. No declarar persistencia entre reinicios todavía.

### P02 — Proxy, cookies y caché

Depende P00/P01. Archivos: `vercel.json`, `legal/vercel.json`, `legal/sw.js`; ajuste localizado de API_BASE si es necesario.

1. Mantener rewrite en ambas configuraciones mientras existan dos raíces posibles; añadir comprobación de coherencia para impedir divergencia.
2. Usar `/api/*` desde dashboard; comprobar método, cuerpo, cookies, Origin y Set-Cookie atravesando proxy. Preview sin configuración OAuth no debe redirigir a un dominio arbitrario.
3. Service worker: cachear solo assets públicos del mismo origen y GET permitido. Excluir API, navegación OAuth con code/state/error y cualquier respuesta privada/no-store. No borrar caches ajenas al prefijo `skb-`.
4. Versionar cache cuando corresponda y probar navegación con worker antiguo y actualizado. Mantener offline de páginas públicas sin simular autenticación offline.
5. Revisar redacción de querystrings/cabeceras sensibles en logs de aplicación y plataforma. Limpiar historial no elimina un code que el proxy ya registró; no exportar esos logs sin sanitizar.

Cierre local: configuraciones coherentes y tests de caché/proxy pasan. Gate remoto para P11: tras OAuth real en prueba controlada, cookie se recibe para dominio visible y `/me` funciona con cookies de terceros bloqueadas. Si no hay prueba de despliegue, marcar pendiente; test local del rewrite no sustituye navegador real.

### P03 — Persistencia cifrada y migración aditiva

Depende P00. Archivos: `dashboard_sessions.py` (nuevo módulo acotado), `webserver.py`, `requirements.txt` si procede, migración nueva y `scripts/test_dashboard_sessions.py`.

1. Generar archivo de migración usando CLI instalado y `--help`; no asumir comandos ni historia remota. Crear tablas nuevas de sesión y state, RLS/grants/índices de la sección 3 en una transacción local.
2. Módulo concreto con crear/cargar/eliminar sesión y operaciones de state; sin framework de repositorios ni interfaces con una implementación. Reusar transporte HTTP existente cuando mantenga errores distinguibles. No cambiar `_sb_upsert` compartido sin probar todos sus callers.
3. Persistir solo hash de cookie y bundle cifrado. Validar inputs antes de PostgREST; ausencia de cookie no debe hacer consultas.
4. Distinguir error almacenamiento de sesión ausente. Eliminar fallback de memoria en producción. Reutilizar contexto Flask `g` para no consultar/descifrar varias veces dentro de una misma request.
5. Tests con Flask real/test_client y transporte simulado; bloquear toda salida de red real en tests. Reinicio simulado recrea módulo/instancia con mismas claves y BD; no basta con recargar el diccionario.

Cierre: dump simulado de BD carece de tokens/IDs reutilizables, cookie alterada/ciphertext inválido rechazados, sesión sobrevive cambio de proceso y fallo de persistencia nunca da login exitoso. Migración local lista; aplicación remota requiere gate de sección 7.

### P04 — OAuth, CSRF y autorización

Depende P01/P02/P03. Archivos: `webserver.py`, `dashboard_sessions.py`, `legal/dashboard.html`, `scripts/test_dashboard_auth.py`.

1. Implementar start/state/intercambio de sección 3.3. Probar dos `/start` simultáneos sin cookies iniciales, respuestas invertidas y ambos callbacks válidos una sola vez. Mantener scopes mínimos y redirect exacto configurado; parámetros de URL no eligen destinos libres.
2. Exigir objeto JSON y campos válidos. Rechazar form-urlencoded, arrays, null, cuerpo vacío y JSON inválido sin escribir defaults.
3. Añadir CSRF a POST autenticados y validación Origin. Actualizar fetch de configuración/logout con header; no copiar cookie a JS.
4. Preservar propiedad/admin `0x8`. Para lectura privada comprobar pertenencia. Revisar límites actuales de rutas leaderboard con nombre `public`: no cambiar audiencia silenciosamente. Propuesta de privacidad: rankings de servidor visibles a miembros; antes de activar restricción inventariar consumidores públicos y documentar decisión de producto.
5. Validar canal por ID, pertenencia al guild, tipo admitido y permisos efectivos del bot necesarios para publicar; no confiar en que apareció en el selector. Canales temporariamente inaccesibles: error recuperable, ninguna escritura.

Cierre: estado ajeno/reutilizado y POST cross-site rechazados; admin/owner aceptados; Manage Server `0x20` solo rechazado; usuario no miembro rechazado en rutas privadas. No publicar un cambio de audiencia sin resolver consumidores existentes.

### P05 — Renovación, logout y retención

Depende P03/P04. Archivos: módulo sesiones, rutas auth y mismos tests; script/SQL de purga acotado.

1. Aplicar tiempos de sección 3 y guardar refresh token cifrado; no renovar un token por cada consulta.
2. Implementar reserva distribuida con actualización condicional de la fila; fijar límite temporal superior a timeout OAuth, p. ej. reserva 30 s y petición 8 s. Probar renovación simultánea y recuperación de reserva vencida.
3. Logout esperado por frontend; revocación local confirmada. Logout durante refresh no puede recrear fila.
4. Implementar desconexión explícita y purga diaria revisable. Definir impacto sobre filas antiguas y copias de seguridad.
5. Configurar secreto estable y rotación documentada. No imprimirlo en terminal, chat, commit ni captura.

Cierre: tiempo simulado t0+29d sigue válido con renovación; t0+30d expira. Revocación Discord obliga a login. 503 no borra sesión. Cookie guardada antes de logout exitoso ya no autentica. No anunciar 30 días antes de pasar estos casos.

### P06 — Peticiones y estado de dashboard

Depende P01/P04. Archivos: `legal/dashboard.html`, tests JS.

1. Crear un helper pequeño de fetch JSON con timeout/cancelación, credenciales y traducción de errores del contrato; aplicarlo a todos los callers del panel.
2. Usar generación de guild + versión por recurso. Eliminar duplicación de contadores; no dejar un contador global que cancele recursos independientes.
3. Comprobar vigencia antes de actualizar DOM tanto en éxito como catch/finally. AbortError no muestra toast. Guardados capturan guild/payload y respuesta solo modifica su estado.
4. Mantener borradores por guild y normalizar valores con un límite común de prefijo. `ready` y `dirty` son explícitos; error de carga nunca habilita Guardar.
5. Resetear canales/métricas al cambiar contexto; cargar solo lo necesario. Identidad y permisos se validan en servidor, caché UI solo optimiza presentación.

Cierre: secuencias A→B→A, usuarios→mensajes, guardar A→abrir B y carga→logout no mezclan datos, no pierden borradores ni reabren vistas cerradas.

### P07 — Sistema visual y navegación

Depende P06. Archivos: `legal/styles.css`, `legal/dashboard.html` y pruebas visuales.

1. Consolidar tokens y reglas de componentes. Borrar duplicados únicamente tras localizar usos en las cinco páginas. Scope `.dashboard-layout` para cambios específicos de panel.
2. Implementar especificación de sección 4. Retirar inline styles que impiden responsive sin renombrar IDs. Declarar media queries después de base o dentro de estructura de cascada clara.
3. Completar foco/tabs/navegación móvil, retirar outline:none sin reemplazo y desplazamiento de paneles no interactivos.
4. Aplicar tarjeta de login y estados de sesión con altura estable. Footer visible y estable; ningún contenido tapado por navbar.

Cierre: capturas login/servidores/tres pestañas en tamaños y temas acordados; contraste medido, controles 44px y cero recortes.

### P08 — Listados, búsqueda y ajustes usables

Depende P06/P07. Archivos: dashboard HTML/CSS y tests JS/browser.

1. Búsqueda de servidores siempre accesible; búsqueda local de resultados de mensajes con límites explícitos.
2. Layout compacto de rankings/mensajes y métricas; URLs validadas con constructor URL y allowlist `https://discord.com/channels/...`. Para deep links aceptar solo formato Discord derivado de IDs válidos. No interpolar URLs en onclick.
3. Añadir estados vacío/error/reintento y loaders con nombre accesible. Capturas con nombres/canales largos y números grandes.
4. Completar selector de canales con teclado, etiquetas y error de campo. Formulario con guardar/discard, borradores y estados de sección 4.

Cierre: buscar/limpiar/reintentar opera sin reload; nombres con marcado se ven como texto; navegación por teclado completa y guardado no ambiguo.

### P09 — Web pública y estado honesto

Depende P07. Archivos: cinco HTML, estilos compartidos y `webserver.py` para status. Dividir en dos commits: shell/status y contenido/landing.

1. Navbar/footer/tema/modal consistentes. Reutilizar un archivo JS pequeño para status/modal si evita cinco copias que divergen; no convertir el sitio a un sistema de templates nuevo.
2. Sustituir estados estáticos por estado desconocido/cargando/operativo/degradado/no disponible y fecha de última comprobación. Uptime es duración, no porcentaje SLA inventado.
3. Backend: falta de proveedor es desconocido; SELECT fallido no prueba BD sana. No efectuar llamadas caras cada render; conservar TTL de status y refrescar al abrir modal.
4. Pulir hero, beneficios, comandos, contacto, changelog y legibilidad legal según sección 4.5. No alterar historial ni mandar correos reales.

Cierre: API caída/DB caída/bot desconectado aparecen de forma coherente en todas las páginas; enlaces limpios y contacto siguen funcionando en entorno simulado.

### P10 — Documentación y privacidad verificable

Depende P03–P09. Archivos: `docs/SECURITY.md`, `docs/DECISIONS.md`, `docs/SYSTEM_CONTEXT.md`, `legal/privacy.html` y referencias obsoletas concretas.

1. Describir arquitectura real, duración, roles, scopes, cifrado, revocación y recuperación. Marcar claramente límites de confianza del operador.
2. Privacy explica datos de perfil/servidores y credenciales OAuth cifradas, finalidad, proveedores, retención, contacto, desconexión y eliminación. No afirmar que no hay credenciales almacenadas si las hay.
3. Registrar quién controla claves, regiones/transferencias y retención de backups reales. Datos no comprobados quedan pendientes de completar antes de publicar texto definitivo; no inventarlos.
4. Decisión registrada solo cuando se implemente. Distinguir pruebas locales, migración aplicada y despliegue verificado en el informe.

Cierre: ninguna promesa contradice configuración/código y flujo de borrado tiene responsable/procedimiento concreto. Revisión legal formal se solicita al responsable si necesita una garantía jurídica; no se simula con tests.

### P11 — Integración, publicación y comprobación final

Depende todos los anteriores y gate de producción resuelto.

1. Ejecutar verificaciones de sección 6 sobre el HEAD exacto que se va a publicar. Si rebase/merge altera archivos relevantes, comprobar resultado integrado antes del push.
2. Comprobar migración aditiva y claves disponibles antes de activar escritor nuevo. No desplegar código que anuncia persistencia con esquema ausente.
3. Commit por paquete coherente, sin cambios de memoria ajenos. No amend de commits publicados. Leer diff completo antes de commit; no encadenar pruebas, commit, pull y push sin revisar resultados.
4. Seguir commit/push automático del proyecto cuando cambios estén completos, verificados y condiciones de publicación resueltas. En mantenimiento/pausa, conservar local y respetar gate existente.
5. Tras despliegue, verificar `/api/health`, cookie first-party y sesión restaurada en navegador real. Prueba controlada de reinicio del backend exige ventana acordada para no interrumpir el bot.
6. Entrega final con SHA, URL, evidencia de pruebas/capturas, estado de migración y pendientes reales. Si falta prueba OAuth/reinicio, decirlo y no declarar persistencia de producción verificada.

## 6. Pruebas y definición de terminado

### Comandos obligatorios del repositorio

```powershell
python -m py_compile main.py webserver.py
python scripts/safeguards_test.py
git diff --check
```

Tras añadir los archivos de este plan:

```powershell
python -m py_compile dashboard_sessions.py
python -m unittest discover -s scripts -p 'test_dashboard_*.py'
node --test scripts/dashboard_regression.test.cjs
node scripts/dashboard_browser_test.mjs
```

`dashboard_browser_test.mjs` será runner con Playwright disponible en entorno/herramientas del proyecto, después de verificar instalación. Usar dependencia de desarrollo fijada si falta y está autorizada. No añadir Playwright a runtime del bot. Browser local debe servir HTML real con API simulada, interceptar endpoints antes de navegar y bloquear red externa salvo recursos permitidos. CUA puede complementar inspección visual, pero dejar runner reproducible.

La prueba de sintaxis debe parsear **todos** los scripts inline y archivos JS, no solo Python. HTMLParser sirve para IDs/enlaces, no valida por sí solo HTML/CSS completo. Usar validación estructural + parser de CSS disponible + inspección del navegador; no enviar páginas con datos de usuarios a un validador remoto.

| Grupo | Casos mínimos que deben fallar si reaparece el bug |
|---|---|
| Login | Primera visita, recarga cookie válida sin code, nueva pestaña, cerrar/reabrir navegador, cancelación OAuth, doble clic, code consumido |
| Sesión | IDs malformados sin llamada BD, ciphertext manipulado, otra identidad/blob, caducidad absoluta, refresh antes de caducar, clave ausente/rotada |
| Persistencia | Dos instancias independientes, reinicio con misma clave, almacenamiento caído, tabla ausente, nunca fallback exitoso a memoria |
| Concurrencia | Dos refresh simultáneos, reserva vencida, renovador atrasado que devuelve invalid_grant después de éxito ajeno, logout durante refresh y escritura condicional que no resucita fila |
| Seguridad HTTP | State ajeno/ausente/caducado/reutilizado; Origin ajeno; CSRF ausente/incorrecto; content-type incorrecto; payload incompleto |
| Permisos | Owner/admin sí; 0x20 solo no; no miembro no; pérdida de admin; canal ajeno/no publicable rechazado sin escribir |
| Logout | Confirmado invalida cookie guardada; DELETE fallido no anuncia éxito; dos pestañas; respuesta perdida seguida de repetición idempotente |
| Errores | 401/403/429/503 diferenciados, HTML en respuesta API, timeout, offline; cero loops y mensajes recuperables |
| Dashboard | Mensajes ok:true muestran contenido; vacío verdadero; A→B con respuestas invertidas; borrador preservado; guardado de A no afecta B |
| XSS/URL | Nombres y errores con comillas/marcado; protocolos javascript/data rechazados; IDs numéricos y URLs válidas preservados |
| BD | Denegación real para anon/authenticated; solo rol backend; purga limitada; ningún token claro en resultados/documentación/logs |
| Diseño | 5 anchos × 2 temas en vistas clave, strings largos, teclado, zoom 200%, movimiento reducido, contraste y targets |
| PWA/CDN | API/Set-Cookie/callback OAuth sin caché; navegación offline pública; versión anterior del worker; dos usuarios sin datos compartidos |

No modificar pruebas para aceptar el bug. Si una prueba antigua fuerza una implementación obsoleta, reemplazar por comportamiento equivalente y explicar por qué. No llamar «50/50» a la cobertura total del producto.

Para privacidad y consola: comprobar ausencia de secretos mediante aserciones que impriman solo pass/fail, sin hacer grep que exponga el secreto encontrado. Capturas y artefactos usan usuarios ficticios.

## 7. Gates de producción y recuperación

Antes de aplicar SQL sobre Supabase existente, preparar consulta de metadatos y diff concreto. Pedir aprobación solo cuando la acción exacta no esté ya autorizada; explicar tabla/columnas/WHERE/impacto. No usar permiso para diseñar como permiso para borrar sesiones reales.

La creación de `dashboard_sessions`/`dashboard_oauth_states` es aditiva. La limpieza de `web_sessions`, retirada de su plaintext, purga programada y cambios de grants/esquema deben describirse expresamente. La regla del proyecto exige confirmación para ALTER/UPDATE/DELETE y similares sobre producción. La política aprobada de purga debe incluir de antemano tablas y condición de expiración; no pedir intervención humana por cada logout normal autorizado por el usuario de la web.

Secuencia segura de activación: revisar esquema/secreto → probar local → aplicar esquema aprobado → desplegar backend compatible → desplegar frontend/proxy → verificar → retirar legado con aprobación. Evitar una ventana donde frontend nuevo llame endpoints ausentes. Cambios de OAuth/CSRF requieren coordinación o un mecanismo temporal de activación explícito; jamás aceptar state ausente como compatibilidad silenciosa.

Si la nueva autenticación falla, mantener el bot online y mostrar error de panel recuperable. Corregir hacia delante o revertir únicamente cambios del despliegue con commit nuevo; no volver automáticamente a guardar tokens legibles ni restaurar sesiones revocadas desde backup. No tocar tablas operativas `settings`/`tracked_messages` para recuperar login.

Puntos de bloqueo legítimos: falta de acceso a configuración/deploy, clave de cifrado por provisionar, aprobación SQL concreta, política de audiencia pública no resuelta o validación OAuth real que necesita interacción del titular. Continuar paquetes independientes; no declarar completo el conjunto mientras falte un gate.

## 8. Instrucciones de ejecución para Luna

Root: preset local `gpt-5.6-luna` con esfuerzo `max`. No modificar configuración global ni aumentar modelo raíz. `explorer/worker/tester/researcher`: Luna medium. Máximo tres subagentes por sesión; reviewer Astra low solo para riesgo material. Si herramienta no admite modelo/skill configurado, informar y seguir root-only con verificaciones equivalentes; no cambiar de modelo silenciosamente.

Delegación propuesta: un explorer para evidencia de deploy/schema, un tester para harness sintético y un reviewer para seguridad final. No delegar archivos que root está editando. Cada encargo lleva objetivo, paths, prohibición de producción/escrituras ajenas y reporte ≤10 puntos; no logs crudos. Usar subagentes, no crear tareas nuevas del usuario.

Antes de programar cambios de diseño, comparar el contrato de sección 4 con código/capturas. `/grill-me` es opcional para preferencias estéticas; recomendarlo si aparece ambigüedad material. La propuesta fija defaults suficientes para trabajar sin una entrevista bloqueante sobre cada tamaño/color.

Reglas por paquete:

1. Leer funciones completas y todos sus callers. Comparar instrucciones con HEAD, no con una respuesta antigua del chat.
2. Añadir primero una prueba de comportamiento relevante para lógica no trivial; verificar que falla por la causa buscada.
3. Editar mediante apply_patch con contexto específico. Parche rechazado: releer; nunca reintentar hunks cada vez más genéricos que puedan insertar un `else` en otro bloque.
4. Ejecutar tests del paquete, parseo JS cuando toque y checks obligatorios. Leer códigos de salida y diff.
5. Registrar evidencia corta y próximo paquete. Actualizar `graphify update .` según instrucciones; no tratar grafo limpio como prueba funcional.
6. Revisar cambios concurrentes antes de commit/integración. Preservar `.agent/memory/episodic/AGENT_LEARNINGS.jsonl` ajeno.
7. No detenerse tras mejorar dos estilos si faltan sesión, búsqueda, accesibilidad o validación solicitadas. No añadir abstracciones especulativas para completar el plan.

Formato de cierre de paquete:

```text
Pxx: completado / pendiente
Cambio: comportamiento concreto y archivos.
Verificación: comando + resultado + límite de evidencia.
Producción: no desplegado / desplegado SHA / migración aplicada y verificada.
Siguiente: Pyy o bloqueo exacto con acción necesaria.
```

Prompt de arranque para otra tarea de Luna:

> Lee `docs/PLAN_DASHBOARD_LUNA.md` y las instrucciones actuales del repositorio. Implementa sus paquetes en orden, comenzando por P00/P01. Revalida los hallazgos contra HEAD. Mantén Vanilla/Flask/IDs, preserva cambios ajenos y usa pruebas de comportamiento. No declares persistencia por tener una cookie ni éxito por pasar solo safeguards. Prepara y solicita únicamente gates remotos concretos que aún no estén autorizados; continúa trabajo independiente mientras tanto. Completa todos los paquetes y entrega evidencia de diseño, sesión, seguridad, migración y despliegue, distinguiendo claramente lo comprobado de lo pendiente.

## 9. Fuentes técnicas y evidencia

Consultadas el 2026-09-10. Revalidar documentación relevante al ejecutar cambios, especialmente APIs/CLI de Supabase y despliegue Vercel.

- [OAuth2 Discord](https://docs.discord.com/developers/topics/oauth2): scopes, state, intercambio, renovación y revocación.
- [Política de desarrolladores Discord](https://support-dev.discord.com/hc/en-us/articles/8563934450327-Discord-Developer-Policy): obligaciones sobre datos de API.
- [Supabase RLS](https://supabase.com/docs/guides/database/postgres/row-level-security): roles, grants y políticas.
- [Supabase changelog](https://supabase.com/changelog): comprobar exposición Data API y compatibilidad del proyecto; el endpoint Markdown no pudo leerse con web y se usó HTML.
- [Vercel rewrites](https://vercel.com/docs/routing/rewrites): proxy externo conservando URL visible.
- [Flask sesiones](https://flask.palletsprojects.com/en/stable/quickstart/#sessions): firma de cookie no es cifrado.
- [Fernet](https://cryptography.io/en/latest/fernet/): cifrado autenticado y claves; consultar versión estable al fijar dependencia.
- [MDN Set-Cookie](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie): HttpOnly, Secure, SameSite y prefijos.
- [WAI tabs](https://www.w3.org/WAI/ARIA/apg/patterns/tabs/) y [WAI modal](https://www.w3.org/WAI/ARIA/apg/patterns/dialog-modal/): interacción accesible.
- [RGPD, texto oficial](https://eur-lex.europa.eu/eli/reg/2016/679/oj): referencia jurídica; el plan no sustituye evaluación legal.

La propuesta de arquitectura/diseño es una decisión del plan basada en código y requisitos; no una afirmación de que Discord, Werewolf o Vercel utilicen exactamente esta implementación.
