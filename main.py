import discord
from discord.ext import commands, tasks
import asyncio
import os
from gtts import gTTS
import re

# --- CARGA DE CONFIGURACIÓN ---
# Solo importamos lo necesario para hablar y conectarse
from config import (
    VOICE_CHANNEL_ID,
    TTS_BRIDGE_CHANNEL_ID,
    TTS_BRIDGE_ROLE_NAME,
    FOLLOWME_EXEMPT_USER_ID
)

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

# --- CONFIGURACIÓN DEL BOT ---
intents = discord.Intents.default()
intents.guilds = True
intents.voice_states = True
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Variables de estado
tts_bridge_enabled = True
followed_user_ids = set()
bot_is_ready = False

# --- FUNCIÓN DE HABLAR (TTS) ---
async def play_tts(voice_client, text, filename="tts.mp3"):
    if not voice_client or not voice_client.is_connected(): return
    try:
        # Si ya está hablando, paramos para decir lo nuevo (opcional, evita cola infinita)
        if voice_client.is_playing():
            voice_client.stop()
            await asyncio.sleep(0.2)

        # Generar audio
        tts = gTTS(text=text, lang='es', slow=False)
        tts.save(filename)
        
        # Reproducir (Acelerado un poco x1.25 para que sea más fluido)
        ffmpeg_options = {"options": "-af atempo=1.25"}
        source = discord.FFmpegPCMAudio(filename, **ffmpeg_options)
        
        voice_client.play(source)
        
        # Esperar a que termine de hablar antes de borrar el archivo
        while voice_client.is_playing(): 
            await asyncio.sleep(0.5)
            
        if os.path.exists(filename): 
            os.remove(filename)

    except Exception as e:
        print(f"Error en TTS: {e}")
        if os.path.exists(filename): os.remove(filename)

# --- EVENTOS ---
@bot.event
async def on_ready():
    global bot_is_ready
    print(f'✅ Bot conectado como: {bot.user.name}')
    
    # 1. Conexión INICIAL
    channel = bot.get_channel(VOICE_CHANNEL_ID)
    if channel:
        if not bot.voice_clients:
            try:
                # Quitamos 'self_deaf=True' que causaba el error
                await channel.connect(reconnect=True)
                print(f"🎧 Conectado inicialmente a: {channel.name}")
            except Exception as e:
                print(f"Error conexión inicial: {e}")
    
    # 2. Arrancar vigilante
    bot_is_ready = True
    if not health_check.is_running():
        health_check.start()

@tasks.loop(seconds=60.0)
async def health_check():
    if not bot_is_ready: return

    try:
        channel = bot.get_channel(VOICE_CHANNEL_ID)
        if not channel: return

        voice_client = channel.guild.voice_client

        # CASO 1: Desconectado totalmente
        if not voice_client:
            print("⚠️ Bot desconectado. Reconectando...")
            # Quitamos 'self_deaf=True' aquí también
            await channel.connect(reconnect=True)
            return

        # CASO 2: Canal incorrecto
        if voice_client.channel.id != VOICE_CHANNEL_ID:
            print("⚠️ Bot en canal incorrecto. Moviendo...")
            await voice_client.disconnect(force=True)
            await asyncio.sleep(3)
            await channel.connect(reconnect=True)
            return
        
    except Exception as e:
        print(f"❌ Error menor en health_check: {e}")

