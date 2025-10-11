# main.py
import discord
from discord.ext import commands
import asyncio
import os
from gtts import gTTS
import random
import io
import google.generativeai as genai
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import time


# --- 1. CARGA DE CONFIGURACIÓN Y TOKEN ---
from config import (
    VOICE_CHANNEL_ID,
    TTS_BRIDGE_CHANNEL_ID,
    TTS_BRIDGE_ROLE_NAME,
    FOLLOWME_EXEMPT_USER_ID,
    DREAM_CHANNEL_ID
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

# --- 4. FUNCIÓN AUXILIAR PARA TEXT-TO-SPEECH (TTS) ---
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

async def dream_task(channel: discord.TextChannel = None):
    """La tarea programada que hace que el bot 'sueñe'."""
    print("🌙 El bot está intentando soñar...")
    if not GEMINI_API_KEY:
        print("❌ El bot no puede soñar sin una API Key de Gemini.")
        return
    try:
        # Usamos el modelo multimodal más potente y estable para AMBAS tareas.
        model = genai.GenerativeModel('gemini-1.5-pro')

        # 1. Generar el texto poético
        prompt_para_texto = "Escribe una única frase muy corta (menos de 15 palabras) que sea poética, surrealista y misteriosa, como el sueño de una inteligencia artificial."
        text_response = await model.generate_content_async(prompt_para_texto)
        dream_text = text_response.text.strip().replace('*', '')
        print(f"Texto del sueño generado: '{dream_text}'")

        # 2. Generar la imagen a partir del texto
        prompt_para_imagen = (
            f"Crea una imagen artística, de alta calidad, surrealista y de ensueño basada en esta frase: '{dream_text}'. "
            "Estilo: pintura digital etérea, colores melancólicos, cinematográfico."
        )
        image_response = await model.generate_content_async(prompt_para_imagen)
        
        # --- MANEJO DE ERRORES FINAL ---
        try:
            image_data = image_response.parts[0].inline_data.data
            if not image_data:
                raise ValueError("Los datos de la imagen están vacíos.")
        except (IndexError, AttributeError, ValueError) as e:
            print(f"❌ Error al extraer la imagen: {e}. La respuesta de la API fue:")
            print(image_response) # Imprimimos la respuesta completa para ver por qué falló
            if channel:
                try:
                    block_reason = image_response.prompt_feedback.block_reason.name
                    await channel.send(f"Lo siento, no pude generar una imagen. Razón del bloqueo: **{block_reason}**.")
                except:
                    await channel.send("Lo siento, la IA no generó una imagen válida, probablemente por sus filtros de seguridad.")
            return
        # --- FIN DEL MANEJO DE ERRORES ---

        image_file = discord.File(io.BytesIO(image_data), filename="sueño.png")

        target_channel = channel or bot.get_channel(DREAM_CHANNEL_ID)
        
        if target_channel:
            await target_channel.send(f"> {dream_text}", file=image_file)
            print(f"😴 El bot ha soñado: {dream_text}")
        else:
            print(f"❌ No se encontró el canal de sueños.")
    except Exception as e:
        print(f"Error durante el sueño del bot: {e}")

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
            
            if GEMINI_API_KEY:
                scheduler = AsyncIOScheduler(timezone="America/Lima")
                trigger = CronTrigger(hour=3, minute=0, jitter=7200)
                scheduler.add_job(dream_task, trigger)
                scheduler.start()
                print("⏰ El programador de sueños está activo.")
        except Exception as e:
            print(f'❌ Error durante la conexión inicial: {e}')

@bot.event
async def on_voice_state_update(member, before, after):
    if not bot_is_ready:
        return
    
    global bot_is_zombie, last_reconnect_attempt
    voice_client = discord.utils.get(bot.voice_clients, guild=member.guild)
    designated_channel = bot.get_channel(VOICE_CHANNEL_ID)

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
    if message.author.bot or not message.guild: return
    voice_client = discord.utils.get(bot.voice_clients, guild=message.guild)
    if not voice_client:
        await bot.process_application_commands(message)
        return
    text_to_speak, should_speak = message.content, False
    is_bridge_message = (tts_bridge_enabled and message.channel.id == TTS_BRIDGE_CHANNEL_ID and discord.utils.get(message.author.roles, name=TTS_BRIDGE_ROLE_NAME))
    is_followed_user_message = message.author.id in followed_user_ids
    if is_bridge_message:
        text_to_speak = f"{message.author.display_name} dice: {text_to_speak}"
        should_speak = True
    elif is_followed_user_message:
        if len(followed_user_ids) > 1 and message.author.id != FOLLOWME_EXEMPT_USER_ID:
            text_to_speak = f"{message.author.display_name} dice: {text_to_speak}"
        should_speak = True
    if should_speak:
        await play_tts(voice_client, text_to_speak, f"speech_{message.id}.mp3")
    await bot.process_application_commands(message)

# --- 6. COMANDOS SLASH ---
@bot.slash_command(name="test_dream", description="Fuerza al bot a soñar ahora mismo para pruebas.")
@commands.is_owner() # Opcional: solo tú podrás usar este comando
async def test_dream(ctx: discord.ApplicationContext):
    """Ejecuta la tarea del sueño manualmente."""
    await ctx.defer(ephemeral=True)
    print(f"--- Forzando un sueño por orden de {ctx.author.name} ---")
    await dream_task(channel=ctx.channel) # Llama a la función y le pasa el canal actual
    await ctx.followup.send("Intento de sueño completado. Revisa la consola para ver los logs.")

# Opcional: Añade un manejador de error si no eres el dueño
@test_dream.error
async def test_dream_error(ctx, error):
    if isinstance(error, commands.NotOwner):
        await ctx.respond("⛔ Solo el dueño del bot puede usar este comando.", ephemeral=True)

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