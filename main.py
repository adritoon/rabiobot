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
import yt_dlp

# --- 1. CARGA DE CONFIGURACIÓN Y TOKEN ---
from config import (
    VOICE_CHANNEL_ID,
    TTS_BRIDGE_CHANNEL_ID,
    TTS_BRIDGE_ROLE_NAME,
    FOLLOWME_EXEMPT_USER_ID,
    RADIO_URL,
    GENERAL_CHANNEL_ID
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
restart_is_pending = False
radio_is_auto = False

# --- 4. CLASE PARA LOS BOTONES DE LA RADIO ---
class RadioControlView(discord.ui.View):
    def __init__(self, voice_client):
        # 1. Restauramos el tiempo de espera a 60 segundos
        super().__init__(timeout=60) 
        self.voice_client = voice_client
        self.message = None # Guardaremos una referencia al mensaje

    async def on_timeout(self):
        """
        Esta función se ejecuta automáticamente cuando los botones caducan.
        """
        # Deshabilitamos todos los botones (se pondrán grises)
        for item in self.children:
            item.disabled = True
        
        # Editamos el mensaje original para mostrar la nueva información
        if self.message:
            await self.message.edit(content="El tiempo para decidir ha terminado. La música continuará.\n*Puedes detenerla en cualquier momento con el comando `/radio stop`.*", view=self)

    @discord.ui.button(label="Detener Radio", style=discord.ButtonStyle.red, emoji="⏹️")
    async def stop_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        global radio_is_auto
        if self.voice_client and self.voice_client.is_playing():
            self.voice_client.stop()
            radio_is_auto = False
            await interaction.response.edit_message(content=f"📻 La radio ha sido detenida por {interaction.user.display_name}.", view=None)
        else:
            await interaction.response.edit_message(content="La radio ya no estaba sonando.", view=None)
        self.stop()

    @discord.ui.button(label="Mantener Música", style=discord.ButtonStyle.green, emoji="🎶")
    async def keep_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.edit_message(content=f"👍 La música seguirá sonando gracias a {interaction.user.display_name}.", view=None)
        self.stop()

# --- 5. FUNCIONES AUXILIARES Y DE MANTENIMIENTO ---
async def play_tts(voice_client, text, filename="tts.mp3"):
    if not voice_client or not voice_client.is_connected(): return
    try:
        radio_was_playing_auto = voice_client.is_playing() and radio_is_auto
        if voice_client.is_playing():
            voice_client.stop()
            await asyncio.sleep(0.5)

        tts = gTTS(text=text, lang='es', slow=False)
        tts.save(filename)
        ffmpeg_options = {"options": "-af atempo=1.25"}
        source = discord.FFmpegPCMAudio(filename, **ffmpeg_options)
        voice_client.play(source)
        while voice_client.is_playing(): await asyncio.sleep(0.5)
        os.remove(filename)

        if radio_was_playing_auto:
            print("TTS finalizado, reanudando radio automática...")
            await start_radio(voice_client)
    except Exception as e:
        print(f"Error en play_tts: {e}")
        if os.path.exists(filename): os.remove(filename)

async def perform_restart(voice_client):
    print("🚀 Iniciando secuencia de reinicio programado...")
    try:
        await play_tts(voice_client, "Iniciando reinicio programado para mantenimiento. Volveré en un momento.")
        await asyncio.sleep(5)
        subprocess.Popen(['/home/robtete2024/rabiobot/restart.sh'])
        print("Apagando el proceso actual para ceder el control al reiniciador...")
        await bot.close()
    except Exception as e:
        print(f"❌ Error durante la secuencia de reinicio: {e}")

async def scheduled_restart_check():
    global restart_is_pending
    print("⏰ Comprobando condiciones para el reinicio nocturno...")
    voice_client = bot.voice_clients[0] if bot.voice_clients else None
    if voice_client and voice_client.is_connected():
        if len(voice_client.channel.members) >= 3:
            await perform_restart(voice_client)
        else:
            restart_is_pending = True
            print("⏳ Reinicio pendiente. Esperando a que haya al menos 2 usuarios en el canal.")
    else:
        print("Bot no está en un canal de voz. Reinicio cancelado para hoy.")

# Reemplaza tu función start_radio con esta
async def start_radio(voice_client: discord.VoiceClient, url: str = RADIO_URL):
    """Inicia la reproducción de un stream de audio en el canal de voz."""
    if not voice_client or not voice_client.is_connected():
        return
    # Si ya está sonando algo, lo paramos primero
    if voice_client.is_playing():
        voice_client.stop()
        await asyncio.sleep(0.5)

    YDL_OPTIONS = {'format': 'bestaudio/best', 'noplaylist': 'True'}
    FFMPEG_OPTIONS = {'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5', 'options': '-vn'}

    try:
        with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
            # Si no es una URL, yt-dlp lo buscará en YouTube
            info = ydl.extract_info(f"ytsearch:{url}" if not url.startswith("http") else url, download=False)
            
            # Si es una búsqueda, tomamos el primer resultado
            if 'entries' in info:
                info = info['entries'][0]
            
            stream_url = info['url']
            source = await discord.FFmpegOpusAudio.from_probe(stream_url, **FFMPEG_OPTIONS)
            
            # Función callback que se ejecuta cuando la canción termina
            def after_playing(error):
                if error:
                    print(f"Error al terminar la reproducción: {error}")
                
                # Lógica para reanudar la radio automática
                if len(voice_client.channel.members) == 1:
                    print("La canción ha terminado y el bot está solo. Reanudando radio automática.")
                    # Usamos bot.loop.create_task para llamar a una función async desde un callback síncrono
                    bot.loop.create_task(start_radio(voice_client, RADIO_URL))
                    global radio_is_auto
                    radio_is_auto = True

            voice_client.play(source, after=after_playing)
            print(f"📻 Reproduciendo: {info.get('title', 'Radio Stream')}")
            return info.get('title', 'Canción desconocida') # Devolvemos el título

    except Exception as e:
        print(f"❌ Error al iniciar la radio/play: {e}")
        return None

async def stop_radio(voice_client: discord.VoiceClient):
    if voice_client and voice_client.is_playing():
        voice_client.stop()
        print("📻 Radio detenida.")

# --- 6. EVENTOS PRINCIPALES DEL BOT ---
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
            trigger = CronTrigger(hour=21, minute=5) 
            scheduler.add_job(scheduled_restart_check, trigger)
            scheduler.start()
            print("⏰ El programador de reinicio inteligente está activo.")
        except Exception as e:
            print(f'❌ Error durante la conexión inicial: {e}')

@bot.event
async def on_voice_state_update(member, before, after):
    if not bot_is_ready:
        return
    
    global bot_is_zombie, last_reconnect_attempt, restart_is_pending, radio_is_auto
    voice_client = discord.utils.get(bot.voice_clients, guild=member.guild)
    designated_channel = bot.get_channel(VOICE_CHANNEL_ID)

    # --- LÓGICA DE RADIO AUTOMÁTICA ---
    # 1. Alguien se va y el bot se queda solo
    if before.channel == designated_channel and len(before.channel.members) == 1 and bot.user in before.channel.members:
        print("🤖 El bot se ha quedado solo. Iniciando radio automática...")
        await start_radio(voice_client)
        radio_is_auto = True
        general_channel = bot.get_channel(GENERAL_CHANNEL_ID)
        if general_channel:
            await general_channel.send(f"🎶 La radio automática ha comenzado en **{voice_client.channel.name}**.")

    # 2. Alguien entra al canal donde el bot está solo con la radio
    radio_prompt_sent = False
    if not member.bot and after.channel == designated_channel and len(after.channel.members) == 2 and radio_is_auto:
        print(f"👤 {member.display_name} ha entrado. Ofreciendo opciones de radio...")
        general_channel = bot.get_channel(GENERAL_CHANNEL_ID)
        if general_channel:
            view = RadioControlView(voice_client)
            message = await general_channel.send(f"¡Hola, {member.display_name}! La radio automática está sonando. ¿Qué quieres hacer?", view=view)
            view.message = message
            radio_prompt_sent = True

    # --- LÓGICA DE REINICIO, RECONEXIÓN Y BIENVENIDA ---
    if restart_is_pending and voice_client and len(voice_client.channel.members) >= 3:
        await perform_restart(voice_client)
        restart_is_pending = False
        return

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

    # --- LÓGICA DE BIENVENIDA Y CURACIÓN DE ZOMBIE (CORREGIDA) ---
    # Solo se activa si un usuario entra al canal designado
    if not member.bot and after.channel == designated_channel:
        
        # CORRECCIÓN: La curación solo se activa si el usuario VIENE DE AFUERA (before.channel es None)
        if bot_is_zombie and before.channel is None:
            print(f"👤 {member.display_name} ha entrado. Es la señal para curar al bot zombie.")
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
        
        # La bienvenida solo se activa si el usuario cambia de canal Y no se enviaron los botones de la radio
        elif voice_client and before.channel != after.channel and not radio_prompt_sent:
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

# --- 7. COMANDOS SLASH ---
@bot.slash_command(name="ping", description="Verifica la latencia del bot.")
async def ping(ctx: discord.ApplicationContext):
    await ctx.respond(f"¡Pong! 🏓 Latencia: {round(bot.latency * 1000)}ms", ephemeral=True)

@bot.slash_command(name="radio", description="Controla la radio 24/7.")
@commands.is_owner()
async def radio(ctx: discord.ApplicationContext, accion: discord.Option(str, choices=["start", "stop"])):
    global radio_is_auto
    voice_client = discord.utils.get(bot.voice_clients, guild=ctx.guild)
    if not voice_client or not voice_client.is_connected():
        return await ctx.respond("No estoy conectado a un canal de voz.", ephemeral=True)
    if accion.lower() == "start":
        if voice_client.is_playing():
            return await ctx.respond("La radio ya está sonando.", ephemeral=True)
        await start_radio(voice_client)
        radio_is_auto = False
        await ctx.respond("📻 Radio iniciada manualmente.", ephemeral=True)
    elif accion.lower() == "stop":
        if not voice_client.is_playing():
            return await ctx.respond("La radio no está sonando.", ephemeral=True)
        await stop_radio(voice_client)
        radio_is_auto = False
        await ctx.respond("📻 Radio detenida.", ephemeral=True)

# ... (después del comando /radio)

@bot.slash_command(name="play", description="Reproduce una canción de YouTube.")
async def play(ctx: discord.ApplicationContext, cancion: str):
    """Busca y reproduce una canción o URL de YouTube."""
    global radio_is_auto
    voice_client = discord.utils.get(bot.voice_clients, guild=ctx.guild)

    # Verificamos si el usuario está en un canal de voz
    if not ctx.author.voice or not ctx.author.voice.channel:
        return await ctx.respond("Debes estar en un canal de voz para poner música.", ephemeral=True)

    # Si el bot no está conectado, se une al canal del usuario
    if not voice_client:
        voice_client = await ctx.author.voice.channel.connect()
    # Si el bot está en otro canal, se mueve al del usuario
    elif voice_client.channel != ctx.author.voice.channel:
        await voice_client.move_to(ctx.author.voice.channel)

    await ctx.defer() # Damos tiempo al bot para buscar la canción

    radio_is_auto = False # Una petición manual siempre desactiva el modo automático
    song_title = await start_radio(voice_client, url=cancion)

    if song_title:
        await ctx.followup.send(f"🎵 Ahora sonando: **{song_title}**")
    else:
        await ctx.followup.send("Lo siento, no pude encontrar o reproducir esa canción.")

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

# --- 8. EJECUCIÓN DEL BOT ---
if __name__ == "__main__":
    if not DISCORD_TOKEN:
        print("❌ ERROR CRÍTICO: La variable de entorno DISCORD_TOKEN no está configurada.")
    else:
        bot.run(DISCORD_TOKEN)