# main.py
import discord
from discord.ext import commands
import asyncio
import os
from gtts import gTTS
import collections
import wave
import time

# --- 1. CARGA DE CONFIGURACIÓN Y TOKEN ---
from config import (
    VOICE_CHANNEL_ID,
    TTS_BRIDGE_CHANNEL_ID,
    TTS_BRIDGE_ROLE_NAME,
    FOLLOWME_EXEMPT_USER_ID,
    MEMENTO_CHANNEL_ID # <-- NUEVA VARIABLE DE CONFIGURACIÓN
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

# --- 4. CLASE PERSONALIZADA PARA EL SINK DE MEMENTO ---

class MementoSink(discord.Sink):
    def __init__(self):
        # Creamos un buffer que guarda 30 segundos de audio (aprox)
        # 100 (muestras/seg) * 2 (canales) * 30 (segundos) = 6000
        self.audio_buffer = collections.deque(maxlen=6000)

    def write(self, data, user):
        # Esta función se llama cada vez que se recibe un paquete de audio
        self.audio_buffer.append(data)

    def save_to_file(self, filename="memento.wav"):
        # Esta es nuestra función personalizada para guardar el buffer
        if not self.audio_buffer:
            return None # No hay nada que guardar

        # Usamos la librería 'wave' para crear un archivo .wav
        with wave.open(filename, "wb") as wf:
            wf.setnchannels(2) # Estéreo
            wf.setsampwidth(2) # 16-bit
            wf.setframerate(48000) # Calidad estándar de Discord
            wf.writeframes(b"".join(self.audio_buffer))
        
        # Limpiamos el buffer después de guardar
        self.audio_buffer.clear()
        return filename

# --- 5. FUNCIÓN AUXILIAR PARA TEXT-TO-SPEECH (TTS) ---
# (Esta función no cambia)
async def play_tts(voice_client, text, filename="tts.mp3"):
    if not voice_client or not voice_client.is_connected(): return
    try:
        tts = gTTS(text=text, lang='es', slow=False)
        tts.save(filename)
        while voice_client.is_playing(): await asyncio.sleep(0.5)
        source = discord.FFmpegPCMAudio(filename)
        voice_client.play(source)
        while voice_client.is_playing(): await asyncio.sleep(0.5)
        os.remove(filename)
    except Exception as e:
        print(f"Error en play_tts: {e}")
        if os.path.exists(filename): os.remove(filename)

# --- 6. EVENTOS PRINCIPALES DEL BOT ---
@bot.event
async def on_ready():
    print(f'✅ Bot conectado como: {bot.user.name} (ID: {bot.user.id})')
    voice_channel = bot.get_channel(VOICE_CHANNEL_ID)
    if voice_channel:
        try:
            vc = await voice_channel.connect()
            print(f'🔗 Conectado a {voice_channel.name}.')
            # ¡AQUÍ EMPIEZA A "ESCUCHAR"!
            vc.start_recording(MementoSink(), once_done)
            print("🎙️ El bot ha comenzado a escuchar para la función Memento.")
        except Exception as e:
            print(f'❌ Error al conectar o iniciar grabación: {e}')

async def once_done(sink: MementoSink, channel: discord.TextChannel, *args):
    # Esta función se llama si la grabación se detiene por alguna razón.
    # No la usaremos activamente, pero es necesaria para start_recording.
    print("La grabación se ha detenido.")

# (El resto de los eventos como on_voice_state_update y on_message no cambian)
@bot.event
async def on_voice_state_update(member, before, after):
    # ... (código sin cambios)
    voice_client = discord.utils.get(bot.voice_clients, guild=member.guild)
    if not member.bot and voice_client and after.channel == voice_client.channel and before.channel != after.channel:
        welcome_message = f"Bienvenido, {member.display_name}"
        await play_tts(voice_client, welcome_message, f"welcome_{member.id}.mp3")
    if member.id == bot.user.id and after.channel is None:
        print("🔴 Bot desconectado. Intentando reconectar en 5 segundos...")
        await asyncio.sleep(5)
        try:
            voice_channel = bot.get_channel(VOICE_CHANNEL_ID)
            if voice_channel:
                vc = await voice_channel.connect()
                vc.start_recording(MementoSink(), once_done) # Vuelve a grabar
                print("✅ Bot reconectado y grabando de nuevo.")
        except Exception as e: print(f"❌ Error al reconectar: {e}")

@bot.event
async def on_message(message):
    # ... (código sin cambios)
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


# --- 7. COMANDOS SLASH ---
# (Comandos /ping, /bridge, /followme, /unfollowme sin cambios)

@bot.slash_command(name="memento", description="Guarda los últimos 30 segundos de audio del canal de voz.")
async def memento(ctx: discord.ApplicationContext):
    voice_client = discord.utils.get(bot.voice_clients, guild=ctx.guild)
    if not voice_client or not voice_client.is_recording():
        return await ctx.respond("No estoy grabando en este momento.", ephemeral=True)

    sink = voice_client.recording
    filename = f"memento_{ctx.author.name}_{int(time.time())}.wav"
    saved_file = sink.save_to_file(filename)

    if saved_file:
        memento_channel = bot.get_channel(MEMENTO_CHANNEL_ID)
        if memento_channel:
            await ctx.respond("¡Momento guardado!", ephemeral=True)
            await memento_channel.send(f"¡Un Memento capturado por **{ctx.author.display_name}**!", file=discord.File(saved_file))
            try:
                os.remove(saved_file)
                print(f"Archivo temporal '{saved_file}' eliminado exitosamente.")
            except OSError as e:
                print(f"Error al eliminar el archivo temporal: {e}")
        else:
            await ctx.respond("No se pudo encontrar el canal para enviar el Memento.", ephemeral=True)
    else:
        await ctx.respond("Aún no hay suficiente audio para guardar un Memento. ¡Inténtalo de nuevo en unos segundos!", ephemeral=True)

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

if __name__ == "__main__":
    if not DISCORD_TOKEN:
        print("❌ ERROR CRÍTICO: La variable de entorno DISCORD_TOKEN no está configurada.")
    else:
        bot.run(DISCORD_TOKEN)