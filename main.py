import discord
import logging
import os
import webserver
import asyncio
import random
from datetime import datetime, timezone
from discord.ext import commands, tasks
from discord import app_commands
from supabase import create_client
from types import SimpleNamespace
import discord.abc
from typing import Optional

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
supabase      = create_client(SUPABASE_URL, SUPABASE_KEY)

OWNER_ID    = 561225979389804544
skull_emoji = '💀'

# ─── Wrappers Async ───────────────────────────────────────────────────────────
async def db_select(table: str, match_col: str, match_val: str, select_cols: str = "*"):
    def _op():
        return supabase.table(table).select(select_cols).eq(match_col, match_val).execute()
    return await asyncio.to_thread(_op)

async def db_insert(table: str, data: dict):
    def _op():
        return supabase.table(table).insert(data).execute()
    return await asyncio.to_thread(_op)

async def db_update(table: str, updates: dict, match_col: str, match_val: str):
    def _op():
        return supabase.table(table).update(updates).eq(match_col, match_val).execute()
    return await asyncio.to_thread(_op)

async def db_upsert(table: str, data: dict):
    def _op():
        return supabase.table(table).upsert(data).execute()
    return await asyncio.to_thread(_op)

# ─── Config ───────────────────────────────────────────────────────────────────
async def get_guild_config(guild_id) -> dict:
    gid  = str(guild_id)
    resp = await db_select("settings", "guild_id", gid)
    if resp.data:
        return resp.data[0]
    default = {"guild_id": gid, "skullboard_channel_id": 0, "min_skulls": 1, "prefix": "sk!"}
    await db_insert("settings", default)
    return default

async def update_guild_config(guild_id, updates: dict):
    await db_update("settings", updates, "guild_id", str(guild_id))

# ─── Tracked messages ─────────────────────────────────────────────────────────
async def get_tracked_message(message_id: str) -> Optional[int]:
    resp = await db_select("tracked_messages", "message_id", str(message_id), "skullboard_message_id")
    if resp.data:
        return resp.data[0]["skullboard_message_id"]
    return None

async def set_tracked_message(message_id: str, skullboard_id: int, count: int, author_id: str, guild_id: str):
    await db_upsert("tracked_messages", {
        "message_id":          str(message_id),
        "skullboard_message_id": skullboard_id,
        "skull_count":         count,
        "author_id":           str(author_id),
        "guild_id":            str(guild_id)
    })

async def update_tracked_count(message_id: str, count: int):
    await db_update("tracked_messages", {"skull_count": count}, "message_id", str(message_id))

async def get_guild_record(guild_id: str) -> int:
    def _op():
        return supabase.table("tracked_messages").select("skull_count") \
            .eq("guild_id", guild_id).order("skull_count", desc=True).limit(1).execute()
    resp = await asyncio.to_thread(_op)
    if resp.data:
        return resp.data[0]["skull_count"]
    return 0

# ─── Ignored channels ─────────────────────────────────────────────────────────
async def is_channel_ignored(guild_id: str, channel_id: str) -> bool:
    def _op():
        return supabase.table("ignored_channels").select("channel_id") \
            .eq("guild_id", guild_id).eq("channel_id", channel_id).execute()
    resp = await asyncio.to_thread(_op)
    return bool(resp.data)

async def add_ignored_channel(guild_id: str, channel_id: str):
    def _op():
        return supabase.table("ignored_channels").upsert(
            {"guild_id": guild_id, "channel_id": channel_id}
        ).execute()
    await asyncio.to_thread(_op)

async def remove_ignored_channel(guild_id: str, channel_id: str):
    def _op():
        return supabase.table("ignored_channels").delete() \
            .eq("guild_id", guild_id).eq("channel_id", channel_id).execute()
    await asyncio.to_thread(_op)

async def get_ignored_channels(guild_id: str) -> list:
    def _op():
        return supabase.table("ignored_channels").select("channel_id").eq("guild_id", guild_id).execute()
    resp = await asyncio.to_thread(_op)
    return [r["channel_id"] for r in resp.data] if resp.data else []

# ─── Prefijo dinámico ─────────────────────────────────────────────────────────
async def get_prefix(bot, message):
    if not message.guild:
        return "sk!"
    cfg = await get_guild_config(message.guild.id)
    return cfg.get("prefix", "sk!")

# ─── Bot ──────────────────────────────────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True
intents.reactions       = True
intents.guilds          = True
intents.members         = True
intents.messages        = True

class SkullBot(commands.Bot):
    async def setup_hook(self):
        synced = await self.tree.sync()
        logger.info(f"✅ Slash commands sincronizados: {len(synced)}")
        if not status_loop.is_running():
            status_loop.start()

bot  = SkullBot(command_prefix=get_prefix, intents=intents, help_command=None)
tree = bot.tree

# Cooldown inteligente: mid -> TimerHandle
processing_messages: dict = {}

async def get_formatted_prefix(ctx_or_interaction) -> str:
    cfg = await get_guild_config(ctx_or_interaction.guild.id)
    return cfg.get("prefix", "sk!")

# ─── Status Loop ──────────────────────────────────────────────────────────────
@tasks.loop(minutes=5)
async def status_loop():
    await bot.wait_until_ready()
    activities = [
        discord.Activity(type=discord.ActivityType.watching, name=f"{len(bot.guilds)} servidores"),
        discord.Game(name="💀 SkullBoard"),
        discord.Activity(type=discord.ActivityType.listening, name="Board Calaverosa")
    ]
    for activity in activities:
        await bot.change_presence(activity=activity)
        await asyncio.sleep(60)

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
    embed.add_field(name="🔗 Invitar",  value=f"[Invitar SkullBoard]({get_invite_url()})",                      inline=False)
    return embed

# ─── Help paginado (slash) ────────────────────────────────────────────────────
class HelpView(discord.ui.View):
    def __init__(self, pages: list):
        super().__init__(timeout=120)
        self.pages   = pages
        self.current = 0
        self._refresh()

    def _refresh(self):
        self.prev_btn.disabled = self.current == 0
        self.next_btn.disabled = self.current == len(self.pages) - 1

    @discord.ui.button(label="◀ Anterior", style=discord.ButtonStyle.secondary)
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current -= 1
        self._refresh()
        await interaction.response.edit_message(embed=self.pages[self.current], view=self)

    @discord.ui.button(label="Siguiente ▶", style=discord.ButtonStyle.secondary)
    async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current += 1
        self._refresh()
        await interaction.response.edit_message(embed=self.pages[self.current], view=self)

def build_slash_help_pages() -> list:
    footer_nav   = "Usa /help para ver los comandos de barra"
    footer_admin = "🔒 Requiere permisos de administrador"

    p1 = discord.Embed(title="📖 Lista de comandos — SkullBoard", description="Página 1 de 3 · General", color=0x8b5cf6)
    p1.add_field(name="/ajustes", value="⚙️ Ver configuración actual", inline=True)
    p1.add_field(name="/ping",    value="🏓 Latencia del bot",          inline=True)
    p1.add_field(name="/invite",  value="🔗 Enlace de invitación",      inline=True)
    p1.set_footer(text=footer_nav)

    p2 = discord.Embed(title="📖 Lista de comandos — SkullBoard", description="Página 2 de 3 · Skullboard", color=0x8b5cf6)
    p2.add_field(name="/top",     value="🏆 Top mensajes más 💀",        inline=True)
    p2.add_field(name="/stats",   value="📊 Estadísticas de un usuario", inline=True)
    p2.add_field(name="/random",  value="🎲 Mensaje aleatorio",          inline=True)
    p2.add_field(name="/ignored", value="🚫 Ver canales ignorados",      inline=True)
    p2.set_footer(text=footer_nav)

    p3 = discord.Embed(title="📖 Lista de comandos — SkullBoard", description="Página 3 de 3 · Configuración", color=0x8b5cf6)
    p3.add_field(name="/set_channel 🔒", value="📌 Configura el canal del skullboard", inline=True)
    p3.add_field(name="/set_min 🔒",     value="💀 Mínimo de reacciones",               inline=True)
    p3.add_field(name="/prefix 🔒",      value="✏️ Cambia el prefijo",                 inline=True)
    p3.add_field(name="/ignore 🔒",      value="🚫 Ignora un canal",                    inline=True)
    p3.add_field(name="/unignore 🔒",    value="✅ Deja de ignorar un canal",           inline=True)
    p3.set_footer(text=footer_admin)

    return [p1, p2, p3]

# ─── On Ready ─────────────────────────────────────────────────────────────────
@bot.event
async def on_ready():
    logger.info(f"🔧 Bot conectado como {bot.user} ({bot.user.id})")

# ─── React Handlers con cooldown inteligente ──────────────────────────────────
@bot.event
async def on_raw_reaction_add(payload):
    if payload.user_id == bot.user.id: return
    if str(payload.emoji) != skull_emoji: return
    await _schedule_check(payload.channel_id, payload.message_id)

