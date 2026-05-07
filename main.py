import discord
import logging
import os
import webserver
import asyncio
from datetime import datetime, timezone
from discord.ext import commands, tasks
from discord import app_commands
from supabase import create_client
from types import SimpleNamespace
import discord.abc
from typing import cast, Optional

# ─── Configuración de Logging ────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("SkullBoard")

# ─── Configuración de Supabase ───────────────────────────────────────────────
DISCORD_TOKEN  = os.getenv("DISCORD_TOKEN")
SUPABASE_URL   = os.getenv("SUPABASE_URL")
SUPABASE_KEY   = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
supabase       = create_client(SUPABASE_URL, SUPABASE_KEY)

# ─── Wrappers Async para Supabase ────────────────────────────────────────────
# Para evitar bloquear el event loop principal con peticiones HTTP síncronas
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

# ─── Funciones de configuración ────────────────────────────────────────────────
async def get_guild_config(guild_id) -> dict:
    gid = str(guild_id)
    resp = await db_select("settings", "guild_id", gid)
    
    if resp.data and len(resp.data) > 0:
        return resp.data[0]
    
    default = {
        "guild_id": gid,
        "skullboard_channel_id": 0,
        "min_skulls": 1,
        "prefix": "sk!"
    }
    # Insertar por defecto si no existe
    await db_insert("settings", default)
    return default

async def update_guild_config(guild_id, updates: dict):
    await db_update("settings", updates, "guild_id", str(guild_id))

# ─── Persistencia de mensajes rastreados ──────────────────────────────────────
async def get_tracked_message(message_id: str) -> Optional[int]:
    resp = await db_select("tracked_messages", "message_id", str(message_id), "skullboard_message_id")
    if resp.data and len(resp.data) > 0:
        return resp.data[0]["skullboard_message_id"]
    return None

async def set_tracked_message(message_id: str, skullboard_id: int):
    await db_upsert("tracked_messages", {
        "message_id": str(message_id),
        "skullboard_message_id": skullboard_id
    })

# ─── Prefijo dinámico ────────────────────────────────────────────────────────
async def get_prefix(bot, message):
    if not message.guild:
        return "sk!"
    cfg = await get_guild_config(message.guild.id)
    return cfg.get("prefix", "sk!")

# ─── Bot y constantes ────────────────────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True
intents.reactions       = True
intents.guilds          = True
intents.members         = True
intents.messages        = True

class SkullBot(commands.Bot):
    async def setup_hook(self):
        # Sincronizar comandos de aplicación (slash commands)
        synced = await self.tree.sync()
        logger.info(f"✅ Comandos sincronizados globalmente: {len(synced)} comandos registrados")
        # Iniciar loop de estado
        if not status_loop.is_running():
            status_loop.start()

bot    = SkullBot(command_prefix=get_prefix, intents=intents, help_command=None)
tree   = bot.tree
skull_emoji        = '💀'
processing_messages = set()

async def get_formatted_prefix(ctx_or_interaction) -> str:
    gid = ctx_or_interaction.guild.id
    cfg = await get_guild_config(gid)
    return cfg.get("prefix", "sk!")

# ─── Status Loop ─────────────────────────────────────────────────────────────
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

# ─── Utilidades ─────────────────────────────────────────────────────────────
def formatear_fecha(fecha: datetime) -> str:
    ahora = datetime.now(timezone.utc)
    diff  = (ahora.date() - fecha.date()).days
    hora  = fecha.strftime("%H:%M")
    if diff == 0:
        return f"Hoy a las {hora}"
    if diff == 1:
        return f"Ayer a las {hora}"
    return fecha.strftime("%d/%m/%Y %H:%M")

def get_invite_url():
    # Usamos ID dinámico del bot si está disponible, si no fallback al hardcoded
    client_id = bot.user.id if bot.user else 1367463352774955059
    permissions = 277025508352
    return f"https://discord.com/oauth2/authorize?client_id={client_id}&permissions={permissions}&scope=bot+applications.commands"

async def send_ajustes_embed(dest):
    cfg           = await get_guild_config(dest.guild.id)
    skull_channel = bot.get_channel(cfg["skullboard_channel_id"])
    prefix        = cfg.get("prefix", "sk!")
    
    embed = discord.Embed(
        title="⚙️ Ajustes del SkullBoard",
        description="Configuración actual del bot:",
        color=discord.Color.purple()
    )
    chan_val = skull_channel.mention if skull_channel else "❌ No configurado"
    
    embed.add_field(name="📌 Canal",    value=chan_val,                               inline=False)
    embed.add_field(name="🔧 Mínimos",  value=f"{cfg['min_skulls']} 💀",              inline=False)
    embed.add_field(name="✏️ Prefijo",  value=f"`{prefix}`",                         inline=False)
    embed.add_field(name="🏓 Latencia", value=f"{round(bot.latency*1000)}ms",        inline=False)
    embed.add_field(name="🔗 Invita",   value=f"[Invitar SkullBoard]({get_invite_url()})", inline=False)

    if isinstance(dest, discord.Interaction):
        if not dest.response.is_done():
            await dest.response.send_message(embed=embed)
        else:
            await dest.followup.send(embed=embed)
    else:
        await dest.send(embed=embed)

# ─── Arranque ────────────────────────────────────────────────────────────────
@bot.event
async def on_ready():
    logger.info(f"🔧 Bot conectado como {bot.user} ({bot.user.id})")

# ── React Handlers ───────────────────────────────────────────────────────────
@bot.event
async def on_raw_reaction_add(payload):
    if payload.user_id == bot.user.id: return
    
    chan = bot.get_channel(payload.channel_id)
    if chan is None: return

    try:
        msg = await chan.fetch_message(payload.message_id)
    except: return

    r = SimpleNamespace(emoji=str(payload.emoji), message=msg)
    await _check(r)

@bot.event
async def on_raw_reaction_remove(payload):
    if payload.user_id == bot.user.id: return
    
    chan = bot.get_channel(payload.channel_id)
    if chan is None: return

    try:
        msg = await chan.fetch_message(payload.message_id)
    except: return

    r = SimpleNamespace(emoji=str(payload.emoji), message=msg)
    await _check(r)


# ── Core logic ────────────────────────────────────────────────────────────────
async def _check(reaction):
    chan = reaction.message.channel
    msg  = reaction.message
    mid  = str(msg.id)
    
    if str(reaction.emoji) != skull_emoji: return
    if mid in processing_messages: return
    
    processing_messages.add(mid)

    try:
        cfg = await get_guild_config(msg.guild.id)
        
        # Reintentos para consistencia de conteo
        skull_reac = None
        for _ in range(3):
            skull_reac = next((r for r in msg.reactions if str(r.emoji) == skull_emoji), None)
            count = skull_reac.count if skull_reac else 0
            if count >= cfg["min_skulls"]:
                break
            await asyncio.sleep(0.5)
            try:
                msg = await chan.fetch_message(mid)
            except: break

        count = skull_reac.count if skull_reac else 0
        if count < cfg["min_skulls"]:
            return

        dest_chan = bot.get_channel(cfg["skullboard_channel_id"])
        if not isinstance(dest_chan, discord.abc.Messageable):
            return
        dest = dest_chan

        # Emoji especial para muchos likes
        emoji = "☠️" if count >= cfg["min_skulls"] * 2 else "💀"

        # Crear Embed mejorado (pero volviendo al estilo visual anterior)
        # Truncar contenido para evitar errores (limite de discord 4096, usamos 1800 para seguridad + embeds)
        content = msg.content or ""
        if len(content) > 1800:
            content = content[:1800] + "...\n*(mensaje truncado)*"
            
        embed = discord.Embed(description=content, color=discord.Color.dark_gray())
        embed.set_author(
            name=msg.author.display_name,
            icon_url=(msg.author.avatar.url if msg.author.avatar else msg.author.default_avatar.url)
        )
        
        # Imagen
        img = next((a for a in msg.attachments if a.content_type and a.content_type.startswith("image/")), None)
        if img:
            embed.set_image(url=img.url)
            
        # Campos extra (Estilo Anterior)
        embed.add_field(name="🔗 Enlace", value=f"[Saltar al mensaje]({msg.jump_url})", inline=False)
        
        # Footer con la fecha formateada (Estilo Anterior)
        # Formato: "6 💀  •  18/12/2025 23:56" o "Ayer a las..."
        embed.set_footer(text=f"{count} {emoji}  •  {formatear_fecha(msg.created_at)}")

        texto = f"{emoji} **{count}** | {msg.channel.mention}"

        existing_id = await get_tracked_message(mid)
        if existing_id:
            try:
                old = await dest.fetch_message(existing_id) # type: ignore
                await old.edit(content=texto, embed=embed)
                return
            except discord.NotFound:
                # Si se borró manualmente, lo reenviamos
                pass

        sent = await dest.send(content=texto, embed=embed) # type: ignore
        await set_tracked_message(mid, sent.id)

    except Exception as e:
        logger.error(f"Error en _check: {e}")
    finally:
        processing_messages.discard(mid)


