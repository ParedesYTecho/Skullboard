import sys
import discord
import logging
import os
import re
import traceback
import webserver
import asyncio
import random
import time
from datetime import datetime, timezone
from discord.ext import commands, tasks
from discord import app_commands
from supabase import acreate_client, AsyncClient
import discord.abc
import aiohttp
from typing import Optional

# ─── Optimización de Event Loop (uvloop en Linux/Render) ─────────────────────
if sys.platform != "win32":
    try:
        import uvloop
        uvloop.install()
        logging.info("🚀 [Performance] uvloop activado como Event Loop principal")
    except ImportError:
        pass

# ─── Serialización JSON Ultra-Rápida (orjson) ────────────────────────────────
try:
    import orjson
    def json_dumps(obj) -> str:
        return orjson.dumps(obj).decode("utf-8")
    def json_loads(s):
        return orjson.loads(s)
except ImportError:
    import json
    def json_dumps(obj) -> str:
        return json.dumps(obj)
    def json_loads(s):
        return json.loads(s)

# ─── Cachés con Desalojo Automático (cachetools) ──────────────────────────────
try:
    from cachetools import TTLCache
    HAS_CACHETOOLS = True
except ImportError:
    HAS_CACHETOOLS = False

# ─── Logging ─────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("SkullBoard")

# ─── Supabase ─────────────────────────────────────────────────────────────────
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
SUPABASE_URL  = os.getenv("SUPABASE_URL")
SUPABASE_KEY  = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
supabase: Optional[AsyncClient] = None

OWNER_ID    = int(os.getenv("BOT_OWNER_ID", "561225979389804544"))
skull_emoji = '💀'
DISCORD_ALERTS_WEBHOOK_URL = os.getenv("DISCORD_ALERTS_WEBHOOK_URL")

_perm_failover_cooldown: dict[str, float] = {}

async def send_system_alert(title: str, description: str, level: str = "ERROR", extra_fields: list = None):
    """Envía un webhook de alerta a Discord para observabilidad y monitoreo en tiempo real."""
    if not DISCORD_ALERTS_WEBHOOK_URL:
        return
    color = 0xef4444 if level == "ERROR" else (0xf59e0b if level == "WARNING" else 0x3b82f6)
    embed = {
        "title": f"🚨 [SkullBoard] {title}",
        "description": description[:2000],
        "color": color,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "footer": {"text": f"Nivel: {level} · Entorno: Render Production v2.5.0"}
    }
    if extra_fields:
        embed["fields"] = extra_fields[:10]
    
    try:
        async with aiohttp.ClientSession() as session:
            await session.post(DISCORD_ALERTS_WEBHOOK_URL, json={"embeds": [embed]}, timeout=5.0)
    except Exception as e:
        logger.warning(f"No se pudo enviar alerta por webhook: {e}")

# ─── Gestores de Concurrencia y Cachés en memoria ─────────────────────────────
# ─── Gestores de Concurrencia y Cachés en memoria ─────────────────────────────
class KeyedAsyncLock:
    """Gestor de locks por clave seguro contra cancelaciones y con desalojo automático."""
    def __init__(self):
        self._locks: dict[str, asyncio.Lock] = {}
        self._counts: dict[str, int] = {}
        self._guard = asyncio.Lock()

    async def acquire(self, key: str):
        return _KeyedLockContext(self, str(key))

class _KeyedLockContext:
    def __init__(self, manager: KeyedAsyncLock, key: str):
        self._manager = manager
        self._key = key
        self._lock: Optional[asyncio.Lock] = None
        self._acquired = False

    async def __aenter__(self):
        async with self._manager._guard:
            if self._key not in self._manager._locks:
                self._manager._locks[self._key] = asyncio.Lock()
                self._manager._counts[self._key] = 0
            self._manager._counts[self._key] += 1
            self._lock = self._manager._locks[self._key]
        
        try:
            await self._lock.acquire()
            self._acquired = True
            return self
        except BaseException:
            # Si se cancela mientras esperaba el lock, decrementar y desalojar
            async with self._manager._guard:
                self._manager._counts[self._key] -= 1
                if self._manager._counts[self._key] <= 0:
                    self._manager._locks.pop(self._key, None)
                    self._manager._counts.pop(self._key, None)
            raise

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._acquired and self._lock:
            self._lock.release()
        async with self._manager._guard:
            self._manager._counts[self._key] -= 1
            if self._manager._counts[self._key] <= 0:
                self._manager._locks.pop(self._key, None)
                self._manager._counts.pop(self._key, None)

class MessageDebouncer:
    """Debouncer que rastrea la versión de la tarea para evitar descarte prematuro de timers."""
    def __init__(self, delay: float = 2.0):
        self.delay = delay
        self._handles: dict[str, tuple[asyncio.TimerHandle, int]] = {}
        self._generation: dict[str, int] = {}

    def schedule(self, mid: int, callback, *args):
        mid_str = str(mid)
        loop = asyncio.get_running_loop()
        gen = self._generation.get(mid_str, 0) + 1
        self._generation[mid_str] = gen

        if mid_str in self._handles:
            old_handle, _ = self._handles[mid_str]
            old_handle.cancel()

        def _fire(target_gen: int):
            if self._generation.get(mid_str) == target_gen:
                self._handles.pop(mid_str, None)
                self._generation.pop(mid_str, None)
                asyncio.create_task(callback(*args))

        handle = loop.call_later(self.delay, _fire, gen)
        self._handles[mid_str] = (handle, gen)

class BoundedTTLCache:
    """Caché LRU auto-gestionada con expiración (TTL) y límite estricto de memoria (anti-fugas)."""
    def __init__(self, maxsize: int = 5000, ttl: float = 300.0):
        self.maxsize = maxsize
        self.ttl = ttl
        self._data: dict[str, tuple[any, float]] = {}

    def __contains__(self, key: str) -> bool:
        if key not in self._data:
            return False
        val, ts = self._data[key]
        if time.time() - ts > self.ttl:
            self._data.pop(key, None)
            return False
        return True

    def get(self, key: str, default=None):
        if self.__contains__(key):
            return self._data[key][0]
        return default

    def __getitem__(self, key: str):
        if self.__contains__(key):
            return self._data[key][0]
        raise KeyError(key)

    def __setitem__(self, key: str, value):
        if len(self._data) >= self.maxsize:
            oldest_k = next(iter(self._data))
            self._data.pop(oldest_k, None)
        self._data[key] = (value, time.time())

    def pop(self, key: str, default=None):
        item = self._data.pop(key, None)
        if item is not None:
            return item[0]
        return default

    def __len__(self) -> int:
        return len(self._data)

def _create_cache(maxsize: int, ttl: float):
    if HAS_CACHETOOLS:
        return TTLCache(maxsize=maxsize, ttl=ttl)
    return BoundedTTLCache(maxsize=maxsize, ttl=ttl)

_msg_locks = KeyedAsyncLock()
_resync_locks = KeyedAsyncLock()
_debouncer = MessageDebouncer(delay=2.0)

_prefix_cache           = _create_cache(maxsize=2000, ttl=120.0)
_guild_config_cache     = _create_cache(maxsize=5000, ttl=300.0)
_ignored_channels_cache = _create_cache(maxsize=5000, ttl=300.0)
_guild_record_cache     = _create_cache(maxsize=5000, ttl=300.0)

SPANISH_MONTHS = {
    1: "enero", 2: "febrero", 3: "marzo", 4: "abril", 5: "mayo", 6: "junio",
    7: "julio", 8: "agosto", 9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre"
}

