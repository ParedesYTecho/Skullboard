# SkullBoard — Referencia Completa de Comandos

SkullBoard dispone de una arquitectura dual de comandos: **Slash Commands** (`/` nativos de Discord) y **Comandos de Texto con Prefijo** (por defecto `sk!`, configurable por servidor).

---

## 1. Tabla Resumen de Comandos

### 1.1. Comandos Generales (Cualquier Usuario)

| Comando Slash | Comando Texto | Alias de Texto | Permisos Requeridos | Descripción |
| :--- | :--- | :--- | :--- | :--- |
| `/ajustes` | `sk!ajustes` | `settings` | Ninguno (@everyone) | Muestra el estado actual del bot, canal configurado, meta de 💀, prefijo y latencia. |
| `/dashboard` | `sk!dashboard` | `web`, `panel` | Ninguno (@everyone) | Enlace al panel web oficial, landing page y recursos legales (con botones interactivos). |
| `/ping` | `sk!ping` | — | Ninguno (@everyone) | Muestra la latencia en milisegundos y el estado de la conexión. |
| `/invite` | `sk!invite` | — | Ninguno (@everyone) | Devuelve el enlace OAuth2 para invitar el bot a otros servidores. |
| `/help` | `sk!help` | `ayuda`, `comandos` | Ninguno (@everyone) | Muestra la guía interactiva de comandos con paginación vía botones (`HelpView`). |
| `/top` | `sk!top` | — | Ninguno (@everyone) | Top 10 mensajes más reaccionados con 💀 en la historia del servidor. |
| `/top_month` | `sk!topmonth` | `monthly`, `top_month` | Ninguno (@everyone) | Top 10 mensajes más reaccionados en el mes natural en curso. |
| `/top_year` | `sk!topyear` | `yearly`, `top_year` | Ninguno (@everyone) | Top 10 mensajes más reaccionados en el año natural en curso. |
| `/stats` | `sk!stats` | `estadisticas` | Ninguno (@everyone) | Estadísticas individuales de un usuario (mensajes en board, total de 💀, récord y enlace al mejor mensaje). |
| `/random` | `sk!random` | — | Ninguno (@everyone) | Recupera y muestra un mensaje destacado aleatorio del skullboard. |
| `/leaderboard` | `sk!leaderboard` | `lb`, `topusers` | Ninguno (@everyone) | Top 10 usuarios con mayor acumulación total de calaveras recibidas. |
| `/server_stats`| `sk!serverstats` | `sstats`, `server_stats`| Ninguno (@everyone) | Estadísticas globales del servidor (total mensajes, calaveras totales, récord y usuario top). |
| `/ignored` | `sk!ignored` | — | Ninguno (@everyone) | Lista los canales configurados que el bot ignora en el servidor. |
| `/notify` | `sk!notify` | — | Ninguno (@everyone) | Consulta o conmuta (`on`/`off`) la recepción de mensajes directos (DM) al entrar al board. |

---

### 1.2. Comandos de Administración (Requieren Permisos)

| Comando Slash | Comando Texto | Alias de Texto | Permisos Requeridos | Descripción |
| :--- | :--- | :--- | :--- | :--- |
| `/set_channel` | `sk!set_channel` | `channel` | **Administrador** | Establece el canal de texto donde se enviarán las publicaciones del Starboard. |
| `/set_min` | `sk!set_min` | `min` | **Administrador** | Fija el umbral mínimo de reacciones 💀 para que un mensaje sea destacado (≥ 1). |
| `/prefix` | `sk!prefix` | `set_prefix` | **Administrador** | Cambia el prefijo para los comandos de texto en el servidor (máx. 10 caracteres). |
| `/ignore` | `sk!ignore` | — | **Administrador** | Añade un canal a la lista negra del bot para que sus reacciones no sean contabilizadas. |
| `/unignore` | `sk!unignore` | — | **Administrador** | Elimina un canal de la lista negra de canales ignorados. |
| `/setup_pin` | `sk!setuppin` | `setup_pin` | **Administrador** | Configura el umbral de 💀 para auto-pinear mensajes en el canal del Starboard (`0` desactiva). |
| `/resync` | `sk!resync` | `sync` | **Administrador** | Resincroniza, re-cuenta y deduplica los mensajes del canal de Starboard con la BD. |
| `/reset` | `sk!reset` | — | **Propietario del Servidor** (`guild.owner_id`) | Elimina todos los registros de `tracked_messages` del servidor tras confirmación. |

---

### 1.3. Comandos Exclusivos del Propietario del Bot (Bot Owner)

Comandos ocultos accesibles únicamente por el ID definido en `OWNER_ID` (`561225979389804544`). No tienen versión slash.

| Comando Texto | Argumentos | Descripción |
| :--- | :--- | :--- |
| `sk!backfill` | Ninguno | Realiza una migración exhaustiva en 3 fases leyendo el canal del Starboard para reconstruir la base de datos con IDs inmutables puras de autor y mensaje original. |
| `sk!announce` | Ninguno | Envía un comunicado enriquecido a través del canal de skullboard o `system_channel` de todos los servidores en los que está presente el bot. |
| `sk!editannounce` | Ninguno | Busca y edita en caliente el último anuncio enviado por el bot en el historial de los canales de todos los servidores. |
| `sk!servers` | Ninguno | Lista todos los servidores conectados con sus nombres y respectivos IDs. |
| `sk!serverinfo` | `<guild_id>` | Muestra información detallada de un servidor específico (ID, propietario, miembros, fecha de creación, total mensajes registrados en BD). |

---