@bot.event
async def on_voice_state_update(member, before, after):
    # 1. Ignorar si el que se mueve es el propio bot
    if member.id == bot.user.id:
        return

    # 2. Detectar el canal designado y el cliente de voz
    designated_channel_id = VOICE_CHANNEL_ID
    voice_client = discord.utils.get(bot.voice_clients, guild=member.guild)
    
    # Si el bot no está conectado o hablando, no puede anunciar nada
    if not voice_client or not voice_client.is_connected():
        return

    # --- CASO: ALGUIEN ENTRA ---
    # (No estaba en el canal designado antes, pero ahora sí está)
    if (not before.channel or before.channel.id != designated_channel_id) and \
       (after.channel and after.channel.id == designated_channel_id):
        
        # Mensaje de bienvenida
        nombre_limpio = re.sub(r'[^a-zA-Z0-9áéíóúñÁÉÍÓÚÑ ]', '', member.display_name).strip()
        saludo = f"Bienvenido, {nombre_limpio}"
        # Usamos el ID del miembro en el nombre del archivo para evitar colisiones si entran varios a la vez
        await play_tts(voice_client, saludo, filename=f"in_{member.id}.mp3")

    # --- CASO: ALGUIEN SALE ---
    # (Estaba en el canal designado, pero ahora ya no está o se fue a otro)
    elif (before.channel and before.channel.id == designated_channel_id) and \
         (not after.channel or after.channel.id != designated_channel_id):
        
        # Mensaje de despedida
        despedida = f"{member.display_name} ha salido"
        await play_tts(voice_client, despedida, filename=f"out_{member.id}.mp3")

@bot.event
async def on_message(message):
    # Ignorar bots y mensajes sin servidor
    if message.author.bot or not message.guild: return
    
    # 1. Usamos clean_content para que @Menciones se conviertan en Nombres reales
    #    y #Canales se conviertan en nombres de canales.
    texto_bruto = message.clean_content

    # 2. Limpieza profunda con Regex
    # - Elimina URLs (http://...)
    # - Elimina emojis personalizados de Discord <:nombre:id> (para que no lea códigos raros)
    texto_limpio = re.sub(r'https?://\S+| <a?:.+?:\d+>', '', texto_bruto).strip()

    # Si después de limpiar no queda nada (ej: solo era una foto o un link), no hacemos nada
    if not texto_limpio: return

    voice_client = discord.utils.get(bot.voice_clients, guild=message.guild)
    if not voice_client: return

    should_speak = False
    text_with_author = texto_limpio

    # Lógica 1: Canal Puente (Bridge)
    is_bridge_msg = (tts_bridge_enabled and 
                     message.channel.id == TTS_BRIDGE_CHANNEL_ID and 
                     discord.utils.get(message.author.roles, name=TTS_BRIDGE_ROLE_NAME))
    
    # Lógica 2: Follow Me
    is_followed = message.author.id in followed_user_ids

    if is_bridge_msg:
        text_with_author = f"{message.author.display_name} dice: {texto_limpio}"
        should_speak = True
    elif is_followed:
        # No decir el nombre si es el usuario exento (tú) y solo te sigue a ti
        if len(followed_user_ids) > 1 and message.author.id != FOLLOWME_EXEMPT_USER_ID:
            text_with_author = f"{message.author.display_name} dice: {texto_limpio}"
        should_speak = True

    if should_speak:
        # Usamos el ID del mensaje en el archivo para evitar conflictos
        await play_tts(voice_client, text_with_author, f"msg_{message.id}.mp3")

# --- COMANDOS SLASH ---

@bot.slash_command(name="bridge", description="Activa/Desactiva que el bot hable.")
@commands.has_role(TTS_BRIDGE_ROLE_NAME)
async def bridge(ctx: discord.ApplicationContext, estado: discord.Option(str, choices=["on", "off"])):
    global tts_bridge_enabled
    tts_bridge_enabled = (estado == "on")
    await ctx.respond(f"Puente de voz: **{estado}**", ephemeral=True)

@bot.slash_command(name="followme", description="El bot leerá todo lo que escribas.")
async def followme(ctx: discord.ApplicationContext):
    followed_user_ids.add(ctx.author.id)
    await ctx.respond("✅ Ahora leo tus mensajes.", ephemeral=True)

@bot.slash_command(name="unfollowme", description="El bot dejará de leerte.")
async def unfollowme(ctx: discord.ApplicationContext):
    followed_user_ids.discard(ctx.author.id)
    await ctx.respond("✅ Ya no te leo.", ephemeral=True)

# --- ARRANQUE ---
if __name__ == "__main__":
    if DISCORD_TOKEN:
        bot.run(DISCORD_TOKEN)
    else:
        print("Falta el DISCORD_TOKEN")