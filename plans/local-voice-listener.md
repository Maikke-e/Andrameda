# План: Гибридный режим — Telegram Bot + Локальный голосовой ассистент

## Текущее состояние (анализ завершён)

### ✅ Уже реализовано (готово к использованию)

| Компонент | Статус | Примечания |
|-----------|--------|------------|
| [`config.py`](config.py:70) | ✅ Готов | Строки 70–78: все настройки `LOCAL_VOICE_*`, `WAKE_WORD_*`, `SILENCE_*`, `MIC_*` |
| [`dev.env`](dev.env:39) | ✅ Готов | Строки 39–44: все переменные окружения для локального голоса |
| [`core/voice_processor.py`](core/voice_processor.py:26) | ✅ Готов | Метод `create_stream_recognizer()` с `SetWords(True)` для потокового Vosk |
| [`core/audio_player.py`](core/audio_player.py:17) | ✅ Готов | `play_file()`, `play_beep()`, `play_double_beep()`, `stop()`, `is_playing()`, `close()` |
| [`core/local_voice_listener.py`](core/local_voice_listener.py:56) | ✅ Готов | Полный цикл: IDLE → LISTENING → PROCESSING → SPEAKING → IDLE |
| [`core/command_router.py`](core/command_router.py:66) | ✅ Готов | `async route()` — принимает `text`, `context`, `user_id`, `reminder_system` |
| [`tts/tts_engine.py`](tts/tts_engine.py:215) | ✅ Готов | `async speak()` — возвращает путь к WAV, кэширование, Silero Ксения |

### ❌ Что нужно сделать

| Файл | Изменение | Строка |
|------|-----------|--------|
| [`main.py`](main.py:43) | Добавить `self.voice_listener` в `AndromedaApp.__init__`, запустить в `start()`, остановить в `stop()` | 46, 58–75, 81–89 |

---

## Архитектура параллельной работы

```
┌─────────────────────────────────────────────────────────────┐
│                    AndromedaApp (main.py)                    │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────────────┐    ┌──────────────────────────┐  │
│  │  Telegram Bot       │    │  Local Voice Listener     │  │
│  │  (asyncio)          │    │  (threading.Thread)       │  │
│  │                     │    │                          │  │
│  │  • Получает сообщения│    │  • Слушает микрофон       │  │
│  │  • Обрабатывает через│    │  • Детектирует wake-word  │  │
│  │    CommandRouter    │    │    через Vosk             │  │
│  │  • Отвечает через   │    │  • Записывает команду     │  │
│  │    TTS              │    │  • Обрабатывает через     │  │
│  │                     │    │    CommandRouter          │  │
│  │                     │    │  • Отвечает через TTS     │  │
│  └─────────────────────┘    └──────────────────────────┘  │
│           │                            │                   │
│           │  общие компоненты          │                   │
│           ├──────────────────────────►│                   │
│           │  CommandRouter, TTS,       │                   │
│           │  ContextManager, и т.д.    │                   │
└─────────────────────────────────────────────────────────────┘
```

### Цикл локального голосового ассистента

```
IDLE (слушает микрофон)
    │
    │ Vosk распознаёт "андромеда" / "андра" / "андрамеда"
    ▼
LISTENING (бип! → запись команды)
    │
    │ VAD: тишина ≥ 1.5 сек → конец фразы
    ▼
PROCESSING (CommandRouter.route())
    │
    │ LLM обрабатывает команду
    ▼
SPEAKING (TTS → AudioPlayer → динамики)
    │
    │ Воспроизведение завершено
    ▼
IDLE (ждёт следующего wake-word)
```

---

## Шаги реализации

### Шаг 1: Модифицировать [`main.py`](main.py)

**Изменения в классе `AndromedaApp`:**

1. Добавить импорт `LOCAL_VOICE_ENABLED` из `config` (строка 22)
2. Добавить атрибут `self.voice_listener` в `__init__` (после строки 46)
3. В `start()` после инициализации Telegram-бота добавить запуск `LocalVoiceListener` (перед строкой 70)
4. В `stop()` добавить остановку `voice_listener` (перед строкой 85)

**Код изменений:**

```python
# Строка 22 — добавить импорт
from config import LOG_LEVEL, LOG_FILE, VA_NAME, VA_VER, LOCAL_VOICE_ENABLED

# Строка 46 — добавить атрибут
self.voice_listener: 'LocalVoiceListener' = None

# В start() после строки 72 (self.telegram_bot = AndromedaTelegramBot())
# Добавить:
if LOCAL_VOICE_ENABLED:
    logger.info("Initializing Local Voice Listener...")
    from core.local_voice_listener import LocalVoiceListener
    self.voice_listener = LocalVoiceListener()
    self.voice_listener.start()
    logger.info("Local Voice Listener started")

# В stop() после строки 85 (if self.telegram_bot:)
# Добавить:
if self.voice_listener:
    logger.info("Stopping Local Voice Listener...")
    self.voice_listener.stop()
    self.voice_listener = None
```

---

### Шаг 2: Проверить [`dev.env`](dev.env)

Настройки уже присутствуют (строки 39–44). Никаких изменений не требуется.

### Шаг 3: Проверить [`requirements.txt`](requirements.txt)

Все необходимые зависимости уже указаны:
- `vosk==0.3.45` — распознавание речи
- `pyaudio==0.2.14` — захват микрофона и воспроизведение
- `numpy==1.26.3` — обработка аудио
- `torch==2.2.0`, `torchaudio==2.2.0`, `silero==0.4.1` — TTS

Никаких изменений не требуется.

---

## Проверка перед запуском

### Автоматические проверки

```powershell
# 1. Проверка доступности микрофона
python -c "import pyaudio; p = pyaudio.PyAudio(); print(p.get_default_input_device_info())"

# 2. Проверка модели Vosk
python -c "import vosk; m = vosk.Model('model_small'); print('Vosk model OK')"

# 3. Проверка импортов
python -c "from core.local_voice_listener import LocalVoiceListener; print('LocalVoiceListener OK')"
```

### Ручная проверка после запуска

1. Запустить `python main.py`
2. Сказать **"Андромеда"** → должен прозвучать сигнал активации (бип)
3. После сигнала сказать команду, например **"сколько времени"** → должна выполниться и прозвучать TTS-ответ
4. Проверить что Telegram-бот продолжает отвечать на сообщения параллельно
5. Проверить что после ответа система возвращается в режим ожидания wake-word

---

## Потенциальные проблемы и решения

| Проблема | Решение |
|----------|---------|
| PyAudio не устанавливается на Windows | Уже установлен согласно заданию |
| Vosk модель не найдена | Убедиться что папка `model_small` существует в корне проекта |
| Конфликт микрофона между потоками | `LocalVoiceListener` использует отдельный экземпляр `PyAudio` |
| Задержка при обработке команды | `CommandRouter` вызывается через `run_until_complete()` в отдельном event loop |
| TTS ответ прерывается новым wake-word | В состоянии `SPEAKING` новые wake-words игнорируются |