## 2. Detalle y Parámetros de Comandos

### `ajustes` / `settings`
- **Sintaxis Texto:** `sk!ajustes`
- **Sintaxis Slash:** `/ajustes`
- **Comportamiento:** Construye un embed que muestra el canal de skullboard (`mention`), la meta de calaveras (`min_skulls`), el prefijo actual, la latencia con indicador visual (🟢/🟡/🔴) y el enlace de invitación.

### `dashboard` / `web` / `panel`
- **Sintaxis Texto:** `sk!dashboard`
- **Sintaxis Slash:** `/dashboard`
- **Comportamiento:** Muestra un embed enriquecido con los enlaces a la web oficial y landing page (`https://skullboard.vercel.app/`), política de privacidad y términos de servicio, acompañado de una botonera de enlaces (`DashboardView`).

### `set_channel` / `channel`
- **Sintaxis Texto:** `sk!set_channel <#canal>`
- **Sintaxis Slash:** `/set_channel channel:<#canal>`
- **Comportamiento:** Guarda `skullboard_channel_id` en la tabla `settings` e invalida la caché local `_guild_config_cache`.

### `set_min` / `min`
- **Sintaxis Texto:** `sk!set_min <cantidad>`
- **Sintaxis Slash:** `/set_min cantidad:<entero>`
- **Restricción:** `cantidad` debe ser mayor o igual a 1.
- **Comportamiento:** Actualiza `min_skulls` en la tabla `settings` e invalida la caché local.

### `prefix` / `set_prefix`
- **Sintaxis Texto:** `sk!prefix <nuevo_prefijo>`
- **Sintaxis Slash:** `/prefix nuevo_prefijo:<texto>`
- **Restricción:** Longitud máxima de 10 caracteres.
- **Comportamiento:** Modifica el prefijo en `settings` e invalida tanto `_guild_config_cache` como `_prefix_cache`.

### `ignore` / `unignore` / `ignored`
- **`ignore`:** Agrega `(guild_id, channel_id)` a `ignored_channels` e invalida `_ignored_channels_cache`.
- **`unignore`:** Elimina el registro en `ignored_channels` e invalida `_ignored_channels_cache`.
- **`ignored`:** Devuelve una lista con las menciones de los canales en la lista de exclusión.

### `stats` / `estadisticas`
- **Sintaxis Texto:** `sk!stats [@usuario]`
- **Sintaxis Slash:** `/stats [usuario:@usuario]`
- **Comportamiento:** Si no se especifica usuario, evalúa al autor del comando. Consulta `tracked_messages` filtrando por `guild_id` y `author_id`. Retorna total de mensajes destacados, calaveras totales acumuladas, récord personal individual y un salto directo (enlace markdown sanitizado) al mensaje con mayor puntuación.

### `top` / `top_month` / `top_year`
- **`top`:** Consulta los 10 mensajes con mayor `skull_count` histórico en el servidor.
- **`top_month` / `top_year`:** Utiliza la función RPC `get_top_periodo` de PostgreSQL para filtrar eficientemente a nivel de base de datos los mensajes del mes o año en curso mediante el snowflake mínimo calculado (`min_snowflake`).

### `leaderboard` / `lb` / `topusers`
- **Sintaxis:** `sk!leaderboard` o `/leaderboard`
- **Comportamiento:** Invoca la RPC `get_guild_leaderboard` para agregar la suma de `skull_count` por cada `author_id` del servidor en PostgreSQL y lista los 10 usuarios con mayor puntuación acumulada. Los nombres se resuelven de forma segura mediante `resolve_display_name()`, evitando inyecciones de markdown.

### `setup_pin` / `setuppin`
- **Sintaxis Texto:** `sk!setuppin <umbral>`
- **Sintaxis Slash:** `/setup_pin umbral:<entero>`
- **Restricción:** El umbral debe ser `0` (para desactivar) o mayor o igual al `min_skulls` del servidor.
- **Comportamiento:** Cuando un mensaje del skullboard alcanza o supera este umbral, el bot lo ancla (*pin*) automáticamente en el canal del Starboard. Si el canal alcanza el límite de 50 pins de Discord, el bot captura la excepción `discord.HTTPException`, auto-desactiva el auto-pin en BD y notifica al canal con un embed de advertencia.

### `resync` / `sync`
- **Sintaxis:** `sk!resync` o `/resync`
- **Restricción:** Permiso de Administrador. Protegido por lock de servidor `_resync_guild_locks` y limitador global `_GlobalRateLimiter(8)`.
- **Comportamiento:**
  1. Descarga el historial del canal de Starboard.
  2. Detecta y agrupa publicaciones duplicadas correspondientes al mismo mensaje original.
  3. Comprueba el recuento real de reacciones en el canal de origen.
  4. Borra duplicados y mensajes huérfanos (mensajes originales que fueron eliminados).
  5. Corrige el contenido del embed y la base de datos con los valores reales.
  6. Presenta una barra de progreso actualizada cada 3 segundos.

### `reset`
- **Sintaxis Texto:** `sk!reset` (Solicita escribir `CONFIRMAR` en el chat antes de 30 segundos).
- **Sintaxis Slash:** `/reset` (Presenta botones de confirmación `ConfirmResetView` con estilo *danger* durante 30 segundos).
- **Restricción:** **Únicamente ejecutable por el Propietario del Servidor (`guild.owner_id`)**.
- **Comportamiento:** Ejecuta un `DELETE` en `tracked_messages` para todo el `guild_id`, restableciendo las estadísticas del servidor sin borrar los mensajes ya enviados en el canal de Discord.
