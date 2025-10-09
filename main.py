# main.py
import discord
from discord.ext import commands
import asyncio
from gtts import gTTS
import os

# Importamos las variables de configuración
from config import (
    DISCORD_TOKEN,
    VOICE_CHANNEL_ID,
    TTS_BRIDGE_CHANNEL_ID,
    TTS_BRIDGE_ROLE_NAME
)

# 1. CONFIGURACIÓN DE INTENTS
# Necesitamos 'members' para identificar roles y 'message_content' para leer mensajes.
intents = discord.Intents.default()
intents.guilds = True
intents.voice_states = True
intents.members = True  # Requerido para verificar roles
intents.message_content = True  # Requerido para leer el contenido de los mensajes

# 2. INICIALIZACIÓN DEL BOT
# Usamos 'commands.Bot' para poder usar decoradores de roles.
bot = commands.Bot(command_prefix="!", intents=intents)

# Variable global para gestionar el estado del puente de voz
tts_bridge_enabled = True

# 3. FUNCIÓN AUXILIAR PARA REPRODUCIR TTS
# Centralizamos la lógica de TTS para no repetir código. Es una buena práctica.
async def play_tts(voice_client, text, filename="tts.mp3"):
    """Genera audio desde texto y lo reproduce en el cliente de voz."""
    if not voice_client or not voice_client.is_connected():
        print("Error: El cliente de voz no está conectado.")
        return

    try:
        # Generamos el archivo de audio usando gTTS
        tts = gTTS(text=text, lang='es', slow=False)
        tts.save(filename)

        # Esperamos si el bot ya está hablando para no superponer audios
        while voice_client.is_playing():
            await asyncio.sleep(1)

        # Reproducimos el audio
        source = discord.FFmpegPCMAudio(filename)
        voice_client.play(source, after=lambda e: print(f'TTS finalizado, error: {e}') if e else None)

        # Esperamos a que termine la reproducción para borrar el archivo
        while voice_client.is_playing():
            await asyncio.sleep(1)
        
        os.remove(filename)

    except Exception as e:
        print(f"Error en la función play_tts: {e}")
        # Asegurarnos de que el archivo se borre incluso si hay un error
        if os.path.exists(filename):
            os.remove(filename)


# 4. EVENTOS PRINCIPALES
@bot.event
async def on_ready():
    """Se activa cuando el bot está online y listo."""
    print(f'✅ Conectado como {bot.user.name}')
    print('--------------------------------------------------')
    voice_channel = bot.get_channel(VOICE_CHANNEL_ID)

    if voice_channel:
        print(f'Canal de voz encontrado: "{voice_channel.name}"')
        try:
            await voice_channel.connect()
            print('🔗 Conectado exitosamente al canal de voz.')
        except Exception as e:
            print(f'❌ Error al conectar al canal de voz: {e}')
    else:
        print(f'❌ No se encontró el canal de voz con ID {VOICE_CHANNEL_ID}.')

@bot.event
async def on_voice_state_update(member, before, after):
    """Gestiona las bienvenidas personalizadas."""
    # Ignoramos al propio bot para evitar bucles
    if member.bot:
        return

    voice_client = discord.utils.get(bot.voice_clients, guild=member.guild)
    
    # Comprobamos si el usuario entró al mismo canal donde está el bot
    if voice_client and after.channel == voice_client.channel and before.channel != after.channel:
        print(f'👋 {member.display_name} ha entrado al canal.')
        welcome_message = f"Bienvenido al canal, {member.display_name}"
        # Usamos un nombre de archivo único para evitar conflictos si entra gente muy rápido
        await play_tts(voice_client, welcome_message, f"welcome_{member.id}.mp3")

@bot.event
async def on_message(message):
    """Gestiona el puente de texto a voz."""
    # Ignoramos mensajes del propio bot y mensajes privados
    if message.author.bot or not message.guild:
        return

    # Comprobamos si el puente está activo, si el canal es el correcto y si el usuario tiene el rol
    if tts_bridge_enabled and message.channel.id == TTS_BRIDGE_CHANNEL_ID:
        role = discord.utils.get(message.author.roles, name=TTS_BRIDGE_ROLE_NAME)
        if role:
            voice_client = discord.utils.get(bot.voice_clients, guild=message.guild)
            if voice_client and voice_client.is_connected():
                print(f'📢 Leyendo mensaje de {message.author.display_name}: "{message.content}"')
                # Usamos un nombre de archivo único para el puente
                await play_tts(voice_client, message.content, f"bridge_{message.id}.mp3")
    
    # Procesamos los comandos slash si los hubiera (importante no borrar esta línea)
    await bot.process_application_commands(message)


# 5. COMANDOS SLASH
@bot.slash_command(name="ping", description="Verifica la latencia del bot.")
async def ping(ctx: discord.ApplicationContext):
    latency = round(bot.latency * 1000)
    await ctx.respond(f"¡Pong! 🏓 Latencia: {latency}ms")

@bot.slash_command(name="bridge", description="Activa o desactiva el puente de texto a voz.")
@commands.has_role(TTS_BRIDGE_ROLE_NAME) # Restricción: solo usuarios con el rol pueden usarlo
async def bridge(ctx: discord.ApplicationContext, estado: discord.Option(str, choices=["on", "off"])):
    """Activa o desactiva el puente de voz."""
    global tts_bridge_enabled
    if estado.lower() == "on":
        tts_bridge_enabled = True
        await ctx.respond("✅ El puente de texto a voz ha sido **activado**.", ephemeral=True)
    elif estado.lower() == "off":
        tts_bridge_enabled = False
        await ctx.respond("❌ El puente de texto a voz ha sido **desactivado**.", ephemeral=True)

# Manejo de errores para el comando /bridge si el usuario no tiene el rol
@bridge.error
async def bridge_error(ctx, error):
    if isinstance(error, commands.MissingRole):
        await ctx.respond(f"⛔ No tienes permiso para usar este comando. Necesitas el rol `{TTS_BRIDGE_ROLE_NAME}`.", ephemeral=True)
    else:
        raise error

# 6. EJECUCIÓN DEL BOT
if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)