# ─── Decorador de Reintento con Exponential Backoff y Jitter ─────────────────
def db_retry(max_retries: int = 3, base_delay: float = 0.3, max_delay: float = 2.0):
    """Reintenta automáticamente llamadas asíncronas ante microcortes o fallos transitorios."""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            delay = base_delay
            last_exc = None
            for attempt in range(1, max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exc = e
                    if attempt == max_retries:
                        logger.error(f"❌ [DB Retry] Falló tras {max_retries} intentos ({func.__name__}): {e}")
                        raise
                    jitter = random.uniform(0.8, 1.2)
                    sleep_time = min(delay * jitter, max_delay)
                    logger.warning(f"⚠️ [DB Retry] Intento {attempt}/{max_retries} en {func.__name__} falló: {e}. Reintentando en {sleep_time:.2f}s...")
                    await asyncio.sleep(sleep_time)
                    delay *= 2
            raise last_exc
        return wrapper
    return decorator

# ─── Wrappers Async para Supabase ───────────────────────────────────────────
@db_retry(max_retries=3, base_delay=0.3, max_delay=2.0)
async def db_select(table: str, match_col: str, match_val: str, select_cols: str = "*"):
    try:
        return await supabase.table(table).select(select_cols).eq(match_col, match_val).execute()
    except Exception as e:
        logger.error(f"Error en db_select en tabla {table}: {e}")
        raise

@db_retry(max_retries=3, base_delay=0.3, max_delay=2.0)
async def db_insert(table: str, data: dict):
    try:
        return await supabase.table(table).insert(data).execute()
    except Exception as e:
        logger.error(f"Error en db_insert en tabla {table}: {e}")
        raise

@db_retry(max_retries=3, base_delay=0.3, max_delay=2.0)
async def db_update(table: str, updates: dict, match_col: str, match_val: str):
    try:
        updates_copy = dict(updates)
        updates_copy.pop("guild_id", None)
        if not updates_copy:
            return None
        return await supabase.table(table).update(updates_copy).eq(match_col, match_val).execute()
    except Exception as e:
        logger.error(f"Error en db_update en tabla {table}: {e}")
        raise

@db_retry(max_retries=3, base_delay=0.3, max_delay=2.0)
async def db_upsert(table: str, data: dict):
    try:
        data_copy = dict(data)
        if "skull_count" in data_copy and isinstance(data_copy["skull_count"], int):
            data_copy["skull_count"] = max(0, data_copy["skull_count"])
        return await supabase.table(table).upsert(data_copy).execute()
    except Exception as e:
        logger.error(f"Error en db_upsert en tabla {table}: {e}")
        raise

# ─── Config ───────────────────────────────────────────────────────────────────
async def get_guild_config(guild_id) -> dict:
    gid = str(guild_id)
    if gid in _guild_config_cache:
        return _guild_config_cache[gid]
    try:
        resp = await db_select("settings", "guild_id", gid)
        if resp.data:
            cfg = resp.data[0]
        else:
            cfg = {"guild_id": gid, "skullboard_channel_id": 0, "min_skulls": 1, "prefix": "sk!"}
            await db_insert("settings", cfg)
        _guild_config_cache[gid] = cfg
        return cfg
    except Exception as e:
        logger.error(f"Error al obtener configuración de guild {gid}: {e}")
        return {"guild_id": gid, "skullboard_channel_id": 0, "min_skulls": 1, "prefix": "sk!"}

async def update_guild_config(guild_id, updates: dict):
    gid = str(guild_id)
    try:
        await db_update("settings", updates, "guild_id", gid)
        _guild_config_cache.pop(gid, None)  # Invalidate config cache
        _prefix_cache.pop(gid, None)        # Invalidate prefix cache
    except Exception as e:
        logger.error(f"Error al actualizar configuración de guild {gid}: {e}")
        raise

# ─── Tracked messages ─────────────────────────────────────────────────────────
async def get_tracked_message(message_id: str) -> Optional[int]:
    try:
        resp = await db_select("tracked_messages", "message_id", str(message_id), "skullboard_message_id")
        if resp.data:
            return resp.data[0]["skullboard_message_id"]
    except Exception as e:
        logger.error(f"Error en get_tracked_message ({message_id}): {e}")
    return None

async def set_tracked_message(message_id: str, skullboard_id: int, count: int, author_id: str, guild_id: str):
    try:
        await db_upsert("tracked_messages", {
            "message_id":            str(message_id),
            "skullboard_message_id": skullboard_id,
            "skull_count":           count,
            "author_id":             str(author_id),
            "guild_id":              str(guild_id)
        })
        _guild_record_cache.pop(str(guild_id), None)  # Invalidate record cache
    except Exception as e:
        logger.error(f"Error en set_tracked_message ({message_id}): {e}")

async def update_tracked_count(message_id: str, count: int):
    try:
        await db_update("tracked_messages", {"skull_count": count}, "message_id", str(message_id))
    except Exception as e:
        logger.error(f"Error en update_tracked_count ({message_id}): {e}")

async def get_guild_record(guild_id: str) -> int:
    gid = str(guild_id)
    if gid in _guild_record_cache:
        return _guild_record_cache[gid]
    try:
        resp = await supabase.table("tracked_messages").select("skull_count") \
            .eq("guild_id", gid).order("skull_count", desc=True).limit(1).execute()
        rec = 0
        if resp.data:
            rec = resp.data[0]["skull_count"] or 0
        _guild_record_cache[gid] = rec
        return rec
    except Exception as e:
        logger.error(f"Error al obtener récord de guild {gid}: {e}")
        return 0

# ─── Ignored channels ─────────────────────────────────────────────────────────
async def get_ignored_channels(guild_id: str) -> list:
    gid = str(guild_id)
    if gid in _ignored_channels_cache:
        return list(_ignored_channels_cache[gid])
    try:
        resp = await supabase.table("ignored_channels").select("channel_id").eq("guild_id", gid).execute()
        chans = [r["channel_id"] for r in resp.data] if resp.data else []
        _ignored_channels_cache[gid] = set(chans)
        return chans
    except Exception as e:
        logger.error(f"Error al obtener canales ignorados de guild {gid}: {e}")
        return []

async def is_channel_ignored(guild_id: str, channel_id: str) -> bool:
    chans = await get_ignored_channels(guild_id)
    return str(channel_id) in chans

async def add_ignored_channel(guild_id: str, channel_id: str):
    gid = str(guild_id)
    cid = str(channel_id)
    try:
        await supabase.table("ignored_channels").upsert({"guild_id": gid, "channel_id": cid}).execute()
        _ignored_channels_cache.pop(gid, None)
    except Exception as e:
        logger.error(f"Error al añadir canal ignorado {cid} en guild {gid}: {e}")
        raise

async def remove_ignored_channel(guild_id: str, channel_id: str):
    gid = str(guild_id)
    cid = str(channel_id)
    try:
        await supabase.table("ignored_channels").delete().eq("guild_id", gid).eq("channel_id", cid).execute()
        _ignored_channels_cache.pop(gid, None)
    except Exception as e:
        logger.error(f"Error al eliminar canal ignorado {cid} en guild {gid}: {e}")
        raise

# ─── Notify settings (con caché en memoria) ───────────────────────────────────
notify_disabled_cache: set = set()

async def load_notify_cache():
    try:
        resp = await supabase.table("notify_settings").select("guild_id,user_id").eq("enabled", False).execute()
        for row in (resp.data or []):
            notify_disabled_cache.add((str(row["guild_id"]), str(row["user_id"])))
        logger.info(f"📬 Notify cache cargada: {len(notify_disabled_cache)} usuarios con notificaciones desactivadas")
    except Exception as e:
        logger.error(f"Error cargando notify cache: {e}")

def is_notify_enabled(guild_id, user_id) -> bool:
    return (str(guild_id), str(user_id)) not in notify_disabled_cache

async def set_notify(guild_id, user_id, enabled: bool):
    gid = str(guild_id)
    uid = str(user_id)
    try:
        await supabase.table("notify_settings").upsert({
            "guild_id": gid, "user_id": uid, "enabled": enabled
        }).execute()
        if enabled:
            notify_disabled_cache.discard((gid, uid))
        else:
            notify_disabled_cache.add((gid, uid))
    except Exception as e:
        logger.error(f"Error al establecer notificación para {uid} en {gid}: {e}")
        raise

# ─── Prefijo dinámico ─────────────────────────────────────────────────────────
async def get_prefix(bot, message):
    if not message.guild:
        return "sk!"
    gid = str(message.guild.id)
    if gid in _prefix_cache:
        return _prefix_cache[gid]
    cfg = await get_guild_config(message.guild.id)
    prefix = cfg.get("prefix", "sk!")
    _prefix_cache[gid] = prefix
    return prefix

# ─── Bot ──────────────────────────────────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True
intents.reactions       = True
intents.guilds          = True
intents.members         = True
intents.messages        = True

class GuildOnlyTree(app_commands.CommandTree):
    """Bloquea todos los slash commands fuera de servidores.

    Sin esto, /top, /ajustes, /stats... crashean en DMs con AttributeError
    porque todo el código asume interaction.guild != None.
    """
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.guild is None:
            try:
                await interaction.response.send_message(
                    "❌ Este comando solo funciona dentro de un servidor.", ephemeral=True
                )
            except Exception:
                pass
            return False
        return True

class SkullBot(commands.AutoShardedBot):
    async def setup_hook(self):
        global supabase
        supabase = await acreate_client(SUPABASE_URL, SUPABASE_KEY)
        logger.info("✅ Cliente Supabase (async) inicializado")
        synced = await self.tree.sync()
        logger.info(f"✅ Slash commands sincronizados: {len(synced)} (AutoShardedBot activo)")
        await load_notify_cache()
        if not status_loop.is_running():
            status_loop.start()

bot  = SkullBot(command_prefix=get_prefix, intents=intents, help_command=None, tree_cls=GuildOnlyTree)
tree = bot.tree

async def get_formatted_prefix(ctx_or_interaction) -> str:
    guild = getattr(ctx_or_interaction, "guild", None)
    if guild is None:
        return "sk!"
    cfg = await get_guild_config(guild.id)
    return cfg.get("prefix", "sk!")

# ─── Status Loop ──────────────────────────────────────────────────────────────
@tasks.loop(minutes=5)
async def status_loop():
    await bot.wait_until_ready()
    try:
        activities = [
            discord.Activity(type=discord.ActivityType.watching, name=f"{len(bot.guilds)} servidores"),
            discord.Game(name="💀 SkullBoard"),
            discord.Activity(type=discord.ActivityType.listening, name="Board Calaverosa")
        ]
        for activity in activities:
            if bot.is_closed():
                break
            await bot.change_presence(activity=activity)
            await asyncio.sleep(60)
    except Exception as e:
        logger.warning(f"⚠️ Error en status_loop (se reintentará en la siguiente iteración): {e}")

# ─── Utilidades ───────────────────────────────────────────────────────────────
def formatear_fecha(fecha: datetime) -> str:
    ahora = datetime.now(timezone.utc)
    diff  = (ahora.date() - fecha.date()).days
    hora  = fecha.strftime("%H:%M")
    if diff == 0: return f"Hoy a las {hora}"
    if diff == 1: return f"Ayer a las {hora}"
    return fecha.strftime("%d/%m/%Y %H:%M")

def get_invite_url():
    client_id   = bot.user.id if bot.user else 1367463352774955059
    permissions = 277025508352
    return f"https://discord.com/oauth2/authorize?client_id={client_id}&permissions={permissions}&scope=bot+applications.commands"

def ping_estado(ms: int) -> str:
    if ms < 100: return "🟢 Óptimo"
    if ms < 200: return "🟡 Aceptable"
    return "🔴 Alto"

def _sanitize_name(name: str) -> str:
    """Neutraliza inyección en embeds. Un apodo malicioso como
    'x](https://phishing.com)' rompería el enlace markdown `[texto](url)` de los
    rankings y crearía un enlace a un sitio externo. Escapamos el markdown y
    convertimos los corchetes/paréntesis en variantes inofensivas."""
    name = discord.utils.escape_markdown(name or "")
    name = name.replace("[", "(").replace("]", ")")
    return name[:40] if name else "Usuario desconocido"

async def resolve_display_name(guild: discord.Guild, user_id) -> str:
    """Resuelve el mejor nombre visible de un usuario: apodo del servidor →
    nombre global (si dejó el servidor) → 'Usuario desconocido'.
    El resultado va SANITIZADO para insertarse con seguridad en embeds."""
    try:
        uid = int(user_id)
    except (TypeError, ValueError):
        return "Usuario desconocido"
    raw = None
    m = guild.get_member(uid)
    if m:
        raw = m.display_name
    else:
        try:
            m = await guild.fetch_member(uid)
            if m:
                raw = m.display_name
        except Exception:
            pass
        if raw is None:
            u = bot.get_user(uid)
            if u is None:
                # Último recurso: la API. Resuelve el nombre global de CUALQUIER
                # usuario válido, aunque haya dejado el servidor y no esté cacheado.
                try:
                    u = await bot.fetch_user(uid)
                except Exception:
                    u = None
            raw = u.display_name if u else None
    return _sanitize_name(raw) if raw else "Usuario desconocido"

async def _is_admin_or_deny(interaction: discord.Interaction) -> bool:
    """True si el usuario es administrador. Si no, responde con el aviso de
    permisos (efímero) y devuelve False. Uso: `if not await _is_admin_or_deny(i): return`."""
    if interaction.user.guild_permissions.administrator:
        return True
    embed = discord.Embed(title="❌ Sin permisos", description="Necesitas permisos de **Administrador**.", color=0xed4245)
    try:
        await interaction.response.send_message(embed=embed, ephemeral=True)
    except Exception:
        pass
    return False

async def _deny_if_not_owner(ctx) -> bool:
    """Para comandos de owner del bot. Si NO es el owner, reacciona con ❓ y
    devuelve True (denegado). Si lo es, devuelve False. Uso: `if await _deny_if_not_owner(ctx): return`."""
    if ctx.author.id == OWNER_ID:
        return False
    try:
        await ctx.message.add_reaction("❓")
    except Exception:
        pass
    return True

# ─── Embed de ajustes ─────────────────────────────────────────────────────────
async def build_ajustes_embed(guild_id) -> discord.Embed:
    cfg           = await get_guild_config(guild_id)
    skull_channel = bot.get_channel(cfg["skullboard_channel_id"])
    ms            = round(bot.latency * 1000)
    embed = discord.Embed(title="⚙️ Ajustes del SkullBoard", color=0x8b5cf6)
    embed.add_field(name="📌 Canal",    value=skull_channel.mention if skull_channel else "❌ No configurado", inline=True)
    embed.add_field(name="💀 Mínimo",   value=f"{cfg['min_skulls']} 💀",                                       inline=True)
    embed.add_field(name="✏️ Prefijo",  value=f"`{cfg.get('prefix','sk!')}`",                                  inline=True)
    embed.add_field(name="🏓 Latencia", value=f"{ping_estado(ms)} · {ms}ms",                                   inline=True)
    embed.add_field(name="\u200b",      value="\u200b",                                                        inline=True)
    embed.add_field(name="\u200b",      value="\u200b",                                                        inline=True)
    embed.add_field(name="🔗 Invitar",  value=f"[Invitar SkullBoard]({get_invite_url()})",                       inline=False)
    return embed

# ─── Dashboard & Web Links ───────────────────────────────────────────────────
DASHBOARD_URL = "https://skullboard.vercel.app/"
PRIVACY_URL   = "https://skullboard.vercel.app/privacy"
TERMS_URL     = "https://skullboard.vercel.app/terms"
CHANGES_URL   = "https://skullboard.vercel.app/cambios"

class DashboardView(discord.ui.View):
    def __init__(self):
        super().__init__()
        self.add_item(discord.ui.Button(label="🌐 Panel Web", url=DASHBOARD_URL, style=discord.ButtonStyle.link))
        self.add_item(discord.ui.Button(label="🔒 Privacidad", url=PRIVACY_URL, style=discord.ButtonStyle.link))
        self.add_item(discord.ui.Button(label="📋 Términos", url=TERMS_URL, style=discord.ButtonStyle.link))
        self.add_item(discord.ui.Button(label="📜 Novedades", url=CHANGES_URL, style=discord.ButtonStyle.link))

def build_dashboard_embed() -> discord.Embed:
    embed = discord.Embed(
        title="🌐 Panel Web & Recursos — SkullBoard",
        description=(
            "Accede a la web oficial de **SkullBoard** para ver las características completas, "
            "documentación legal y panel informativo.\n\n"
            f"• 🏠 **Web oficial:** [skullboard.vercel.app]({DASHBOARD_URL})\n"
            f"• 🔒 **Política de Privacidad:** [Ver política]({PRIVACY_URL})\n"
            f"• 📋 **Términos de Servicio:** [Ver términos]({TERMS_URL})\n"
            f"• 📜 **Historial de Cambios:** [Ver cambios]({CHANGES_URL})\n"
            f"• 🔗 **Invitar al bot:** [Enlace directo]({get_invite_url()})"
        ),
        color=0x8b5cf6
    )
    embed.set_footer(text="SkullBoard · Bot de Discord comunitario · 💀")
    return embed

# ─── Help paginado (slash) ────────────────────────────────────────────────────
class HelpView(discord.ui.View):
    def __init__(self, pages: list):
        super().__init__(timeout=120)
        self.pages   = pages
        self.current = 0
        self.message: Optional[discord.Message] = None
        self._update_buttons()

    def _update_buttons(self):
        self.prev_btn.disabled = self.current == 0
        self.next_btn.disabled = self.current == len(self.pages) - 1

    async def on_timeout(self):
        # Deshabilita los botones al expirar para que no queden clicks "muertos"
        for child in self.children:
            child.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except Exception:
                pass

    @discord.ui.button(label="◀ Anterior", style=discord.ButtonStyle.secondary)
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current -= 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self.pages[self.current], view=self)

    @discord.ui.button(label="Siguiente ▶", style=discord.ButtonStyle.secondary)
    async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current += 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self.pages[self.current], view=self)

def build_slash_help_pages() -> list:
    footer_nav   = "Usa /help para ver los comandos de barra"
    footer_admin = "🔒 Requiere permisos de administrador"

    p1 = discord.Embed(title="📖 Lista de comandos — SkullBoard", description="Página 1 de 4 · General", color=0x8b5cf6)
    p1.add_field(name="/ajustes",   value="⚙️ Ver configuración actual", inline=True)
    p1.add_field(name="/dashboard", value="🌐 Panel web y recursos",      inline=True)
    p1.add_field(name="/ping",      value="🏓 Latencia del bot",          inline=True)
    p1.add_field(name="/invite",    value="🔗 Enlace de invitación",      inline=True)
    p1.add_field(name="/notify",    value="📬 Activa/desactiva tus DMs",   inline=True)
    p1.set_footer(text=footer_nav)

    p2 = discord.Embed(title="📖 Lista de comandos — SkullBoard", description="Página 2 de 4 · Skullboard", color=0x8b5cf6)
    p2.add_field(name="/top",     value="🏆 Top mensajes más 💀",        inline=True)
    p2.add_field(name="/stats",   value="📊 Estadísticas de un usuario", inline=True)
    p2.add_field(name="/random",  value="🎲 Mensaje aleatorio",          inline=True)
    p2.add_field(name="/ignored", value="🚫 Ver canales ignorados",      inline=True)
    p2.set_footer(text=footer_nav)

    p3 = discord.Embed(title="📖 Lista de comandos — SkullBoard", description="Página 3 de 4 · Estadísticas", color=0x8b5cf6)
    p3.add_field(name="/leaderboard",  value="👑 Top usuarios del servidor",  inline=True)
    p3.add_field(name="/server_stats", value="📊 Stats globales del servidor", inline=True)
    p3.add_field(name="/top_month",    value="📅 Top mensajes del mes",        inline=True)
    p3.add_field(name="/top_year",     value="🗓️ Top mensajes del año",       inline=True)
    p3.set_footer(text=footer_nav)

    p4 = discord.Embed(title="📖 Lista de comandos — SkullBoard", description="Página 4 de 4 · Configuración", color=0x8b5cf6)
    p4.add_field(name="/set_channel 🔒", value="📌 Configura el canal del skullboard", inline=True)
    p4.add_field(name="/set_min 🔒",     value="💀 Mínimo de reacciones",               inline=True)
    p4.add_field(name="/prefix 🔒",      value="✏️ Cambia el prefijo",                 inline=True)
    p4.add_field(name="/ignore 🔒",      value="🚫 Ignora un canal",                   inline=True)
    p4.add_field(name="/unignore 🔒",    value="✅ Deja de ignorar un canal",           inline=True)
    p4.add_field(name="/setup_pin 🔒",   value="📌 Auto-pin de mensajes",               inline=True)
    p4.add_field(name="/resync 🔒",      value="🔄 Resincroniza los conteos de 💀",     inline=True)
    p4.add_field(name="/reset ⚠️",        value="⚠️ Resetea el skullboard · solo propietario", inline=True)
    p4.set_footer(text=footer_admin)

    return [p1, p2, p3, p4]

