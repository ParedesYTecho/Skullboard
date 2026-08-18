# 🏛️ SYSTEM_CONTEXT.md — Documento Maestro de Arquitectura y Gobernanza Técnica

> **ESTADO DEL DOCUMENTO:** VIVO / PRODUCCIÓN  
> **VERSIÓN:** 2.4.0 (Post Super-Auditoría 360°)  
> **FECHA DE ÚLTIMA ACTUALIZACIÓN:** 18 de agosto de 2026  
> **PROPIETARIO TÉCNICO:** GlobalFerociouS (ID: `561225979389804544`)  
> **APLICACIÓN / BOT ID:** `1367463352774955059`  
> **DOMINIOS OFICIALES:**  
> • Frontend & Dashboard: https://skullboard.vercel.app/  
> • Backend & API REST: https://skullboard-fqf1.onrender.com  
> • Soporte & Contacto: globalsupportpyt@gmail.com

---

## 1. 🛑 PROTOCOLO OBLIGATORIO DE GOBERNANZA PARA AGENTES IA & REGLAS DE ORO

> [!CAUTION]
> ### CLÁUSULA DE LECTURA Y CONFORMIDAD OBLIGATORIA
> Todo agente de Inteligencia Artificial (Claude, ChatGPT, Gemini, Copilot, Cursor, Windsurf, Antigravity, etc.) y cualquier desarrollador humano **DEBE LEER ÍNTEGRAMENTE este documento antes de planificar, sugerir, refactorizar o ejecutar cualquier modificación** en la base de código.
> 
> **Queda estrictamente prohibido introducir parches temporales, atajos arquitectónicos o librerías externas innecesarias que violen las directrices aquí establecidas.**

### 1.1. Decálogo de Invariantes Arquitectónicas (Reglas de Oro)

1. **Gestión de Concurrencia Inmune a Cancelaciones (`KeyedAsyncLock`):**
   Cualquier operación sobre un mensaje o servidor debe usar `async with await lock.acquire(key):`. Nunca instanciar locks manuales sin decremento de referencias atómico en caso de cancelación de corrutinas (`asyncio.CancelledError`).
2. **Prohibición de Consultas $O(N)$ en Memoria:**
   Las estadísticas globales, leaderboards y consultas temporales se ejecutan **exclusivamente mediante Funciones RPC en PostgreSQL** (`get_guild_leaderboard`, `get_guild_server_stats`, `get_top_periodo`). Nunca descargar tablas enteras a memoria para agregarlas en bucles de Python.
3. **Resiliencia Obligatoria en Base de Datos (`@db_retry`):**
   Toda llamada a Supabase (`db_select`, `db_insert`, `db_update`, `db_upsert`) debe estar protegida con el decorador `@db_retry` para mitigar microcortes con *exponential backoff* y *jitter*.
4. **Desacoplamiento Estricto de I/O en Flask (`webserver.py`):**
   Las peticiones a APIs externas o bases de datos (Supabase, Resend, Discord) **nunca deben ejecutarse dentro de bloques `with _stats_lock:` o locks de memoria**. Los locks multihilo solo protegen estructuras en RAM.
5. **Clean URLs y Cero Extensiones `.html`:**
   En todo el ecosistema (HTML, JS, Python, Vercel, Flask, Discord Embeds), las URLs deben ser limpias (`/`, `/privacy`, `/terms`, `/cambios`). Vercel y Flask redirigen con 301/308 permanente cualquier acceso con `.html`.
6. **No Retención de Contenido de Mensajes (Privacidad Absoluta):**
   Solo se almacenan en base de datos IDs numéricas (snowflakes) y contadores enteros. **Nunca guardar el texto, imágenes o adjuntos de los mensajes**.
7. **Control de Acceso y Permisos de Discord:**
   Los comandos administrativos deben exigir `@commands.has_permissions(administrator=True)` y validación en tiempo de ejecución (`_is_admin_or_deny()`). `sk!reset` es exclusivo del **Server Owner** (`ctx.author.id == ctx.guild.owner_id`).
8. **Sanitización y Anti-Inyección (CRLF, XSS, Markdown):**
   Todo texto proveniente de usuarios (nombres de servidor, emails, mensajes de contacto) debe ser sanitizado con `re.sub(r'[\r\n]+', ' ', ...)` y `html.escape()` antes de procesarse o enviarse por correo.
9. **Accesibilidad Web (WCAG AA):**
   Todos los componentes interactivos del frontend deben contar con soporte de teclado (`Tab`, `Enter`, `Espacio`), roles semánticos (`role="button"`), estados `aria-expanded` y contraste de texto $\ge 4.5:1$.
10. **Principio de Simplicidad Radical (Ponytail):**
    Preferir siempre la biblioteca estándar de Python y funciones nativas de PostgreSQL antes de añadir dependencias o capas de abstracción innecesarias.

### 1.2. Protocolo de Modificación y Mantenimiento del Documento Maestro
* **Obligación de Sincronización:** Cada vez que se agregue un nuevo comando slash/prefijo, se altere una ruta de la API, se modifique una tabla de Supabase o se actualice una función RPC, este archivo `SYSTEM_CONTEXT.md` **debe ser actualizado en el mismo commit**.
* **Checklist de Verificación Previa:**
  1. `python -m py_compile main.py webserver.py` (0 errores de sintaxis).
  2. Verificación de tipos e índices en Supabase.
  3. Verificación de Clean URLs y enlaces en el frontend.

---

## 2. 🏗️ TOPOLOGÍA DEL SISTEMA Y ARQUITECTURA DETALLADA

### 2.1. Desglose del Stack Tecnológico

```mermaid
graph TD
    subgraph Discord_Cloud["Plataforma Discord"]
        Client["Clientes Discord (Móvil / Desktop / Web)"]
        Gateway["Discord Gateway (WebSockets v10)"]
        DiscordREST["Discord REST API v10"]
    end

    subgraph Render_PaaS["Backend Host (Render Cloud)"]
        subgraph Python_Process["Proceso Python Único"]
            subgraph Main_Thread["Hilo Principal: Asyncio Event Loop"]
                Bot["SkullBot (discord.ext.commands.Bot)"]
                Tree["GuildOnlyTree (Slash Commands)"]
                Debouncer["MessageDebouncer (Generacional 2.0s)"]
                MsgLocks["KeyedAsyncLock (_check_locks / _resync_locks)"]
                DBSync["DB Wrappers (@db_retry)"]
                RAM_Cache["Cachés en RAM (TTL 120s - 300s)"]
            end
            
            subgraph Worker_Thread["Hilo Secundario: Flask WSGI (threaded=True)"]
                FlaskServer["Flask App (PORT $PORT / 8080)"]
                StatsCache["_stats_cache (TTL 60s)"]
                ContactLRU["_contact_last (LRU Throttling)"]
                OAuthHandler["OAuth2 Manager (Anti-CSRF State)"]
            end
        end
    end

    subgraph Vercel_Edge["Frontend & Landing (Vercel Edge Network)"]
        VercelCDN["Vercel Static Hosting (Clean URLs, 308 Redirects)"]
        DashboardUI["Dashboard / Web (legal/index.html, styles.css)"]
        DocPages["Páginas Legales (/privacy, /terms, /cambios)"]
    end

    subgraph Data_Layer["Capa de Persistencia & Cloud Services"]
        SupabasePostgres[("Supabase PostgreSQL 15+\n(RPCs nativas, Índices de alto rendimiento)")]
        ResendAPI["Resend Email API (Transaccional)"]
    end

    %% Relaciones
    Client -->|Reacciona con 💀 / Envía Comandos| Gateway
    Gateway -->|RAW Events (Add/Remove Reaction, Message Delete)| Bot
    Bot -->|Programar Verificación| Debouncer
    Debouncer -->|Ejecutar tras 2.0s| MsgLocks
    MsgLocks -->|Consultas con Retry| DBSync
    DBSync <-->|HTTP/2 PostgREST / RPCs| SupabasePostgres
    MsgLocks -->|Publicar / Editar Embeds / Auto-Pin| DiscordREST
    
    Client -->|Navega a skullboard.vercel.app| VercelCDN
    VercelCDN --> DashboardUI
    DashboardUI -->|GET /api/stats (AbortController 8s)| FlaskServer
    DashboardUI -->|POST /api/contact (AbortController 12s)| FlaskServer
    FlaskServer -->|Envío de Email| ResendAPI
    FlaskServer -->|Consulta periódica de conteos| SupabasePostgres
```