@bot.event
async def on_raw_reaction_remove(payload):
    if payload.user_id == bot.user.id: return
    if str(payload.emoji) != skull_emoji: return
    await _schedule_check(payload.channel_id, payload.message_id)

async def _schedule_check(channel_id: int, message_id: int):
    mid = str(message_id)
    if mid in processing_messages:
        processing_messages[mid].cancel()
    loop   = asyncio.get_event_loop()
    handle = loop.call_later(
        2.0,
        lambda: asyncio.ensure_future(_run_check(channel_id, message_id))
    )
    processing_messages[mid] = handle

async def _run_check(channel_id: int, message_id: int):
    mid = str(message_id)
    processing_messages.pop(mid, None)
    chan = bot.get_channel(channel_id)
    if chan is None: return
    try:
        msg = await chan.fetch_message(message_id)
    except Exception: return
    await _check(msg)

# ─── Core logic ───────────────────────────────────────────────────────────────
async def _check(msg: discord.Message):
    try:
        cfg = await get_guild_config(msg.guild.id)
        gid = str(msg.guild.id)

        # Ignorar canal skullboard
        if msg.channel.id == cfg["skullboard_channel_id"]: return
        # Ignorar canales excluidos
        if await is_channel_ignored(gid, str(msg.channel.id)): return

        skull_reac = next((r for r in msg.reactions if str(r.emoji) == skull_emoji), None)
        count      = skull_reac.count if skull_reac else 0
        if count < cfg["min_skulls"]: return

        dest_chan = bot.get_channel(cfg["skullboard_channel_id"])
        if not isinstance(dest_chan, discord.abc.Messageable): return

        emoji  = "☠️" if count >= cfg["min_skulls"] * 2 else "💀"
        record = await get_guild_record(gid)

        content = msg.content or ""
        if len(content) > 1800:
            content = content[:1800] + "...\n*(mensaje truncado)*"

        embed = discord.Embed(description=content, color=discord.Color.dark_gray())
        embed.set_author(
            name=msg.author.display_name,
            icon_url=(msg.author.avatar.url if msg.author.avatar else msg.author.default_avatar.url)
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
        mid   = str(msg.id)

        existing_id = await get_tracked_message(mid)
        if existing_id:
            try:
                old = await dest_chan.fetch_message(existing_id)
                await old.edit(content=texto, embed=embed)
                await update_tracked_count(mid, count)
                return
            except discord.NotFound:
                pass

        sent = await dest_chan.send(content=texto, embed=embed)
        await set_tracked_message(mid, sent.id, count, msg.author.id, gid)

    except Exception as e:
        logger.error(f"Error en _check: {e}")

# ─── COMANDOS DE TEXTO ────────────────────────────────────────────────────────

@bot.command(name="prefix", aliases=["set_prefix"])
@commands.has_permissions(administrator=True)
async def prefix_cmd(ctx, nuevo_prefijo: str = None):
    if not nuevo_prefijo:
        embed = discord.Embed(title="❌ Falta el prefijo", description="Indica el nuevo prefijo.", color=0xed4245)
        return await ctx.send(embed=embed)
    await update_guild_config(ctx.guild.id, {"prefix": nuevo_prefijo})
    embed = discord.Embed(title="✅ Prefijo actualizado", description=f"Ahora puedes usar comandos con `{nuevo_prefijo}`", color=0x57f287)
    await ctx.send(embed=embed)

@bot.command(name="set_channel", aliases=["channel"])
@commands.has_permissions(administrator=True)
async def set_channel_cmd(ctx, canal: discord.TextChannel = None):
    if not canal:
        embed = discord.Embed(title="❌ Falta el canal", description="Menciona el canal (ej: `#general`).", color=0xed4245)
        return await ctx.send(embed=embed)
    await update_guild_config(ctx.guild.id, {"skullboard_channel_id": canal.id})
    embed = discord.Embed(title="✅ Canal configurado", description=f"Los mensajes se enviarán a {canal.mention}", color=0x57f287)
    await ctx.send(embed=embed)

@bot.command(name="set_min", aliases=["min"])
@commands.has_permissions(administrator=True)
async def set_min_cmd(ctx, n: int = None):
    if not n or n < 1:
        embed = discord.Embed(title="❌ Número inválido", description="Introduce un número mayor a 0.", color=0xed4245)
        return await ctx.send(embed=embed)
    await update_guild_config(ctx.guild.id, {"min_skulls": n})
    embed = discord.Embed(title="✅ Meta establecida", description=f"Se necesitan **{n}** reacciones 💀 para destacar un mensaje.", color=0x57f287)
    await ctx.send(embed=embed)

@bot.command(name="ajustes", aliases=["settings"])
async def ajustes_cmd(ctx):
    embed = await build_ajustes_embed(ctx.guild.id)
    await ctx.send(embed=embed)

@bot.command()
async def ping(ctx):
    ms    = round(bot.latency * 1000)
    embed = discord.Embed(title="🏓 Pong!", color=0x5865F2)
    embed.add_field(name="Latencia", value=f"**{ms}ms**", inline=True)
    embed.add_field(name="Estado",   value=ping_estado(ms),  inline=True)
    await ctx.send(embed=embed)

@bot.command()
async def invite(ctx):
    embed = discord.Embed(title="💀 SkullBoard", description="Añade este Bot a tu servidor y disfruta!", color=0x8b5cf6)
    embed.add_field(name="🔗 Invitar al servidor", value=f"[Haz click aquí para invitarme]({get_invite_url()})", inline=False)
    embed.set_footer(text=f"Más de {len(bot.guilds)} servidores confían en SkullBoard")
    await ctx.send(embed=embed)

@bot.command(name="help", aliases=["ayuda", "comandos"])
async def help_cmd(ctx):
    p     = await get_formatted_prefix(ctx)
    embed = discord.Embed(title="📖 Lista de comandos — SkullBoard", description="Comandos de texto disponibles:", color=0x8b5cf6)
    embed.add_field(name=f"{p}ajustes",        value="⚙️ Ver configuración",       inline=True)
    embed.add_field(name=f"{p}ping",           value="🏓 Latencia del bot",         inline=True)
    embed.add_field(name=f"{p}invite",         value="🔗 Enlace de invitación",     inline=True)
    embed.add_field(name=f"{p}top",            value="🏆 Top mensajes más 💀",       inline=True)
    embed.add_field(name=f"{p}random",         value="🎲 Mensaje aleatorio",         inline=True)
    embed.add_field(name=f"{p}stats @usuario", value="📊 Estadísticas de usuario",  inline=True)
    embed.add_field(name=f"{p}set_channel 🔒", value="📌 Configura el canal",        inline=True)
    embed.add_field(name=f"{p}set_min 🔒",     value="💀 Mínimo de reacciones",      inline=True)
    embed.add_field(name=f"{p}prefix 🔒",      value="✏️ Cambia el prefijo",        inline=True)
    embed.add_field(name=f"{p}ignore 🔒",      value="🚫 Ignora un canal",           inline=True)
    embed.add_field(name=f"{p}unignore 🔒",    value="✅ Deja de ignorar un canal", inline=True)
    embed.add_field(name=f"{p}reset 🔒",       value="⚠️ Resetea el skullboard",    inline=True)
    embed.set_footer(text="Usa /help para ver los comandos de barra.")
    await ctx.send(embed=embed)

@bot.command(name="reset", hidden=True)
@commands.has_permissions(administrator=True)
async def reset_cmd(ctx):
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

    def _del():
        return supabase.table("tracked_messages").delete().eq("guild_id", gid).execute()
    resp    = await asyncio.to_thread(_del)
    deleted = len(resp.data) if resp.data else 0
    embed   = discord.Embed(
        title="✅ Skullboard reseteado",
        description=f"Se han eliminado **{deleted} mensajes** del registro. El skullboard empieza de cero.",
        color=0x57f287
    )
    await ctx.send(embed=embed)

@bot.command(name="ignore")
@commands.has_permissions(administrator=True)
async def ignore_cmd(ctx, canal: discord.TextChannel = None):
    if not canal:
        embed = discord.Embed(title="❌ Falta el canal", description="Menciona el canal a ignorar.", color=0xed4245)
        return await ctx.send(embed=embed)
    await add_ignored_channel(str(ctx.guild.id), str(canal.id))
    embed = discord.Embed(title="🚫 Canal ignorado", description=f"Los mensajes de {canal.mention} ya no podrán llegar al skullboard.", color=0xed4245)
    await ctx.send(embed=embed)

@bot.command(name="unignore")
@commands.has_permissions(administrator=True)
async def unignore_cmd(ctx, canal: discord.TextChannel = None):
    if not canal:
        embed = discord.Embed(title="❌ Falta el canal", description="Menciona el canal a desbloquear.", color=0xed4245)
        return await ctx.send(embed=embed)
    await remove_ignored_channel(str(ctx.guild.id), str(canal.id))
    embed = discord.Embed(title="✅ Canal desbloqueado", description=f"Los mensajes de {canal.mention} ya pueden llegar al skullboard.", color=0x57f287)
    await ctx.send(embed=embed)

@bot.command(name="top")
async def top_cmd(ctx):
    gid = str(ctx.guild.id)
    def _op():
        return supabase.table("tracked_messages") \
            .select("skull_count,author_id,skullboard_message_id") \
            .eq("guild_id", gid).order("skull_count", desc=True).limit(10).execute()
    resp = await asyncio.to_thread(_op)
    if not resp.data:
        embed = discord.Embed(title="🏆 Top Skullboard", description="Aún no hay mensajes en el skullboard.", color=0x4e5058)
        return await ctx.send(embed=embed)

    medals = ["🥇", "🥈", "🥉"]
    cfg    = await get_guild_config(ctx.guild.id)
    lines  = []
    for i, row in enumerate(resp.data):
        pos   = medals[i] if i < 3 else f"{i+1}."
        count = row["skull_count"]
        try:
            m    = ctx.guild.get_member(int(row["author_id"])) if row["author_id"] else None
            name = m.display_name if m else "Usuario desconocido"
        except Exception:
            name = "Usuario desconocido"
        sb_id = row.get("skullboard_message_id")
        if cfg["skullboard_channel_id"] and sb_id:
            link = f"https://discord.com/channels/{gid}/{cfg['skullboard_channel_id']}/{sb_id}"
            lines.append(f"{pos} [{name}]({link}) — **{count} 💀**")
        else:
            lines.append(f"{pos} {name} — **{count} 💀**")

    embed = discord.Embed(title="🏆 Top Skullboard", description="\n".join(lines), color=0xfaa61a)
    embed.set_footer(text=f"Top {len(resp.data)} mensajes del servidor")
    await ctx.send(embed=embed)

@bot.command(name="random")
async def random_cmd(ctx):
    gid = str(ctx.guild.id)
    def _op():
        return supabase.table("tracked_messages").select("*").eq("guild_id", gid).execute()
    resp = await asyncio.to_thread(_op)
    if not resp.data:
        embed = discord.Embed(title="🎲 Mensaje aleatorio", description="Aún no hay mensajes en el skullboard.", color=0x4e5058)
        return await ctx.send(embed=embed)

    row     = random.choice(resp.data)
    cfg     = await get_guild_config(ctx.guild.id)
    sb_chan  = bot.get_channel(cfg["skullboard_channel_id"])
    sb_id   = row.get("skullboard_message_id")

    try:
        sb_msg = await sb_chan.fetch_message(sb_id) if sb_chan and sb_id else None
    except Exception:
        sb_msg = None

    if sb_msg and sb_msg.embeds:
        embed = sb_msg.embeds[0].copy()
    else:
        embed = discord.Embed(color=discord.Color.dark_gray())

    embed.title = "🎲 Mensaje aleatorio del skullboard"
    await ctx.send(embed=embed)

@bot.command(name="stats")
async def stats_cmd(ctx, member: discord.Member = None):
    member = member or ctx.author
    gid    = str(ctx.guild.id)
    uid    = str(member.id)

    def _op():
        return supabase.table("tracked_messages") \
            .select("skull_count,skullboard_message_id") \
            .eq("guild_id", gid).eq("author_id", uid).execute()
    resp = await asyncio.to_thread(_op)

    if not resp.data:
        embed = discord.Embed(
            title=f"📊 Stats de {member.display_name}",
            description="Este usuario no tiene ningún mensaje en el skullboard.",
            color=0x4e5058
        )
        return await ctx.send(embed=embed)

    total_msgs   = len(resp.data)
    total_skulls = sum(r["skull_count"] for r in resp.data)
    best_row     = max(resp.data, key=lambda r: r["skull_count"])
    best_count   = best_row["skull_count"]
    best_sb_id   = best_row.get("skullboard_message_id")
    cfg          = await get_guild_config(ctx.guild.id)
    link         = None
    if best_sb_id and cfg["skullboard_channel_id"]:
        link = f"https://discord.com/channels/{gid}/{cfg['skullboard_channel_id']}/{best_sb_id}"

    embed = discord.Embed(title=f"📊 Stats de {member.display_name}", color=0x8b5cf6)
    embed.set_thumbnail(url=member.avatar.url if member.avatar else member.default_avatar.url)
    embed.add_field(name="📌 Mensajes en el board",        value=str(total_msgs),    inline=False)
    embed.add_field(name="💀 Calaveras totales recibidas",  value=str(total_skulls),  inline=False)
    embed.add_field(name="🏆 Récord personal",              value=f"{best_count} 💀", inline=False)
    if link:
        embed.add_field(name="🔗 Mejor mensaje", value=f"[Saltar al mensaje]({link})", inline=False)
    embed.set_footer(text=f"Estadísticas de {member.display_name} en este servidor")
    await ctx.send(embed=embed)

@bot.command(name="ignored")
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

# ─── Comandos privados del owner ──────────────────────────────────────────────
@bot.command(name="announce", hidden=True)
async def announce_cmd(ctx):
    if ctx.author.id != OWNER_ID:
        try: await ctx.message.add_reaction("❓")
        except: pass
        return

    embed = discord.Embed(
        title="💀 SkullBoard — Novedades",
        description=(
            "Se han añadido nuevas funciones y mejorado el diseño.\n"
            "Usa `/help` o `sk!help` para ver todos los comandos disponibles.\n\n"
            "**✨ Novedades principales:**\n"
            "• `/top` — Top mensajes más reaccionados\n"
            "• `/stats` — Estadísticas de usuarios\n"
            "• `/random` — Mensaje aleatorio del board\n"
            "• `/ignore` — Excluye canales del skullboard\n"
            "• Embeds rediseñados y más limpios"
        ),
        color=0x8b5cf6
    )

    enviados = 0
    fallidos = 0

    for guild in bot.guilds:
        canal = None
        try:
            cfg = await get_guild_config(guild.id)
            cid = cfg.get("skullboard_channel_id", 0)
            if cid:
                canal = bot.get_channel(cid)
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

@bot.command(name="servers", hidden=True)
async def servers_cmd(ctx):
    if ctx.author.id != OWNER_ID:
        try: await ctx.message.add_reaction("❓")
        except: pass
        return
    total = len(bot.guilds)
    texto = "\n".join(f"• {g.name} (`{g.id}`)" for g in bot.guilds)
    if len(texto) > 1900:
        texto = texto[:1900] + "\n... (truncado)"
    embed = discord.Embed(title=f"🌍 El bot está en {total} servidores:", description=texto, color=discord.Color.gold())
    await ctx.send(embed=embed)

@bot.command(name="serverinfo", hidden=True)
async def serverinfo_cmd(ctx, guild_id: int = None):
    if ctx.author.id != OWNER_ID:
        try: await ctx.message.add_reaction("❓")
        except: pass
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

    def _count():
        return supabase.table("tracked_messages").select("message_id", count="exact").eq("guild_id", gid).execute()
    count_resp = await asyncio.to_thread(_count)
    msg_count  = count_resp.count if count_resp.count else 0

    owner   = guild.owner
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
@app_commands.describe(nuevo_prefijo="Prefijo nuevo")
async def prefix_slash(interaction: discord.Interaction, nuevo_prefijo: str):
    if not interaction.user.guild_permissions.administrator:
        embed = discord.Embed(title="❌ Sin permisos", description="Necesitas permisos de **Administrador**.", color=0xed4245)
        return await interaction.response.send_message(embed=embed, ephemeral=True)
    await update_guild_config(interaction.guild.id, {"prefix": nuevo_prefijo})
    embed = discord.Embed(title="✅ Prefijo actualizado", description=f"Ahora puedes usar comandos con `{nuevo_prefijo}`", color=0x57f287)
    await interaction.response.send_message(embed=embed)

@tree.command(name="set_channel", description="Configura el canal del SkullBoard")
@app_commands.describe(channel="Canal donde se enviarán los mensajes del SkullBoard")
async def set_channel_slash(interaction: discord.Interaction, channel: discord.TextChannel):
    if not interaction.user.guild_permissions.administrator:
        embed = discord.Embed(title="❌ Sin permisos", description="Necesitas permisos de **Administrador**.", color=0xed4245)
        return await interaction.response.send_message(embed=embed, ephemeral=True)
    await update_guild_config(interaction.guild.id, {"skullboard_channel_id": channel.id})
    embed = discord.Embed(title="✅ Canal configurado", description=f"Los mensajes se enviarán a {channel.mention}", color=0x57f287)
    await interaction.response.send_message(embed=embed)

@tree.command(name="set_min", description="Fija el mínimo de reacciones 💀")
@app_commands.describe(cantidad="Número mínimo de reacciones para destacar un mensaje (≥ 1)")
async def set_min_slash(interaction: discord.Interaction, cantidad: int):
    if not interaction.user.guild_permissions.administrator:
        embed = discord.Embed(title="❌ Sin permisos", description="Necesitas permisos de **Administrador**.", color=0xed4245)
        return await interaction.response.send_message(embed=embed, ephemeral=True)
    if cantidad < 1:
        embed = discord.Embed(title="❌ Número inválido", description="El mínimo debe ser ≥ 1.", color=0xed4245)
        return await interaction.response.send_message(embed=embed, ephemeral=True)
    await update_guild_config(interaction.guild.id, {"min_skulls": cantidad})
    embed = discord.Embed(title="✅ Meta establecida", description=f"Se necesitan **{cantidad}** reacciones 💀 para destacar un mensaje.", color=0x57f287)
    await interaction.response.send_message(embed=embed)

@tree.command(name="ping", description="Ver latencia")
async def ping_slash(interaction: discord.Interaction):
    ms    = round(bot.latency * 1000)
    embed = discord.Embed(title="🏓 Pong!", color=0x5865F2)
    embed.add_field(name="Latencia", value=f"**{ms}ms**", inline=True)
    embed.add_field(name="Estado",   value=ping_estado(ms),  inline=True)
    await interaction.response.send_message(embed=embed)

@tree.command(name="invite", description="Invita al bot")
async def invite_slash(interaction: discord.Interaction):
    embed = discord.Embed(title="💀 SkullBoard", description="Añade este Bot a tu servidor y disfruta!", color=0x8b5cf6)
    embed.add_field(name="🔗 Invitar al servidor", value=f"[Haz click aquí para invitarme]({get_invite_url()})", inline=False)
    embed.set_footer(text=f"Más de {len(bot.guilds)} servidores confían en SkullBoard")
    await interaction.response.send_message(embed=embed)

@tree.command(name="help", description="Muestra los comandos disponibles del bot")
async def help_slash(interaction: discord.Interaction):
    pages = build_slash_help_pages()
    view  = HelpView(pages)
    await interaction.response.send_message(embed=pages[0], view=view)

@tree.command(name="top", description="Top mensajes más reaccionados del servidor")
async def top_slash(interaction: discord.Interaction):
    await interaction.response.defer()
    gid = str(interaction.guild.id)
    def _op():
        return supabase.table("tracked_messages") \
            .select("skull_count,author_id,skullboard_message_id") \
            .eq("guild_id", gid).order("skull_count", desc=True).limit(10).execute()
    resp = await asyncio.to_thread(_op)
    if not resp.data:
        embed = discord.Embed(title="🏆 Top Skullboard", description="Aún no hay mensajes en el skullboard.", color=0x4e5058)
        return await interaction.followup.send(embed=embed)

    medals = ["🥇", "🥈", "🥉"]
    cfg    = await get_guild_config(interaction.guild.id)
    lines  = []
    for i, row in enumerate(resp.data):
        pos   = medals[i] if i < 3 else f"{i+1}."
        count = row["skull_count"]
        try:
            m    = interaction.guild.get_member(int(row["author_id"])) if row["author_id"] else None
            name = m.display_name if m else "Usuario desconocido"
        except Exception:
            name = "Usuario desconocido"
        sb_id = row.get("skullboard_message_id")
        if cfg["skullboard_channel_id"] and sb_id:
            link = f"https://discord.com/channels/{gid}/{cfg['skullboard_channel_id']}/{sb_id}"
            lines.append(f"{pos} [{name}]({link}) — **{count} 💀**")
        else:
            lines.append(f"{pos} {name} — **{count} 💀**")

    embed = discord.Embed(title="🏆 Top Skullboard", description="\n".join(lines), color=0xfaa61a)
    embed.set_footer(text=f"Top {len(resp.data)} mensajes del servidor")
    await interaction.followup.send(embed=embed)

@tree.command(name="random", description="Muestra un mensaje aleatorio del skullboard")
async def random_slash(interaction: discord.Interaction):
    await interaction.response.defer()
    gid = str(interaction.guild.id)
    def _op():
        return supabase.table("tracked_messages").select("*").eq("guild_id", gid).execute()
    resp = await asyncio.to_thread(_op)
    if not resp.data:
        embed = discord.Embed(title="🎲 Mensaje aleatorio", description="Aún no hay mensajes en el skullboard.", color=0x4e5058)
        return await interaction.followup.send(embed=embed)

    row    = random.choice(resp.data)
    cfg    = await get_guild_config(interaction.guild.id)
    sb_chan = bot.get_channel(cfg["skullboard_channel_id"])
    sb_id  = row.get("skullboard_message_id")

    try:
        sb_msg = await sb_chan.fetch_message(sb_id) if sb_chan and sb_id else None
    except Exception:
        sb_msg = None

    if sb_msg and sb_msg.embeds:
        embed = sb_msg.embeds[0].copy()
    else:
        embed = discord.Embed(color=discord.Color.dark_gray())

    embed.title = "🎲 Mensaje aleatorio del skullboard"
    await interaction.followup.send(embed=embed)

@tree.command(name="stats", description="Estadísticas de un usuario en el skullboard")
@app_commands.describe(usuario="Usuario del que ver las estadísticas")
async def stats_slash(interaction: discord.Interaction, usuario: discord.Member = None):
    await interaction.response.defer()
    member = usuario or interaction.user
    gid    = str(interaction.guild.id)
    uid    = str(member.id)

    def _op():
        return supabase.table("tracked_messages") \
            .select("skull_count,skullboard_message_id") \
            .eq("guild_id", gid).eq("author_id", uid).execute()
    resp = await asyncio.to_thread(_op)

    if not resp.data:
        embed = discord.Embed(
            title=f"📊 Stats de {member.display_name}",
            description="Este usuario no tiene ningún mensaje en el skullboard.",
            color=0x4e5058
        )
        return await interaction.followup.send(embed=embed)

    total_msgs   = len(resp.data)
    total_skulls = sum(r["skull_count"] for r in resp.data)
    best_row     = max(resp.data, key=lambda r: r["skull_count"])
    best_count   = best_row["skull_count"]
    best_sb_id   = best_row.get("skullboard_message_id")
    cfg          = await get_guild_config(interaction.guild.id)
    link         = None
    if best_sb_id and cfg["skullboard_channel_id"]:
        link = f"https://discord.com/channels/{gid}/{cfg['skullboard_channel_id']}/{best_sb_id}"

    embed = discord.Embed(title=f"📊 Stats de {member.display_name}", color=0x8b5cf6)
    embed.set_thumbnail(url=member.avatar.url if member.avatar else member.default_avatar.url)
    embed.add_field(name="📌 Mensajes en el board",        value=str(total_msgs),    inline=False)
    embed.add_field(name="💀 Calaveras totales recibidas",  value=str(total_skulls),  inline=False)
    embed.add_field(name="🏆 Récord personal",              value=f"{best_count} 💀", inline=False)
    if link:
        embed.add_field(name="🔗 Mejor mensaje", value=f"[Saltar al mensaje]({link})", inline=False)
    embed.set_footer(text=f"Estadísticas de {member.display_name} en este servidor")
    await interaction.followup.send(embed=embed)

@tree.command(name="ignore", description="Ignora un canal (admin)")
@app_commands.describe(canal="Canal a ignorar")
async def ignore_slash(interaction: discord.Interaction, canal: discord.TextChannel):
    if not interaction.user.guild_permissions.administrator:
        embed = discord.Embed(title="❌ Sin permisos", description="Necesitas permisos de **Administrador**.", color=0xed4245)
        return await interaction.response.send_message(embed=embed, ephemeral=True)
    await add_ignored_channel(str(interaction.guild.id), str(canal.id))
    embed = discord.Embed(title="🚫 Canal ignorado", description=f"Los mensajes de {canal.mention} ya no podrán llegar al skullboard.", color=0xed4245)
    await interaction.response.send_message(embed=embed)

@tree.command(name="unignore", description="Deja de ignorar un canal (admin)")
@app_commands.describe(canal="Canal a desbloquear")
async def unignore_slash(interaction: discord.Interaction, canal: discord.TextChannel):
    if not interaction.user.guild_permissions.administrator:
        embed = discord.Embed(title="❌ Sin permisos", description="Necesitas permisos de **Administrador**.", color=0xed4245)
        return await interaction.response.send_message(embed=embed, ephemeral=True)
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

# ─── Manejo de errores global ─────────────────────────────────────────────────
@bot.event
async def on_command_error(ctx, error):
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
    logger.error(f"Error en comando de texto: {error}")

@tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    embed = discord.Embed(title="❌ Ha ocurrido un error", description=str(error), color=0xed4245)
    try:
        if not interaction.response.is_done():
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            await interaction.followup.send(embed=embed, ephemeral=True)
    except Exception:
        pass
    logger.error(f"Error en slash command: {error}")

# ─── Ejecución ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    webserver.keep_alive()
    bot.run(DISCORD_TOKEN)
