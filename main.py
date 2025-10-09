# main.py
import discord
from discord.ext import commands
import asyncio
import os
from gtts import gTTS

# --- 1. CARGA DE CONFIGURACIÓN Y TOKEN ---
from config import (
    VOICE_CHANNEL_ID,
    TTS_BRIDGE_CHANNEL_ID,
    TTS_BRIDGE_ROLE_NAME,
    FOLLOWME_EXEMPT_USER_ID # Carga el ID del usuario exento
)
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

# --- 2. CONFIGURACIÓN DE INTENTS DEL BOT ---
intents = discord.Intents.default()
intents.guilds = True
intents.voice_states = True # Para saber quién entra/sale de canales de voz
intents.members = True  # Para verificar los roles de los miembros
intents.message_content = True  # Para leer el contenido de los mensajes

# --- 3. INICIALIZACIÓN DEL BOT Y VARIABLES DE ESTADO ---
bot = commands.Bot(command_prefix="!", intents=intents)

tts_bridge_enabled = True
followed_user_ids = set() # Almacena los IDs de los usuarios seguidos

# --- 4. FUNCIÓN AUXILIAR PARA TEXT-TO-SPEECH (TTS) ---
async def play_tts(voice_client, text, filename="tts.mp3"):
    """Genera audio desde texto, lo reproduce y luego lo elimina."""
    if not voice_client or not voice_client.is_connected():
        return
    try:
        tts = gTTS(text=text, lang='es', slow=False)
        tts.save(filename)
        while voice_client.is_playing():
            await asyncio.sleep(0.5)
        source = discord.FFmpegPCMAudio(filename)
        voice_client.play(source)
        while voice_client.is_playing():
            await asyncio.sleep(0.5)
        os.remove(filename)
    except Exception as e:
        print(f"Error en play_tts: {e}")
        if os.path.exists(filename):
            os.remove(filename)

# --- 5. EVENTOS PRINCIPALES DEL BOT ---
@bot.event
async def on_ready():
    """Se ejecuta una vez que el bot se conecta a Discord."""
    print(f'✅ Bot conectado como: {bot.user.name} (ID: {bot.user.id})')
    voice_channel = bot.get_channel(VOICE_CHANNEL_ID)
    if voice_channel:
        try:
            await voice_channel.connect()
            print(f'🔗 Conectado a {voice_channel.name}.')
        except Exception as e:
            print(f'❌ Error al conectar al canal de voz: {e}')

@bot.event
async def on_voice_state_update(member, before, after):
    """Gestiona bienvenidas y la reconexión automática del bot."""
    voice_client = discord.utils.get(bot.voice_clients, guild=member.guild)
    
    # Lógica de Bienvenida para Usuarios
    if not member.bot and voice_client and after.channel == voice_client.channel and before.channel != after.channel:
        welcome_message = f"Bienvenido, {member.display_name}"
        await play_tts(voice_client, welcome_message, f"welcome_{member.id}.mp3")

    # Lógica de Reconexión Automática para el Bot
    if member.id == bot.user.id and after.channel is None:
        print("🔴 Bot desconectado. Intentando reconectar en 5 segundos...")
        await asyncio.sleep(5)
        try:
            voice_channel = bot.get_channel(VOICE_CHANNEL_ID)
            if voice_channel:
                await voice_channel.connect()
                print("✅ Bot reconectado exitosamente.")
        except Exception as e:
            print(f"❌ Error al reconectar: {e}")

@bot.event
async def on_message(message):
    """Gestiona la lectura de mensajes con la lógica de anuncio de nombres."""
    if message.author.bot or not message.guild:
        return

    voice_client = discord.utils.get(bot.voice_clients, guild=message.guild)
    if not voice_client:
        await bot.process_application_commands(message)
        return

    text_to_speak = message.content
    should_speak = False

    # Condición 1: Mensaje en el canal puente
    if (tts_bridge_enabled and
        message.channel.id == TTS_BRIDGE_CHANNEL_ID and
        discord.utils.get(message.author.roles, name=TTS_BRIDGE_ROLE_NAME)):
        
        text_to_speak = f"{message.author.display_name} dice: {text_to_speak}"
        should_speak = True
    
    # Condición 2: Mensaje de un usuario seguido
    elif message.author.id in followed_user_ids:
        # Lógica de anuncio de nombre para /followme
        if len(followed_user_ids) > 1 and message.author.id != FOLLOWME_EXEMPT_USER_ID:
            text_to_speak = f"{message.author.display_name} dice: {text_to_speak}"
        
        should_speak = True

    if should_speak:
        await play_tts(voice_client, text_to_speak, f"speech_{message.id}.mp3")

    await bot.process_application_commands(message)

# --- 6. COMANDOS SLASH ---
@bot.slash_command(name="ping", description="Verifica la latencia del bot.")
async def ping(ctx: discord.ApplicationContext):
    await ctx.respond(f"¡Pong! 🏓 Latencia: {round(bot.latency * 1000)}ms", ephemeral=True)

@bot.slash_command(name="bridge", description="Activa o desactiva el puente de texto a voz.")
@commands.has_role(TTS_BRIDGE_ROLE_NAME)
async def bridge(ctx: discord.ApplicationContext, estado: discord.Option(str, choices=["on", "off"])):
    global tts_bridge_enabled
    if estado.lower() == "on":
        tts_bridge_enabled = True
        await ctx.respond("✅ Puente de voz **activado**.", ephemeral=True)
    else:
        tts_bridge_enabled = False
        await ctx.respond("❌ Puente de voz **desactivado**.", ephemeral=True)

@bridge.error
async def bridge_error(ctx, error):
    if isinstance(error, commands.MissingRole):
        await ctx.respond(f"⛔ Necesitas el rol `{TTS_BRIDGE_ROLE_NAME}` para usar este comando.", ephemeral=True)

@bot.slash_command(name="followme", description="Hace que el bot lea en voz alta todo lo que escribes.")
async def followme(ctx: discord.ApplicationContext):
    global followed_user_ids
    if ctx.author.id in followed_user_ids:
        await ctx.respond("El bot ya te está siguiendo.", ephemeral=True)
    else:
        followed_user_ids.add(ctx.author.id)
        await ctx.respond(f"✅ ¡Ok! Leeré tus mensajes. Usa `/unfollowme` para detener.", ephemeral=True)
        print(f"▶️ El bot ahora sigue a {ctx.author.display_name}.")

@bot.slash_command(name="unfollowme", description="Hace que el bot deje de leer tus mensajes.")
async def unfollowme(ctx: discord.ApplicationContext):
    global followed_user_ids
    if ctx.author.id in followed_user_ids:
        followed_user_ids.discard(ctx.author.id)
        await ctx.respond("✅ Dejaré de seguir tus mensajes.", ephemeral=True)
        print(f"⏹️ El bot ha dejado de seguir a {ctx.author.display_name}.")
    else:
        await ctx.respond("El bot no te está siguiendo.", ephemeral=True)

# --- 7. EJECUCIÓN DEL BOT ---
if __name__ == "__main__":
    if not DISCORD_TOKEN:
        print("❌ ERROR CRÍTICO: La variable de entorno DISCORD_TOKEN no está configurada.")
    else:
        bot.run(DISCORD_TOKEN)