---

### 2.2. Diagrama de Secuencia: Flujo de Vida de una Reacción 💀

```mermaid
sequenceDiagram
    autonumber
    actor Usuario as Usuario Discord
    participant GW as Discord Gateway
    participant Bot as SkullBot (main.py)
    participant Debounce as MessageDebouncer
    participant Lock as KeyedAsyncLock
    participant DB as Supabase PostgreSQL
    participant REST as Discord REST API

    Usuario->>GW: Añade reacción 💀 a un mensaje
    GW->>Bot: on_raw_reaction_add (Payload)
    
    Bot->>Bot: Verificar canal no ignorado (_ignored_channels_cache)
    Bot->>Debounce: schedule(message_id, 2.0s)
    Note over Debounce: Agrupa ráfagas de reacciones y cancela timers previos
    
    Debounce->>Bot: Dispara _check_message_safe(channel_id, message_id)
    Bot->>Lock: acquire(message_id)
    activate Lock
    
    Bot->>REST: fetch_message(message_id)
    REST-->>Bot: Mensaje Original (Reacciones, Adjuntos, Autor)
    
    Bot->>DB: get_guild_config(guild_id)
    DB-->>Bot: Configuración (threshold, channel_id, self_skull, etc.)
    
    alt Reacciones >= Umbral (Threshold)
        Bot->>DB: select tracked_messages where message_id = ID
        alt Mensaje ya publicado en Skullboard
            Bot->>REST: edit_message(skullboard_msg_id, nuevo_conteo_embed)
            Bot->>DB: update tracked_messages (skull_count)
        else Nuevo mensaje que supera el umbral
            Bot->>REST: send_message(skullboard_channel, embed_con_autor_y_media)
            REST-->>Bot: skullboard_message_id
            Bot->>DB: insert tracked_messages (message_id, sb_id, skull_count, author_id)
            
            opt Récord del Servidor Superado
                Bot->>REST: pin_message(skullboard_message_id)
            end
        end
    else Reacciones < Umbral y existe en Skullboard
        Bot->>REST: delete_message(skullboard_msg_id)
        Bot->>DB: delete from tracked_messages where message_id = ID
    end
    
    deactivate Lock
```

---

## 3. 🗄️ MODELO DE DATOS, PERSISTENCIA Y RPCs DE POSTGRESQL

### 3.1. Diagrama Entidad-Relación (ERD)

```mermaid
erDiagram
    settings {
        TEXT guild_id PK "Snowflake ID del Servidor"
        BIGINT skullboard_channel_id "ID del canal donde se publican calaveras"
        INTEGER skull_threshold "Umbral mínimo de calaveras (default: 3)"
        BOOLEAN self_skull "Permitir auto-reacciones (default: false)"
        BOOLEAN auto_pin "Auto-fijar mensajes con récord (default: true)"
        TEXT prefix "Prefijo personalizado de comandos (default: 'sk!')"
        TIMESTAMPTZ created_at "Fecha de creación del registro"
        TIMESTAMPTZ updated_at "Fecha de última modificación"
    }

    tracked_messages {
        TEXT message_id PK "Snowflake ID del mensaje original"
        BIGINT skullboard_message_id "Snowflake ID del mensaje en el skullboard"
        INTEGER skull_count "Número actual de reacciones calavera"
        TEXT author_id "Snowflake ID del autor del mensaje"
        TEXT guild_id "Snowflake ID del servidor (FK conceptual)"
        TIMESTAMPTZ created_at "Fecha de registro"
    }

    ignored_channels {
        TEXT channel_id PK "Snowflake ID del canal ignorado"
        TEXT guild_id "Snowflake ID del servidor"
        TIMESTAMPTZ created_at "Fecha de adición"
    }

    notify_settings {
        BIGINT id PK "ID autoincremental"
        TEXT guild_id "Snowflake ID del servidor"
        TEXT user_id "Snowflake ID del usuario"
        BOOLEAN enabled "Estado de alertas DM (default: true)"
        TIMESTAMPTZ created_at "Fecha de configuración"
    }

    settings ||--o{ tracked_messages : "registra"
    settings ||--o{ ignored_channels : "ignora"
    settings ||--o{ notify_settings : "gestiona"
```

