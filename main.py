import discord
import logging
import os
import webserver
from datetime import datetime, timezone
from discord.ext import commands
from discord import app_commands
from supabase import create_client

# ─── Configuración de Supabase ───────────────────────────────────────────────
DISCORD_TOKEN  = os.getenv("DISCORD_TOKEN")
SUPABASE_URL   = os.getenv("SUPABASE_URL")
SUPABASE_KEY   = os.getenv("SUPABASE_KEY")
supabase       = create_client(SUPABASE_URL, SUPABASE_KEY)

# ─── Funciones de configuración ────────────────────────────────────────────────
def get_guild_config(guild_id):
    guild_id = str(guild_id)
    resp = supabase.table("settings").select("*").eq("guild_id", guild_id).execute()
    if resp.data:
        return resp.data[0]
    default = {
        "guild_id": guild_id,
        "skullboard_channel_id": 0,
        "min_skulls": 1,
        "prefix": "sk!"
    }
    supabase.table("settings").insert(default).execute()
    return default

def update_guild_config(guild_id, updates: dict):
    supabase.table("settings").update(updates).eq("guild_id", str(guild_id)).execute()

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
    client_id  = 1367463352774955059
    permissions= 277025508352
    return f"https://discord.com/oauth2/authorize?client_id={client_id}&permissions={permissions}&scope=bot+applications.commands"

async def send_ajustes_embed(dest):
    guild_cfg     = get_guild_config(dest.guild.id)
    skull_channel = bot.get_channel(guild_cfg["skullboard_channel_id"])
    prefix        = guild_cfg.get("prefix", "sk!")
    embed = discord.Embed(
        title="⚙️ Ajustes del SkullBoard",
        description="Configuración actual del bot:",
        color=discord.Color.purple()
    )
    embed.add_field(name="📌 Canal",    value=skull_channel.mention if skull_channel else "❌ No configurado", inline=False)
    embed.add_field(name="🔧 Mínimos",  value=f"{guild_cfg['min_skulls']} 💀",                 inline=False)
    embed.add_field(name="✏️ Prefijo",  value=f"`{prefix}`",                               inline=False)
    embed.add_field(name="🏓 Latencia", value=f"{round(bot.latency*1000)}ms",              inline=False)
    embed.add_field(name="🔗 Invita",   value=f"[Invitar]({get_invite_url()})",            inline=False)

    if isinstance(dest, discord.Interaction):
        await dest.response.send_message(embed=embed)
    else:
        await dest.send(embed=embed)

# ─── Persistencia de mensajes ────────────────────────────────────────────────
def get_tracked_message(msg_id: str):
    resp = supabase.table("tracked_messages").select("skullboard_message_id").eq("message_id", msg_id).execute()
    return resp.data[0]["skullboard_message_id"] if resp.data else None

def set_tracked_message(msg_id: str, skull_id: int):
    supabase.table("tracked_messages").upsert({
        "message_id": msg_id,
        "skullboard_message_id": skull_id
    }).execute()

# ─── Eventos básicos ─────────────────────────────────────────────────────────
@bot.event
async def on_ready():
    logging.info(f"🔧 Conectado como {bot.user} ({bot.user.id})")
    for guild in bot.guilds:
        try:
            cmds = await tree.sync(guild=guild)
            logging.info(f"✅ Slash sync en {guild.name} → {len(cmds)} cmd(s)")
        except Exception as e:
            logging.error(f"❌ Sync failed en {guild.name}: {e}")
    logging.info("🔗 Bot listo.")

# ─── Reacciones ───────────────────────────────────────────────────────────────
@bot.event
async def on_reaction_add(reaction, user):
    await _check(reaction)

@bot.event
async def on_reaction_remove(reaction, user):
    await _check(reaction)

