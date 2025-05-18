import discord
from discord.ext import commands
from discord import app_commands
import json
import os
import webserver
from datetime import datetime, timezone, timedelta

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

# Cargar toda la config
def load_config():
    try:
        with open('config.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

# Guardar toda la config
def save_config(data):
    with open('config.json', 'w') as f:
        json.dump(data, f, indent=4)

# Cargar mensajes rastreados del JSON
def load_tracked_messages():
    try:
        with open("tracked_messages.json", "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

# Guardar mensajes rastreados al JSON
def save_tracked_messages():
    with open("tracked_messages.json", "w") as f:
        json.dump(tracked_messages, f, indent=4)

# Obtener o crear config para un servidor específico
def get_guild_config(guild_id):
    guild_id = str(guild_id)
    if guild_id not in config:
        config[guild_id] = {
            "skullboard_channel_id": 0,
            "min_skulls": 1,
            "prefix": "sk!"
        }
        save_config(config)
    if "prefix" not in config[guild_id]:
        config[guild_id]["prefix"] = "sk!"
        save_config(config)
    return config[guild_id]


config = load_config()

intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True
intents.guilds = True
intents.members = True
intents.messages = True

async def get_prefix(bot, message):
    if not message.guild:
        return "sk!"  # predeterminado para DMs
    guild_config = get_guild_config(message.guild.id)
    return guild_config.get("prefix", "sk!")


bot = commands.Bot(command_prefix=get_prefix, intents=intents, help_command=None)

tree = bot.tree
skull_emoji = '💀'
tracked_messages = load_tracked_messages()
processing_messages = set()

def get_formatted_prefix(ctx_or_interaction) -> str:
    if isinstance(ctx_or_interaction, discord.Interaction):
        guild_id = ctx_or_interaction.guild.id
    else:
        guild_id = ctx_or_interaction.guild.id
    return get_guild_config(guild_id).get("prefix", "sk!")

# Evento de inicio
@bot.event
async def on_ready():
    import time
    print("⏳ Esperando a que el bot esté completamente listo...")
    await bot.wait_until_ready()
    time.sleep(1)  # Forzar espera mínima por si Render lo trunca

    print(f'🔧 Bot conectado como {bot.user.name} - {bot.user.id}')
    print(f'📌 Mensajes rastreados cargados: {len(tracked_messages)}')
    print(f'🗂️ Configuración cargada: {len(config)} servidores')
    print(f'🤖 Estoy en {len(bot.guilds)} servidores:')
    for guild in bot.guilds:
        print(f" - {guild.name} (ID: {guild.id})")

    for guild in bot.guilds:
        try:
            synced = await tree.sync(guild=guild)
            print(f"✅ Slash commands sincronizados en: {guild.name} ({guild.id}) → {len(synced)} comandos")
        except Exception as e:
            print(f"❌ Error al sincronizar en {guild.name} ({guild.id}): {e}")

    print("🔗 Bot en línea y listo para recibir comandos.")

### ========== COMANDOS CON PREFIJO ==========

@bot.command()
@commands.has_permissions(administrator=True)
async def set_prefix(ctx, nuevo_prefijo: str = None):
    if not nuevo_prefijo:
        await ctx.send("❌ Debes proporcionar un nuevo prefijo. Ejemplo: `sk!set_prefix ?`")
        return

    guild_config = get_guild_config(ctx.guild.id)
    guild_config["prefix"] = nuevo_prefijo
    save_config(config)
    await ctx.send(f"✅ Prefijo actualizado a `{nuevo_prefijo}`")

@bot.command()
async def ajustes(ctx):
    await send_ajustes_embed(ctx)

@bot.command()
@commands.has_permissions(administrator=True)
async def set_channel(ctx, channel: discord.TextChannel = None):
    if channel is None:
        await ctx.send("❌ Debes mencionar un canal válido. Ejemplo: `sk!set_channel #nombre-del-canal`")
        return

    guild_config = get_guild_config(ctx.guild.id)
    guild_config["skullboard_channel_id"] = channel.id
    save_config(config)
    await ctx.send(f"✅ Canal del SkullBoard configurado en {channel.mention}")

@bot.command()
@commands.has_permissions(administrator=True)
async def set_min(ctx, cantidad: int = None):
    if cantidad is None or cantidad <= 0:
        await ctx.send("❌ Debes proporcionar una cantidad válida mayor que 0. Ejemplo: `sk!set_min 3`")
        return

    guild_config = get_guild_config(ctx.guild.id)
    guild_config["min_skulls"] = cantidad
    save_config(config)
    await ctx.send(f"✅ Reacciones mínimas actualizadas a {cantidad}")



@bot.command()
async def help(ctx):
    prefix = get_formatted_prefix(ctx)

    embed = discord.Embed(
        title="📖 Lista de comandos - SkullBoard",
        description="Aquí tienes los comandos disponibles del bot.",
        color=discord.Color.teal()
    )
    embed.add_field(name=f"{prefix}ajustes", value="📋 Ver configuración del bot.", inline=False)
    embed.add_field(name=f"{prefix}set_channel 🔒", value="📌 Establece el canal de SkullBoard.", inline=False)
    embed.add_field(name=f"{prefix}set_min 🔒", value="💀 Cambia el mínimo de reacciones.", inline=False)
    embed.add_field(name=f"{prefix}set_prefix 🔒", value="✏️ Cambia el prefijo del bot.", inline=False)
    embed.add_field(name=f"{prefix}ping", value="🏓 Ver latencia del bot.", inline=False)
    embed.add_field(name=f"{prefix}invite", value="🔗 Invita al bot a tu servidor.", inline=False)
    embed.add_field(name=f"{prefix}help", value="❓ Muestra esta ayuda.", inline=False)

    embed.set_footer(text="🔒 Requiere permisos de administrador • También puedes usar los comandos con barra (/).")
    embed.set_thumbnail(url=bot.user.avatar.url if bot.user.avatar else None)
    await ctx.send(embed=embed)



@bot.command()
async def ping(ctx):
    latency = round(bot.latency * 1000)
    embed = discord.Embed(
        title="🏓 Pong!",
        description=f"Latencia actual: `{latency}ms`",
        color=discord.Color.green()
    )
    await ctx.send(embed=embed)

@bot.command()
async def invite(ctx):
    invite_url = get_invite_url()
    embed = discord.Embed(
        title="🔗 Invita a SkullBoard",
        description=f"[Haz clic aquí para invitar al bot a tu servidor]({invite_url})",
        color=discord.Color.blue()
    )
    await ctx.send(embed=embed)

def formatear_fecha(fecha: datetime) -> str:
    ahora = datetime.now(timezone.utc)
    diferencia = ahora.date() - fecha.date()
    hora_min = fecha.strftime("%H:%M")

    if diferencia.days == 0:
        return f"Hoy a las {hora_min}"
    elif diferencia.days == 1:
        return f"Ayer a las {hora_min}"
    else:
        return fecha.strftime("%d/%m/%Y %H:%M")

@bot.command(name="servers", hidden=True)
@commands.has_permissions(administrator=True)
async def servers(ctx):
    servidores = bot.guilds
    total = len(servidores)
    
    texto = "\n".join(f"• {g.name} (`{g.id}`)" for g in servidores)
    if len(texto) > 1900:
        texto = texto[:1900] + "\n... (truncado)"
    
    embed = discord.Embed(
        title=f"🌍 El bot está en {total} servidor{'es' if total != 1 else ''}:",
        description=texto,
        color=discord.Color.gold()
    )
    await ctx.send(embed=embed)

### ========== COMANDOS DE BARRA ==========

@tree.command(name="set_prefix", description="Cambia el prefijo de comandos del bot (admin)")
@app_commands.describe(nuevo_prefijo="El nuevo prefijo que quieres usar")
async def set_prefix_slash(interaction: discord.Interaction, nuevo_prefijo: str):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message(
            "❌ Necesitas permisos de **Administrador** para usar este comando.",
            ephemeral=True
        )
        return

    guild_config = get_guild_config(interaction.guild.id)
    guild_config["prefix"] = nuevo_prefijo
    save_config(config)
    await interaction.response.send_message(f"✅ Prefijo actualizado a `{nuevo_prefijo}`")

@tree.command(name="ajustes", description="Muestra los ajustes actuales del bot")
async def ajustes_slash(interaction: discord.Interaction):
    await send_ajustes_embed(interaction)

@tree.command(name="set_channel", description="Configura el canal del SkullBoard")
@app_commands.describe(channel="Canal de destino para los mensajes con 💀")
async def set_channel_slash(interaction: discord.Interaction, channel: discord.TextChannel):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message(
            "❌ Necesitas permisos de **Administrador** para usar este comando.",
            ephemeral=True
        )
        return

    guild_config = get_guild_config(interaction.guild.id)
    guild_config["skullboard_channel_id"] = channel.id
    save_config(config)
    await interaction.response.send_message(f'✅ Canal del SkullBoard configurado en {channel.mention}')

@tree.command(name="set_min", description="Configura la cantidad mínima de reacciones 💀")
@app_commands.describe(cantidad="Número mínimo de reacciones para enviar al SkullBoard")
async def set_min_slash(interaction: discord.Interaction, cantidad: int):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message(
            "❌ Necesitas permisos de **Administrador** para usar este comando.",
            ephemeral=True
        )
        return

    guild_config = get_guild_config(interaction.guild.id)
    guild_config["min_skulls"] = cantidad
    save_config(config)
    await interaction.response.send_message(f'✅ Reacciones mínimas actualizadas a {cantidad}')

@tree.command(name="ping", description="Muestra la latencia actual del bot")
async def ping_slash(interaction: discord.Interaction):
    latency = round(bot.latency * 1000)
    embed = discord.Embed(
        title="🏓 Pong!",
        description=f"Latencia actual: `{latency}ms`",
        color=discord.Color.green()
    )
    await interaction.response.send_message(embed=embed)

@tree.command(name="invite", description="Obtén el enlace de invitación del bot")
async def invite_slash(interaction: discord.Interaction):
    invite_url = get_invite_url()
    embed = discord.Embed(
        title="🔗 Invita a SkullBoard",
        description=f"[Haz clic aquí para invitar al bot a tu servidor]({invite_url})",
        color=discord.Color.blue()
    )
    await interaction.response.send_message(embed=embed)

@tree.command(name="help", description="Muestra los comandos disponibles del bot")
async def help_slash(interaction: discord.Interaction):
    prefix = get_formatted_prefix(interaction)

    embed = discord.Embed(
        title="📖 Lista de comandos - SkullBoard",
        description="Aquí tienes los comandos disponibles del bot.",
        color=discord.Color.teal()
    )
    embed.add_field(name="/ajustes", value="📋 Ver configuración del bot.", inline=False)
    embed.add_field(name="/set_channel 🔒", value="📌 Establece el canal de SkullBoard.", inline=False)
    embed.add_field(name="/set_min 🔒", value="💀 Cambia el mínimo de reacciones.", inline=False)
    embed.add_field(name="/set_prefix 🔒", value="✏️ Cambia el prefijo del bot.", inline=False)
    embed.add_field(name="/ping", value="🏓 Ver latencia del bot.", inline=False)
    embed.add_field(name="/invite", value="🔗 Invita al bot a tu servidor.", inline=False)

    embed.set_footer(text=f"🔒 Requiere permisos de administrador • También puedes usar los comandos con `{prefix}` si lo prefieres.")
    embed.set_thumbnail(url=bot.user.avatar.url if bot.user.avatar else None)

    await interaction.response.send_message(embed=embed)

### ========== FUNCIONES COMUNES ==========

def get_invite_url():
    client_id = 1367463352774955059
    permissions = 277025508352
    return f"https://discord.com/oauth2/authorize?client_id={client_id}&permissions={permissions}&scope=bot+applications.commands"

async def send_ajustes_embed(dest):
    if isinstance(dest, discord.Interaction):
        guild_id = dest.guild.id
    else:
        guild_id = dest.guild.id

    guild_config = get_guild_config(guild_id)
    skull_channel = bot.get_channel(guild_config["skullboard_channel_id"])
    prefix = guild_config.get("prefix", "sk!")

    embed = discord.Embed(
        title="⚙️ Ajustes del SkullBoard",
        description="Configuración actual del bot:",
        color=discord.Color.purple()
    )
    embed.add_field(name="📌 Canal configurado", value=skull_channel.mention if skull_channel else "❌ No configurado", inline=False)
    embed.add_field(name="🔧 Reacciones mínimas", value=f"{guild_config['min_skulls']} 💀", inline=False)
    embed.add_field(name="✏️ Prefijo actual", value=f"`{prefix}`", inline=False)
    embed.add_field(name="🏓 Latencia", value=f"{round(bot.latency * 1000)}ms", inline=False)
    embed.add_field(name="🔗 Invitación", value=f"[Invitar SkullBoard]({get_invite_url()})", inline=False)

    if isinstance(dest, discord.Interaction):
        await dest.response.send_message(embed=embed)
    else:
        await dest.send(embed=embed)



### ========== EVENTOS DE REACCIÓN ==========
@bot.event
async def on_reaction_add(reaction, user):
    await check_reaction(reaction)

@bot.event
async def on_reaction_remove(reaction, user):
    await check_reaction(reaction)

async def check_reaction(reaction):
    message = reaction.message
    message_id = str(message.id)  # Usamos el ID como string para el diccionario
    guild_config = get_guild_config(message.guild.id)

    # 🚫 Evitar procesar varias veces el mismo mensaje al mismo tiempo
    if message_id in processing_messages:
        return
    processing_messages.add(message_id)

    try:
        # 💀 Solo procesar reacciones con el emoji correspondiente
        if str(reaction.emoji) != skull_emoji:
            return

        # 📉 Verificar si se alcanzó el umbral mínimo de reacciones
        if reaction.count < guild_config["min_skulls"]:
            return

        # 📍 Obtener el canal destino del SkullBoard
        skullboard_channel = bot.get_channel(guild_config["skullboard_channel_id"])
        if not skullboard_channel or not message.guild:
            return

        # 🚫 Evitar republicar mensajes que ya están en el canal SkullBoard
        if message.channel.id == skullboard_channel.id:
            return

        # ✅ Verificar si el mensaje tiene texto o adjuntos
        has_text = bool(message.content.strip())
        attachments = message.attachments

        # 🖼️ Buscar la primera imagen adjunta (si existe)
        image_attachment = next(
            (a for a in attachments if a.content_type and a.content_type.startswith("image/")),
            None
        )

        # 🧼 Ignorar mensajes completamente vacíos
        if not has_text and not attachments:
            return

        # 🧠 Elegir emoji según la cantidad de reacciones
        emoji = "☠️" if reaction.count >= guild_config["min_skulls"] * 2 else "💀"
        fecha_formateada = formatear_fecha(message.created_at)

        # 📦 Crear el embed para mostrar el contenido
        embed = discord.Embed(
            description=message.content if has_text else None,
            color=discord.Color.dark_gray()
        )
        embed.set_author(
            name=message.author.display_name,
            icon_url=message.author.avatar.url if message.author.avatar else None
        )

        if image_attachment:
            embed.set_image(url=image_attachment.url)

        # 📎 Adjuntar archivos no-imagen como enlaces
        non_image_attachments = [
            a for a in attachments
            if not (a.content_type and a.content_type.startswith("image/"))
        ]
        if non_image_attachments:
            files_list = "\n".join(f"[{a.filename}]({a.url})" for a in non_image_attachments)
            embed.add_field(name="🗂️ Archivos adjuntos", value=files_list, inline=False)

        # 🔗 Agregar enlace al mensaje original
        jump_link = f"[Saltar al mensaje]({message.jump_url})"
        embed.add_field(name="🔗 Enlace", value=jump_link, inline=False)

        # 🦶 Pie de embed con info de reacciones y fecha
        embed.set_footer(text=f"{reaction.count} {emoji}  •  {fecha_formateada}")

        # ✏️ Texto visible fuera del embed
        skullboard_text = f"{emoji} {reaction.count} | {message.channel.mention}"

        # 🔄 Si ya existe en el SkullBoard, editar
        if message_id in tracked_messages:
            try:
                existing_msg = await skullboard_channel.fetch_message(tracked_messages[message_id])
                await existing_msg.edit(content=skullboard_text, embed=embed)
                return
            except discord.NotFound:
                pass  # Si fue borrado, continuar para reenviarlo

        # 🆕 Publicar por primera vez
        sent_msg = await skullboard_channel.send(content=skullboard_text, embed=embed)
        tracked_messages[message_id] = sent_msg.id
        save_tracked_messages()

    finally:
        processing_messages.discard(message_id)  # 🔓 Liberar bloqueo para este mensaje

### ========== GESTIÓN DE ERRORES ==========
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ No tienes permiso de **Administrador** para usar este comando.")
    elif isinstance(error, commands.BadArgument):
        await ctx.send("❌ Argumento inválido. Verifica el tipo de dato o el formato.")
    elif isinstance(error, commands.MissingRequiredArgument):
        prefix = get_formatted_prefix(ctx)
        await ctx.send(f"❌ Faltan argumentos. Usa `{prefix}help` para ver cómo se usa el comando.")
    elif isinstance(error, commands.CommandNotFound):
        prefix = get_formatted_prefix(ctx)
        await ctx.send(f"❌ Ese comando no existe. Usa `{prefix}help` para ver los comandos disponibles.")
    else:
        raise error  # Útil para depurar errores inesperados


### ========== EJECUCIÓN ==========

webserver.keep_alive()
bot.run(DISCORD_TOKEN)
# El token y el ID del bot se encuentran en el archivo secrets_1.py
# Asegúrate de que el archivo config.json esté en la misma carpeta que este script y tenga el siguiente formato: