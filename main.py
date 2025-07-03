import discord
import logging
import os
import webserver
from datetime import datetime, timezone
from discord.ext import commands
from discord import app_commands
from supabase import create_client
from types import SimpleNamespace
import discord.abc
from typing import cast

# ─── Configuración de Supabase ───────────────────────────────────────────────
DISCORD_TOKEN  = os.getenv("DISCORD_TOKEN")
SUPABASE_URL   = os.getenv("SUPABASE_URL")
SUPABASE_KEY   = os.getenv("SUPABASE_KEY")
supabase       = create_client(SUPABASE_URL, SUPABASE_KEY)

# ─── Funciones de configuración ────────────────────────────────────────────────
def get_guild_config(guild_id):
    gid = str(guild_id)
    resp = supabase.table("settings").select("*").eq("guild_id", gid).execute()
    if resp.data and len(resp.data) > 0:
        return resp.data[0]
    default = {
        "guild_id": gid,
        "skullboard_channel_id": 0,
        "min_skulls": 1,
        "prefix": "sk!"
    }
    supabase.table("settings").insert(default).execute()
    return default

def update_guild_config(guild_id, updates: dict):
    supabase.table("settings").update(updates).eq("guild_id", str(guild_id)).execute()

# ─── Persistencia de mensajes rastreados ──────────────────────────────────────
def get_tracked_message(message_id: str):
    resp = supabase.table("tracked_messages").select("skullboard_message_id").eq("message_id", str(message_id)).execute()
    if resp.data and len(resp.data) > 0:
        return resp.data[0]["skullboard_message_id"]
    return None

def set_tracked_message(message_id: str, skullboard_id: int):
    supabase.table("tracked_messages").upsert({
        "message_id": str(message_id),
        "skullboard_message_id": skullboard_id
    }).execute()

# ─── Prefijo dinámico ────────────────────────────────────────────────────────
async def get_prefix(bot, message):
    if not message.guild:
        return "sk!"
    cfg = get_guild_config(message.guild.id)
    return cfg.get("prefix", "sk!")

# ─── Bot y constantes ────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO)
intents = discord.Intents.default()
intents.message_content = True
intents.reactions       = True
intents.guilds          = True
intents.members         = True
intents.messages        = True

bot    = commands.Bot(command_prefix=get_prefix, intents=intents, help_command=None)
tree   = bot.tree
skull_emoji        = '💀'
processing_messages = set()

def get_formatted_prefix(ctx_or_interaction) -> str:
    gid = ctx_or_interaction.guild.id
    return get_guild_config(gid).get("prefix", "sk!")

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
    client_id   = 1367463352774955059
    permissions = 277025508352
    return f"https://discord.com/oauth2/authorize?client_id={client_id}&permissions={permissions}&scope=bot+applications.commands"

async def send_ajustes_embed(dest):
    cfg           = get_guild_config(dest.guild.id)
    skull_channel = bot.get_channel(cfg["skullboard_channel_id"])
    prefix        = cfg.get("prefix", "sk!")
    embed = discord.Embed(
        title="⚙️ Ajustes del SkullBoard",
        description="Configuración actual del bot:",
        color=discord.Color.purple()
    )
    embed.add_field(name="📌 Canal",    value=skull_channel.mention if skull_channel else "❌ No configurado", inline=False)
    embed.add_field(name="🔧 Mínimos",  value=f"{cfg['min_skulls']} 💀",                            inline=False)
    embed.add_field(name="✏️ Prefijo",  value=f"`{prefix}`",                                       inline=False)
    embed.add_field(name="🏓 Latencia", value=f"{round(bot.latency*1000)}ms",                     inline=False)
    embed.add_field(name="🔗 Invita",   value=f"[Invitar SkullBoard]({get_invite_url()})",        inline=False)

    if isinstance(dest, discord.Interaction):
        await dest.response.send_message(embed=embed)
    else:
        await dest.send(embed=embed)

# ─── Arranque y sincronización ────────────────────────────────────────────────
@bot.event
async def on_ready():
    logging.info(f"🔧 Bot conectado como {bot.user} ({bot.user.id})")
    # Esto reemplaza tu bucle por guilds:
    synced = await bot.tree.sync()
    logging.info(f"✅ Comandos sincronizados globalmente: {len(synced)} comandos registrados")
    # Sincronizar comandos de aplicación (slash commands)
    await bot.change_presence(activity=discord.Game(name="💀 SkullBoard"))

from types import SimpleNamespace
import discord.abc
from typing import cast

# ── React hooks ──────────────────────────────────────────────────────────────