# ─── On Ready ─────────────────────────────────────────────────────────────────
@bot.event
async def on_ready():
    logger.info(f"🔧 Bot conectado como {bot.user} ({bot.user.id})")

# ─── React Handlers con cooldown inteligente ──────────────────────────────────
@bot.event
async def on_raw_reaction_add(payload):
    if payload.guild_id is None: return
    if payload.user_id == bot.user.id: return
    if str(payload.emoji) != skull_emoji: return
    await _schedule_check(payload.guild_id, payload.channel_id, payload.message_id)

@bot.event
async def on_raw_reaction_remove(payload):
    if payload.guild_id is None: return
    if payload.user_id == bot.user.id: return
    if str(payload.emoji) != skull_emoji: return
    await _schedule_check(payload.guild_id, payload.channel_id, payload.message_id)

async def _schedule_check(guild_id: int, channel_id: int, message_id: int):
    _debouncer.schedule(message_id, _run_check, guild_id, channel_id, message_id)

async def _run_check(guild_id: int, channel_id: int, message_id: int):
    # Filtros tempranos (solo cachés)
    try:
        cfg = await get_guild_config(guild_id)
        if channel_id == cfg.get("skullboard_channel_id"): return
        if await is_channel_ignored(str(guild_id), str(channel_id)): return
    except Exception:
        pass

    chan = bot.get_channel(channel_id)
    if chan is None:
        try:
            chan = await bot.fetch_channel(channel_id)
        except Exception:
            return
    try:
        msg = await chan.fetch_message(message_id)
    except Exception:
        return
    await _check(msg)

# ─── Core logic ───────────────────────────────────────────────────────────────
def _build_repost(msg: discord.Message, count: int, record: int, min_skulls: int):
    """Construye el (contenido, embed) de un mensaje destacado del skullboard."""
    emoji   = "☠️" if count >= min_skulls * 2 else "💀"
    content = msg.content or ""
    if len(content) > 1800:
        content = content[:1800] + "...\n*(mensaje truncado)*"
    embed = discord.Embed(description=content, color=discord.Color.dark_gray())
    embed.set_author(
        name=msg.author.display_name,
        icon_url=msg.author.display_avatar.url
    )
    img = next((a for a in msg.attachments if a.content_type and a.content_type.startswith("image/")), None)
    if img:
        embed.set_image(url=img.url)
    embed.add_field(name="🔗 Enlace", value=f"[Saltar al mensaje]({msg.jump_url})", inline=False)
    footer = f"{count} {emoji}  •  {formatear_fecha(msg.created_at)}"
    if count >= record and count > 0:
        footer += "  •  🏆 Récord del servidor"
    embed.set_footer(text=footer)
    texto = f"{emoji} **{count}** | {msg.channel.mention}"
    return texto, embed

async def _check(msg: discord.Message):
    if msg.guild is None:
        return

    mid = str(msg.id)

    async with await _msg_locks.acquire(mid):
        try:
            cfg = await get_guild_config(msg.guild.id)
            gid = str(msg.guild.id)

            if msg.channel.id == cfg["skullboard_channel_id"]: return
            if await is_channel_ignored(gid, str(msg.channel.id)): return

            skull_reac = next((r for r in msg.reactions if str(r.emoji) == skull_emoji), None)
            count      = skull_reac.count if skull_reac else 0

            existing_id = await get_tracked_message(mid)

            if count < cfg["min_skulls"] and not existing_id:
                return

            dest_chan = bot.get_channel(cfg["skullboard_channel_id"])
            if dest_chan is None:
                try:
                    dest_chan = await bot.fetch_channel(cfg["skullboard_channel_id"])
                except Exception:
                    pass
            if not isinstance(dest_chan, discord.abc.Messageable): return

            record       = await get_guild_record(gid)
            texto, embed = _build_repost(msg, count, record, cfg["min_skulls"])

            if existing_id:
                try:
                    if hasattr(dest_chan, "get_partial_message"):
                        old = dest_chan.get_partial_message(existing_id)
                    else:
                        old = await dest_chan.fetch_message(existing_id)
                    await old.edit(content=texto, embed=embed)
                    await update_tracked_count(mid, count)
                    _guild_record_cache.pop(gid, None)
                    return
                except discord.NotFound:
                    if count < cfg["min_skulls"]:
                        try:
                            await supabase.table("tracked_messages").delete() \
                                .eq("message_id", mid).execute()
                        except Exception:
                            pass
                        _guild_record_cache.pop(gid, None)
                        return

            if count < cfg["min_skulls"]:
                return

            try:
                sent = await dest_chan.send(content=texto, embed=embed)
            except discord.Forbidden:
                now = time.time()
                if now - _perm_failover_cooldown.get(gid, 0) > 3600:
                    _perm_failover_cooldown[gid] = now
                    logger.warning(f"⚠️ [Perm Failover] Sin permisos para enviar en canal {cfg['skullboard_channel_id']} ({msg.guild.name})")
                    owner = msg.guild.owner
                    if not owner and msg.guild.owner_id:
                        try:
                            owner = await bot.fetch_user(msg.guild.owner_id)
                        except Exception:
                            owner = None
                    if owner:
                        try:
                            owner_embed = discord.Embed(
                                title="⚠️ [SkullBoard] Faltan permisos en tu canal de Starboard",
                                description=(
                                    f"Hola, SkullBoard intentó publicar un mensaje destacado en tu canal configurado en **{msg.guild.name}**, "
                                    f"pero el bot carece de los permisos **Enviar Mensajes** o **Insertar Enlaces** (`EMBED_LINKS`) en dicho canal.\n\n"
                                    f"👉 Por favor, otorga los permisos necesarios al rol de SkullBoard en ese canal para que el Starboard funcione correctamente."
                                ),
                                color=0xf59e0b
                            )
                            owner_embed.set_footer(text="Auto-Diagnóstico Defensivo · SkullBoard v2.5.0")
                            await owner.send(embed=owner_embed)
                        except Exception:
                            pass
                return
            await set_tracked_message(mid, sent.id, count, msg.author.id, gid)
            _guild_record_cache.pop(gid, None)

            # DM de notificación al autor
            if is_notify_enabled(gid, msg.author.id):
                try:
                    dm_embed = discord.Embed(
                        title="💀 ¡Tu mensaje ha llegado al skullboard!",
                        description=(
                            f"Tu mensaje en el servidor **{msg.guild.name}** ha alcanzado las "
                            f"**{count} 💀** y ha sido destacado en el skullboard."
                        ),
                        color=0x8b5cf6
                    )
                    dm_embed.add_field(
                        name="🔗 Ver mensaje",
                        value=f"[Saltar al skullboard]({sent.jump_url})",
                        inline=False
                    )
                    dm_embed.set_footer(text="Si no quieres recibir estas notificaciones usa /notify off")
                    await msg.author.send(embed=dm_embed)
                except (discord.Forbidden, discord.HTTPException):
                    pass
                except Exception as e:
                    logger.warning(f"Error enviando DM a {msg.author.id}: {e}")

            # Auto-pin
            threshold = cfg.get("pin_threshold", 0) or 0
            if threshold > 0 and count >= threshold and not sent.pinned:
                try:
                    await sent.pin(reason=f"Auto-pin: superó {threshold} 💀")
                except discord.HTTPException as e:
                    logger.warning(f"No se pudo pinear en {gid}: {e}")
                    await update_guild_config(msg.guild.id, {"pin_threshold": 0})
                    try:
                        err_embed = discord.Embed(
                            title="⚠️ Auto-pin desactivado",
                            description=(
                                "No se ha podido pinear el último mensaje en este canal "
                                "(probablemente se ha alcanzado el límite de 50 pins).\n\n"
                                "El **auto-pin se ha desactivado automáticamente**. "
                                "Libera pins y vuelve a configurarlo con `/setup_pin`."
                            ),
                            color=0xed4245
                        )
                        await dest_chan.send(embed=err_embed)
                    except Exception:
                        pass

        except Exception as e:
            logger.error(f"Error en _check: {e}")

# ─── Borrado de mensajes ──────────────────────────────────────────────────────
_delete_sem = asyncio.Semaphore(8)

async def _handle_deleted_messages(mids: list[str]):
    """Procesa un lote de mensajes borrados con pocas queries (batched)."""
    if not mids:
        return
    try:
        resp = await supabase.table("tracked_messages") \
            .select("message_id,skullboard_message_id,guild_id") \
            .in_("message_id", mids).execute()

        rows = resp.data or []
        touched_guilds: set[str] = set()

        for row in rows:
            sb_id = row.get("skullboard_message_id")
            gid   = row.get("guild_id")
            if gid:
                touched_guilds.add(str(gid))
            if not (sb_id and gid):
                continue
            try:
                cfg     = await get_guild_config(int(gid))
                sb_chan = bot.get_channel(cfg["skullboard_channel_id"])
                if sb_chan is None:
                    sb_chan = await bot.fetch_channel(cfg["skullboard_channel_id"])
                if sb_chan:
                    try:
                        if hasattr(sb_chan, "get_partial_message"):
                            await sb_chan.get_partial_message(sb_id).delete()
                        else:
                            sb_msg = await sb_chan.fetch_message(sb_id)
                            await sb_msg.delete()
                    except (discord.NotFound, discord.HTTPException):
                        pass
                    await asyncio.sleep(0.1)
            except Exception:
                pass

        if rows:
            await supabase.table("tracked_messages").delete() \
                .in_("message_id", [r["message_id"] for r in rows]).execute()

        resp2 = await supabase.table("tracked_messages") \
            .select("guild_id") \
            .in_("skullboard_message_id", mids).execute()
        if resp2.data:
            for r in resp2.data:
                if r.get("guild_id"):
                    touched_guilds.add(str(r["guild_id"]))
            await supabase.table("tracked_messages").delete() \
                .in_("skullboard_message_id", mids).execute()

        for gid in touched_guilds:
            _guild_record_cache.pop(gid, None)
    except Exception as e:
        logger.error(f"Error procesando lote de {len(mids)} borrados: {e}")

@bot.event
async def on_raw_message_delete(payload):
    async with _delete_sem:
        await _handle_deleted_messages([str(payload.message_id)])

@bot.event
async def on_raw_bulk_message_delete(payload):
    mids = [str(m) for m in payload.message_ids]
    async with _delete_sem:
        for i in range(0, len(mids), 100):
            await _handle_deleted_messages(mids[i:i + 100])

# ─── COMANDOS DE TEXTO ────────────────────────────────────────────────────────

def _validate_prefix(p: Optional[str]) -> tuple[bool, str]:
    if not p:
        return False, "Indica el nuevo prefijo."
    p_clean = p.strip()
    if not p_clean:
        return False, "El prefijo no puede estar compuesto únicamente por espacios."
    if any(c in p_clean for c in ("\n", "\r", "\t")):
        return False, "El prefijo no puede contener saltos de línea ni tabuladores."
    if len(p_clean) > 10:
        return False, "El prefijo no puede superar los **10 caracteres**."
    return True, p_clean

@bot.command(name="prefix", aliases=["set_prefix"])
@commands.guild_only()
@commands.has_permissions(administrator=True)
async def prefix_cmd(ctx, nuevo_prefijo: str = None):
    valido, res = _validate_prefix(nuevo_prefijo)
    if not valido:
        embed = discord.Embed(title="❌ Prefijo inválido", description=res, color=0xed4245)
        return await ctx.send(embed=embed)
    await update_guild_config(ctx.guild.id, {"prefix": res})
    _prefix_cache.pop(str(ctx.guild.id), None)
    embed = discord.Embed(title="✅ Prefijo actualizado", description=f"Ahora puedes usar comandos con `{res}`", color=0x57f287)
    await ctx.send(embed=embed)

@bot.command(name="set_channel", aliases=["channel"])
@commands.guild_only()
@commands.has_permissions(administrator=True)
async def set_channel_cmd(ctx, canal: discord.TextChannel = None):
    if not canal:
        embed = discord.Embed(title="❌ Falta el canal", description="Menciona el canal (ej: `#general`).", color=0xed4245)
        return await ctx.send(embed=embed)
    await update_guild_config(ctx.guild.id, {"skullboard_channel_id": canal.id})
    embed = discord.Embed(title="✅ Canal configurado", description=f"Los mensajes se enviarán a {canal.mention}", color=0x57f287)
    await ctx.send(embed=embed)

