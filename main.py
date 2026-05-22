import asyncio
import logging
import signal
import sys
import os
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parent))

# Set console output to UTF-8 to avoid UnicodeEncodeError on Windows
import io
if hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
elif hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
else:
    os.environ['PYTHONIOENCODING'] = 'utf-8'

from config import LOG_LEVEL, LOG_FILE, VA_NAME, VA_VER, LOCAL_VOICE_ENABLED
from core.telegram_bot import AndromedaTelegramBot

def setup_logging():
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    
    # Create stream handler with UTF-8 encoding
    stream_handler = logging.StreamHandler(stream=sys.stdout)
    
    logging.basicConfig(
        level=getattr(logging, LOG_LEVEL),
        format=log_format,
        handlers=[
            logging.FileHandler(LOG_FILE, encoding='utf-8'),
            stream_handler
        ]
    )


class AndromedaApp:
    
    def __init__(self):
        self.telegram_bot: AndromedaTelegramBot = None
        self.voice_listener = None
        self.running = False
        
        # Setup signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        logging.info(f"Received signal {signum}, shutting down...")
        self.running = False
    
    async def start(self):
        """Start Andromeda"""
        setup_logging()
        logger = logging.getLogger(__name__)
        
        logger.info(f"╔══════════════════════════════════════════╗")
        logger.info(f"║     {VA_NAME} v{VA_VER} Starting...      ║")
        logger.info(f"╚══════════════════════════════════════════╝")
        
        self.running = True
        
        try:
            # Initialize Local Voice Listener
            if LOCAL_VOICE_ENABLED:
                logger.info("Initializing Local Voice Listener...")
                from core.local_voice_listener import LocalVoiceListener
                self.voice_listener = LocalVoiceListener()
                self.voice_listener.start()
                logger.info("Local Voice Listener started")

            # Initialize Telegram Bot
            logger.info("Initializing Telegram Bot...")
            self.telegram_bot = AndromedaTelegramBot()
            
            # Start bot
            await self.telegram_bot.start()
            
        except Exception as e:
            logger.error(f"Fatal error: {e}", exc_info=True)
            raise
    
    async def stop(self):
        """Stop Andromeda"""
        logging.info("Stopping Andromeda...")
        
        if self.voice_listener:
            logging.info("Stopping Local Voice Listener...")
            self.voice_listener.stop()
            self.voice_listener = None
        
        if self.telegram_bot:
            # Cleanup
            pass
        
        logging.info("Andromeda stopped")


async def main():
    """Main entry point"""
    app = AndromedaApp()
    
    try:
        await app.start()
    except KeyboardInterrupt:
        print("\nShutdown requested...")
    finally:
        await app.stop()


if __name__ == "__main__":
    # Print banner
    print(f"""
    ╔══════════════════════════════════════════════════════════════╗
    ║                                                              ║
    ║         🤖 АНДРОМЕДА v{VA_VER} - Голосовой Ассистент        ║
    ║                                                              ║
    ║   ✨ Telegram Bot с голосовым управлением                   ║
    ║   🌐 Управление браузером Яндекс                            ║
    ║   🪟 Расширенное управление окнами                            ║
    ║   🧠 Контекстные диалоги с памятью                          ║
    ║   😊 Эмоциональный интеллект                                ║
    ║   ⏰ Напоминания, таймеры, будильники                       ║
    ║                                                              ║
    ╚══════════════════════════════════════════════════════════════╝
    """)
    
    # Run main
    asyncio.run(main())