### 3.2. Catálogo de Índices de Alto Rendimiento

1. `idx_tracked_messages_guild_author_skulls` en `(guild_id, author_id, skull_count)`: Acelera agregaciones y conteos por usuario.
2. `idx_tracked_messages_guild_msgid_skulls` en `(guild_id, (message_id::BIGINT), skull_count DESC)`: Acelera filtros cronológicos.
3. `idx_tracked_messages_sb_id` en `(skullboard_message_id)`: Acelera búsquedas de mensajes borrados de $O(N)$ a $O(1)$.
4. `idx_notify_settings_disabled` en `(guild_id, user_id)` con filtro `WHERE enabled = false`: Optimiza la carga de la caché de notificaciones al inicio.

---

### 3.3. Especificación Técnica de Funciones Almacenadas (PostgreSQL RPCs)

#### 1. `get_guild_leaderboard(p_guild_id TEXT, p_limit INT DEFAULT 10)`
* **Objetivo:** Devuelve los autores con mayor número acumulado de calaveras en un servidor.
* **Firma de Retorno:** `TABLE (author_id TEXT, total_skulls BIGINT, message_count BIGINT)`
* **Seguridad:** `SECURITY INVOKER`, límites forzados entre 1 y 100 con `LEAST(GREATEST(p_limit, 1), 100)`.

#### 2. `get_guild_server_stats(p_guild_id TEXT)`
* **Objetivo:** Retorna las estadísticas globales de un servidor de forma 100% blindada contra `NULL` (usando `COALESCE`).
* **Firma de Retorno:** `TABLE (total_messages BIGINT, total_skulls BIGINT, record_count INT, top_author_id TEXT, top_author_skulls BIGINT)`
* **Comportamiento:** Si el servidor no tiene mensajes registrados, devuelve ceros limpios `(0, 0, 0, NULL, 0)` evitando `TypeError` en Python.

#### 3. `get_random_tracked_message(p_guild_id TEXT)`
* **Objetivo:** Selecciona 1 mensaje destacado aleatorio directamente en la base de datos sin descargar la tabla a RAM.
* **Firma de Retorno:** `TABLE (message_id TEXT, skullboard_message_id BIGINT, skull_count INT, author_id TEXT, guild_id TEXT)`

#### 4. `get_top_periodo(p_guild_id TEXT, p_min_snowflake BIGINT, p_limit INT DEFAULT 10)`
* **Objetivo:** Filtra mensajes generados a partir de un timestamp de Discord (snowflake) mediante regex numérico seguro `message_id ~ '^[0-9]{15,21}$'`.
* **Firma de Retorno:** `TABLE (message_id TEXT, skullboard_message_id BIGINT, skull_count INT, author_id TEXT)`

---

## 4. 📜 CATÁLOGO COMPLETO DE COMANDOS Y API ENDPOINTS

### 4.1. Comandos de Discord (Slash & Prefijo)