@bot.command(name="set_min", aliases=["min"])
@commands.guild_only()
@commands.has_permissions(administrator=True)
async def set_min_cmd(ctx, n: int = None):
    if not n or n < 1:
        embed = discord.Embed(title="❌ Número inválido", description="Introduce un número mayor a 0.", color=0xed4245)
        return await ctx.send(embed=embed)
    await update_guild_config(ctx.guild.id, {"min_skulls": n})
    embed = discord.Embed(title="✅ Meta establecida", description=f"Se necesitan **{n}** reacciones 💀 para destacar un mensaje.", color=0x57f287)
    await ctx.send(embed=embed)

@bot.command(name="ajustes", aliases=["settings"])
@commands.guild_only()
async def ajustes_cmd(ctx):
    embed = await build_ajustes_embed(ctx.guild.id)
    await ctx.send(embed=embed)

@bot.command()
@commands.guild_only()
async def ping(ctx):
    ms    = round(bot.latency * 1000)
    embed = discord.Embed(title="🏓 Pong!", color=0x8b5cf6)
    embed.add_field(name="⚡ Latencia", value=f"**{ms}ms**", inline=True)
    embed.add_field(name="📡 Estado",   value=ping_estado(ms),  inline=True)
    await ctx.send(embed=embed)

@bot.command()
@commands.guild_only()
async def invite(ctx):
    embed = discord.Embed(title="💀 SkullBoard", description="Añade este bot a tu servidor y ¡disfruta!", color=0x8b5cf6)
    embed.add_field(name="🔗 Invitar al servidor", value=f"[Haz click aquí para invitarme]({get_invite_url()})", inline=False)
    embed.set_footer(text=f"Más de {len(bot.guilds)} servidores confían en SkullBoard")
    await ctx.send(embed=embed)

@bot.command(name="dashboard", aliases=["web", "panel"])
@commands.guild_only()
async def dashboard_cmd(ctx):
    embed = build_dashboard_embed()
    view  = DashboardView()
    await ctx.send(embed=embed, view=view)

@bot.command(name="help", aliases=["ayuda", "comandos"])
@commands.guild_only()
async def help_cmd(ctx):
    p = await get_formatted_prefix(ctx)
    footer_nav   = f"Usa /help para ver los comandos de barra"
    footer_admin = "🔒 Requiere permisos de administrador"

    p1 = discord.Embed(title="📖 Lista de comandos — SkullBoard", description="Página 1 de 4 · General", color=0x8b5cf6)
    p1.add_field(name=f"{p}ajustes",   value="⚙️ Ver configuración actual", inline=True)
    p1.add_field(name=f"{p}dashboard", value="🌐 Panel web y recursos",      inline=True)
    p1.add_field(name=f"{p}ping",      value="🏓 Latencia del bot",          inline=True)
    p1.add_field(name=f"{p}invite",    value="🔗 Enlace de invitación",      inline=True)
    p1.add_field(name=f"{p}notify",    value="📬 Activa/desactiva tus DMs",   inline=True)
    p1.set_footer(text=footer_nav)

    p2 = discord.Embed(title="📖 Lista de comandos — SkullBoard", description="Página 2 de 4 · Skullboard", color=0x8b5cf6)
    p2.add_field(name=f"{p}top",            value="🏆 Top mensajes más 💀",        inline=True)
    p2.add_field(name=f"{p}stats @usuario", value="📊 Estadísticas de un usuario", inline=True)
    p2.add_field(name=f"{p}random",         value="🎲 Mensaje aleatorio",          inline=True)
    p2.add_field(name=f"{p}ignored",        value="🚫 Ver canales ignorados",      inline=True)
    p2.set_footer(text=footer_nav)

    p3 = discord.Embed(title="📖 Lista de comandos — SkullBoard", description="Página 3 de 4 · Estadísticas", color=0x8b5cf6)
    p3.add_field(name=f"{p}leaderboard", value="👑 Top usuarios del servidor",  inline=True)
    p3.add_field(name=f"{p}serverstats", value="📊 Stats globales del servidor", inline=True)
    p3.add_field(name=f"{p}topmonth",    value="📅 Top mensajes del mes",        inline=True)
    p3.add_field(name=f"{p}topyear",     value="🗓️ Top mensajes del año",       inline=True)
    p3.set_footer(text=footer_nav)

    p4 = discord.Embed(title="📖 Lista de comandos — SkullBoard", description="Página 4 de 4 · Configuración", color=0x8b5cf6)
    p4.add_field(name=f"{p}set_channel 🔒", value="📌 Configura el canal del skullboard", inline=True)
    p4.add_field(name=f"{p}set_min 🔒",     value="💀 Mínimo de reacciones",               inline=True)
    p4.add_field(name=f"{p}prefix 🔒",      value="✏️ Cambia el prefijo",                 inline=True)
    p4.add_field(name=f"{p}ignore 🔒",      value="🚫 Ignora un canal",                    inline=True)
    p4.add_field(name=f"{p}unignore 🔒",    value="✅ Deja de ignorar un canal",           inline=True)
    p4.add_field(name=f"{p}setuppin 🔒",    value="📌 Auto-pin de mensajes",               inline=True)
    p4.add_field(name=f"{p}resync 🔒",      value="🔄 Resincroniza los conteos de 💀",     inline=True)
    p4.add_field(name=f"{p}reset 🔒",       value="⚠️ Resetea el skullboard · solo el propietario del servidor", inline=True)
    p4.set_footer(text=footer_admin)

    pages = [p1, p2, p3, p4]
    view  = HelpView(pages)
    view.message = await ctx.send(embed=pages[0], view=view)

@bot.command(name="reset", hidden=True)
@commands.guild_only()
async def reset_cmd(ctx):
    if ctx.author.id != ctx.guild.owner_id:
        embed = discord.Embed(
            title="❌ Solo el propietario del servidor",
            description="Únicamente el **propietario del servidor** puede usar este comando.",
            color=0xed4245
        )
        return await ctx.send(embed=embed)
    gid        = str(ctx.guild.id)
    embed_warn = discord.Embed(
        title="⚠️ ¿Estás seguro?",
        description=(
            "Esto borrará **todos los mensajes** del skullboard de este servidor.\n"
            "Esta acción **no se puede deshacer**.\n\n"
            "Escribe `CONFIRMAR` en el chat para continuar. Tienes **30 segundos**."
        ),
        color=0xed4245
    )
    await ctx.send(embed=embed_warn)

    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel and m.content == "CONFIRMAR"

    try:
        await bot.wait_for("message", check=check, timeout=30.0)
    except asyncio.TimeoutError:
        embed = discord.Embed(title="❌ Reset cancelado", description="No se recibió confirmación a tiempo.", color=0x4e5058)
        return await ctx.send(embed=embed)

    try:
        resp = await supabase.table("tracked_messages").delete().eq("guild_id", gid).execute()
        deleted = len(resp.data) if resp.data else 0
        _guild_record_cache.pop(gid, None)
        embed = discord.Embed(
            title="✅ Skullboard reseteado",
            description=(
                        f"Se han eliminado **{deleted} mensajes** del registro. El skullboard empieza de cero.\n\n"
                        "ℹ️ Los mensajes ya publicados en el canal del skullboard **no se borran**. "
                        "Si quieres empezar de cero del todo, vacía también ese canal — "
                        "si no, un `/resync` los volvería a importar."
                    ),
            color=0x57f287
        )
        await ctx.send(embed=embed)
    except Exception as e:
        logger.error(f"Error reseteando tracked_messages en reset_cmd para guild {gid}: {e}")
        embed = discord.Embed(title="❌ Error", description="No se pudo resetear la base de datos.", color=0xed4245)
        await ctx.send(embed=embed)

@bot.command(name="ignore")
@commands.guild_only()
@commands.has_permissions(administrator=True)
async def ignore_cmd(ctx, canal: discord.TextChannel = None):
    if not canal:
        embed = discord.Embed(title="❌ Falta el canal", description="Menciona el canal a ignorar.", color=0xed4245)
        return await ctx.send(embed=embed)
    await add_ignored_channel(str(ctx.guild.id), str(canal.id))
    embed = discord.Embed(title="🚫 Canal ignorado", description=f"Los mensajes de {canal.mention} ya no podrán llegar al skullboard.", color=0x57f287)
    await ctx.send(embed=embed)

@bot.command(name="unignore")
@commands.guild_only()
@commands.has_permissions(administrator=True)
async def unignore_cmd(ctx, canal: discord.TextChannel = None):
    if not canal:
        embed = discord.Embed(title="❌ Falta el canal", description="Menciona el canal a desbloquear.", color=0xed4245)
        return await ctx.send(embed=embed)
    await remove_ignored_channel(str(ctx.guild.id), str(canal.id))
    embed = discord.Embed(title="✅ Canal desbloqueado", description=f"Los mensajes de {canal.mention} ya pueden llegar al skullboard.", color=0x57f287)
    await ctx.send(embed=embed)

@bot.command(name="top")
@commands.guild_only()
async def top_cmd(ctx):
    gid = str(ctx.guild.id)
    try:
        resp = await supabase.table("tracked_messages") \
            .select("skull_count,author_id,skullboard_message_id") \
            .eq("guild_id", gid).order("skull_count", desc=True).limit(10).execute()
    except Exception as e:
        logger.error(f"Error en top_cmd para guild {gid}: {e}")
        embed = discord.Embed(title="❌ Error", description="No se pudo obtener el top.", color=0xed4245)
        return await ctx.send(embed=embed)

    if not resp.data:
        embed = discord.Embed(title="🏆 Top Skullboard", description="Aún no hay mensajes en el skullboard.", color=0x4e5058)
        return await ctx.send(embed=embed)

    medals = ["🥇", "🥈", "🥉"]
    cfg    = await get_guild_config(ctx.guild.id)
    lines  = []
    for i, row in enumerate(resp.data):
        pos   = medals[i] if i < 3 else f"{i+1}."
        count = row.get("skull_count") or 0
        name  = await resolve_display_name(ctx.guild, row.get("author_id"))
        sb_id = row.get("skullboard_message_id")
        if cfg["skullboard_channel_id"] and sb_id:
            link = f"https://discord.com/channels/{gid}/{cfg['skullboard_channel_id']}/{sb_id}"
            lines.append(f"{pos} **[{name}]({link})** — **{count} 💀**")
        else:
            lines.append(f"{pos} **{name}** — **{count} 💀**")

    embed = discord.Embed(title="🏆 Top Skullboard", description="\n".join(lines), color=0xfaa61a)
    embed.set_footer(text=f"Top {len(resp.data)} mensajes del servidor")
    await ctx.send(embed=embed)

@bot.command(name="stats", aliases=["estadisticas"])
@commands.guild_only()
async def stats_cmd(ctx, member: discord.Member = None):
    member = member or ctx.author
    embed  = await _stats_embed(ctx.guild, member)
    await ctx.send(embed=embed)

async def _handle_random_message(guild: discord.Guild) -> tuple[Optional[str], Optional[discord.Embed]]:
    gid = str(guild.id)
    try:
        resp = await supabase.rpc("get_random_tracked_message", {"p_guild_id": gid}).execute()
    except Exception as e:
        logger.error(f"Error en RPC get_random_tracked_message para guild {gid}: {e}")
        return None, discord.Embed(title="❌ Error", description="No se pudo obtener un mensaje aleatorio.", color=0xed4245)

    if not resp.data:
        return None, discord.Embed(title="🎲 Mensaje aleatorio", description="Aún no hay mensajes en el skullboard.", color=0x4e5058)

    row = resp.data[0]
    cfg = await get_guild_config(guild.id)
    sb_channel_id = cfg.get("skullboard_channel_id")
    sb_chan = bot.get_channel(sb_channel_id) if sb_channel_id else None
    if sb_chan is None and sb_channel_id:
        try:
            sb_chan = await bot.fetch_channel(sb_channel_id)
        except Exception:
            pass

    sb_id = row.get("skullboard_message_id")
    sb_msg = None
    if sb_chan and sb_id:
        try:
            sb_msg = await sb_chan.fetch_message(sb_id)
        except Exception:
            sb_msg = None

    if sb_msg and sb_msg.embeds:
        embed = sb_msg.embeds[0].copy()
        embed.title = "🎲 Mensaje aleatorio del skullboard"
        return sb_msg.content, embed
    return None, discord.Embed(title="🎲 Mensaje aleatorio", description="No se pudo recuperar el mensaje.", color=0x4e5058)

@bot.command(name="random")
@commands.guild_only()
async def random_cmd(ctx):
    content, embed = await _handle_random_message(ctx.guild)
    if content:
        await ctx.send(content=content, embed=embed)
    else:
        await ctx.send(embed=embed)

@bot.command(name="ignored")
@commands.guild_only()
async def ignored_cmd(ctx):
    gid      = str(ctx.guild.id)
    channels = await get_ignored_channels(gid)
    if not channels:
        embed = discord.Embed(title="🚫 Canales ignorados", description="No hay ningún canal ignorado en este servidor.", color=0x4e5058)
        return await ctx.send(embed=embed)
    lines = [f"🔇 {bot.get_channel(int(c)).mention if bot.get_channel(int(c)) else f'`{c}`'}" for c in channels]
    p     = await get_formatted_prefix(ctx)
    embed = discord.Embed(title="🚫 Canales ignorados", description="\n".join(lines), color=0x8b5cf6)
    embed.set_footer(text=f"{len(channels)} canal(es) ignorado(s) · Usa {p}unignore para desbloquear")
    await ctx.send(embed=embed)

