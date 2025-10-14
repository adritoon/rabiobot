# main.py
import discord
from discord.ext import commands
import asyncio
import os
from gtts import gTTS
import time
import re
import subprocess
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

# --- 1. CARGA DE CONFIGURACIÓN Y TOKEN ---
from config import (
    VOICE_CHANNEL_ID,
    TTS_BRIDGE_CHANNEL_ID,
    TTS_BRIDGE_ROLE_NAME,
    FOLLOWME_EXEMPT_USER_ID
)
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

# --- 2. CONFIGURACIÓN DE INTENTS DEL BOT ---
intents = discord.Intents.default()
intents.guilds = True
intents.voice_states = True
intents.members = True
intents.message_content = True

# --- 3. INICIALIZACIÓN DEL BOT Y VARIABLES DE ESTADO ---
bot = commands.Bot(command_prefix="!", intents=intents)

tts_bridge_enabled = True
followed_user_ids = set()
bot_is_zombie = False
bot_is_ready = False
last_reconnect_attempt = 0
restart_is_pending = False # Para el reinicio inteligente

# --- 4. FUNCIONES AUXILIARES Y DE MANTENIMIENTO ---
async def play_tts(voice_client, text, filename="tts.mp3"):
    if not voice_client or not voice_client.is_connected(): return
    try:
        tts = gTTS(text=text, lang='es', slow=False)
        tts.save(filename)
        while voice_client.is_playing(): await asyncio.sleep(0.5)
        ffmpeg_options = {"options": "-af atempo=1.25"}
        source = discord.FFmpegPCMAudio(filename, **ffmpeg_options)
        voice_client.play(source)
        while voice_client.is_playing(): await asyncio.sleep(0.5)
        os.remove(filename)
    except Exception as e:
        print(f"Error en play_tts: {e}")
        if os.path.exists(filename): os.remove(filename)

async def perform_restart(voice_client):
    """Anuncia, lanza el script de reinicio y se apaga limpiamente."""
    print("🚀 Iniciando secuencia de reinicio programado...")
    try:
        await play_tts(voice_client, "Iniciando reinicio programado para mantenimiento. Volveré en un momento.")
        await asyncio.sleep(5)
        
        # Lanza restart.sh como un proceso completamente independiente
        subprocess.Popen(['/home/robtete2024/rabiobot/restart.sh'])
        
        # Se apaga a sí mismo de forma limpia
        print("Apagando el proceso actual para ceder el control al reiniciador...")
        await bot.close()

    except Exception as e:
        print(f"❌ Error durante la secuencia de reinicio: {e}")

async def scheduled_restart_check():
    """Comprueba si se cumplen las condiciones para un reinicio."""
    global restart_is_pending
    print("⏰ Comprobando condiciones para el reinicio nocturno...")
    
    voice_client = bot.voice_clients[0] if bot.voice_clients else None

    if voice_client and voice_client.is_connected():
        # La condición es: bot + 2 usuarios = 3 o más miembros
        if len(voice_client.channel.members) >= 3:
            await perform_restart(voice_client)
        else:
            restart_is_pending = True
            print("⏳ Reinicio pendiente. Esperando a que haya al menos 2 usuarios en el canal.")
    else:
        print("Bot no está en un canal de voz. Reinicio cancelado para hoy.")

# --- 5. EVENTOS PRINCIPALES DEL BOT ---
@bot.event
async def on_ready():
    global bot_is_ready
    print(f'✅ Bot conectado como: {bot.user.name}')
    voice_channel = bot.get_channel(VOICE_CHANNEL_ID)
    if voice_channel:
        try:
            await voice_channel.connect()
            print(f'🔗 Conectado a {voice_channel.name}.')
            bot_is_ready = True
            
            # --- LÓGICA DE REINICIO INTELIGENTE ---
            scheduler = AsyncIOScheduler(timezone="America/Lima")
            # Comprobará cada día a las 4:00 AM
            trigger = CronTrigger(hour=13, minute=5) 
            scheduler.add_job(scheduled_restart_check, trigger)
            scheduler.start()
            print("⏰ El programador de reinicio inteligente está activo.")
        except Exception as e:
            print(f'❌ Error durante la conexión inicial: {e}')