| Comando Slash | Comando Prefijo | Permisos Requeridos | Descripción y Parámetros |
| :--- | :--- | :--- | :--- |
| `/help` | `sk!help` | Todos | Muestra la guía interactiva con paginación (`HelpView`). |
| `/dashboard` | `sk!dashboard` | Todos | Enlaces oficiales a la web, TOS, privacidad y botón de invitación. |
| `/server_stats`| `sk!serverstats` | Todos | Muestra el resumen del servidor (mensajes, calaveras, récord y MVP). |
| `/top` | `sk!top` | Todos | Mensajes con más calaveras históricas del servidor. |
| `/top_month` | `sk!topmonth` | Todos | Mensajes más votados en los últimos 30 días. |
| `/top_year` | `sk!topyear` | Todos | Mensajes más votados en los últimos 365 días. |
| `/leaderboard`| `sk!leaderboard`| Todos | Ranking de los 10 usuarios con más calaveras acumuladas. |
| `/random` | `sk!random` | Todos | Muestra un mensaje al azar que haya alcanzado el skullboard. |
| `/stats` | `sk!stats` | Todos | Estadísticas globales de un usuario (`user: Member`). |
| `/notify` | `sk!notify` | Todos | Activa o desactiva las notificaciones por mensaje directo (`enabled: bool`). |
| `/setup` | `sk!setup` | Administrador | Asistente de configuración del canal skullboard y umbral. |
| `/set_channel`| `sk!setchannel`| Administrador | Define el canal de publicación (`channel: TextChannel`). |
| `/set_skulls` | `sk!setskulls` | Administrador | Define el umbral de calaveras (`count: int`, entre 1 y 50). |
| `/self_skull` | `sk!selfskull` | Administrador | Permite o prohíbe que los autores voten sus propios mensajes (`allow: bool`). |
| `/autopin` | `sk!autopin` | Administrador | Activa/desactiva fijar automáticamente los récords (`enabled: bool`). |
| `/ignore` | `sk!ignore` | Administrador | Añade un canal a la lista negra de calaveras (`channel: TextChannel`). |
| `/unignore` | `sk!unignore` | Administrador | Elimina un canal de la lista negra (`channel: TextChannel`). |
| `/ignored` | `sk!ignored` | Administrador | Lista todos los canales ignorados del servidor. |
| `/resync` | `sk!resync` | Administrador | Escanea y resincroniza todas las calaveras corrigiendo descuadres. |
| `—` | `sk!prefix` | Administrador | Cambia el prefijo de comandos de texto (`nuevo_prefijo: str`). |
| `—` | `sk!reset` | **Server Owner** | Restablece toda la configuración y borra el historial del servidor. |
| `—` | `sk!announce` | **Bot Owner** | Envía un comunicado oficial a todos los canales skullboard configurados. |
| `—` | `sk!backfill` | **Bot Owner** | Reconcilia IDs originales de mensajes antiguos leyendo el historial. |

---

### 4.2. API REST del Servidor Web (`webserver.py`)

| Endpoint | Método | Autenticación / Rate Limit | Descripción / Respuesta |
| :--- | :---: | :--- | :--- |
| `/` | `GET` | Público | Sirve `legal/index.html` con soporte para temas y assets. |
| `/<filename>` | `GET` | Público | Enrutador estático con Clean URLs y redirección 301 para `.html`. |
| `/api/stats` | `GET` | Público (Cache 60s) | Retorna `{"servers": int, "highlighted": int}` para la dashboard. |
| `/api/contact` | `POST` | 1 req / 30s por IP (LRU)<br>10 req / min global | Recibe formulario de contacto, sanitiza CRLF/XSS y despacha vía Resend. |
| `/verify` | `GET` | Discord OAuth2 | Inicia el flujo de verificación de rol con token anti-CSRF (`state`). |
| `/callback` | `GET` | Validación de State TTL | Finaliza OAuth2 y asigna el Linked Role (`is_owner`) en Discord. |

---

## 5. 🛠️ HISTORIAL DE INCIDENCIAS CRÍTICAS Y REGRESIONES PREVENIDAS

