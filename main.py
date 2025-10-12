# main.py
import discord
from discord.ext import commands
import asyncio
import os
from gtts import gTTS
import random
import io
import time
from serpapi import GoogleSearch
import aiohttp

# Importamos ambas librerías de Google
import google.generativeai as genai
from google.cloud import aiplatform
from vertexai.vision_models import ImageGenerationModel

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

# --- 1. CARGA DE CONFIGURACIÓN Y TOKEN ---
from config import (
    VOICE_CHANNEL_ID,
    TTS_BRIDGE_CHANNEL_ID,
    TTS_BRIDGE_ROLE_NAME,
    FOLLOWME_EXEMPT_USER_ID,
    DREAM_CHANNEL_ID
)
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
PROJECT_ID = "plucky-rarity-473620-v0" # Tu ID de proyecto

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

# --- 4. FUNCIONES AUXILIARES ---
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

# --- Función bloqueante para la generación de imagen ---
def generate_image_blocking(prompt):
    """
    Esta función contiene el trabajo pesado y síncrono de generar la imagen.
    Se ejecutará en un hilo separado para no congelar el bot.
    """
    try:
        aiplatform.init(project=PROJECT_ID)
        model = ImageGenerationModel.from_pretrained("imagegeneration@006")
        response = model.generate_images(prompt=prompt, number_of_images=1)
        return response.images[0]._image_bytes
    except Exception as e:
        print(f"Error en el hilo de generación de imagen: {e}")
        return None

async def dream_task(channel: discord.TextChannel = None):
    """La tarea programada que hace que el bot 'sueñe'."""
    print("🌙 El bot está intentando soñar...")
    try:
        # PASO 1: Generar texto con la librería 'google-generativeai'
        text_model = genai.GenerativeModel('gemini-2.5-pro')
        prompt_para_texto = "Escribe una única frase muy corta (menos de 15 palabras) que sea poética, surrealista y misteriosa..."
        text_response = await text_model.generate_content_async(prompt_para_texto)
        dream_text = text_response.text.strip().replace('*', '')
        print(f"Texto del sueño generado: '{dream_text}'")

        # PASO 2: Generar imagen en un hilo separado con la librería 'google-cloud-aiplatform'
        prompt_para_imagen = (
            f"Una imagen artística, de alta calidad, surrealista y de ensueño basada en esta frase: '{dream_text}'. "
            "Estilo: pintura digital etérea, colores melancólicos, cinematográfico."
        )
        
        loop = asyncio.get_running_loop()
        image_data = await loop.run_in_executor(
            None, generate_image_blocking, prompt_para_imagen
        )

        if not image_data:
            raise ValueError("La generación de imagen no devolvió datos.")

        image_file = discord.File(io.BytesIO(image_data), filename="sueño.png")
        target_channel = channel or bot.get_channel(DREAM_CHANNEL_ID)

        if target_channel:
            await target_channel.send(f"> {dream_text}", file=image_file)
            print("😴 El bot ha soñado con éxito.")
        else:
            print("❌ No se encontró el canal de sueños.")

    except Exception as e:
        print(f"Error durante el sueño del bot: {e}")
        if channel:
            await channel.send("Lo siento, hubo un error al intentar soñar.")

