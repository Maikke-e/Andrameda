# ============================================
# Andromeda Telegram Bot - aiogram 3
# ============================================

import asyncio
import logging
import tempfile
import time
import random
from pathlib import Path
from typing import Optional, Set, Dict, Any
from datetime import datetime

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, FSInputFile
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

import sys
sys.path.append(str(Path(__file__).parent.parent))

from config import (
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_WHITE_LIST,
    VA_NAME,
    LOG_LEVEL,
    LOG_FILE,
    SCREENSHOT_DIR
)
from core.voice_processor import VoiceProcessor
from core.command_router import CommandRouter
from core.context_manager import ContextManager
from core.timing_analyzer import TimingAnalyzer
from tts.tts_engine import TTSEngine
from browser.yandex_controller import YandexBrowserController
from windows.window_manager import WindowManager
from reminders.reminder_system import ReminderSystem

# Setup logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class AndromedaTelegramBot:
    """Telegram Bot for Andromeda Voice Assistant"""
    
    def __init__(self):
        self.bot = Bot(
            token=TELEGRAM_BOT_TOKEN,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML)
        )
        self.dp = Dispatcher()
        
        # Initialize components
        self.voice_processor = VoiceProcessor()
        self.command_router = CommandRouter()
        self.context_manager = ContextManager()
        self.timing_analyzer = TimingAnalyzer()
        self.tts_engine = TTSEngine()
        self.browser = YandexBrowserController()
        self.window_manager = WindowManager()
        self.reminder_system = ReminderSystem(self._send_notification)
        
        # System status cache
        self._system_status_cache = {}
        self._system_status_cache_time = 0
        self._system_status_cache_ttl = 5  # seconds
        
        # Register handlers
        self._register_handlers()
        
        logger.info(f"{VA_NAME} Telegram Bot initialized")
    
    def _get_system_status(self) -> Dict[str, Any]:
        """Get current system status with caching"""
        current_time = time.time()
        
        # Return cached data if still valid
        if (current_time - self._system_status_cache_time) < self._system_status_cache_ttl and self._system_status_cache:
            return self._system_status_cache
        
        import psutil
        
        # Get basic system info
        cpu_percent = psutil.cpu_percent()
        memory = psutil.virtual_memory()
        memory_percent = memory.percent
        
        # Get additional system details
        try:
            # Number of processes
            num_processes = len(psutil.pids())
        except Exception:
            num_processes = 0
            
        # Temperature info (if available)
        try:
            temps = psutil.sensors_temperatures()
            cpu_temp = 0
            if 'coretemp' in temps:
                cpu_temp = temps['coretemp'][0].current if temps['coretemp'] else 0
            elif 'cpu_thermal' in temps:
                cpu_temp = temps['cpu_thermal'][0].current if temps['cpu_thermal'] else 0
        except Exception:
            cpu_temp = 0
        
        # Prepare status data
        status_data = {
            'cpu_percent': cpu_percent,
            'memory_percent': memory_percent,
            'memory_used_gb': memory.used // (1024**3),
            'memory_total_gb': memory.total // (1024**3),
            'num_processes': num_processes,
            'cpu_temp': cpu_temp,
            'timestamp': current_time
        }
        
        # Cache the data
        self._system_status_cache = status_data
        self._system_status_cache_time = current_time
        
        return status_data
    
    def _generate_mood_response(self, status: Dict[str, Any]) -> str:
        """Generate mood response based on system status"""
        cpu_percent = status['cpu_percent']
        memory_percent = status['memory_percent']
        
        # Determine load level
        if cpu_percent > 90 or memory_percent > 95:
            load_level = "critical"
        elif cpu_percent > 70 or memory_percent > 80:
            load_level = "high"
        elif cpu_percent > 30 or memory_percent > 50:
            load_level = "medium"
        else:
            load_level = "low"
        
        # Define responses for each level
        responses = {
            "low": [
                "Отлично! 😊 Всё работает идеально!",
                "Всё супер! 🚀 Готов к новым задачам!",
                "Работаю без проблем! 💫 Полный заряд энергии!",
                "Прекрасно! ✨ Система в оптимальном режиме!",
                "Замечательно! 🌟 Всё функционирует flawlessly!"
            ],
            "medium": [
                "Нормально 👍 Всё работает стабильно",
                "Никаких проблем 😌 Работаю в штатном режиме",
                "Всё под контролем 🔧 Стабильная работа",
                "Радушен помочь! 💪 Готов к работе",
                "Всё хорошо 🙂 Система в норме"
            ],
            "high": [
                "Сейчас немного перегружен 😅 Работаю в пределах возможностей",
                "Может немного тормозить ⚠️ Но справляюсь",
                "Потихоньку успокаиваюсь 😌 Нагрузка повышена",
                "Работаю с усилием 💪 Но всё под контролем",
                "Система под нагрузкой 🔥 Но я не сдаюсь"
            ],
            "critical": [
                "Серьёзно задействован 😰 Потихоньку успокаиваюсь",
                "Может подёргивать 😬 Работаю в режиме экономии",
                "На пределе возможностей 💥 Но продолжаю работать",
                "Система перегружена 🚨 Но я не отключаюсь",
                "Работаю на износ 😓 Но не сдамся"
            ]
        }
        
        # Select random response from appropriate category
        import random
        response = random.choice(responses[load_level])
        
        # Add detailed info if needed
        if load_level in ["high", "critical"]:
            detail_info = f"\n\n📊 Детали: CPU {cpu_percent}%, RAM {memory_percent}%"
            response += detail_info
        
        return response

    def _generate_detailed_response(self, status: Dict[str, Any]) -> str:
        """Generate detailed system status response"""
        cpu_percent = status['cpu_percent']
        memory_percent = status['memory_percent']
        memory_used_gb = status['memory_used_gb']
        memory_total_gb = status['memory_total_gb']
        num_processes = status['num_processes']
        cpu_temp = status['cpu_temp']

        # Build detailed response
        response = (
            f"<b>📊 Подробный статус системы {VA_NAME}</b>\n\n"
            f"🖥️ CPU: <code>{cpu_percent}%</code>"
        )

        if cpu_temp > 0:
            response += f" (температура: {cpu_temp}°C)"

        response += (
            f"\n💾 RAM: <code>{memory_percent}%</code> "
            f"({memory_used_gb}GB / {memory_total_gb}GB)\n"
        )

        response += (
            f"⚙️ Процессов: <code>{num_processes}</code>\n"
            f"💾 Использование кэша TTS: "
            f"<code>{'Вкл' if self.tts_engine.cache_enabled else 'Выкл'}</code>\n"
            f"😊 Эмоциональный движок: "
            f"<code>{'Вкл' if self.tts_engine.emotion_enabled else 'Выкл'}</code>\n"
            f"📝 Контекст диалога: "
            f"<code>активен</code> команд\n"
        )

        # Add load assessment
        if cpu_percent > 90 or memory_percent > 95:
            response += "\n🚨 <b>Нагрузка: КРИТИЧЕСКАЯ</b>\n"
            response += "Система сильно перегружена, возможны задержки"
        elif cpu_percent > 70 or memory_percent > 80:
            response += "\n⚠️ <b>Нагрузка: ВЫСОКАЯ</b>\n"
            response += "Система под нагрузкой, но работает стабильно"
        elif cpu_percent > 30 or memory_percent > 50:
            response += "\n📊 <b>Нагрузка: СРЕДНЯЯ</b>\n"
            response += "Умеренное использование ресурсов"
        else:
            response += "\n✅ <b>Нагрузка: НИЗКАЯ</b>\n"
            response += "Система работает в оптимальном режиме"

        return response
    
    def _register_handlers(self):
        """Register message handlers"""
        
        # Start command
        @self.dp.message(CommandStart())
        async def cmd_start(message: Message):
            if not self._check_access(message):
                return
            
            await message.answer(
                f"👋 <b>Привет! Я {VA_NAME}</b>\n\n"
                f"🎙️ Отправь голосовое сообщение или напиши команду\n"
                f"📋 Используй /help для списка команд\n\n"
                f"✨ Я умею:\n"
                f"• Управлять браузером Яндекс\n"
                f"• Управлять окнами\n"
                f"• Ставить напоминания и таймеры\n"
                f"• Понимать контекст разговора"
            )
        
        # Help command
        @self.dp.message(Command("help"))
        async def cmd_help(message: Message):
            if not self._check_access(message):
                return
            
            help_text = (
                "<b>📋 Доступные команды:</b>\n\n"
                
                "<b>🌐 Браузер:</b>\n"
                "• <code>открой яндекс</code>\n"
                "• <code>закрой вкладку с [название]</code>\n"
                "• <code>переключись на вкладку [название]</code>\n"
                "• <code>прочитай новости</code>\n"
                "• <code>сохрани статью</code>\n\n"
                
                "<b>🪟 Окна:</b>\n"
                "• <code>переключись на [название окна]</code>\n"
                "• <code>сверни [название]</code>\n"
                "• <code>разверни [название]</code>\n"
                "• <code>слева [название]</code> / <code>справа [название]</code>\n"
                "• <code>на весь экран [название]</code>\n\n"
                
                "<b>⏰ Напоминания:</b>\n"
                "• <code>напомни через 5 минут позвонить маме</code>\n"
                "• <code>таймер 10 минут</code>\n"
                "• <code>будильник на 7:00</code>\n"
                "• <code>мои напоминания</code>\n"
                "• <code>отмени напоминание [id]</code>\n\n"
                
                "<b>📊 Система:</b>\n"
                "• <code>/status</code> - статус системы\n"
                "• <code>/screenshot</code> - скриншот экрана\n"
                "• <code>/context</code> - показать контекст\n"
                "• <code>/timing</code> - анализ времени ответа"
            )
            await message.answer(help_text)
        
        # Status command
        @self.dp.message(Command("status"))
        async def cmd_status(message: Message):
            if not self._check_access(message):
                return

            status = self._get_system_status()

            cpu = status['cpu_percent']
            memory_percent = status['memory_percent']
            memory_used_gb = status['memory_used_gb']
            memory_total_gb = status['memory_total_gb']

            status_text = (
                f"<b>📊 Статус системы {VA_NAME}</b>\n\n"
                f"🖥️ CPU: <code>{cpu}%</code>\n"
                f"💾 RAM: <code>{memory_percent}%</code> ({memory_used_gb}GB / {memory_total_gb}GB)\n"
                f"📝 Контекст: <code>{len(self.context_manager.get_context(message.from_user.id))} команд</code>\n"
                f"🔊 TTS Cache: <code>{'Вкл' if self.tts_engine.cache_enabled else 'Выкл'}</code>\n"
                f"😊 Эмоции: <code>{'Вкл' if self.tts_engine.emotion_enabled else 'Выкл'}</code>"
            )
            await message.answer(status_text)
        
        # Context command
        @self.dp.message(Command("context"))
        async def cmd_context(message: Message):
            if not self._check_access(message):
                return
            
            context = self.context_manager.get_context(message.from_user.id)
            if not context:
                await message.answer("📭 Контекст пуст")
                return
            
            context_text = "<b>📝 Последние команды:</b>\n\n"
            for i, item in enumerate(context[-5:], 1):
                context_text += f"{i}. <code>{item['command']}</code> ({item['timestamp']})\n"
            
            await message.answer(context_text)
        
        # Timing analysis command
        @self.dp.message(Command("timing"))
        async def cmd_timing(message: Message):
            if not self._check_access(message):
                return
            
            stats = self.timing_analyzer.get_stats()
            
            timing_text = (
                f"<b>⏱️ Анализ времени ответа</b>\n\n"
                f"📊 <b>Общая статистика:</b>\n"
                f"• Среднее время: <code>{stats.get('avg_total', 0):.2f}с</code>\n"
                f"• Минимальное: <code>{stats.get('min_total', 0):.2f}с</code>\n"
                f"• Максимальное: <code>{stats.get('max_total', 0):.2f}с</code>\n\n"
                f"🔍 <b>По этапам (среднее):</b>\n"
                f"• Распознавание речи: <code>{stats.get('avg_stt', 0):.2f}с</code>\n"
                f"• Обработка LLM: <code>{stats.get('avg_llm', 0):.2f}с</code>\n"
                f"• Генерация TTS: <code>{stats.get('avg_tts', 0):.2f}с</code>\n"
                f"• Воспроизведение: <code>{stats.get('avg_playback', 0):.2f}с</code>"
            )
            await message.answer(timing_text)
        
        # Screenshot command
        @self.dp.message(Command("screenshot"))
        async def cmd_screenshot(message: Message):
            if not self._check_access(message):
                return

            try:
                import pyautogui

                screenshot = pyautogui.screenshot()

                # Generate filename with timestamp
                timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
                filename = f'screenshot_{timestamp}.png'
                filepath = SCREENSHOT_DIR / filename

                # Save screenshot to the dedicated folder
                screenshot.save(filepath)

                # Send to Telegram
                photo = FSInputFile(filepath)
                await message.answer_photo(photo, caption="📸 Скриншот экрана")

            except Exception as e:
                logger.error(f"Screenshot error: {e}")
                await message.answer(f"❌ Ошибка: {e}")
        
        # Text message handler
        @self.dp.message(F.text)
        async def handle_text(message: Message):
            if not self._check_access(message):
                return
            
            text = message.text.lower().strip()
            
            # Check for mood/status phrases
            mood_phrases = [
                'как дела', 'как ты', 'настроение', 'как настроение',
                'как жизнь', 'как поживаешь', 'как сам', 'как чувствуешь',
                'как поживаешь', 'как ты поживаешь', 'как у тебя дела'
            ]
            
            # Check for detail request phrases
            detail_phrases = ['подробнее', 'детали', 'подробности', 'detail', 'details']
            
            # Check if any mood phrase is in the text
            is_mood_query = any(phrase in text for phrase in mood_phrases)
            is_detail_request = any(phrase in text for phrase in detail_phrases)
            
            if is_mood_query:
                # Get system status and generate mood response
                status = self._get_system_status()
                mood_response = self._generate_mood_response(status)
                await message.answer(mood_response)
                return
            elif is_detail_request:
                # Get system status and generate detailed response
                status = self._get_system_status()
                detailed_response = self._generate_detailed_response(status)
                await message.answer(detailed_response)
                return
            
            await self._process_command(message, message.text)
        
        # Voice message handler
        @self.dp.message(F.voice)
        async def handle_voice(message: Message):
            if not self._check_access(message):
                return
            
            # Download voice file
            voice_file = await self.bot.get_file(message.voice.file_id)
            
            with tempfile.NamedTemporaryFile(suffix='.ogg', delete=False) as f:
                await self.bot.download_file(voice_file.file_path, f.name)
                
                # Start timing
                self.timing_analyzer.start_timer(message.from_user.id)
                
                # Process voice
                text = await self.voice_processor.transcribe(f.name)
                
                self.timing_analyzer.record_stt(message.from_user.id)
                
                # Delete temp file
                Path(f.name).unlink(missing_ok=True)
            
            if text:
                await message.answer(f"🎙️ Распознано: <i>{text}</i>")
                await self._process_command(message, text, is_voice=True)
            else:
                await message.answer("❌ Не удалось распознать голосовое сообщение")
    
    def _check_access(self, message: Message) -> bool:
        """Check if user is in white list"""
        user_id = str(message.from_user.id)
        username = message.from_user.username or ''
        
        if not TELEGRAM_WHITE_LIST:
            return True
        
        if user_id in TELEGRAM_WHITE_LIST or username in TELEGRAM_WHITE_LIST:
            return True
        
        logger.warning(f"Access denied for user {username} ({user_id})")
        asyncio.create_task(
            message.answer("⛔ Доступ запрещён. Обратитесь к администратору.")
        )
        return False
    
    async def _process_command(self, message: Message, text: str, is_voice: bool = False):
        """Process user command"""
        user_id = message.from_user.id
        
        # Add to context
        self.context_manager.add_command(user_id, text)
        
        # Get context for processing
        context = self.context_manager.get_context(user_id)
        
        # Route command
        response, action_type = await self.command_router.route(
            text=text,
            context=context,
            user_id=user_id
        )
        
        self.timing_analyzer.record_llm(user_id)
        
        # Send text response
        await message.answer(response)
        
        # Generate and send voice response if needed
        if is_voice or action_type in ['tts_required', 'voice_response']:
            voice_path = await self.tts_engine.speak(response, user_id=user_id)
            self.timing_analyzer.record_tts(user_id)
            
            if voice_path:
                voice_file = FSInputFile(voice_path)
                await message.answer_voice(voice_file)
        
        # Record total time
        self.timing_analyzer.record_total(user_id)
    
    async def _send_notification(self, user_id: int, text: str):
        """Send notification to user"""
        try:
            await self.bot.send_message(user_id, f"🔔 <b>Напоминание:</b>\n{text}")
        except Exception as e:
            logger.error(f"Notification error: {e}")
    
    async def start(self):
        """Start the bot"""
        logger.info(f"Starting {VA_NAME} Telegram Bot...")
        await self.dp.start_polling(self.bot)


async def main():
    """Main entry point"""
    bot = AndromedaTelegramBot()
    await bot.start()


if __name__ == "__main__":
    asyncio.run(main())
