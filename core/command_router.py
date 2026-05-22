# ============================================
# Command Router - Routes commands to handlers
# ============================================

import asyncio
import logging
import re
from typing import Dict, List, Tuple, Optional, Any
from datetime import datetime

from groq import AsyncGroq

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from config import GROQ_API_KEY, GROQ_MODEL, GROQ_TEMPERATURE, GROQ_MAX_TOKENS, VA_NAME

logger = logging.getLogger(__name__)


class CommandRouter:
    """Routes user commands to appropriate handlers"""
    
    def __init__(self):
        self.groq = AsyncGroq(api_key=GROQ_API_KEY)
        self.handlers = self._register_handlers()
    
    def _register_handlers(self) -> Dict[str, callable]:
        """Register command handlers"""
        return {
            # Browser commands
            'browser_open': self._handle_browser_open,
            'browser_close_tab': self._handle_browser_close_tab,
            'browser_switch_tab': self._handle_browser_switch_tab,
            'browser_read_news': self._handle_browser_read_news,
            'browser_save_article': self._handle_browser_save_article,
            'browser_launch_or_focus': self._handle_browser_launch_or_focus,
            
            # Window commands
            'window_switch': self._handle_window_switch,
            'window_minimize': self._handle_window_minimize,
            'window_maximize': self._handle_window_maximize,
            'window_snap_left': self._handle_window_snap_left,
            'window_snap_right': self._handle_window_snap_right,
            'window_fullscreen': self._handle_window_fullscreen,
            
            # Reminder commands
            'reminder_set': self._handle_reminder_set,
            'reminder_timer': self._handle_timer,
            'reminder_alarm': self._handle_alarm,
            'reminder_list': self._handle_reminder_list,
            'reminder_cancel': self._handle_reminder_cancel,
            
            # System commands
            'system_status': self._handle_system_status,
            'system_volume': self._handle_system_volume,
            
            # File commands
            'file_create': self._handle_file_create,
            'file_edit': self._handle_file_edit,
            'file_delete': self._handle_file_delete,
            'file_write': self._handle_file_write,
        }
    
    async def route(self, text: str, context: List[Dict], user_id: int,
                    reminder_system=None) -> Tuple[str, str]:
        """
        Route command to appropriate handler
        Returns: (response_text, action_type)
        """
        text_lower = text.lower().strip()
        
        # Try pattern matching first
        command_type, params = self._parse_command(text_lower)
        
        if command_type and command_type in self.handlers:
            try:
                # Lazy import to avoid circular dependencies
                from browser.yandex_controller import YandexBrowserController
                from windows.window_manager import WindowManager
                
                browser = YandexBrowserController()
                window_manager = WindowManager()
                
                # Use provided reminder_system or create new one (without callback)
                if reminder_system is None:
                    from reminders.reminder_system import ReminderSystem
                    reminder_system = ReminderSystem()
                
                handler = self.handlers[command_type]
                response = await handler(params, browser, window_manager, reminder_system, user_id)
                return response, 'command_executed'
            except Exception as e:
                logger.error(f"Handler error: {e}")
                return f"❌ Ошибка выполнения: {e}", 'error'
        
        # Use LLM for general conversation with full context
        return await self._handle_conversation(text, context, user_id, reminder_system)
    
    def _parse_command(self, text: str) -> Tuple[Optional[str], Dict]:
        """Parse command text to determine command type and parameters"""
        
        patterns = {
            # Browser patterns
            'browser_open': r'(открой|запусти)\s+(яндекс|браузер|youtube|ютуб|вк|vk|гугл|google)',
            'browser_launch_or_focus': r'(открой|запусти|активируй|переключи)\s+(яндекс\s+браузер|браузер\s+яндекс|яндекс)',
            'browser_close_tab': r'(закрой|закрыть)\s+(вкладку|вкладки)\s+(с\s+)?(.+)',
            'browser_switch_tab': r'(переключись|перейди)\s+(на\s+)?вкладку\s+(.+)',
            'browser_read_news': r'(прочитай|покажи)\s+новости',
            'browser_save_article': r'(сохрани|добавь)\s+(статью|в закладки)',
            
            # Window patterns
            'window_switch': r'(переключись|перейди)\s+на\s+(.+)',
            'window_minimize': r'(сверни|минимизируй)\s+(.+)',
            'window_maximize': r'(разверни|максимизируй)\s+(.+)',
            'window_snap_left': r'(слева|лево|на лево)\s+(.+)',
            'window_snap_right': r'(справа|право|на право)\s+(.+)',
            'window_fullscreen': r'(на весь экран|полный экран)\s+(.+)',
            
            # Reminder patterns
            'reminder_set': r'напомни\s+(через\s+(\d+)\s*(минут|минуту|час|часа|секунд|секунду)\s+)?(.+)',
            'reminder_timer': r'таймер\s+(на\s+)?(\d+)\s*(минут|минуту|секунд|секунду|час|часа)',
            'reminder_alarm': r'будильник\s+(на\s+)?(\d{1,2}):(\d{2})',
            'reminder_list': r'(мои\s+)?напоминания',
            'reminder_cancel': r'(отмени|удали)\s+напоминание\s+(\d+)',
            
            # System patterns
            'system_status': r'(статус|состояние|как дела)',
            'system_volume': r'(громкость|звук)\s+(\d+|вкл|выкл|больше|меньше)',
            
            # File patterns
            'file_create': r'(создай|создать)\s+(файл|текстовый документ)\s+(.+)',
            'file_edit': r'(отредактируй|измени|обнови)\s+(файл|текстовый документ)\s+(.+)',
            'file_delete': r'(удали|удалить)\s+(файл|текстовый документ)\s+(.+)',
            'file_write': r'(запиши|добавь|напиши)\s+(в\s+)?(файл|текстовый документ)\s+(.+?)\s+(с текстом\s+)?(.+)',
        }
        
        for command_type, pattern in patterns.items():
            match = re.search(pattern, text)
            if match:
                params = {'full_match': match.group(0), 'groups': match.groups()}
                return command_type, params
        
        return None, {}
    
    async def _handle_conversation(self, text: str, context: List[Dict],
                                    user_id: int, reminder_system=None) -> Tuple[str, str]:
        """Handle general conversation with LLM using full conversation history"""
        try:
            # Lazy import to avoid circular dependencies
            from core.context_manager import ContextManager
            context_manager = ContextManager()
            
            # Get full conversation history in LLM-friendly format
            conversation_history = context_manager.get_conversation_history(
                user_id, max_entries=20
            )
            
            # Get current time for context
            current_time = datetime.now().strftime("%H:%M")
            current_date = datetime.now().strftime("%d.%m.%Y")
            
            system_prompt = f"""Ты — голосовой ассистент {VA_NAME}. Ты дружелюбная, умная и немного игривая.

Текущее время: {current_time}
Текущая дата: {current_date}

Ты можешь:
- Управлять браузером Яндекс (открывать, закрывать вкладки, читать новости)
- Управлять окнами (переключать, сворачивать, разворачивать, расположать)
- Ставить напоминания, таймеры и будильники
- Работать с текстовыми файлами на рабочем столе (создавать, редактировать, удалять)
- Поддерживать разговор и отвечать на вопросы

ВАЖНО: У тебя есть доступ к полной истории диалога с пользователем. Используй её для понимания контекста.
Если пользователь отвечает коротко (да, нет, хорошо, ок, конечно) — это ответ на твой предыдущий вопрос или предложение.
Если пользователь просит продолжить что-то — вспомни, о чём шла речь ранее.

Отвечай кратко (1-3 предложения), по-человечески, с эмодзи. Если пользователь просит что-то сделать, что ты не умеешь — предложи альтернативу или объясни, что можешь сделать."""

            # Build messages for LLM with full conversation history
            messages = [{"role": "system", "content": system_prompt}]
            
            # Add conversation history
            messages.extend(conversation_history)
            
            # Add current user message
            messages.append({"role": "user", "content": text})
            
            response = await self.groq.chat.completions.create(
                model=GROQ_MODEL,
                messages=messages,
                temperature=GROQ_TEMPERATURE,
                max_tokens=GROQ_MAX_TOKENS
            )
            
            answer = response.choices[0].message.content
            return answer, 'conversation'
            
        except Exception as e:
            logger.error(f"LLM error: {e}")
            return f"Извини, не могу сейчас ответить. Ошибка: {e}", 'error'
    
    # ============== Browser Handlers ==============
    
    async def _handle_browser_open(self, params, browser, wm, rs, user_id):
        target = params['groups'][-1] if params['groups'] else 'yandex'

        urls = {
            'яндекс': 'https://ya.ru',
            'yandex': 'https://ya.ru',
            'браузер': 'https://ya.ru',
            'youtube': 'https://youtube.com',
            'ютуб': 'https://youtube.com',
            'вк': 'https://vk.com',
            'vk': 'https://vk.com',
            'гугл': 'https://google.com',
            'google': 'https://google.com',
        }

        url = urls.get(target, f'https://{target}.com')
        success = await browser.open_url(url)

        if success:
            return f"🌐 Открываю {target}..."
        return f"❌ Не удалось открыть {target}"

    async def _handle_browser_launch_or_focus(self, params, browser, wm, rs, user_id):
        """
        Handler for 'launch or focus Yandex Browser' command.

        If the browser is already running → activates its window.
        If not running → starts a new instance.
        """
        result = await browser.launch_or_focus()

        if result['success']:
            action_emoji = {
                'focused': '🪟',
                'launched': '🚀',
            }.get(result['action'], '✅')
            return f"{action_emoji} {result['message']}"

        return f"❌ {result['message']}"
    
    async def _handle_browser_close_tab(self, params, browser, wm, rs, user_id):
        tab_name = params['groups'][-1] if params['groups'] else ''
        success = await browser.close_tab_by_name(tab_name)
        
        if success:
            return f"🗑️ Закрыла вкладку с {tab_name}"
        return f"❌ Не нашла вкладку с {tab_name}"
    
    async def _handle_browser_switch_tab(self, params, browser, wm, rs, user_id):
        tab_name = params['groups'][-1] if params['groups'] else ''
        success = await browser.switch_to_tab(tab_name)
        
        if success:
            return f"🔄 Переключилась на вкладку {tab_name}"
        return f"❌ Не нашла вкладку {tab_name}"
    
    async def _handle_browser_read_news(self, params, browser, wm, rs, user_id):
        headlines = await browser.get_headlines()
        
        if headlines:
            response = "📰 <b>Последние новости:</b>\n\n"
            for i, headline in enumerate(headlines[:5], 1):
                response += f"{i}. {headline}\n"
            return response
        return "❌ Не удалось получить новости"
    
    async def _handle_browser_save_article(self, params, browser, wm, rs, user_id):
        success = await browser.save_current_page()
        
        if success:
            return "💾 Статья сохранена в закладки!"
        return "❌ Не удалось сохранить статью"
    
    # ============== Window Handlers ==============
    
    async def _handle_window_switch(self, params, browser, wm, rs, user_id):
        window_name = params['groups'][-1] if params['groups'] else ''
        success = wm.switch_to_window(window_name)
        
        if success:
            return f"🪟 Переключилась на окно: {window_name}"
        return f"❌ Не нашла окно: {window_name}"
    
    async def _handle_window_minimize(self, params, browser, wm, rs, user_id):
        window_name = params['groups'][-1] if params['groups'] else ''
        success = wm.minimize_window(window_name)
        
        if success:
            return f"⬇️ Свернула окно: {window_name}"
        return f"❌ Не удалось свернуть окно: {window_name}"
    
    async def _handle_window_maximize(self, params, browser, wm, rs, user_id):
        window_name = params['groups'][-1] if params['groups'] else ''
        success = wm.maximize_window(window_name)
        
        if success:
            return f"⬆️ Развернула окно: {window_name}"
        return f"❌ Не удалось развернуть окно: {window_name}"
    
    async def _handle_window_snap_left(self, params, browser, wm, rs, user_id):
        window_name = params['groups'][-1] if params['groups'] else ''
        success = wm.snap_window(window_name, 'left')
        
        if success:
            return f"⬅️ Окно {window_name} слева"
        return f"❌ Не удалось расположить окно"
    
    async def _handle_window_snap_right(self, params, browser, wm, rs, user_id):
        window_name = params['groups'][-1] if params['groups'] else ''
        success = wm.snap_window(window_name, 'right')
        
        if success:
            return f"➡️ Окно {window_name} справа"
        return f"❌ Не удалось расположить окно"
    
    async def _handle_window_fullscreen(self, params, browser, wm, rs, user_id):
        window_name = params['groups'][-1] if params['groups'] else ''
        success = wm.snap_window(window_name, 'fullscreen')
        
        if success:
            return f"🖥️ Окно {window_name} на весь экран"
        return f"❌ Не удалось развернуть окно"
    
    # ============== Reminder Handlers ==============
    
    async def _handle_reminder_set(self, params, browser, wm, rs, user_id):
        groups = params.get('groups', [])
        
        # Parse time
        time_value = 0
        time_unit = 'minutes'
        message = ''
        
        if len(groups) >= 4:
            if groups[1]:  # has time specification
                time_value = int(groups[1]) if groups[1] else 0
                time_unit = groups[2] if groups[2] else 'minutes'
                message = groups[3] if groups[3] else 'Напоминание'
            else:
                message = groups[3] if groups[3] else 'Напоминание'
        
        # Convert to minutes
        if 'час' in time_unit:
            time_value *= 60
        elif 'секунд' in time_unit:
            time_value = time_value / 60
        
        reminder_id = rs.add_reminder(user_id, message, minutes=int(time_value))
        return f"⏰ Напоминание установлено через {time_value} минут: {message}"
    
    async def _handle_timer(self, params, browser, wm, rs, user_id):
        groups = params.get('groups', [])
        
        time_value = int(groups[1]) if len(groups) > 1 and groups[1] else 5
        time_unit = groups[2] if len(groups) > 2 and groups[2] else 'минут'
        
        if 'час' in time_unit:
            time_value *= 60
        elif 'секунд' in time_unit:
            time_value = max(1, time_value // 60)
        
        reminder_id = rs.add_timer(user_id, time_value)
        return f"⏱️ Таймер на {time_value} минут установлен!"
    
    async def _handle_alarm(self, params, browser, wm, rs, user_id):
        groups = params.get('groups', [])
        
        hour = int(groups[1]) if len(groups) > 1 and groups[1] else 7
        minute = int(groups[2]) if len(groups) > 2 and groups[2] else 0
        
        reminder_id = rs.add_alarm(user_id, hour, minute)
        return f"🕐 Будильник установлен на {hour:02d}:{minute:02d}!"
    
    async def _handle_reminder_list(self, params, browser, wm, rs, user_id):
        reminders = rs.get_user_reminders(user_id)
        
        if not reminders:
            return "📭 У вас нет активных напоминаний"
        
        response = "<b>📝 Ваши напоминания:</b>\n\n"
        for r in reminders:
            response += f"ID: <code>{r['id']}</code> - {r['message']} ({r['time']})\n"
        
        return response
    
    async def _handle_reminder_cancel(self, params, browser, wm, rs, user_id):
        groups = params.get('groups', [])
        reminder_id = int(groups[1]) if len(groups) > 1 and groups[1] else 0
        
        success = rs.cancel_reminder(reminder_id)
        
        if success:
            return f"✅ Напоминание {reminder_id} отменено"
        return f"❌ Не удалось отменить напоминание {reminder_id}"
    
    # ============== System Handlers ==============
    
    async def _handle_system_status(self, params, browser, wm, rs, user_id):
        import psutil
        
        cpu = psutil.cpu_percent()
        memory = psutil.virtual_memory()
        
        return (
            f"📊 <b>Статус системы:</b>\n"
            f"🖥️ CPU: {cpu}%\n"
            f"💾 RAM: {memory.percent}%\n"
            f"✨ Всё работает отлично!"
        )
    
    async def _handle_system_volume(self, params, browser, wm, rs, user_id):
        groups = params.get('groups', [])
        volume_cmd = groups[1] if len(groups) > 1 and groups[1] else '50'
        
        try:
            from ctypes import cast, POINTER
            from comtypes import CLSCTX_ALL
            from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
            
            devices = AudioUtilities.GetSpeakers()
            interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            volume = cast(interface, POINTER(IAudioEndpointVolume))
            
            if volume_cmd.isdigit():
                vol = int(volume_cmd) / 100
                volume.SetMasterVolumeLevelScalar(vol, None)
                return f"🔊 Громкость установлена на {volume_cmd}%"
            elif volume_cmd in ['вкл', 'on']:
                volume.SetMute(0, None)
                return "🔊 Звук включён"
            elif volume_cmd in ['выкл', 'off']:
                volume.SetMute(1, None)
                return "🔇 Звук выключен"
            elif volume_cmd in ['больше', 'громче']:
                current = volume.GetMasterVolumeLevelScalar()
                volume.SetMasterVolumeLevelScalar(min(1.0, current + 0.1), None)
                return "🔊 Громкость увеличена"
            elif volume_cmd in ['меньше', 'тише']:
                current = volume.GetMasterVolumeLevelScalar()
                volume.SetMasterVolumeLevelScalar(max(0.0, current - 0.1), None)
                return "🔉 Громкость уменьшена"
            
        except Exception as e:
            logger.error(f"Volume control error: {e}")
            return f"❌ Ошибка управления громкостью: {e}"
    
    # ============== File Handlers ==============
      
    async def _handle_file_create(self, params, browser, wm, rs, user_id):
        """Handler for creating a text file on desktop"""
        from utils.desktop_file_manager import create_desktop_file, FileAction
        
        filename = params['groups'][-1] if params['groups'] else 'новый_файл'
        
        result = create_desktop_file(filename)
        
        if result['success']:
            return f"[OK] {result['message']}"
        return f"[ERR] {result['message']}"
    
    async def _handle_file_edit(self, params, browser, wm, rs, user_id):
        """Handler for editing a text file on desktop"""
        from utils.desktop_file_manager import edit_desktop_file
        
        filename = params['groups'][-1] if params['groups'] else ''
        
        if not filename:
            return "[ERR] Укажите имя файла для редактирования"
        
        result = edit_desktop_file(filename)
        
        if result['success']:
            return f"[OK] {result['message']}"
        return f"[ERR] {result['message']}"
    
    async def _handle_file_delete(self, params, browser, wm, rs, user_id):
        """Handler for deleting a text file from desktop"""
        from utils.desktop_file_manager import delete_desktop_file
        
        filename = params['groups'][-1] if params['groups'] else ''
        
        if not filename:
            return "[ERR] Укажите имя файла для удаления"
        
        result = delete_desktop_file(filename)
        
        if result['success']:
            return f"[OK] {result['message']}"
        return f"[ERR] {result['message']}"
    
    async def _handle_file_write(self, params, browser, wm, rs, user_id):
        """Handler for writing text to a file on desktop"""
        from utils.desktop_file_manager import manage_desktop_file, FileAction
        
        groups = params.get('groups', [])
        # groups: (запиши/добавь/напиши, в/пусто, файл/текстовый документ, имя_файла, None, текст)
        filename = groups[3] if len(groups) > 3 else ''
        content = groups[5] if len(groups) > 5 else ''
        
        if not filename:
            return "[ERR] Укажите имя файла"
        
        if not content:
            return "[ERR] Укажите текст для записи"
        
        # Создаём файл с содержимым сразу
        result = manage_desktop_file(filename, content, FileAction.CREATE)
        
        if result['success']:
            return f"[OK] Текст записан в файл: {filename}.txt"
        return f"[ERR] {result['message']}"
