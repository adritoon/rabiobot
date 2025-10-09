# main.py
import discord
from discord.ext import commands
import asyncio
import os
from gtts import gTTS

# --- 1. CARGA DE CONFIGURACIÓN Y TOKEN ---

# Carga las configuraciones no secretas desde config.py
from config import (
    VOICE_CHANNEL_ID,
    TTS_BRIDGE_CHANNEL_ID,
    TTS_BRIDGE_ROLE_NAME
)

# Carga el token secreto desde las variables de entorno del servidor.
# Esto es más seguro que escribir el token directamente en el código.
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

# --- 2. CONFIGURACIÓN DE INTENTS DEL BOT ---

# Los intents son los permisos que le damos al bot para recibir ciertos eventos.
intents = discord.Intents.default()
intents.guilds = True
intents.voice_states = True  # Para saber quién entra/sale de canales de voz
intents.members = True       # Para verificar los roles de los miembros
intents.message_content = True # Para leer el contenido de los mensajes

# --- 3. INICIALIZACIÓN DEL BOT ---

# Usamos 'commands.Bot' para poder gestionar comandos y roles fácilmente.
bot = commands.Bot(command_prefix="!", intents=intents)

# Variable global para gestionar el estado del puente de voz.
tts_bridge_enabled = True

# --- 4. FUNCIÓN AUXILIAR PARA TEXT-TO-SPEECH (TTS) ---

async def play_tts(voice_client, text, filename="tts.mp3"):
    """Genera audio desde texto, lo reproduce y luego lo elimina."""
    if not voice_client or not voice_client.is_connected():
        print("Error: El cliente de voz no está conectado para reproducir TTS.")
        return

    try:
        # Genera el archivo de audio usando la librería de Google Text-to-Speech.
        tts = gTTS(text=text, lang='es', slow=False)
        tts.save(filename)

        # Espera si el bot ya está hablando para no crear un caos de voces.
        while voice_client.is_playing():
            await asyncio.sleep(0.5)

        # Crea la fuente de audio y la reproduce.
        source = discord.FFmpegPCMAudio(filename)
        voice_client.play(source)

        # Espera a que termine la reproducción para poder borrar el archivo.
        while voice_client.is_playing():
            await asyncio.sleep(0.5)
        
        os.remove(filename)

    except Exception as e:
        print(f"Error en la función play_tts: {e}")
        # Asegura la eliminación del archivo temporal incluso si hay un error.
        if os.path.exists(filename):
            os.remove(filename)

# --- 5. EVENTOS PRINCIPALES DEL BOT ---

@bot.event
async def on_ready():
    """Se ejecuta una vez que el bot se conecta exitosamente a Discord."""
    print(f'✅ Bot conectado como: {bot.user.name} (ID: {bot.user.id})')
    print('--------------------------------------------------')
    
    voice_channel = bot.get_channel(VOICE_CHANNEL_ID)
    if voice_channel:
        print(f'Canal de voz encontrado: "{voice_channel.name}"')
        try:
            await voice_channel.connect()
            print('🔗 Conectado exitosamente al canal de voz 24/7.')
        except Exception as e:
            print(f'❌ Error al conectar al canal de voz: {e}')
    else:
        print(f'❌ No se encontró el canal de voz con ID {VOICE_CHANNEL_ID}.')

@bot.event
async def on_voice_state_update(member, before, after):
    """Gestiona las bienvenidas personalizadas cuando un usuario entra al canal."""
    # Ignora al propio bot para evitar bucles.
    if member.bot:
        return

    voice_client = discord.utils.get(bot.voice_clients, guild=member.guild)
    
    # Comprueba si un usuario ENTRÓ al mismo canal donde está el bot.
    if voice_client and after.channel == voice_client.channel and before.channel != after.channel:
        print(f'👋 {member.display_name} ha entrado al canal.')
        welcome_message = f"Bienvenido, {member.display_name}"
        # Usa un nombre de archivo único para evitar conflictos si varios usuarios entran a la vez.
        await play_tts(voice_client, welcome_message, f"welcome_{member.id}.mp3")

@bot.event
async def on_message(message):
    """Gestiona el puente de texto a voz desde el canal designado."""
    # Ignora mensajes del propio bot, de otros bots y mensajes privados.
    if message.author.bot or not message.guild:
        return

    # Comprueba si se cumplen todas las condiciones para leer el mensaje en voz alta.
    if tts_bridge_enabled and message.channel.id == TTS_BRIDGE_CHANNEL_ID:
        role = discord.utils.get(message.author.roles, name=TTS_BRIDGE_ROLE_NAME)
        if role:
            voice_client = discord.utils.get(bot.voice_clients, guild=message.guild)
            if voice_client and voice_client.is_connected():
                print(f'📢 Leyendo mensaje de {message.author.display_name}: "{message.content}"')
                await play_tts(voice_client, message.content, f"bridge_{message.id}.mp3")
    
    # Es importante mantener esta línea para que los comandos slash sigan funcionando.
    await bot.process_application_commands(message)

# --- 6. COMANDOS SLASH ---

@bot.slash_command(name="ping", description="Verifica la latencia del bot.")
async def ping(ctx: discord.ApplicationContext):
    """Responde con 'Pong!' y la latencia del bot."""
    latency = round(bot.latency * 1000)
    await ctx.respond(f"¡Pong! 🏓 Latencia: {latency}ms", ephemeral=True)

@bot.slash_command(name="bridge", description="Activa o desactiva el puente de texto a voz.")
@commands.has_role(TTS_BRIDGE_ROLE_NAME) # Restricción de rol.
async def bridge(ctx: discord.ApplicationContext, estado: discord.Option(str, choices=["on", "off"])):
    """Comando para controlar el estado del puente de voz."""
    global tts_bridge_enabled
    if estado.lower() == "on":
        tts_bridge_enabled = True
        await ctx.respond("✅ El puente de texto a voz ha sido **activado**.", ephemeral=True)
    elif estado.lower() == "off":
        tts_bridge_enabled = False
        await ctx.respond("❌ El puente de texto a voz ha sido **desactivado**.", ephemeral=True)

# Manejo de errores específico para el comando /bridge.
@bridge.error
async def bridge_error(ctx, error):
    if isinstance(error, commands.MissingRole):
        await ctx.respond(f"⛔ No tienes permiso. Necesitas el rol `{TTS_BRIDGE_ROLE_NAME}`.", ephemeral=True)
    else:
        raise error

# --- 7. EJECUCIÓN DEL BOT ---

if __name__ == "__main__":
    if not DISCORD_TOKEN:
        print("❌ ERROR CRÍTICO: La variable de entorno DISCORD_TOKEN no está configurada.")
    else:
        bot.run(DISCORD_TOKEN)