@bot.command(name="notify")
@commands.guild_only()
async def notify_cmd(ctx, estado: str = None):
    if not estado or estado.lower() not in ("on", "off"):
        enabled = is_notify_enabled(ctx.guild.id, ctx.author.id)
        actual  = "🔔 Activadas" if enabled else "🔕 Desactivadas"
        p       = await get_formatted_prefix(ctx)
        embed = discord.Embed(
            title="📬 Notificaciones del Skullboard",
            description=(
                f"Tus notificaciones en este servidor están: **{actual}**\n\n"
                f"Usa `{p}notify on` o `{p}notify off` para cambiarlo."
            ),
            color=0x8b5cf6
        )
        return await ctx.send(embed=embed)

    enable = estado.lower() == "on"
    await set_notify(ctx.guild.id, ctx.author.id, enable)
    if enable:
        embed = discord.Embed(
            title="🔔 Notificaciones activadas",
            description=f"Recibirás un MD cuando un mensaje tuyo llegue al skullboard de **{ctx.guild.name}**.",
            color=0x57f287
        )
    else:
        embed = discord.Embed(
            title="🔕 Notificaciones desactivadas",
            description=f"No recibirás más MDs del skullboard de **{ctx.guild.name}**.",
            color=0x4e5058
        )
    await ctx.send(embed=embed)

@bot.command(name="setuppin", aliases=["setup_pin"])
@commands.guild_only()
@commands.has_permissions(administrator=True)
async def setuppin_cmd(ctx, umbral: int = None):
    if umbral is None:
        cfg = await get_guild_config(ctx.guild.id)
        actual = cfg.get("pin_threshold", 0) or 0
        if actual == 0:
            desc = "El auto-pin está **desactivado** en este servidor."
        else:
            desc = f"El auto-pin está activado a partir de **{actual} 💀**."
        p = await get_formatted_prefix(ctx)
        embed = discord.Embed(
            title="📌 Auto-pin",
            description=f"{desc}\n\nUsa `{p}setuppin <número>` para configurar.\nUsa `{p}setuppin 0` para desactivar.",
            color=0x8b5cf6
        )
        return await ctx.send(embed=embed)

    if umbral < 0:
        embed = discord.Embed(title="❌ Número inválido", description="El umbral no puede ser negativo.", color=0xed4245)
        return await ctx.send(embed=embed)

    cfg = await get_guild_config(ctx.guild.id)
    min_skulls = cfg.get("min_skulls", 1)

    if umbral > 0 and umbral < min_skulls:
        embed = discord.Embed(
            title="❌ Umbral demasiado bajo",
            description=f"El umbral de auto-pin debe ser **mayor o igual al mínimo** del skullboard ({min_skulls} 💀).\n\nUsa un número ≥ {min_skulls} o `0` para desactivar.",
            color=0xed4245
        )
        return await ctx.send(embed=embed)

    await update_guild_config(ctx.guild.id, {"pin_threshold": umbral})
    if umbral == 0:
        embed = discord.Embed(
            title="📌 Auto-pin desactivado",
            description="Ya no se pinearán mensajes automáticamente en el skullboard.",
            color=0x4e5058
        )
    else:
        embed = discord.Embed(
            title="✅ Auto-pin configurado",
            description=f"Los mensajes con **{umbral}** o más 💀 se pinearán automáticamente.",
            color=0x57f287
        )
    await ctx.send(embed=embed)

async def _build_leaderboard_embed(guild: discord.Guild) -> discord.Embed:
    gid = str(guild.id)
    try:
        resp = await supabase.rpc("get_guild_leaderboard", {"p_guild_id": gid, "p_limit": 10}).execute()
    except Exception as e:
        logger.error(f"Error en RPC get_guild_leaderboard para guild {gid}: {e}")
        return discord.Embed(title="❌ Error", description="No se pudo obtener la clasificación.", color=0xed4245)

    if not resp.data:
        return discord.Embed(title="🏆 Top Usuarios", description="Aún no hay datos en el skullboard.", color=0x4e5058)

    medals = ["🥇", "🥈", "🥉"]
    lines  = []
    for i, row in enumerate(resp.data):
        pos   = medals[i] if i < 3 else f"{i+1}."
        name  = await resolve_display_name(guild, row.get("author_id"))
        total = row.get("total_skulls") or 0
        lines.append(f"{pos} **{name}** — **{total} 💀**")

    embed = discord.Embed(title="🏆 Top Usuarios — Skullboard", description="\n".join(lines), color=0xfaa61a)
    embed.set_footer(text=f"Top {len(resp.data)} usuarios por calaveras totales")
    return embed

@bot.command(name="leaderboard", aliases=["lb", "topusers"])
@commands.guild_only()
async def leaderboard_cmd(ctx):
    embed = await _build_leaderboard_embed(ctx.guild)
    await ctx.send(embed=embed)

async def _build_serverstats_embed(guild: discord.Guild) -> discord.Embed:
    gid = str(guild.id)
    try:
        resp = await supabase.rpc("get_guild_server_stats", {"p_guild_id": gid}).execute()
    except Exception as e:
        logger.error(f"Error en RPC get_guild_server_stats para guild {gid}: {e}")
        return discord.Embed(title="❌ Error", description="No se pudieron obtener las estadísticas del servidor.", color=0xed4245)

    if not resp.data or resp.data[0]["total_messages"] == 0:
        return discord.Embed(title="📊 Stats del Servidor", description="Aún no hay mensajes en el skullboard.", color=0x4e5058)

    stats = resp.data[0]
    total_msgs    = stats["total_messages"]
    total_skulls  = stats["total_skulls"]
    record_count  = stats["record_count"]
    top_author_id = stats["top_author_id"]
    top_skulls    = stats["top_author_skulls"]

    top_user_name = await resolve_display_name(guild, top_author_id) if top_author_id else "—"

    embed = discord.Embed(title=f"📊 Stats de {guild.name}", color=0x8b5cf6)
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    embed.add_field(name="📌 Mensajes en el board", value=f"{total_msgs:,}",    inline=True)
    embed.add_field(name="💀 Calaveras totales",     value=f"{total_skulls:,}",  inline=True)
    embed.add_field(name="🏆 Récord",                value=f"**{record_count} 💀**", inline=True)
    embed.add_field(name="👑 Usuario más reaccionado", value=f"{top_user_name} · **{top_skulls} 💀**", inline=False)
    embed.set_footer(text="Estadísticas globales del servidor")
    return embed

@bot.command(name="serverstats", aliases=["sstats", "server_stats"])
@commands.guild_only()
async def serverstats_cmd(ctx):
    embed = await _build_serverstats_embed(ctx.guild)
    await ctx.send(embed=embed)

# ─── Helper para top por periodo (snowflake timestamp & RPC) ──────────────────
def datetime_to_min_snowflake(dt: datetime) -> int:
    """Calcula el snowflake mínimo de Discord para mensajes creados a partir de dt."""
    timestamp_ms = int(dt.timestamp() * 1000)
    return max(0, (timestamp_ms - 1420070400000) << 22)

async def get_top_periodo(guild: discord.Guild, desde: datetime, titulo: str) -> discord.Embed:
    """Devuelve un embed con el top de mensajes en el período dado usando RPC y Snowflake."""
    gid = str(guild.id)
    min_snowflake = datetime_to_min_snowflake(desde)
    try:
        resp = await supabase.rpc("get_top_periodo", {
            "p_guild_id": gid,
            "p_min_snowflake": min_snowflake,
            "p_limit": 10
        }).execute()
    except Exception as e:
        logger.error(f"Error en get_top_periodo RPC para guild {gid}: {e}")
        return discord.Embed(title=titulo, description="No se pudo obtener el top para este período.", color=0xed4245)

    if not resp.data:
        return discord.Embed(title=titulo, description="No hay mensajes en este período.", color=0x4e5058)

    medals = ["🥇", "🥈", "🥉"]
    cfg    = await get_guild_config(guild.id)
    lines  = []
    for i, row in enumerate(resp.data):
        pos   = medals[i] if i < 3 else f"{i+1}."
        count = row.get("skull_count") or 0
        name  = await resolve_display_name(guild, row.get("author_id"))
        sb_id = row.get("skullboard_message_id")
        if cfg.get("skullboard_channel_id") and sb_id:
            link = f"https://discord.com/channels/{gid}/{cfg['skullboard_channel_id']}/{sb_id}"
            lines.append(f"{pos} **[{name}]({link})** — **{count} 💀**")
        else:
            lines.append(f"{pos} **{name}** — **{count} 💀**")

    embed = discord.Embed(title=titulo, description="\n".join(lines), color=0xfaa61a)
    embed.set_footer(text=f"Top {len(resp.data)} mensajes del período · {resp.data[0].get('skull_count', 0)} 💀 el récord del período")
    return embed

@bot.command(name="topmonth", aliases=["monthly", "top_month"])
@commands.guild_only()
async def topmonth_cmd(ctx):
    ahora = datetime.now(timezone.utc)
    desde = ahora.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    mes_nombre = SPANISH_MONTHS[ahora.month].capitalize()
    embed = await get_top_periodo(ctx.guild, desde, f"🏆 Top del mes — {mes_nombre} {ahora.year}")
    await ctx.send(embed=embed)

@bot.command(name="topyear", aliases=["yearly", "top_year"])
@commands.guild_only()
async def topyear_cmd(ctx):
    ahora = datetime.now(timezone.utc)
    desde = ahora.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    embed = await get_top_periodo(ctx.guild, desde, f"🏆 Top del año — {ahora.year}")
    await ctx.send(embed=embed)

# ─── Resync: deduplica el canal y reconcilia la BD con la realidad ────────────
# ─── Infraestructura de resync: rate limiter GLOBAL + locks por servidor ──────
class _GlobalRateLimiter:
    """Token-bucket compartido por TODOS los resync del proceso.

    Como el bot es un único proceso, aunque N servidores lancen /resync a la vez
    todas las llamadas pasan por este mismo limitador, de modo que el total
    agregado NUNCA supera `rate` llamadas/seg a la API de Discord. Así, con 1 o
    con 100 servidores simultáneos, jamás se dispara el rate limit global.
    """
    def __init__(self, rate_per_sec: float):
        self._interval = 1.0 / rate_per_sec
        self._lock = asyncio.Lock()
        self._next = 0.0

    async def acquire(self):
        async with self._lock:
            now   = asyncio.get_running_loop().time()
            start = self._next if self._next > now else now
            self._next = start + self._interval
            wait_for   = start - now
        if wait_for > 0:
            await asyncio.sleep(wait_for)

# 8 llamadas/seg TOTALES entre todos los resync (Discord permite ~50/seg global,
# así que dejamos amplio margen para la actividad normal del bot).
_resync_limiter = _GlobalRateLimiter(8)

def _progress_bar(done: int, total: int, width: int = 18) -> str:
    if total <= 0:
        return "▱" * width + "  0%"
    frac   = min(max(done / total, 0.0), 1.0)
    filled = int(frac * width)
    return "▰" * filled + "▱" * (width - filled) + f"  {done}/{total} ({int(frac * 100)}%)"

def _parse_repost_count(msg: discord.Message):
    """Extrae el número de 💀 que muestra actualmente un repost del skullboard."""
    m = re.search(r'\*\*(\d+)\*\*', msg.content or "")
    return int(m.group(1)) if m else None

def _resync_busy_embed() -> discord.Embed:
    return discord.Embed(
        title="⏳ Ya hay un resync en curso",
        description="Este servidor ya se está resincronizando. Espera a que termine antes de lanzar otro.",
        color=0xed4245
    )

async def _delete_rows_by_sb_id(gid: str, sb_id):
    """Borra de la BD cualquier fila que apunte a un repost concreto."""
    try:
        await supabase.table("tracked_messages").delete() \
            .eq("guild_id", gid).eq("skullboard_message_id", sb_id).execute()
    except Exception as e:
        logger.error(f"Error borrando fila por sb_id {sb_id} en guild {gid}: {e}")