# ─── COMANDOS TEXTO ──────────────────────────────────────────────────────────
@bot.command(name="prefix", aliases=["set_prefix"])
@commands.has_permissions(administrator=True)
async def prefix(ctx, nuevo_prefijo: str=None):
    if not nuevo_prefijo:
        return await ctx.send("❌ ¡Falta el nuevo prefijo!")
    await update_guild_config(ctx.guild.id, {"prefix": nuevo_prefijo})
    # Mensaje mejorado
    await ctx.send(f"✅ **Prefijo actualizado**\nAhora puedes usar comandos con `{nuevo_prefijo}`")

@bot.command(name="set_channel", aliases=["channel"])
@commands.has_permissions(administrator=True)
async def set_channel(ctx, canal: discord.TextChannel = None):
    if not canal:
        return await ctx.send("❌ ¡Debes mencionar el canal (ej: `#general`)!")
    await update_guild_config(ctx.guild.id, {"skullboard_channel_id": canal.id})
    # Mensaje mejorado
    await ctx.send(f"✅ **Canal configurado**\nLos mensajes se enviarán a {canal.mention}")

@bot.command(name="set_min", aliases=["min"])
@commands.has_permissions(administrator=True)
async def set_min(ctx, n: int = None):
    if not n or n < 1:
        return await ctx.send("❌ ¡Introduce un número válido mayor a 0!")
    await update_guild_config(ctx.guild.id, {"min_skulls": n})
    # Mensaje mejorado
    await ctx.send(f"✅ **Meta establecida**\nSe necesitan **{n}** reacciones 💀 para destacar un mensaje.")

@bot.command(name="ajustes", aliases=["settings"])
async def ajustes(ctx):
    await send_ajustes_embed(ctx)

@bot.command()
async def ping(ctx):
    await ctx.send(f"🏓 Pong! `{round(bot.latency*1000)}ms`")

@bot.command()
async def invite(ctx):
    await ctx.send(f"🔗 Invita al bot: {get_invite_url()}")

@bot.command(name="help", aliases=["ayuda", "comandos"])
async def help_cmd(ctx):
    prefix = await get_formatted_prefix(ctx)
    embed = discord.Embed(
        title="📖 Lista de comandos - SkullBoard",
        description="Comandos de texto disponibles:",
        color=discord.Color.teal()
    )
    embed.add_field(name=f"{prefix}ajustes",       value="📋 Ver configuración", inline=False)
    embed.add_field(name=f"{prefix}set_channel 🔒", value="📌 Configurar canal",   inline=False)
    embed.add_field(name=f"{prefix}set_min 🔒",     value="💀 Mínimo de reacciones", inline=False)
    embed.add_field(name=f"{prefix}prefix 🔒",      value="✏️ Cambiar prefijo",    inline=False)
    embed.add_field(name=f"{prefix}ping",           value="🏓 Latencia",           inline=False)
    embed.add_field(name=f"{prefix}invite",         value="🔗 Invitarme",          inline=False)
    embed.set_footer(text="Usa /help para ver comandos de barra.")
    await ctx.send(embed=embed)

@bot.command(name="servers", hidden=True)
@commands.has_permissions(administrator=True)
async def servers(ctx):
    total = len(bot.guilds)
    texto = "\n".join(f"• {g.name} (`{g.id}`)" for g in bot.guilds)
    if len(texto) > 1900:
        texto = texto[:1900] + "\n... (truncado)"
    embed = discord.Embed(
        title=f"🌍 El bot está en {total} servidores:",
        description=texto,
        color=discord.Color.gold()
    )
    await ctx.send(embed=embed)

# ─── SLASH COMMANDS ──────────────────────────────────────────────────────────
@tree.command(name="ajustes", description="Ver configuración del bot")
async def ajustes_slash(interaction: discord.Interaction):
    await send_ajustes_embed(interaction)