| Incidencia Histórica | Causa Raíz | Solución Implementada (Definitiva) | Regla de Prevención |
| :--- | :--- | :--- | :--- |
| **Desbordamiento de Enteros (32,767)** | La columna `skull_count` era `SMALLINT` en PostgreSQL. | Migrada a `INTEGER` en DDL de Supabase. | Nunca limitar contadores de votos a tipos de 16 bits. |
| **Race Conditions en Cancelaciones** | Si una corrutina era cancelada esperando `lock.acquire()`, el lock quedaba huérfano. | `KeyedAsyncLock` con captura `BaseException` en `__aenter__` que desaloja el contador. | No usar primitivas `asyncio.Lock` desnudas sin gestión de ciclo de vida. |
| **Bloqueo Multihilo en `/api/stats`** | Las llamadas síncronas a Supabase se hacían dentro de `with _stats_lock:`. | Se extrajo el I/O fuera del lock; el lock solo actualiza la variable en RAM. | Prohibido hacer I/O de red dentro de bloques de sincronización de hilos. |
| **Descuadre en Rankings Temporales** | La query ordenaba los Snowflakes alfabéticamente en Python en lugar de numéricamente. | Creada la RPC `get_top_periodo` con filtro numérico `message_id::BIGINT >= min_snowflake`. | Los Snowflakes de Discord deben compararse siempre como enteros de 64 bits. |
| **Inyección CRLF en Contacto** | Cabeceras de email vulnerables a saltos de línea `\r\n` en el campo nombre. | Sanitización regex `re.sub(r'[\r\n]+', ' ', name)` y escape HTML completo. | Sanitizar exhaustivamente cualquier entrada antes de pasarla a APIs de correo. |
| **Penalización SEO por `.html`** | Google indexaba páginas con `.html` generando URLs duplicadas y poco estéticas. | `vercel.json` con `cleanUrls: true`, redirecciones 301 en Flask y `sitemap.xml`. | Mantener siempre rutas limpias sin extensión en todo el ecosistema. |

---

## 6. ⚙️ MATRIZ DE CONFIGURACIÓN, VARIABLES DE ENTORNO Y PERMISOS

### 6.1. Variables de Entorno Requeridas

| Variable | Entorno | Propósito Técnico |
| :--- | :--- | :--- |
| `DISCORD_TOKEN` | Render / Local | Token secreto del bot de Discord para autenticación en Gateway y REST API. |
| `SUPABASE_URL` | Render / Local | URL del proyecto Supabase (ej. `https://tjmcclgyirqjatezkqgr.supabase.co`). |
| `SUPABASE_KEY` | Render / Local | API Key de servicio de Supabase (Service Role / Anon). |
| `APPLICATION_ID` | Render / Local | ID de la aplicación de Discord (`1367463352774955059`). |
| `DISCORD_CLIENT_SECRET`| Render / Local | Secreto OAuth2 para el intercambio de tokens en Linked Roles. |
| `RESEND_API_KEY` | Render / Local | Clave de API de Resend para el despacho de correos en `/api/contact`. |
| `PORT` | Render / Local | Puerto TCP para el servidor web Flask (por defecto `8080`). |

---

### 6.2. Matriz de Permisos de Discord (Principio de Menor Privilegio)

```
Discord Permissions Integer: 277025508352
```

1. **`View Channels` (Ver Canales):** Necesario para detectar reacciones en los canales de texto del servidor.
2. **`Send Messages` (Enviar Mensajes):** Necesario para publicar los embeds en el canal skullboard.
3. **`Embed Links` (Insertar Enlaces):** Necesario para formatear y renderizar las tarjetas visuales de los mensajes destacados.
4. **`Read Message History` (Leer el Historial de Mensajes):** Fundamental para reconstruir mensajes originales y validar conteos reales en `/resync` y `sk!backfill`.
5. **`Add Reactions` (Añadir Reacciones):** Permite al bot interactuar con confirmaciones visuales.
6. **`Pin Messages` (Fijar Mensajes):** Requerido exclusivamente cuando el servidor tiene activada la función de auto-pin de récord (`/autopin true`).

#### Privileged Gateway Intents
* **`Message Content Intent`:** Requerido para leer adjuntos, avatares y texto al momento de publicar el embed en el skullboard.
* **`Guild Members Intent`:** Requerido para resolver nombres de usuario, avatares actualizados y menciones en los rankings.
