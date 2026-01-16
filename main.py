import discord
from discord.ext import commands
import asyncio
import os
from gtts import gTTS
import re

# --- CONFIGURACIÓN ---
from config import (
    VOICE_CHANNEL_ID,
    TTS_BRIDGE_CHANNEL_ID,
    TTS_BRIDGE_ROLE_NAME,
    FOLLOWME_EXEMPT_USER_ID
)

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

# --- INTENTS ---
intents = discord.Intents.default()
intents.guilds = True
intents.voice_states = True
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# --- VARIABLES DE ESTADO ---
tts_bridge_enabled = True
followed_user_ids = set()
# SEMÁFORO: Esta variable evita que el bot intente conectarse 5 veces a la vez
is_reconnecting = False 

# --- FUNCIONES DE AUDIO ---
async def play_tts(voice_client, text, filename="tts.mp3"):
    if not voice_client or not voice_client.is_connected(): return
    try:
        if voice_client.is_playing():
            voice_client.stop()
            await asyncio.sleep(0.2)

        tts = gTTS(text=text, lang='es', slow=False)
        tts.save(filename)
        
        ffmpeg_options = {"options": "-af atempo=1.25"}
        source = discord.FFmpegPCMAudio(filename, **ffmpeg_options)
        voice_client.play(source)
        
        while voice_client.is_playing(): 
            await asyncio.sleep(0.5)
        if os.path.exists(filename): os.remove(filename)
    except Exception:
        pass

async def conectar_seguro():
    """Maneja la conexión de forma ordenada usando el semáforo global."""
    global is_reconnecting
    
    channel = bot.get_channel(VOICE_CHANNEL_ID)
    if not channel: return

    guild = channel.guild
    voice_client = guild.voice_client

    # 1. Si ya estamos conectados y bien, no hacemos nada
    if voice_client and voice_client.is_connected():
        return

    # 2. Limpieza de zombies (si existe el objeto pero no funciona)
    if voice_client:
        try:
            await voice_client.disconnect(force=True)
        except:
            pass
        # Espera técnica para que Discord procese la salida
        await asyncio.sleep(3)

    # 3. Intento de conexión
    try:
        print(f"🔌 Intentando conectar a {channel.name}...")
        await channel.connect(timeout=30.0, reconnect=True)
        print("✅ Conexión establecida correctamente.")
        is_reconnecting = False # Bajamos la bandera de alerta
    except Exception as e:
        print(f"❌ Falló la conexión: {e}")
        # Si falla, esperamos un poco más antes de permitir otro intento
        await asyncio.sleep(5)
        is_reconnecting = False

# --- EVENTOS ---
@bot.event
async def on_ready():
    print(f'🤖 Bot v3.0 listo como: {bot.user.name}')
    # Primer intento al arrancar
    await conectar_seguro()

@bot.event
async def on_voice_state_update(member, before, after):
    global is_reconnecting

    # --- LÓGICA DEL BOT (AUTORRECONEXIÓN) ---
    if member.id == bot.user.id:
        # Caso: Me desconecté (after.channel es None)
        if after.channel is None:
            # SI YA ESTAMOS RECONECTANDO, IGNORAMOS ESTE EVENTO (STOP LOOP)
            if is_reconnecting:
                return
            
            print("⚠️ ¡Se cayó la conexión! Iniciando protocolo de rescate...")
            is_reconnecting = True # Levantamos la bandera
            await asyncio.sleep(2) # Esperamos un poco
            await conectar_seguro()

        # Caso: Me movieron de canal
        elif after.channel.id != VOICE_CHANNEL_ID:
            print("⚠️ Me movieron. Regresando...")
            await asyncio.sleep(1)
            await member.move_to(bot.get_channel(VOICE_CHANNEL_ID))

    # --- LÓGICA DE USUARIOS (BIENVENIDAS) ---
    elif not member.bot:
        voice_client = discord.utils.get(bot.voice_clients, guild=member.guild)
        if not voice_client or not voice_client.is_connected(): return

        # Entra alguien
        if after.channel and after.channel.id == VOICE_CHANNEL_ID and before.channel != after.channel:
            nombre = re.sub(r'[^a-zA-Z0-9áéíóúñÁÉÍÓÚÑ ]', '', member.display_name).strip()
            bot.loop.create_task(play_tts(voice_client, f"Bienvenido, {nombre}", f"in_{member.id}.mp3"))
        
        # Sale alguien
        elif before.channel and before.channel.id == VOICE_CHANNEL_ID and after.channel != before.channel:
            nombre = re.sub(r'[^a-zA-Z0-9áéíóúñÁÉÍÓÚÑ ]', '', member.display_name).strip()
            bot.loop.create_task(play_tts(voice_client, f"{nombre} ha salido", f"out_{member.id}.mp3"))

# ... (El resto de on_message y comandos sigue igual) ...
@bot.event
async def on_message(message):
    if message.author.bot or not message.guild: return
    texto_limpio = re.sub(r'https?://\S+| <a?:.+?:\d+>', '', message.clean_content).strip()
    if not texto_limpio: return
    voice_client = discord.utils.get(bot.voice_clients, guild=message.guild)
    should_speak = False
    text_to_say = texto_limpio
    if (tts_bridge_enabled and message.channel.id == TTS_BRIDGE_CHANNEL_ID and discord.utils.get(message.author.roles, name=TTS_BRIDGE_ROLE_NAME)):
        text_to_say = f"{message.author.display_name} dice: {texto_limpio}"
        should_speak = True
    elif message.author.id in followed_user_ids:
        if len(followed_user_ids) > 1 and message.author.id != FOLLOWME_EXEMPT_USER_ID:
            text_to_say = f"{message.author.display_name} dice: {texto_limpio}"
        should_speak = True
    if should_speak and voice_client:
        await play_tts(voice_client, text_to_say, f"msg_{message.id}.mp3")

@bot.slash_command(name="followme")
async def followme(ctx):
    followed_user_ids.add(ctx.author.id)
    await ctx.respond("✅ Activado.", ephemeral=True)

@bot.slash_command(name="unfollowme")
async def unfollowme(ctx):
    followed_user_ids.discard(ctx.author.id)
    await ctx.respond("✅ Desactivado.", ephemeral=True)

if __name__ == "__main__":
    if DISCORD_TOKEN:
        bot.run(DISCORD_TOKEN)
    else:
        print("❌ ERROR: No Token.")