@tree.command(name="prefix", description="Cambiar prefijo (admin)")
@app_commands.describe(nuevo_prefijo="Prefijo nuevo")
async def prefix_slash(interaction: discord.Interaction, nuevo_prefijo: str):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("❌ ¡No tienes permiso!", ephemeral=True)
    await update_guild_config(interaction.guild.id, {"prefix": nuevo_prefijo})
    # Mensaje mejorado
    await interaction.response.send_message(f"✅ **Prefijo actualizado**\nAhora es: `{nuevo_prefijo}`")

@tree.command(name="set_channel", description="Configura el canal del SkullBoard")
@app_commands.describe(channel="Canal donde se enviarán los mensajes del SkullBoard")
async def set_channel_slash(interaction: discord.Interaction, channel: discord.TextChannel):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("❌ No tienes permiso de **Administrador**.", ephemeral=True)
    await update_guild_config(interaction.guild.id, {"skullboard_channel_id": channel.id})
    # Mensaje mejorado
    await interaction.response.send_message(f"✅ **Canal configurado**\nMensajes a {channel.mention}")

@tree.command(name="set_min", description="Fija el mínimo de reacciones 💀")
@app_commands.describe(cantidad="Número mínimo de reacciones para destacar un mensaje (≥ 1)")
async def set_min_slash(interaction: discord.Interaction, cantidad: int):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("❌ No tienes permiso de **Administrador**.", ephemeral=True)
    if cantidad < 1:
        return await interaction.response.send_message("❌ ¡Número inválido! Debe ser ≥ 1.", ephemeral=True)
    await update_guild_config(interaction.guild.id, {"min_skulls": cantidad})
    # Mensaje mejorado
    await interaction.response.send_message(f"✅ **Meta establecida**\nMínimo: {cantidad} 💀")

@tree.command(name="ping", description="Ver latencia")
async def ping_slash(interaction: discord.Interaction):
    await interaction.response.send_message(f"🏓 Pong! `{round(bot.latency*1000)}ms`")

@tree.command(name="invite", description="Invita al bot")
async def invite_slash(interaction: discord.Interaction):
    await interaction.response.send_message(f"🔗 Invita al bot: {get_invite_url()}")

@tree.command(name="help", description="Muestra los comandos disponibles del bot")
async def help_slash(interaction: discord.Interaction):
    prefix = await get_formatted_prefix(interaction)
    embed = discord.Embed(
        title="📖 Lista de comandos - SkullBoard",
        description="Comandos de texto y barra:",
        color=discord.Color.teal()
    )
    embed.add_field(name="/ajustes",       value="📋 Ver configuración", inline=True)
    embed.add_field(name="/ping",          value="🏓 Latencia",           inline=True)
    embed.add_field(name="/invite",        value="🔗 Enlace invitación",  inline=True)
    embed.add_field(name="/set_channel 🔒", value="📌 Configurar canal",   inline=True)
    embed.add_field(name="/set_min 🔒",     value="💀 Mínimo reacciones",  inline=True)
    embed.add_field(name="/prefix 🔒",      value="✏️ Cambiar prefijo",    inline=True)
    
    embed.set_footer(text="🔒 = Requiere permisos de administrador")
    await interaction.response.send_message(embed=embed)

# ─── MANEJO DE ERRORES GLOBAL ────────────────────────────────────────────────
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        return await ctx.send("❌ No tienes permiso de **Administrador**.")
    if isinstance(error, commands.BadArgument):
        return await ctx.send("❌ Argumento inválido.")
    if isinstance(error, commands.MissingRequiredArgument):
        try:
            p = await get_formatted_prefix(ctx)
            return await ctx.send(f"❌ Faltan argumentos. Usa `{p}help`.")
        except:
             return await ctx.send("❌ Faltan argumentos.")
    if isinstance(error, commands.CommandNotFound):
        # Responder al usuario que el comando no existe
        try:
             # Usamos unicode emoji o simple texto
             return await ctx.message.add_reaction("❓")
        except:
             return await ctx.send(f"❌ Comando desconocido. Usa /help para ver la lista.")
    logger.error(f"Error en comando de texto: {error}")

@tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        if not interaction.response.is_done():
            await interaction.response.send_message("❌ No tienes permisos para usar este comando.", ephemeral=True)
    else:
        logger.error(f"Error en slash command: {error}")
        if not interaction.response.is_done():
            await interaction.response.send_message("❌ Ha ocurrido un error inesperado.", ephemeral=True)

# ─── EJECUCIÓN ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    webserver.keep_alive()
    bot.run(DISCORD_TOKEN)