@bot.event
async def on_raw_reaction_add(payload):
    if payload.user_id == bot.user.id:
        return

    # Obtenemos el canal y comprobamos que es Messageable
    chan = bot.get_channel(payload.thread_id or payload.channel_id)
    if not isinstance(chan, discord.abc.Messageable):
        return
    channel = cast(discord.abc.Messageable, chan)

    try:
        msg = await channel.fetch_message(payload.message_id)  # type: ignore[attr-defined]
    except Exception:
        return

    r = SimpleNamespace(emoji=str(payload.emoji), message=msg)
    await _check(r)

@bot.event
async def on_raw_reaction_remove(payload):
    if payload.user_id == bot.user.id:
        return

    chan = bot.get_channel(payload.thread_id or payload.channel_id)
    if not isinstance(chan, discord.abc.Messageable):
        return
    channel = cast(discord.abc.Messageable, chan)

    try:
        msg = await channel.fetch_message(payload.message_id)  # type: ignore[attr-defined]
    except Exception:
        return

    r = SimpleNamespace(emoji=str(payload.emoji), message=msg)
    await _check(r)


# ── Core logic ────────────────────────────────────────────────────────────────

async def _check(reaction):
    msg = reaction.message
    mid = str(msg.id)
    cfg = get_guild_config(msg.guild.id)

    if reaction.emoji != skull_emoji or mid in processing_messages:
        return
    processing_messages.add(mid)
    try:
        skull_reac = next((r for r in msg.reactions if str(r.emoji) == skull_emoji), None)
        count = skull_reac.count if skull_reac else 0
        if count < cfg["min_skulls"]:
            return

        dest_chan = bot.get_channel(cfg["skullboard_channel_id"])
        if not isinstance(dest_chan, discord.abc.Messageable):
            return
        dest = cast(discord.abc.Messageable, dest_chan)

        emoji = "☠️" if count >= cfg["min_skulls"] * 2 else "💀"
        embed = discord.Embed(description=msg.content or None, color=discord.Color.dark_gray())
        embed.set_author(
            name=msg.author.display_name,
            icon_url=(msg.author.avatar.url if msg.author.avatar else None)
        )

        img = next((a for a in msg.attachments if a.content_type and a.content_type.startswith("image/")), None)
        if img:
            embed.set_image(url=img.url)

        embed.add_field(name="🔗 Enlace", value=f"[Saltar al mensaje]({msg.jump_url})", inline=False)
        embed.set_footer(text=f"{count} {emoji}  •  {formatear_fecha(msg.created_at)}")

        texto = f"{emoji} {count} | {msg.channel.mention}"

        existing = get_tracked_message(mid)
        if existing:
            try:
                old = await dest.fetch_message(existing)  # type: ignore[attr-defined]
                await old.edit(content=texto, embed=embed)
                return
            except discord.NotFound:
                pass

        sent = await dest.send(content=texto, embed=embed)  # type: ignore[attr-defined]
        set_tracked_message(mid, sent.id)

    finally:
        processing_messages.discard(mid)


# ─── COMANDOS CON PREFIJO ─────────────────────────────────────────────────────
@bot.command(name="prefix", aliases=["set_prefix"])
@commands.has_permissions(administrator=True)
async def prefix(ctx, nuevo_prefijo: str=None):
    if not nuevo_prefijo:
        return await ctx.send("❌ ¡Falta el nuevo prefijo!")
    update_guild_config(ctx.guild.id, {"prefix": nuevo_prefijo})
    await ctx.send(f"✅ Prefijo cambiado a `{nuevo_prefijo}`")

@bot.command(name="set_channel", aliases=["channel"])
@commands.has_permissions(administrator=True)
async def set_channel(ctx, canal: discord.TextChannel = None):
    if not canal:
        return await ctx.send("❌ ¡Menciona un canal!")
    update_guild_config(ctx.guild.id, {"skullboard_channel_id": canal.id})
    await ctx.send(f"✅ SkullBoard apuntando a {canal.mention}")

@bot.command(name="set_min", aliases=["min"])
@commands.has_permissions(administrator=True)
async def set_min(ctx, n: int = None):
    if not n or n < 1:
        return await ctx.send("❌ ¡Número inválido!")
    update_guild_config(ctx.guild.id, {"min_skulls": n})
    await ctx.send(f"✅ Mínimo de reacciones ajustado a {n}")

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
    prefix = get_formatted_prefix(ctx)
    embed = discord.Embed(
        title="📖 Lista de comandos - SkullBoard",
        description="Estos son los comandos disponibles:",
        color=discord.Color.teal()
    )
    embed.add_field(name=f"{prefix}ajustes",        value="📋 Ver configuración del bot.", inline=False)
    embed.add_field(name=f"{prefix}set_channel 🔒",  value="📌 Establece el canal de SkullBoard.", inline=False)
    embed.add_field(name=f"{prefix}set_min 🔒",      value="💀 Cambia el mínimo de reacciones.", inline=False)
    embed.add_field(name=f"{prefix}prefix 🔒",   value="✏️ Cambia el prefijo del bot.", inline=False)
    embed.add_field(name=f"{prefix}ping",            value="🏓 Ver latencia del bot.", inline=False)
    embed.add_field(name=f"{prefix}invite",          value="🔗 Obtén el enlace de invitación.", inline=False)
    embed.add_field(name=f"{prefix}help",            value="❓ Muestra esta ayuda.", inline=False)
    embed.set_footer(text="🔒 Requiere permisos de Administrador donde aparezca el candado")
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
    update_guild_config(interaction.guild.id, {"prefix": nuevo_prefijo})
    await interaction.response.send_message(f"✅ Prefijo cambiado a `{nuevo_prefijo}`")

# ─── Slash: configurar canal SkullBoard ────────────────────────────────────────
@tree.command(
    name="set_channel",
    description="Configura el canal del SkullBoard"
)
@app_commands.describe(
    channel="Canal donde se enviarán los mensajes del SkullBoard"
)
async def set_channel_slash(interaction: discord.Interaction, channel: discord.TextChannel):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message(
            "❌ No tienes permiso de **Administrador**.",
            ephemeral=True
        )
    # Actualiza en Supabase
    update_guild_config(interaction.guild.id, {"skullboard_channel_id": channel.id})
    await interaction.response.send_message(
        f"✅ Los mensajes destacados se enviarán a {channel.mention}",
    )

# ─── Slash: fijar mínimo de reacciones ────────────────────────────────────────
@tree.command(
    name="set_min",
    description="Fija el mínimo de reacciones 💀"
)
@app_commands.describe(
    cantidad="Número mínimo de reacciones para destacar un mensaje (≥ 1)"
)
async def set_min_slash(interaction: discord.Interaction, cantidad: int):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message(
            "❌ No tienes permiso de **Administrador**.",
            ephemeral=True
        )
    if cantidad < 1:
        return await interaction.response.send_message(
            "❌ ¡Número inválido! Debe ser ≥ 1.",
            ephemeral=True
        )
    # Actualiza en Supabase
    update_guild_config(interaction.guild.id, {"min_skulls": cantidad})
    await interaction.response.send_message(
        f"✅ Mínimo de reacciones ajustado a {cantidad} 💀",
    )

@tree.command(name="ping", description="Ver latencia")
async def ping_slash(interaction: discord.Interaction):
    await interaction.response.send_message(f"🏓 Pong! `{round(bot.latency*1000)}ms`")

@tree.command(name="invite", description="Invita al bot")
async def invite_slash(interaction: discord.Interaction):
    await interaction.response.send_message(f"🔗 Invita al bot: {get_invite_url()}")

@tree.command(name="help", description="Muestra los comandos disponibles del bot")
async def help_slash(interaction: discord.Interaction):
    prefix = get_formatted_prefix(interaction)
    embed = discord.Embed(
        title="📖 Lista de comandos - SkullBoard",
        description="Estos son los comandos disponibles:",
        color=discord.Color.teal()
    )
    embed.add_field(name=f"{prefix}ajustes",        value="📋 Ver configuración del bot.", inline=False)
    embed.add_field(name=f"{prefix}set_channel 🔒",  value="📌 Establece el canal de SkullBoard.", inline=False)
    embed.add_field(name=f"{prefix}set_min 🔒",      value="💀 Cambia el mínimo de reacciones.", inline=False)
    embed.add_field(name=f"{prefix}prefix 🔒",   value="✏️ Cambia el prefijo del bot.", inline=False)
    embed.add_field(name=f"{prefix}ping",            value="🏓 Ver latencia del bot.", inline=False)
    embed.add_field(name=f"{prefix}invite",          value="🔗 Obtén el enlace de invitación.", inline=False)
    embed.add_field(name=f"{prefix}help",            value="❓ Muestra esta ayuda.", inline=False)
    embed.set_footer(text="🔒 Requiere permisos de Administrador donde aparezca el candado")
    await interaction.response.send_message(embed=embed)

# ─── GESTIÓN DE ERRORES ───────────────────────────────────────────────────────
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        return await ctx.send("❌ No tienes permiso de **Administrador**.")
    if isinstance(error, commands.BadArgument):
        return await ctx.send("❌ Argumento inválido.")
    if isinstance(error, commands.MissingRequiredArgument):
        p = get_formatted_prefix(ctx)
        return await ctx.send(f"❌ Faltan argumentos. Usa `{p}help`.")
    if isinstance(error, commands.CommandNotFound):
        p = get_formatted_prefix(ctx)
        return await ctx.send(f"❌ Comando no existe. Usa `{p}help`.")
    raise error

# ─── EJECUCIÓN ───────────────────────────────────────────────────────────────
webserver.keep_alive()
bot.run(DISCORD_TOKEN)
