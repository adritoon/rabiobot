import discord
from discord.ext import commands, tasks
import asyncio
import os
from dotenv import load_dotenv
from gtts import gTTS
import re
import discord.opus # CRÍTICO PARA LINUX

# --- CARGA DE CONFIGURACIÓN ---
try:
    from config import (
        VOICE_CHANNEL_ID,
        TTS_BRIDGE_CHANNEL_ID,
        TTS_BRIDGE_ROLE_NAME,
        FOLLOWME_EXEMPT_USER_ID
    )
except ImportError:
    print("⚠️ Error: No encontré config.py. Asegúrate de crear ese archivo con las variables.")
    VOICE_CHANNEL_ID = 0 # Evita que el bot crashee si falta el archivo

load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

# --- PARCHE PARA VM DE GOOGLE CLOUD (Evita 'Unclosed Connection') ---
if not discord.opus.is_loaded():
    try:
        discord.opus.load_opus('libopus.so.0')
        print("✅ Librería de audio (Opus) cargada manualmente.")
    except Exception as e:
        print(f"⚠️ Advertencia: No se pudo cargar Opus automáticamente: {e}")
        print("ℹ️ Si el bot se desconecta, ejecuta: sudo apt install libopus0")

# --- INTENTS ---
intents = discord.Intents.default()
intents.message_content = True
# intents.voice_states = True # Lo desactivamos para evitar conflictos
bot = commands.Bot(command_prefix="!", intents=intents)

# --- VARIABLES ---
followed_user_ids = set()

# --- SISTEMA DE AUDIO ---
async def play_tts(voice_client, text):
    if not voice_client or not voice_client.is_connected(): return
    try:
        # Si ya está hablando, no interrumpimos
        if voice_client.is_playing(): return 

        # Nombre aleatorio para evitar conflictos de archivos
        filename = f"tts_{os.urandom(4).hex()}.mp3"
        
        # Generar audio
        tts = gTTS(text=text, lang='es', slow=False)
        tts.save(filename)
        
        # Opciones de FFmpeg (Velocidad 1.25x)
        ffmpeg_options = {"options": "-af atempo=1.25"}
        source = discord.FFmpegPCMAudio(filename, **ffmpeg_options)
        
        # Reproducir y borrar archivo al terminar
        voice_client.play(source, after=lambda e: clean_file(filename))
    except Exception as e:
        print(f"❌ Error audio: {e}")
        clean_file(filename)

def clean_file(filename):
    if os.path.exists(filename):
        try: os.remove(filename)
        except: pass

# --- GUARDIA DE SEGURIDAD (Versión Flexible) ---
# Revisa la conexión cada 30 segundos
@tasks.loop(seconds=30) 
async def maintenance_loop():
    # 1. Verificar si el bot ya está conectado a CUALQUIER canal
    voice_client = None
    for guild in bot.guilds:
        if guild.voice_client:
            voice_client = guild.voice_client
            break

    # 2. Canal por defecto (Lobby)
    default_channel = bot.get_channel(VOICE_CHANNEL_ID)
    
    try:
        # CASO A: El bot está totalmente desconectado -> Ir al Lobby
        if voice_client is None:
            if default_channel:
                print(f"🔌 Conectando al canal de inicio...")
                await default_channel.connect()
            else:
                print("⚠️ No encuentro el canal por defecto (Revisa el ID en config.py).")

        # CASO B: El bot cree que está conectado, pero la conexión murió -> Reiniciar
        elif not voice_client.is_connected():
            print("⚠️ Conexión muerta detectada. Reiniciando...")
            await voice_client.disconnect(force=True)
            
        # CASO C: El bot está conectado y feliz (en cualquier canal) -> NO HACER NADA
        else:
            # Aquí es donde permitimos que tú lo muevas. 
            # El bot ve que está conectado y se queda quieto.
            pass

    except Exception as e:
        print(f"⚠️ Error en mantenimiento: {e}")

# Esperar a que el bot esté listo antes de iniciar el bucle
@maintenance_loop.before_loop
async def before_maintenance():
    await bot.wait_until_ready()

# --- COMANDOS ---
@bot.slash_command(name="followme", description="El bot leerá todo lo que escribas")
async def followme(ctx):
    followed_user_ids.add(ctx.author.id)
    await ctx.respond(f"✅ Ahora te sigo, {ctx.author.name}. Hablaré por ti.", ephemeral=True)

@bot.slash_command(name="unfollowme", description="El bot dejará de leerte")
async def unfollowme(ctx):
    followed_user_ids.discard(ctx.author.id)
    await ctx.respond("✅ Ya no te sigo.", ephemeral=True)

# --- EVENTOS ---
@bot.event
async def on_ready():
    print(f'✅ Bot conectado: {bot.user.name}')
    if not maintenance_loop.is_running():
        maintenance_loop.start()

@bot.event
async def on_message(message):
    if message.author.bot or not message.guild: return
    
    # Solo intentamos hablar si el bot está conectado a algún canal
    voice_client = discord.utils.get(bot.voice_clients, guild=message.guild)
    if not voice_client or not voice_client.is_connected(): return

    texto_limpio = re.sub(r'https?://\S+| <a?:.+?:\d+>', '', message.clean_content).strip()
    if not texto_limpio: return

    should_speak = False
    text_to_say = texto_limpio

    # Lógica TTS Bridge (Roles)
    if (message.channel.id == TTS_BRIDGE_CHANNEL_ID and 
        discord.utils.get(message.author.roles, name=TTS_BRIDGE_ROLE_NAME)):
        text_to_say = f"{message.author.display_name} dice: {texto_limpio}"
        should_speak = True
    
    # Lógica Follow Me
    elif message.author.id in followed_user_ids:
        if message.author.id != FOLLOWME_EXEMPT_USER_ID:
             text_to_say = f"{message.author.display_name} dice: {texto_limpio}"
        should_speak = True

    if should_speak:
        await play_tts(voice_client, text_to_say)

if __name__ == "__main__":
    if DISCORD_TOKEN:
        bot.run(DISCORD_TOKEN)
    else:
        print("❌ ERROR: No encontré el token. Revisa tu archivo .env")