async def _check(reaction):
    msg      = reaction.message
    msg_id   = str(msg.id)
    cfg      = get_guild_config(msg.guild.id)
    if str(reaction.emoji)!=skull_emoji or msg_id in processing_messages:
        return
    processing_messages.add(msg_id)
    try:
        if reaction.count < cfg["min_skulls"]:
            return
        dest = bot.get_channel(cfg["skullboard_channel_id"])
        if not dest or msg.channel.id==dest.id:
            return
        emoji = "☠️" if reaction.count>=cfg["min_skulls"]*2 else "💀"
        embed = discord.Embed(description=msg.content or None, color=discord.Color.dark_gray())
        embed.set_author(name=msg.author.display_name, icon_url=msg.author.avatar.url if msg.author.avatar else None)
        img = next((a for a in msg.attachments if a.content_type and a.content_type.startswith("image/")), None)
        if img:
            embed.set_image(url=img.url)
        embed.add_field(name="🔗 Enlace", value=f"[Saltar al mensaje]({msg.jump_url})", inline=False)
        embed.set_footer(text=f"{reaction.count} {emoji}  •  {formatear_fecha(msg.created_at)}")
        texto = f"{emoji} {reaction.count} | {msg.channel.mention}"

        exist_id = get_tracked_message(msg_id)
        if exist_id:
            try:
                sent = await dest.fetch_message(exist_id)
                await sent.edit(content=texto, embed=embed)
                return
            except discord.NotFound:
                pass
        sent = await dest.send(content=texto, embed=embed)
        set_tracked_message(msg_id, sent.id)
    finally:
        processing_messages.discard(msg_id)

# ─── Comandos de texto ────────────────────────────────────────────────────────
@bot.command()
@commands.has_permissions(administrator=True)
async def set_prefix(ctx, nuevo_prefijo: str=None):
    if not nuevo_prefijo:
        return await ctx.send("❌ ¡Falta el nuevo prefijo!")
    update_guild_config(ctx.guild.id, {"prefix": nuevo_prefijo})
    await ctx.send(f"✅ Prefijo cambiado a `{nuevo_prefijo}`")

@bot.command()
@commands.has_permissions(administrator=True)
async def set_channel(ctx, canal: discord.TextChannel=None):
    if not canal:
        return await ctx.send("❌ ¡Menciona un canal!")
    update_guild_config(ctx.guild.id, {"skullboard_channel_id": canal.id})
    await ctx.send(f"✅ SkullBoard apuntando a {canal.mention}")

@bot.command()
@commands.has_permissions(administrator=True)
async def set_min(ctx, n: int=None):
    if not n or n<1:
        return await ctx.send("❌ ¡Número inválido!")
    update_guild_config(ctx.guild.id, {"min_skulls": n})
    await ctx.send(f"✅ Mínimo de reacciones ajustado a {n}")

@bot.command()
async def ajustes(ctx):
    await send_ajustes_embed(ctx)

@bot.command()
async def ping(ctx):
    await ctx.send(f"🏓 Pong! `{round(bot.latency*1000)}ms`")

@bot.command()
async def invite(ctx):
    await ctx.send(get_invite_url())

# ─── Slash commands ──────────────────────────────────────────────────────────
@tree.command(name="ajustes", description="Ver ajustes actuales")
async def ajustes_slash(interaction: discord.Interaction):
    await send_ajustes_embed(interaction)

@tree.command(name="set_prefix", description="Cambiar prefijo (admin)")
@app_commands.describe(nuevo_prefijo="Prefijo nuevo")
async def set_prefix_slash(interaction: discord.Interaction, nuevo_prefijo: str):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("❌ ¡No tienes permiso!", ephemeral=True)
    update_guild_config(interaction.guild.id, {"prefix": nuevo_prefijo})
    await interaction.response.send_message(f"✅ Prefijo `{nuevo_prefijo}`")

@tree.command(name="set_channel", description="Configurar canal SkullBoard")
@app_commands.describe(canal="Canal destino")
async def set_channel_slash(interaction: discord.Interaction, canal: discord.TextChannel):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("❌ ¡No tienes permiso!", ephemeral=True)
    update_guild_config(interaction.guild.id, {"skullboard_channel_id": canal.id})
    await interaction.response.send_message(f"✅ Canal set a {canal.mention}")

@tree.command(name="set_min", description="Fijar mínimo de reacciones")
@app_commands.describe(n="Número mínimo")
async def set_min_slash(interaction: discord.Interaction, n: int):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("❌ ¡No tienes permiso!", ephemeral=True)
    update_guild_config(interaction.guild.id, {"min_skulls": n})
    await interaction.response.send_message(f"✅ Mínimo {n}")

@tree.command(name="ping", description="Ver latencia")
async def ping_slash(interaction: discord.Interaction):
    await interaction.response.send_message(f"🏓 Pong `{round(bot.latency*1000)}ms`")

@tree.command(name="invite", description="Invita al bot")
async def invite_slash(interaction: discord.Interaction):
    await interaction.response.send_message(get_invite_url())

# ─── Arranque ────────────────────────────────────────────────────────────────
webserver.keep_alive()
bot.run(DISCORD_TOKEN)