async def _resync_guild(guild: discord.Guild, status_msg: Optional[discord.Message] = None) -> dict:
    gid           = str(guild.id)
    cfg           = await get_guild_config(guild.id)
    min_skulls    = cfg.get("min_skulls", 1)
    sb_channel_id = cfg.get("skullboard_channel_id")

    sb_chan = bot.get_channel(sb_channel_id) if sb_channel_id else None
    if sb_chan is None and sb_channel_id:
        try:
            sb_chan = await bot.fetch_channel(sb_channel_id)
        except Exception:
            pass

    res = {"originales": 0, "ya_correctos": 0, "sincronizados": 0,
           "duplicados_borrados": 0, "huerfanos_borrados": 0, "no_localizables": 0}
    if sb_chan is None:
        return res

    # ── Barra de progreso (edición muy espaciada para no añadir presión) ──
    _last_pb = 0.0
    async def _tick(done: int, total: int, fase: str = ""):
        nonlocal _last_pb
        if status_msg is None:
            return
        now = asyncio.get_running_loop().time()
        if done < total and (now - _last_pb) < 3.0:
            return  # throttle: como mucho un refresco cada 3s
        _last_pb = now
        embed = discord.Embed(
            title="🔄 Resincronizando el skullboard",
            description=f"`{_progress_bar(done, total)}`" + (f"\n{fase}" if fase else ""),
            color=0x8b5cf6
        )
        await _resync_limiter.acquire()
        try:
            await status_msg.edit(embed=embed)
        except Exception:
            pass

    # 1) Escanear el canal y agrupar reposts por mensaje original
    await _tick(0, 1, "📖 Leyendo el canal del skullboard...")
    grupos: dict[str, list] = {}
    async for sb_msg in sb_chan.history(limit=None):
        if sb_msg.author.id != bot.user.id: continue
        if not sb_msg.embeds: continue
        emb_str = str(sb_msg.embeds[0].to_dict())
        m = re.search(r'discord\.com/channels/(\d+)/(\d+)/(\d+)', emb_str)
        if not m: continue
        grupos.setdefault(m.group(3), []).append((sb_msg, int(m.group(2))))

    total = len(grupos)
    res["originales"] = total
    record = await get_guild_record(gid)

    done = 0
    for orig_msg_id, reposts in grupos.items():
        reposts.sort(key=lambda t: t[0].created_at, reverse=True)
        survivor, orig_chan_id = reposts[0]
        extras = reposts[1:]

        # Localizar el canal del mensaje original
        orig_chan = bot.get_channel(orig_chan_id)
        if orig_chan is None:
            try:
                await _resync_limiter.acquire()
                orig_chan = await bot.fetch_channel(orig_chan_id)
            except Exception:
                orig_chan = None
        if orig_chan is None:
            res["no_localizables"] += 1
            done += 1
            await _tick(done, total)
            continue

        # Recontar las 💀 reales del mensaje original
        confirmado_borrado = False
        real_count = None
        author_id  = None
        original   = None
        try:
            await _resync_limiter.acquire()
            original   = await orig_chan.fetch_message(int(orig_msg_id))
            skull_reac = next((r for r in original.reactions if str(r.emoji) == skull_emoji), None)
            real_count = skull_reac.count if skull_reac else 0
            author_id  = str(original.author.id)
        except discord.NotFound:
            confirmado_borrado = True
        except Exception:
            res["no_localizables"] += 1
            done += 1
            await _tick(done, total)
            continue

        # Original borrado (confirmado) → eliminar todos sus reposts y filas
        if confirmado_borrado:
            for rp, _ in reposts:
                try:
                    await _resync_limiter.acquire()
                    await rp.delete()
                except Exception:
                    pass
                await _delete_rows_by_sb_id(gid, rp.id)
            try:
                await supabase.table("tracked_messages").delete() \
                    .eq("message_id", orig_msg_id).eq("guild_id", gid).execute()
            except Exception:
                pass
            res["huerfanos_borrados"] += 1
            done += 1
            await _tick(done, total)
            continue

        # Borrar los reposts duplicados (queda solo el superviviente)
        for rp, _ in extras:
            try:
                await _resync_limiter.acquire()
                await rp.delete()
                res["duplicados_borrados"] += 1
            except Exception:
                pass
            await _delete_rows_by_sb_id(gid, rp.id)

        # Si ya está correcto (sin duplicados y con el conteo real) NO tocamos
        # nada: evita ediciones innecesarias, que son lo que dispara el rate limit.
        if not extras and _parse_repost_count(survivor) == real_count:
            res["ya_correctos"] += 1
            done += 1
            await _tick(done, total)
            continue

        # Reescribir el superviviente con el conteo real
        try:
            texto, embed = _build_repost(original, real_count, record, min_skulls)
            await _resync_limiter.acquire()
            await survivor.edit(content=texto, embed=embed)
        except Exception:
            pass
        try:
            await db_upsert("tracked_messages", {
                "message_id":            str(orig_msg_id),
                "skullboard_message_id": survivor.id,
                "skull_count":           real_count,
                "author_id":             author_id or "0",
                "guild_id":              gid,
            })
        except Exception:
            pass
        res["sincronizados"] += 1
        done += 1
        await _tick(done, total)

    _guild_record_cache.pop(gid, None)  # Invalida la caché del récord
    return res

def _resync_result_embed(res: dict) -> discord.Embed:
    return discord.Embed(
        title="✅ Resincronización completada",
        description=(
            f"📊 Mensajes únicos: **{res['originales']}**\n"
            f"✅ Ya estaban correctos: **{res['ya_correctos']}**\n"
            f"🔄 Sincronizados (conteo corregido): **{res['sincronizados']}**\n"
            f"🧹 Reposts duplicados eliminados: **{res['duplicados_borrados']}**\n"
            f"🗑️ Entradas obsoletas eliminadas (originales borrados): **{res['huerfanos_borrados']}**"
        ),
        color=0x57f287
    )

@bot.command(name="resync", aliases=["sync"])
@commands.guild_only()
@commands.has_permissions(administrator=True)
async def resync_cmd(ctx):
    cfg = await get_guild_config(ctx.guild.id)
    if not cfg.get("skullboard_channel_id"):
        return await ctx.send(embed=discord.Embed(
            title="❌ Sin canal configurado",
            description="Configura primero el canal del skullboard con `set_channel`.",
            color=0xed4245
        ))
    gid  = str(ctx.guild.id)
    async with await _resync_locks.acquire(gid):
        status = await ctx.send(embed=discord.Embed(
            title="🔄 Resincronizando el skullboard",
            description=f"`{_progress_bar(0, 1)}`\n📖 Preparando...",
            color=0x8b5cf6
        ))
        res = await _resync_guild(ctx.guild, status)
        await status.edit(embed=_resync_result_embed(res))

# ─── Comandos privados del owner (BACKFILL IDs PURAS - 1 a 1) ─────────────────────────
@bot.command(name="backfill", hidden=True)
@commands.guild_only()
async def backfill_cmd(ctx):
    if await _deny_if_not_owner(ctx):
        return

    gid = str(ctx.guild.id)
    async with await _resync_locks.acquire(gid):
        cfg = await get_guild_config(ctx.guild.id)
        sb_channel_id = cfg.get("skullboard_channel_id")

        if not sb_channel_id:
            return await ctx.send(embed=discord.Embed(
                title="❌ Error", description="No hay canal skullboard configurado en este servidor.", color=0xed4245
            ))

        channel = bot.get_channel(sb_channel_id)
        if not channel:
            try:
                channel = await bot.fetch_channel(sb_channel_id)
            except Exception:
                channel = None
        if not channel:
            return await ctx.send(embed=discord.Embed(
                title="❌ Error", description="No se encontró el canal skullboard.", color=0xed4245
            ))

        msg_status = await ctx.send(embed=discord.Embed(
            title="⏳ Paso 1/3 — Recopilando enlaces...",
            description="Buscando los enlaces de todos los mensajes en el canal...",
            color=0x8b5cf6
        ))

        enlaces = {}
        leidos = 0

        # PASO 1: Extraer solo los enlaces de los mensajes del board
        async for sb_msg in channel.history(limit=None, oldest_first=False):
            if not sb_msg.author.bot: continue 
            if not sb_msg.embeds: continue

            emb = sb_msg.embeds[0]
            embed_str = str(emb.to_dict())
            
            match_msg = re.search(r'discord\.com/channels/\d+/(\d+)/(\d+)', embed_str)
            if match_msg:
                orig_chan_id = int(match_msg.group(1))
                orig_msg_id = match_msg.group(2)
                
                count = 0
                nums = re.findall(r'\d+', sb_msg.content)
                if nums: count = int(nums[0])
                
                fallback_author = None
                if emb.author and emb.author.icon_url:
                    match_auth = re.search(r'(?:avatars|users)/(\d+)/', str(emb.author.icon_url))
                    if match_auth: fallback_author = match_auth.group(1)

                enlaces[orig_msg_id] = {
                    "sb_msg_id": str(sb_msg.id),
                    "orig_chan_id": orig_chan_id,
                    "count_fallback": count,
                    "author_fallback": fallback_author
                }
            leidos += 1

        await msg_status.edit(embed=discord.Embed(
            title="⏳ Paso 2/3 — Obteniendo IDs Puras...",
            description=f"Se extrajeron {len(enlaces)} enlaces.\nVisitando los mensajes originales para sacar la ID real... ☕ (Iremos lento para que Discord no nos bloquee)",
            color=0x8b5cf6
        ))

        registros_dict = {}
        procesados = 0
        errores_borrados = 0

        # PASO 2: Fetch seguro
        for orig_msg_id, data in enlaces.items():
            author_id = data["author_fallback"]
            count = data["count_fallback"]
            
            try:
                orig_chan = bot.get_channel(data["orig_chan_id"])
                if orig_chan is None:
                    orig_chan = await bot.fetch_channel(data["orig_chan_id"])
                if orig_chan:
                    orig_msg = await orig_chan.fetch_message(int(orig_msg_id))
                    author_id = str(orig_msg.author.id)
                    
                    skull_reac = next((r for r in orig_msg.reactions if str(r.emoji) == skull_emoji), None)
                    if skull_reac: count = skull_reac.count
            except discord.NotFound:
                errores_borrados += 1
            except Exception:
                pass
            
            if author_id:
                if orig_msg_id in registros_dict:
                    if count > registros_dict[orig_msg_id]["skull_count"]:
                        registros_dict[orig_msg_id]["skull_count"] = count
                        registros_dict[orig_msg_id]["skullboard_message_id"] = data["sb_msg_id"]
                else:
                    registros_dict[orig_msg_id] = {
                        "message_id": str(orig_msg_id),
                        "skullboard_message_id": data["sb_msg_id"],
                        "skull_count": count,
                        "author_id": str(author_id),
                        "guild_id": gid
                    }

            procesados += 1
            if procesados % 30 == 0:
                await msg_status.edit(embed=discord.Embed(
                    title="⏳ Paso 2/3 — Obteniendo IDs Puras...",
                    description=f"Progreso: **{procesados}/{len(enlaces)}** mensajes procesados...",
                    color=0x8b5cf6
                ))
            
            await asyncio.sleep(0.5)

        registros_a_subir = list(registros_dict.values())

        await msg_status.edit(embed=discord.Embed(
            title="⏳ Paso 3/3 — Subiendo a BD...",
            description=f"Guardando **{len(registros_a_subir)}** IDs en Supabase por lotes optimizados...",
            color=0x8b5cf6
        ))

        # PASO 3: Subir a Supabase en Lotes de 100 (Atómico y 100x más rápido)
        exitosos = 0
        errores_db = 0
        BATCH_SIZE = 100
        for i in range(0, len(registros_a_subir), BATCH_SIZE):
            lote = registros_a_subir[i:i + BATCH_SIZE]
            try:
                await supabase.table("tracked_messages").upsert(lote).execute()
                exitosos += len(lote)
            except Exception as e:
                logger.error(f"Error subiendo lote de backfill ({i}-{i+len(lote)}): {e}")
                errores_db += len(lote)
            await asyncio.sleep(0.1)

        _guild_record_cache.pop(gid, None)  # Invalidate record cache
        await msg_status.edit(embed=discord.Embed(
            title="✅ Backfill de IDs Completado",
            description=(
                f"📖 Mensajes leídos: **{leidos}**\n"
                f"🛡️ Guardados con éxito: **{exitosos}**\n"
                f"⚠️ Originales borrados (usado fallback): **{errores_borrados}**\n"
                f"❌ Conflictos de BD ignorados: **{errores_db}**\n\n"
                "**¡Listo! Base de datos limpia y asignada a las IDs inmutables.**"
            ),
            color=0x57f287
        ))
    
def _build_announce_embed() -> discord.Embed:
    return discord.Embed(
        title="💀 SkullBoard — Actualización",
        description=(
            "¡Se ha pulido el bot por dentro! Estos son los cambios de esta versión:\n\n"
            "**🔧 Correcciones**\n"
            "• Los conteos de 💀 ahora se mantienen **sincronizados** con la realidad: "
            "se acabaron los números desactualizados en `/top`, `/stats` y `/leaderboard`.\n"
            "• Eliminados los **mensajes duplicados** que a veces aparecían repetidos en el skullboard.\n"
            "• El botón **«Saltar al mejor mensaje»** ahora te lleva siempre al mensaje correcto.\n\n"
            "**✨ Nuevo para administradores**\n"
            "• `/resync` (o `sk!resync`) — recuenta las 💀 reales de todos los mensajes, "
            "borra duplicados y corrige cualquier descuadre de golpe.\n\n"
            "**🔒 Permisos**\n"
            "• `sk!reset` ahora **solo puede usarlo el propietario del servidor**.\n\n"
            "Usa `/help` o `sk!help` para ver todos los comandos. ¡Gracias por usar SkullBoard! 💀"
        ),
        color=0x8b5cf6
    )

@bot.command(name="announce", hidden=True)
async def announce_cmd(ctx):
    if await _deny_if_not_owner(ctx):
        return

    embed = _build_announce_embed()

    enviados = 0
    fallidos = 0

    for guild in bot.guilds:
        canal = None
        try:
            cfg = await get_guild_config(guild.id)
            cid = cfg.get("skullboard_channel_id", 0)
            if cid:
                canal = bot.get_channel(cid)
                if canal is None:
                    canal = await bot.fetch_channel(cid)
        except Exception:
            pass
        if not canal:
            canal = guild.system_channel
        if canal:
            try:
                await canal.send(embed=embed)
                enviados += 1
                await asyncio.sleep(1)
            except Exception:
                fallidos += 1
        else:
            fallidos += 1

    resultado = discord.Embed(
        title="📊 Anuncio enviado",
        description=f"✅ Enviado: **{enviados}** servidores\n❌ Sin canal: **{fallidos}** servidores",
        color=0x57f287
    )
    await ctx.send(embed=resultado)

@bot.command(name="editannounce", hidden=True)
async def editannounce_cmd(ctx):
    if await _deny_if_not_owner(ctx):
        return

    nuevo_embed = _build_announce_embed()

    editados = 0
    fallidos = 0

    for guild in bot.guilds:
        canal = None
        try:
            cfg = await get_guild_config(guild.id)
            cid = cfg.get("skullboard_channel_id", 0)
            if cid:
                canal = bot.get_channel(cid)
                if canal is None:
                    canal = await bot.fetch_channel(cid)
        except Exception:
            pass
        if not canal:
            canal = guild.system_channel
        if not canal:
            fallidos += 1
            continue

        try:
            encontrado = False
            async for msg in canal.history(limit=50):
                if msg.author.id == bot.user.id and msg.embeds:
                    titulo = msg.embeds[0].title or ""
                    if "Novedades" in titulo or "SkullBoard" in titulo:
                        await msg.edit(embed=nuevo_embed)
                        editados += 1
                        encontrado = True
                        break
            if not encontrado:
                fallidos += 1
            await asyncio.sleep(0.5)
        except Exception:
            fallidos += 1

    resultado = discord.Embed(
        title="📊 Anuncio editado",
        description=f"✅ Editados: **{editados}** servidores\n❌ No encontrado/error: **{fallidos}** servidores",
        color=0x57f287
    )
    await ctx.send(embed=resultado)

