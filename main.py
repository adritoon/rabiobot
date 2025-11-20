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

# Leemos el token del sistema (recuerda actualizarlo en tu .bashrc con el nuevo)
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

# --- INTENTS ---
intents = discord.Intents.default()
intents.guilds = True
intents.voice_states = True # Vital para detectar desconexiones
intents.members = True      # Vital para leer nombres
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Variables
tts_bridge_enabled = True
followed_user_ids = set()

# --- FUNCIONES AUXILIARES ---
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

async def conectar_al_canal():
    """Función centralizada para conectar de forma segura"""
    channel = bot.get_channel(VOICE_CHANNEL_ID)
    if not channel: return
    
    try:
        # Si ya está conectado, no hacemos nada
        if channel.guild.voice_client and channel.guild.voice_client.is_connected():
            return

        print(f"🔌 Conectando a {channel.name}...")
        await channel.connect(reconnect=True)
        print("✅ Conexión establecida.")
    except Exception as e:
        print(f"❌ Error al conectar: {e}")

# --- EVENTOS ---

@bot.event
async def on_ready():
    print(f'🤖 Nuevo Bot conectado como: {bot.user.name}')
    # Conexión inicial
    await conectar_al_canal()

@bot.event
async def on_voice_state_update(member, before, after):
    # 1. LÓGICA DE AUTORRECONEXIÓN (El Fénix)
    # Si el usuario que cambió de estado SOY YO (el bot)...
    if member.id == bot.user.id:
        # ...y el canal 'after' es None, significa que me desconecté/me kickearon
        if after.channel is None:
            print("⚠️ ¡Me he desconectado! Intentando volver a entrar...")
            await asyncio.sleep(1) # Espera técnica
            await conectar_al_canal()
        # Si me movieron a otro canal que no es el mio, vuelvo al mio
        elif after.channel.id != VOICE_CHANNEL_ID:
            print("⚠️ Me movieron de canal. Volviendo a casa...")
            await member.move_to(bot.get_channel(VOICE_CHANNEL_ID))

    # 2. LÓGICA DE BIENVENIDA/DESPEDIDA (Para usuarios normales)
    if member.id != bot.user.id:
        voice_client = discord.utils.get(bot.voice_clients, guild=member.guild)
        if not voice_client: return

        # Entra alguien a mi canal
        if after.channel and after.channel.id == VOICE_CHANNEL_ID and before.channel != after.channel:
            nombre = re.sub(r'[^a-zA-Z0-9áéíóúñÁÉÍÓÚÑ ]', '', member.display_name).strip()
            await play_tts(voice_client, f"Bienvenido, {nombre}", f"in_{member.id}.mp3")
        
        # Sale alguien de mi canal
        elif before.channel and before.channel.id == VOICE_CHANNEL_ID and after.channel != before.channel:
            nombre = re.sub(r'[^a-zA-Z0-9áéíóúñÁÉÍÓÚÑ ]', '', member.display_name).strip()
            await play_tts(voice_client, f"{nombre} ha salido", f"out_{member.id}.mp3")

@bot.event
async def on_message(message):
    if message.author.bot or not message.guild: return
    
    texto_limpio = re.sub(r'https?://\S+| <a?:.+?:\d+>', '', message.clean_content).strip()
    if not texto_limpio: return

    voice_client = discord.utils.get(bot.voice_clients, guild=message.guild)
    
    # COMANDOS DE TEXTO (Bridge y Followme)
    should_speak = False
    text_to_say = texto_limpio

    # Bridge
    if (tts_bridge_enabled and 
        message.channel.id == TTS_BRIDGE_CHANNEL_ID and 
        discord.utils.get(message.author.roles, name=TTS_BRIDGE_ROLE_NAME)):
        text_to_say = f"{message.author.display_name} dice: {texto_limpio}"
        should_speak = True
    
    # Follow me
    elif message.author.id in followed_user_ids:
        if len(followed_user_ids) > 1 and message.author.id != FOLLOWME_EXEMPT_USER_ID:
            text_to_say = f"{message.author.display_name} dice: {texto_limpio}"
        should_speak = True

    if should_speak and voice_client:
        await play_tts(voice_client, text_to_say, f"msg_{message.id}.mp3")

# --- COMANDOS SLASH ---
@bot.slash_command(name="followme", description="El bot leerá tus mensajes.")
async def followme(ctx):
    followed_user_ids.add(ctx.author.id)
    await ctx.respond("✅ Activado.", ephemeral=True)

@bot.slash_command(name="unfollowme", description="El bot dejará de leerte.")
async def unfollowme(ctx):
    followed_user_ids.discard(ctx.author.id)
    await ctx.respond("✅ Desactivado.", ephemeral=True)

if __name__ == "__main__":
    if DISCORD_TOKEN:
        bot.run(DISCORD_TOKEN)
    else:
        print("❌ ERROR: No hay Token configurado.")