@bot.event
async def on_voice_state_update(member, before, after):
    if not bot_is_ready:
        return
    
    global bot_is_zombie, last_reconnect_attempt, restart_is_pending
    voice_client = discord.utils.get(bot.voice_clients, guild=member.guild)
    designated_channel = bot.get_channel(VOICE_CHANNEL_ID)

    # --- LÓGICA DE DISPARO DE REINICIO PENDIENTE ---
    if restart_is_pending and voice_client and len(voice_client.channel.members) >= 3:
        await perform_restart(voice_client)
        restart_is_pending = False
        return

    # --- LÓGICA DE MANEJO DE DESCONEXIÓN ---
    if member.id == bot.user.id and after.channel is None:
        current_time = time.time()
        if current_time - last_reconnect_attempt < 60:
            print("🔥 ¡BUCLE DE RECONEXIÓN DETECTADO! Abortando.")
            return
        last_reconnect_attempt = current_time

        print("🔴 El bot ha sido desconectado. Intentando reconexión...")
        await asyncio.sleep(5)
        try:
            await designated_channel.connect()
            bot_is_zombie = False
            print("✅ Bot reconectado exitosamente.")
        except discord.errors.ClientException as e:
            if "Already connected" in str(e):
                bot_is_zombie = True
                print("🤖 Estado 'zombie' detectado. Esperando a un usuario para repararse.")
            else:
                print(f"❌ Error inesperado al reconectar: {e}")
        return

    # --- LÓGICA DE BIENVENIDA Y CURACIÓN DE ZOMBIE ---
    if not member.bot and after.channel == designated_channel:
        if bot_is_zombie:
            print(f"👤 Usuario ha entrado. Curando al bot zombie...")
            last_reconnect_attempt = time.time()
            try:
                current_vc = discord.utils.get(bot.voice_clients, guild=member.guild)
                if current_vc:
                    await current_vc.disconnect(force=True)
                    await asyncio.sleep(1)
                await designated_channel.connect()
                bot_is_zombie = False
                print("✅ Bot curado y funcional.")
            except Exception as surgery_error:
                print(f"❌ Error durante la curación: {surgery_error}")
        elif voice_client and before.channel != after.channel:
            welcome_message = f"Bienvenido, {member.display_name}"
            await play_tts(voice_client, welcome_message, f"welcome_{member.id}.mp3")

@bot.event
async def on_message(message):
    if message.author.bot or not message.guild:
        await bot.process_application_commands(message)
        return

    text_to_read = re.sub(r'https?://\S+', '', message.content).strip()
    
    if (not text_to_read and message.attachments) or not text_to_read:
        await bot.process_application_commands(message)
        return

    voice_client = discord.utils.get(bot.voice_clients, guild=message.guild)
    if not voice_client:
        await bot.process_application_commands(message)
        return

    should_speak = False
    text_with_author = text_to_read
    
    is_bridge_message = (tts_bridge_enabled and message.channel.id == TTS_BRIDGE_CHANNEL_ID and discord.utils.get(message.author.roles, name=TTS_BRIDGE_ROLE_NAME))
    is_followed_user_message = message.author.id in followed_user_ids

    if is_bridge_message:
        text_with_author = f"{message.author.display_name} dice: {text_to_read}"
        should_speak = True
    elif is_followed_user_message:
        if len(followed_user_ids) > 1 and message.author.id != FOLLOWME_EXEMPT_USER_ID:
            text_with_author = f"{message.author.display_name} dice: {text_to_read}"
        should_speak = True
    
    if should_speak:
        await play_tts(voice_client, text_with_author, f"speech_{message.id}.mp3")
    
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