async def get_lima_photo_of_the_day():
    """
    Busca una foto reciente de Lima, la descarga y genera un caption.
    Implementa todas tus sugerencias.
    """
    print("📸 Buscando la foto del día de Lima...")
    serpapi_key = os.getenv("SERPAPI_KEY")
    if not serpapi_key:
        print("❌ Falta la variable de entorno SERPAPI_KEY.")
        return None, None, None

    try:
        # --- 1. La Búsqueda (tu query) ---
        params = {
            "q": '"Lima Perú" (site:instagram.com OR site:x.com OR site:flickr.com)',
            "tbm": "isch",
            "tbs": "qdr:d", # Últimas 24 horas
            "api_key": serpapi_key
        }
        search = GoogleSearch(params)
        results = search.get_dict()
        
        # --- 2. Selección Inteligente de Imagen (tu lógica) ---
        valid_images = [img for img in results.get("images_results", []) if "original" in img]
        if not valid_images:
            print("❌ No se encontraron imágenes válidas recientes.")
            return None, None, None

        choice = random.choice(valid_images[:5]) # Elige entre las 5 primeras
        image_url = choice["original"]
        source_link = choice.get("link") or choice.get("source") # Para el crédito
        print(f"🖼️ Descargando imagen desde: {image_url}")

        # --- 3. Descarga de la Imagen ---
        async with aiohttp.ClientSession() as session:
            async with session.get(image_url) as resp:
                if resp.status != 200:
                    raise ValueError(f"No se pudo descargar: {resp.status}")
                image_bytes = await resp.read()

        # --- 4. Generación del Caption con Gemini ---
        # Compatibilidad de formato (tu lógica)
        mime_type = "image/jpeg"
        if image_url.endswith(".png"): mime_type = "image/png"
        elif image_url.endswith(".webp"): mime_type = "image/webp"
        
        model = genai.GenerativeModel('gemini-2.5-pro')
        prompt_caption = "Basado en esta imagen de Lima, escribe una única frase poética y evocadora (menos de 15 palabras) que capture su esencia."
        image_part = {"mime_type": mime_type, "data": image_bytes}
        response = await model.generate_content_async([prompt_caption, image_part])
        caption = response.text.strip().replace('*', '')
        print(f"✒️ Caption generado: '{caption}'")

        return image_bytes, caption, source_link

    except Exception as e:
        print(f"Error en get_lima_photo_of_the_day: {e}")
        return None, None, None

# --- Función para la Automatización (tu lógica) ---
async def post_lima_photo_auto():
    """Función que se ejecutará automáticamente cada día."""
    channel = bot.get_channel(LIMA_PHOTO_CHANNEL_ID)
    if not channel:
        print(f"❌ No se encontró el canal para la foto de Lima con ID: {LIMA_PHOTO_CHANNEL_ID}")
        return
    
    image_data, caption, source = await get_lima_photo_of_the_day()
    if image_data and caption:
        image_file = discord.File(io.BytesIO(image_data), filename="lima_hoy.jpg")
        await channel.send(content=f"> {caption}\n📸 Fuente: <{source}>", file=image_file)

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
            
            scheduler = AsyncIOScheduler(timezone="America/Lima")
            trigger = CronTrigger(hour=3, minute=0, jitter=7200)
            scheduler.add_job(dream_task, trigger)
            photo_trigger = CronTrigger(hour=19, minute=30, timezone="America/Lima")
            scheduler.add_job(post_lima_photo_auto, photo_trigger)
            scheduler.start()
            print("⏰ El programador de sueños y de la foto de Lima están activos.")
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
@commands.is_owner()
async def test_dream(ctx: discord.ApplicationContext):
    await ctx.defer(ephemeral=True)
    print(f"--- Forzando un sueño por orden de {ctx.author.name} ---")
    await dream_task(channel=ctx.channel)
    await ctx.followup.send("Intento de sueño completado. Revisa la consola para ver los logs.")

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

@bot.slash_command(name="lima_de_hoy", description="Busca y muestra una foto reciente de Lima.")
@commands.is_owner() # Es buena idea restringirlo para no gastar la cuota de la API
async def lima_de_hoy(ctx: discord.ApplicationContext):
    await ctx.defer()
    image_data, caption, source = await get_lima_photo_of_the_day()
    
    if image_data and caption:
        image_file = discord.File(io.BytesIO(image_data), filename="lima_hoy.jpg")
        await ctx.followup.send(content=f"> {caption}\n📸 Fuente: <{source}>", file=image_file)
    else:
        await ctx.followup.send("Lo siento, no pude encontrar una foto de Lima hoy.")

# --- 7. EJECUCIÓN DEL BOT ---
if __name__ == "__main__":
    if not DISCORD_TOKEN:
        print("❌ ERROR CRÍTICO: La variable de entorno DISCORD_TOKEN no está configurada.")
    else:
        bot.run(DISCORD_TOKEN)