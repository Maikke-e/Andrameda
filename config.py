# ============================================
# Andromeda Configuration
# ============================================

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv('dev.env')

# --- Base Paths ---
BASE_DIR = Path(__file__).parent
CACHE_DIR = BASE_DIR / 'cache'
DATA_DIR = BASE_DIR / 'data'
LOGS_DIR = BASE_DIR / 'logs'

# --- Screenshot Settings ---
SCREENSHOT_DIR = Path(os.getenv('SCREENSHOT_DIR', r'C:\Users\Andra\Pictures\Andra_Screenshots'))

# Create directories
for dir_path in [CACHE_DIR, DATA_DIR, LOGS_DIR, SCREENSHOT_DIR]:
    dir_path.mkdir(exist_ok=True)

# --- Assistant Info ---
VA_NAME = 'Андромеда'
VA_VER = "3.0"
VA_ALIAS = ('андра', 'андрамеда', 'андрюшка')

# --- Trigger Words ---
VA_TBR = (
    'скажи', 'покажи', 'ответь', 'произнеси', 
    'расскажи', 'сколько', 'слушай', 'сделай',
    'открой', 'закрой', 'включи', 'выключи',
    'переключи', 'перемести', 'сверни', 'разверни'
)

# --- Telegram Settings ---
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_WHITE_LIST = set()

# Parse white list
_white_list_raw = os.getenv('TELEGRAM_WHITE_LIST', '')
if _white_list_raw:
    TELEGRAM_WHITE_LIST = set(item.strip() for item in _white_list_raw.split(',') if item.strip())

# --- API Keys ---
PICOVOICE_TOKEN = os.getenv('PICOVOICE_TOKEN', '')
GROQ_API_KEY = os.getenv('GROQ_API_KEY', '')

# --- Vosk ---
VOSK_MODEL_PATH = os.getenv('VOSK_MODEL_PATH', 'model_small')

# --- TTS Settings ---
TTS_CACHE_ENABLED = os.getenv('TTS_CACHE_ENABLED', 'true').lower() == 'true'
TTS_CACHE_DIR = Path(os.getenv('TTS_CACHE_DIR', 'cache/tts'))
TTS_STREAMING_ENABLED = os.getenv('TTS_STREAMING_ENABLED', 'true').lower() == 'true'
TTS_STREAMING_CHUNK_SIZE = 1024

# --- Context Settings ---
CONTEXT_MAX_COMMANDS = int(os.getenv('CONTEXT_MAX_COMMANDS', '10'))
CONTEXT_TTL = int(os.getenv('CONTEXT_TTL', '30'))  # minutes

# --- Browser Settings ---
BROWSER_TYPE = os.getenv('BROWSER_TYPE', 'yandex')
BROWSER_DEBUG_PORT = int(os.getenv('BROWSER_DEBUG_PORT', '9222'))
YANDEX_BROWSER_PATH = os.getenv('YANDEX_BROWSER_PATH', r'C:\Program Files\Yandex\YandexBrowser\Application\browser.exe')
YANDEX_BROWSER_LNK_PATH = os.getenv('YANDEX_BROWSER_LNK_PATH', r'C:\Andromeda\bin\Яндекс Браузер с Алисой AI.lnk')

# --- Window Management ---
WINDOW_SNAP_DELAY = 0.5

# --- Logging ---
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOG_FILE = LOGS_DIR / 'andromeda.log'

# --- Groq Models ---
GROQ_MODEL = "llama-3.1-8b-instant"
GROQ_TEMPERATURE = 0.7
GROQ_MAX_TOKENS = 1024

# --- Timing Analysis ---
TIMING_LOG_FILE = DATA_DIR / 'timing_analysis.json'
