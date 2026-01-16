import discord
from discord.ext import commands, tasks # Importamos tasks para el bucle
import asyncio
import os
from dotenv import load_dotenv
from gtts import gTTS
import re

# --- CONFIGURACIÓN ---
from config import VOICE_CHANNEL_ID

load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

# --- INTENTS ---
intents = discord.Intents.default()
intents.message_content = True
# intents.voice_states = True # Ya no es crítico para la reconexión, pero útil
bot = commands.Bot(command_prefix="!", intents=intents)

# --- SISTEMA DE AUDIO (Simplificado) ---
async def play_tts(voice_client, text):
    if not voice_client or not voice_client.is_connected(): return
    try:
        # Si ya está hablando, no interrumpimos (o puedes poner stop() si prefieres)
        if voice_client.is_playing(): return 

        filename = f"tts_{os.urandom(4).hex()}.mp3"
        tts = gTTS(text=text, lang='es', slow=False)
        tts.save(filename)
        
        # Opciones para que suene más rápido/natural
        ffmpeg_options = {"options": "-af atempo=1.25"}
        source = discord.FFmpegPCMAudio(filename, **ffmpeg_options)
        
        voice_client.play(source, after=lambda e: clean_file(filename))
    except Exception as e:
        print(f"Error audio: {e}")
        clean_file(filename)

def clean_file(filename):
    if os.path.exists(filename):
        try: os.remove(filename)
        except: pass

# --- BUCLE DE CONEXIÓN ETERNA ---
@tasks.loop(seconds=30) # Revisa cada 30 segundos
async def maintenance_loop():
    channel = bot.get_channel(VOICE_CHANNEL_ID)
    if not channel:
        print("❌ Error: No encuentro el canal de voz.")
        return

    # Buscamos si el bot ya tiene una conexión en ese servidor
    voice_client = discord.utils.get(bot.voice_clients, guild=channel.guild)

    try:
        if voice_client is None:
            # CASO 1: No está conectado -> Conectar
            print("🔌 Conectando al canal...")
            await channel.connect()
        elif not voice_client.is_connected():
            # CASO 2: El objeto existe pero está 'muerto' -> Limpiar y reconectar
            await voice_client.disconnect(force=True)
            await channel.connect()
        elif voice_client.channel.id != VOICE_CHANNEL_ID:
            # CASO 3: Está conectado pero en el canal equivocado -> Mover
            print("kamove a su sitio...")
            await voice_client.move_to(channel)
        else:
            # CASO 4: Todo perfecto -> No hacer nada
            pass
            
    except Exception as e:
        print(f"⚠️ Error en mantenimiento: {e}")

# Esperar a que el bot esté listo antes de arrancar el bucle
@maintenance_loop.before_loop
async def before_maintenance():
    await bot.wait_until_ready()

# --- EVENTOS ---
@bot.event
async def on_ready():
    print(f'✅ Bot conectado como: {bot.user.name}')
    # Arrancamos el guardia de seguridad si no está corriendo ya
    if not maintenance_loop.is_running():
        maintenance_loop.start()

@bot.event
async def on_message(message):
    if message.author.bot or not message.guild: return
    
    # Filtro simple: Solo lee mensajes en el canal de texto donde esté configurado
    # Opcional: añade condiciones aquí si solo quieres que lea ciertos canales
    
    voice_client = discord.utils.get(bot.voice_clients, guild=message.guild)
    
    # Limpieza de texto (URLs y Emojis de Discord)
    texto_limpio = re.sub(r'https?://\S+| <a?:.+?:\d+>', '', message.clean_content).strip()
    
    if texto_limpio and voice_client:
        texto_final = f"{message.author.display_name} dice: {texto_limpio}"
        await play_tts(voice_client, texto_final)

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)