@bot.command(name="servers", hidden=True)
async def servers_cmd(ctx):
    if await _deny_if_not_owner(ctx):
        return
    total = len(bot.guilds)
    texto = "\n".join(f"• {g.name} (`{g.id}`)" for g in bot.guilds)
    if len(texto) > 1900:
        texto = texto[:1900] + "\n... (truncado)"
    embed = discord.Embed(title=f"🌍 El bot está en {total} servidores:", description=texto, color=0xfaa61a)
    await ctx.send(embed=embed)

@bot.command(name="serverinfo", hidden=True)
async def serverinfo_cmd(ctx, guild_id: int = None):
    if await _deny_if_not_owner(ctx):
        return
    if not guild_id:
        embed = discord.Embed(title="❌ Falta el ID", description=f"Usa `{await get_formatted_prefix(ctx)}serverinfo <ID>`", color=0xed4245)
        return await ctx.send(embed=embed)
    guild = bot.get_guild(guild_id)
    if not guild:
        embed = discord.Embed(title="❌ Servidor no encontrado", description="El bot no está en ningún servidor con ese ID.", color=0xed4245)
        return await ctx.send(embed=embed)

    cfg = await get_guild_config(guild.id)
    gid = str(guild.id)

    try:
        resp = await supabase.table("tracked_messages").select("message_id", count="exact").eq("guild_id", gid).execute()
        msg_count = resp.count if resp.count else 0
    except Exception as e:
        logger.error(f"Error en serverinfo_cmd para guild {gid}: {e}")
        msg_count = 0

    owner = guild.owner
    if not owner and guild.owner_id:
        try:
            owner = await bot.fetch_user(guild.owner_id)
        except Exception:
            owner = None
    created = guild.created_at.strftime("%d/%m/%Y")

    embed = discord.Embed(title=guild.name, color=0xfaa61a)
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    embed.add_field(name="🆔 ID",         value=f"`{guild.id}`",                                          inline=False)
    embed.add_field(name="👑 Owner",       value=f"{owner} (`{owner.id}`)" if owner else "Desconocido",   inline=False)
    embed.add_field(name="👥 Miembros",    value=str(guild.member_count),                                 inline=False)
    embed.add_field(name="📅 Creado",      value=created,                                                 inline=False)
    embed.add_field(name="💀 Skullboard",  value=f"{msg_count} mensajes · mínimo {cfg['min_skulls']} 💀", inline=False)
    embed.set_footer(text="Información del servidor")
    await ctx.send(embed=embed)

# ─── SLASH COMMANDS ───────────────────────────────────────────────────────────
@tree.command(name="ajustes", description="Ver configuración del bot")
async def ajustes_slash(interaction: discord.Interaction):
    embed = await build_ajustes_embed(interaction.guild.id)
    await interaction.response.send_message(embed=embed)

@tree.command(name="prefix", description="Cambiar prefijo (admin)")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(nuevo_prefijo="Prefijo nuevo")
async def prefix_slash(interaction: discord.Interaction, nuevo_prefijo: str):
    if not await _is_admin_or_deny(interaction):
        return
    valido, res = _validate_prefix(nuevo_prefijo)
    if not valido:
        embed = discord.Embed(title="❌ Prefijo inválido", description=res, color=0xed4245)
        return await interaction.response.send_message(embed=embed, ephemeral=True)
    await update_guild_config(interaction.guild.id, {"prefix": res})
    _prefix_cache.pop(str(interaction.guild.id), None)
    embed = discord.Embed(title="✅ Prefijo actualizado", description=f"Ahora puedes usar comandos con `{res}`", color=0x57f287)
    await interaction.response.send_message(embed=embed)

@tree.command(name="set_channel", description="Configura el canal del SkullBoard (admin)")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(channel="Canal donde se enviarán los mensajes del SkullBoard")
async def set_channel_slash(interaction: discord.Interaction, channel: discord.TextChannel):
    if not await _is_admin_or_deny(interaction):
        return
    await update_guild_config(interaction.guild.id, {"skullboard_channel_id": channel.id})
    embed = discord.Embed(title="✅ Canal configurado", description=f"Los mensajes se enviarán a {channel.mention}", color=0x57f287)
    await interaction.response.send_message(embed=embed)

@tree.command(name="set_min", description="Fija el mínimo de reacciones 💀 (admin)")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(cantidad="Número mínimo de reacciones para destacar un mensaje (≥ 1)")
async def set_min_slash(interaction: discord.Interaction, cantidad: int):
    if not await _is_admin_or_deny(interaction):
        return
    if cantidad < 1:
        embed = discord.Embed(title="❌ Número inválido", description="El mínimo debe ser ≥ 1.", color=0xed4245)
        return await interaction.response.send_message(embed=embed, ephemeral=True)
    await update_guild_config(interaction.guild.id, {"min_skulls": cantidad})
    embed = discord.Embed(title="✅ Meta establecida", description=f"Se necesitan **{cantidad}** reacciones 💀 para destacar un mensaje.", color=0x57f287)
    await interaction.response.send_message(embed=embed)

@tree.command(name="ping", description="Ver latencia")
async def ping_slash(interaction: discord.Interaction):
    ms    = round(bot.latency * 1000)
    embed = discord.Embed(title="🏓 Pong!", color=0x8b5cf6)
    embed.add_field(name="⚡ Latencia", value=f"**{ms}ms**", inline=True)
    embed.add_field(name="📡 Estado",   value=ping_estado(ms),  inline=True)
    await interaction.response.send_message(embed=embed)

@tree.command(name="invite", description="Invita al bot")
async def invite_slash(interaction: discord.Interaction):
    embed = discord.Embed(title="💀 SkullBoard", description="Añade este bot a tu servidor y ¡disfruta!", color=0x8b5cf6)
    embed.add_field(name="🔗 Invitar al servidor", value=f"[Haz click aquí para invitarme]({get_invite_url()})", inline=False)
    embed.set_footer(text=f"Más de {len(bot.guilds)} servidores confían en SkullBoard")
    await interaction.response.send_message(embed=embed)

@tree.command(name="dashboard", description="Enlace a la web oficial y recursos de SkullBoard")
async def dashboard_slash(interaction: discord.Interaction):
    embed = build_dashboard_embed()
    view  = DashboardView()
    await interaction.response.send_message(embed=embed, view=view)

@tree.command(name="help", description="Muestra los comandos disponibles del bot")
async def help_slash(interaction: discord.Interaction):
    pages = build_slash_help_pages()
    view  = HelpView(pages)
    await interaction.response.send_message(embed=pages[0], view=view)
    try:
        view.message = await interaction.original_response()
    except Exception:
        pass

@tree.command(name="top", description="Top mensajes más reaccionados del servidor")
async def top_slash(interaction: discord.Interaction):
    await interaction.response.defer()
    gid = str(interaction.guild.id)
    try:
        resp = await supabase.table("tracked_messages") \
            .select("skull_count,author_id,skullboard_message_id") \
            .eq("guild_id", gid).order("skull_count", desc=True).limit(10).execute()
    except Exception as e:
        logger.error(f"Error en /top: {e}")
        embed = discord.Embed(title="❌ Error", description="No se pudo obtener el top.", color=0xed4245)
        return await interaction.followup.send(embed=embed)

    if not resp.data:
        embed = discord.Embed(title="🏆 Top Skullboard", description="Aún no hay mensajes en el skullboard.", color=0x4e5058)
        return await interaction.followup.send(embed=embed)

    medals = ["🥇", "🥈", "🥉"]
    cfg    = await get_guild_config(interaction.guild.id)
    lines  = []
    for i, row in enumerate(resp.data):
        pos   = medals[i] if i < 3 else f"{i+1}."
        count = row.get("skull_count") or 0
        name  = await resolve_display_name(interaction.guild, row.get("author_id"))
        sb_id = row.get("skullboard_message_id")
        if cfg.get("skullboard_channel_id") and sb_id:
            link = f"https://discord.com/channels/{gid}/{cfg['skullboard_channel_id']}/{sb_id}"
            lines.append(f"{pos} **[{name}]({link})** — **{count} 💀**")
        else:
            lines.append(f"{pos} **{name}** — **{count} 💀**")

    embed = discord.Embed(title="🏆 Top Skullboard", description="\n".join(lines), color=0xfaa61a)
    embed.set_footer(text=f"Top {len(resp.data)} mensajes del servidor")
    await interaction.followup.send(embed=embed)

@tree.command(name="random", description="Muestra un mensaje aleatorio del skullboard")
async def random_slash(interaction: discord.Interaction):
    await interaction.response.defer()
    content, embed = await _handle_random_message(interaction.guild)
    if content:
        await interaction.followup.send(content=content, embed=embed)
    else:
        await interaction.followup.send(embed=embed)

async def _stats_embed(guild: discord.Guild, member: discord.Member) -> discord.Embed:
    """Embed de estadísticas de un usuario. Compartido por sk!stats y /stats."""
    gid = str(guild.id)
    uid = str(member.id)
    try:
        resp = await supabase.rpc("get_guild_user_stats", {"p_guild_id": gid, "p_author_id": uid}).execute()
    except Exception as e:
        logger.error(f"Error en RPC get_guild_user_stats para {uid} en guild {gid}: {e}")
        return discord.Embed(title="❌ Error", description="No se pudieron obtener las estadísticas.", color=0xed4245)

    if not resp.data or resp.data[0].get("total_messages", 0) == 0:
        return discord.Embed(
            title=f"📊 Stats de {member.display_name}",
            description="Este usuario no tiene ningún mensaje en el skullboard.",
            color=0x4e5058
        )

    stats        = resp.data[0]
    total_msgs   = stats.get("total_messages") or 0
    total_skulls = stats.get("total_skulls") or 0
    best_count   = stats.get("record_count") or 0
    best_sb_id   = stats.get("best_skullboard_message_id")
    cfg          = await get_guild_config(guild.id)
    link         = None
    if best_sb_id and cfg.get("skullboard_channel_id"):
        link = f"https://discord.com/channels/{gid}/{cfg['skullboard_channel_id']}/{best_sb_id}"

    embed = discord.Embed(title=f"📊 Stats de {member.display_name}", color=0x8b5cf6)
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="📌 Mensajes en el board",        value=str(total_msgs),    inline=False)
    embed.add_field(name="💀 Calaveras totales recibidas",  value=str(total_skulls),  inline=False)
    embed.add_field(name="🏆 Récord personal",              value=f"{best_count} 💀", inline=False)
    if link:
        embed.add_field(name="🔗 Mejor mensaje", value=f"[Saltar al mensaje]({link})", inline=False)
    embed.set_footer(text=f"Estadísticas de {member.display_name} en este servidor")
    return embed

@tree.command(name="stats", description="Estadísticas de un usuario en el skullboard")
@app_commands.describe(usuario="Usuario del que ver las estadísticas")
async def stats_slash(interaction: discord.Interaction, usuario: discord.Member = None):
    await interaction.response.defer()
    member = usuario or interaction.user
    embed  = await _stats_embed(interaction.guild, member)
    await interaction.followup.send(embed=embed)

@tree.command(name="ignore", description="Ignora un canal (admin)")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(canal="Canal a ignorar")
async def ignore_slash(interaction: discord.Interaction, canal: discord.TextChannel):
    if not await _is_admin_or_deny(interaction):
        return
    await add_ignored_channel(str(interaction.guild.id), str(canal.id))
    embed = discord.Embed(title="🚫 Canal ignorado", description=f"Los mensajes de {canal.mention} ya no podrán llegar al skullboard.", color=0x57f287)
    await interaction.response.send_message(embed=embed)

@tree.command(name="unignore", description="Deja de ignorar un canal (admin)")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(canal="Canal a desbloquear")
async def unignore_slash(interaction: discord.Interaction, canal: discord.TextChannel):
    if not await _is_admin_or_deny(interaction):
        return
    await remove_ignored_channel(str(interaction.guild.id), str(canal.id))
    embed = discord.Embed(title="✅ Canal desbloqueado", description=f"Los mensajes de {canal.mention} ya pueden llegar al skullboard.", color=0x57f287)
    await interaction.response.send_message(embed=embed)

@tree.command(name="ignored", description="Ver canales ignorados del servidor")
async def ignored_slash(interaction: discord.Interaction):
    gid      = str(interaction.guild.id)
    channels = await get_ignored_channels(gid)
    if not channels:
        embed = discord.Embed(title="🚫 Canales ignorados", description="No hay ningún canal ignorado en este servidor.", color=0x4e5058)
        return await interaction.response.send_message(embed=embed)
    lines = [f"🔇 {bot.get_channel(int(c)).mention if bot.get_channel(int(c)) else f'`{c}`'}" for c in channels]
    embed = discord.Embed(title="🚫 Canales ignorados", description="\n".join(lines), color=0x8b5cf6)
    embed.set_footer(text=f"{len(channels)} canal(es) ignorado(s) · Usa /unignore para desbloquear")
    await interaction.response.send_message(embed=embed)

@tree.command(name="notify", description="Activa o desactiva las notificaciones por DM del skullboard")
@app_commands.describe(estado="Activa (on) o desactiva (off) tus notificaciones en este servidor")
@app_commands.choices(estado=[
    app_commands.Choice(name="on",  value="on"),
    app_commands.Choice(name="off", value="off"),
])
async def notify_slash(interaction: discord.Interaction, estado: app_commands.Choice[str] = None):
    if estado is None:
        enabled = is_notify_enabled(interaction.guild.id, interaction.user.id)
        actual  = "🔔 Activadas" if enabled else "🔕 Desactivadas"
        embed = discord.Embed(
            title="📬 Notificaciones del Skullboard",
            description=(
                f"Tus notificaciones en este servidor están: **{actual}**\n\n"
                "Usa `/notify on` o `/notify off` para cambiarlo."
            ),
            color=0x8b5cf6
        )
        return await interaction.response.send_message(embed=embed, ephemeral=True)

    enable = estado.value == "on"
    await set_notify(interaction.guild.id, interaction.user.id, enable)
    if enable:
        embed = discord.Embed(
            title="🔔 Notificaciones activadas",
            description=f"Recibirás un MD cuando un mensaje tuyo llegue al skullboard de **{interaction.guild.name}**.",
            color=0x57f287
        )
    else:
        embed = discord.Embed(
            title="🔕 Notificaciones desactivadas",
            description=f"No recibirás más MDs del skullboard de **{interaction.guild.name}**.",
            color=0x4e5058
        )
    await interaction.response.send_message(embed=embed, ephemeral=True)

@tree.command(name="setup_pin", description="Configura el auto-pin de mensajes (admin)")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(umbral="Mínimo de 💀 para pinear automáticamente. 0 = desactivado")
async def setup_pin_slash(interaction: discord.Interaction, umbral: int):
    if not await _is_admin_or_deny(interaction):
        return

    if umbral < 0:
        embed = discord.Embed(title="❌ Número inválido", description="El umbral no puede ser negativo.", color=0xed4245)
        return await interaction.response.send_message(embed=embed, ephemeral=True)

    cfg = await get_guild_config(interaction.guild.id)
    min_skulls = cfg.get("min_skulls", 1)

    if umbral > 0 and umbral < min_skulls:
        embed = discord.Embed(
            title="❌ Umbral demasiado bajo",
            description=f"El umbral de auto-pin debe ser **mayor o igual al mínimo** del skullboard ({min_skulls} 💀).\n\nUsa un número ≥ {min_skulls} o `0` para desactivar.",
            color=0xed4245
        )
        return await interaction.response.send_message(embed=embed, ephemeral=True)

    await update_guild_config(interaction.guild.id, {"pin_threshold": umbral})
    if umbral == 0:
        embed = discord.Embed(
            title="📌 Auto-pin desactivado",
            description="Ya no se pinearán mensajes automáticamente en el skullboard.",
            color=0x4e5058
        )
    else:
        embed = discord.Embed(
            title="✅ Auto-pin configurado",
            description=f"Los mensajes con **{umbral}** o más 💀 se pinearán automáticamente.",
            color=0x57f287
        )
    await interaction.response.send_message(embed=embed)

@tree.command(name="leaderboard", description="Top usuarios con más calaveras totales del servidor")
async def leaderboard_slash(interaction: discord.Interaction):
    await interaction.response.defer()
    embed = await _build_leaderboard_embed(interaction.guild)
    await interaction.followup.send(embed=embed)

@tree.command(name="server_stats", description="Estadísticas globales del skullboard del servidor")
async def server_stats_slash(interaction: discord.Interaction):
    await interaction.response.defer()
    embed = await _build_serverstats_embed(interaction.guild)
    await interaction.followup.send(embed=embed)

@tree.command(name="top_month", description="Top mensajes más reaccionados del mes actual")
async def top_month_slash(interaction: discord.Interaction):
    await interaction.response.defer()
    ahora = datetime.now(timezone.utc)
    desde = ahora.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    mes_nombre = SPANISH_MONTHS[ahora.month].capitalize()
    embed = await get_top_periodo(interaction.guild, desde, f"🏆 Top del mes — {mes_nombre} {ahora.year}")
    await interaction.followup.send(embed=embed)

@tree.command(name="top_year", description="Top mensajes más reaccionados del año actual")
async def top_year_slash(interaction: discord.Interaction):
    await interaction.response.defer()
    ahora = datetime.now(timezone.utc)
    desde = ahora.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    embed = await get_top_periodo(interaction.guild, desde, f"🏆 Top del año — {ahora.year}")
    await interaction.followup.send(embed=embed)

@tree.command(name="resync", description="Resincroniza los conteos de 💀 con la realidad (admin)")
@app_commands.default_permissions(administrator=True)
async def resync_slash(interaction: discord.Interaction):
    if not await _is_admin_or_deny(interaction):
        return
    cfg = await get_guild_config(interaction.guild.id)
    if not cfg.get("skullboard_channel_id"):
        return await interaction.response.send_message(embed=discord.Embed(
            title="❌ Sin canal configurado",
            description="Configura primero el canal del skullboard con `/set_channel`.",
            color=0xed4245
        ), ephemeral=True)
    gid = str(interaction.guild.id)
    async with await _resync_locks.acquire(gid):
        await interaction.response.defer()
        status = await interaction.followup.send(embed=discord.Embed(
            title="🔄 Resincronizando el skullboard",
            description=f"`{_progress_bar(0, 1)}`\n📖 Preparando...",
            color=0x8b5cf6
        ))
        res = await _resync_guild(interaction.guild, status)
        await status.edit(embed=_resync_result_embed(res))

@tree.command(name="reset", description="Resetea el skullboard del servidor (solo el propietario)")
@app_commands.default_permissions(administrator=True)
async def reset_slash(interaction: discord.Interaction):
    if interaction.user.id != interaction.guild.owner_id:
        embed = discord.Embed(
            title="❌ Solo el propietario del servidor",
            description="Únicamente el **propietario del servidor** puede usar este comando.",
            color=0xed4245
        )
        return await interaction.response.send_message(embed=embed, ephemeral=True)

    class ConfirmResetView(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=30)
            self.confirmed = False

        @discord.ui.button(label="CONFIRMAR RESET", style=discord.ButtonStyle.danger)
        async def confirm_btn(self, btn_interaction: discord.Interaction, button: discord.ui.Button):
            if btn_interaction.user.id != interaction.user.id:
                return await btn_interaction.response.send_message("Solo el propietario puede confirmar.", ephemeral=True)
            self.confirmed = True
            self.stop()
            gid = str(interaction.guild.id)
            try:
                resp = await supabase.table("tracked_messages").delete().eq("guild_id", gid).execute()
                deleted = len(resp.data) if resp.data else 0
                _guild_record_cache.pop(gid, None)
                embed = discord.Embed(
                    title="✅ Skullboard reseteado",
                    description=(
                        f"Se han eliminado **{deleted} mensajes** del registro. El skullboard empieza de cero.\n\n"
                        "ℹ️ Los mensajes ya publicados en el canal del skullboard **no se borran**. "
                        "Si quieres empezar de cero del todo, vacía también ese canal — "
                        "si no, un `/resync` los volvería a importar."
                    ),
                    color=0x57f287
                )
                await btn_interaction.response.edit_message(embed=embed, view=None)
            except Exception as e:
                logger.error(f"Error reseteando tracked_messages en /reset para guild {gid}: {e}")
                embed = discord.Embed(title="❌ Error", description="No se pudo resetear la base de datos.", color=0xed4245)
                await btn_interaction.response.edit_message(embed=embed, view=None)

        @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.secondary)
        async def cancel_btn(self, btn_interaction: discord.Interaction, button: discord.ui.Button):
            self.stop()
            embed = discord.Embed(title="❌ Reset cancelado", description="No se ha realizado ningún cambio.", color=0x4e5058)
            await btn_interaction.response.edit_message(embed=embed, view=None)

        async def on_timeout(self):
            pass

    embed_warn = discord.Embed(
        title="⚠️ ¿Estás seguro?",
        description=(
            "Esto borrará **todos los mensajes** del skullboard de este servidor.\n"
            "Esta acción **no se puede deshacer**.\n\n"
            "Pulsa **CONFIRMAR RESET** para continuar. Tienes **30 segundos**."
        ),
        color=0xed4245
    )
    view = ConfirmResetView()
    await interaction.response.send_message(embed=embed_warn, view=view, ephemeral=True)

# ─── Eventos de Sharding y Conectividad ────────────────────────────────────────
@bot.event
async def on_shard_disconnect(shard_id: int):
    logger.warning(f"⚠️ Shard #{shard_id} desconectado de la Gateway")
    await send_system_alert(
        title=f"Shard #{shard_id} Desconectado",
        description=f"El shard #{shard_id} ha perdido conexión con la Gateway de Discord.",
        level="WARNING",
        extra_fields=[
            {"name": "Shard ID", "value": str(shard_id), "inline": True},
            {"name": "Total Shards", "value": str(bot.shard_count or "Desconocido"), "inline": True}
        ]
    )

# ─── Manejo de errores global ─────────────────────────────────────────────────
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.NoPrivateMessage):
        return
    if isinstance(error, commands.MissingPermissions):
        embed = discord.Embed(title="❌ Sin permisos", description="Necesitas permisos de **Administrador** para usar este comando.", color=0xed4245)
        return await ctx.send(embed=embed)
    if isinstance(error, commands.BadArgument):
        embed = discord.Embed(title="❌ Argumento inválido", description="Comprueba los parámetros del comando.", color=0xed4245)
        return await ctx.send(embed=embed)
    if isinstance(error, commands.MissingRequiredArgument):
        p     = await get_formatted_prefix(ctx)
        embed = discord.Embed(title="❌ Faltan argumentos", description=f"Usa `{p}help` para ver el uso correcto.", color=0xed4245)
        return await ctx.send(embed=embed)
    if isinstance(error, commands.CommandNotFound):
        try: await ctx.message.add_reaction("❓")
        except: pass
        return
    logger.error(f"Error en comando de texto: {error}", exc_info=error)
    try:
        tb = "".join(traceback.format_exception(type(error), error, error.__traceback__))
    except Exception:
        tb = str(error)
    await send_system_alert(
        title=f"Error en comando: `{ctx.command}`",
        description=f"```{tb[:1900]}```",
        level="ERROR",
        extra_fields=[
            {"name": "Servidor", "value": f"{ctx.guild.name} (`{ctx.guild.id}`)" if ctx.guild else "DM", "inline": True},
            {"name": "Canal", "value": f"{ctx.channel.name} (`{ctx.channel.id}`)" if hasattr(ctx.channel, "name") else "DM", "inline": True},
            {"name": "Autor", "value": f"{ctx.author} (`{ctx.author.id}`)", "inline": True}
        ]
    )

@tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    # Mensaje genérico al usuario (no filtramos str(error): puede exponer
    # rutas o estado interno). El detalle completo va al log.
    embed = discord.Embed(
        title="❌ Ha ocurrido un error",
        description="Algo ha fallado al ejecutar el comando. Inténtalo de nuevo más tarde.",
        color=0xed4245
    )
    try:
        if not interaction.response.is_done():
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            await interaction.followup.send(embed=embed, ephemeral=True)
    except Exception:
        pass
    logger.error(f"Error en slash command: {error}", exc_info=error)
    cmd_name = interaction.command.name if interaction.command else "desconocido"
    try:
        tb = "".join(traceback.format_exception(type(error), error, error.__traceback__))
    except Exception:
        tb = str(error)
    await send_system_alert(
        title=f"Error en Slash Command: `/{cmd_name}`",
        description=f"```{tb[:1900]}```",
        level="ERROR",
        extra_fields=[
            {"name": "Servidor", "value": f"{interaction.guild.name} (`{interaction.guild.id}`)" if interaction.guild else "DM", "inline": True},
            {"name": "Usuario", "value": f"{interaction.user} (`{interaction.user.id}`)", "inline": True}
        ]
    )

# ─── Ejecución Resiliente con Protección contra 429 / Cloudflare ────────────
def _reset_bot_session():
    """Limpia el estado interno y el conector HTTP cerrado para permitir reintentos limpios."""
    bot._closing_task = None
    bot.http.connector = discord.utils.MISSING
    bot.loop = asyncio.get_running_loop()
    if hasattr(bot, "_ready") and bot._ready is not discord.utils.MISSING:
        bot._ready.clear()

async def main_runner():
    """Ejecutor asíncrono con reintentos y backoff ante bloqueos temporales de IP (Cloudflare 1015 / 429)."""
    delay = 30
    while True:
        try:
            _reset_bot_session()
            async with bot:
                await bot.start(DISCORD_TOKEN)
            break
        except discord.HTTPException as e:
            if e.status == 429:
                logger.warning(
                    f"⚠️ [Rate Limit Cloudflare/Discord 429] IP bloqueada temporalmente por Cloudflare (Error 1015). "
                    f"Esperando {delay}s antes de reintentar para no reiniciar el baneo de IP..."
                )
                await asyncio.sleep(delay)
                delay = min(delay * 2, 600)  # Exponential backoff hasta 10 min
            else:
                logger.error(f"Error HTTP al iniciar bot: {e}")
                await asyncio.sleep(15)
        except (discord.GatewayNotFound, discord.ConnectionClosed) as e:
            logger.warning(f"Desconexión de Gateway al iniciar ({e}). Reintentando en 10s...")
            await asyncio.sleep(10)
        except Exception as e:
            logger.error(f"Error inesperado al iniciar bot: {e}", exc_info=e)
            await asyncio.sleep(15)

if __name__ == "__main__":
    faltan = [n for n, v in {
        "DISCORD_TOKEN": DISCORD_TOKEN,
        "SUPABASE_URL": SUPABASE_URL,
        "SUPABASE_SERVICE_ROLE_KEY": SUPABASE_KEY,
    }.items() if not v]
    if faltan:
        raise SystemExit(f"❌ Faltan variables de entorno: {', '.join(faltan)}")
    webserver.keep_alive()
    asyncio.run(main_runner())