import discord
from discord.ext import tasks
import os
from dotenv import load_dotenv
import asyncio
import discord.opus # Necesario para el handshake aunque no hable

# --- CONFIGURACIÓN ---
# Si no tienes config.py, pon el ID numérico aquí directo
try:
    from config import VOICE_CHANNEL_ID
except ImportError:
    VOICE_CHANNEL_ID = 123456789012345678 

load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

# --- PARCHE PARA VM DE LINUX ---
if not discord.opus.is_loaded():
    try:
        discord.opus.load_opus('libopus.so.0')
    except:
        pass # Si falla, esperamos que funcione igual

class SilentBot(discord.Client):
    def __init__(self):
        # Intents mínimos (ahorran recursos)
        intents = discord.Intents.default()
        super().__init__(intents=intents)

    async def on_ready(self):
        print(f'🗿 Bot Estatua conectado como: {self.user}')
        # Iniciamos el bucle de "aferrarse al canal"
        self.keep_alive_loop.start()

    @tasks.loop(seconds=30)
    async def keep_alive_loop(self):
        # Buscamos el canal objetivo
        channel = self.get_channel(VOICE_CHANNEL_ID)
        if not channel:
            print("❌ No encuentro el canal.")
            return

        # Verificamos si ya estamos conectados en ese servidor
        voice_client = channel.guild.voice_client

        try:
            if voice_client is None:
                print("🔌 Entrando al canal...")
                await channel.connect()
                
            elif not voice_client.is_connected():
                print("⚠️ Reconectando...")
                await voice_client.disconnect(force=True)
                await channel.connect()

            # TRUCO: Si alguien mueve al bot, este código NO lo regresa.
            # Se queda donde lo dejes. Solo se preocupa de estar conectado.
            
        except Exception as e:
            print(f"⚠️ Error de conexión: {e}")

    @keep_alive_loop.before_loop
    async def before_keep_alive(self):
        await self.wait_until_ready()

if __name__ == "__main__":
    bot = SilentBot()
    bot.run(DISCORD_TOKEN)