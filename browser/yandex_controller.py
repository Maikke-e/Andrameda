# ============================================
# Yandex Browser Controller
# ============================================

import asyncio
import json
import logging
import websockets
import psutil
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
from datetime import datetime

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

import sys
import subprocess
import time
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from config import BROWSER_DEBUG_PORT, YANDEX_BROWSER_PATH, YANDEX_BROWSER_LNK_PATH

logger = logging.getLogger(__name__)

# Имена процессов Яндекс Браузера для проверки
YANDEX_PROCESS_NAMES = [
    'browser.exe',
    'YandexBrowser.exe',
    'YandexBrowser',
]

# Ключевые слова в заголовке окна для идентификации Яндекс Браузера
YANDEX_WINDOW_KEYWORDS = [
    'яндекс',
    'yandex',
    'yandexbrowser',
]


@dataclass
class TabInfo:
    """Browser tab information"""
    id: str
    title: str
    url: str
    favicon: str = ""
    
    def to_dict(self) -> Dict:
        return {
            'id': self.id,
            'title': self.title,
            'url': self.url,
            'favicon': self.favicon
        }


class YandexBrowserController:
    """
    Controller for Yandex Browser

    Features:
    - Open/close tabs
    - Switch between tabs
    - Get tab information
    - Read page content
    - Save articles/bookmarks
    - Check if browser is running
    - Launch or focus existing browser window
    """

    def __init__(self):
        self.driver: Optional[webdriver.Chrome] = None
        self.debug_port = BROWSER_DEBUG_PORT
        self.browser_path = YANDEX_BROWSER_PATH
        self.ws_url: Optional[str] = None
        self.ws_connection: Optional[websockets.WebSocketClientProtocol] = None
        self.tabs: List[TabInfo] = []
        self._window_manager = None

    # ============== Process & Window Detection ==============

    def is_browser_running(self) -> bool:
        """
        Check if Yandex Browser process is currently running.

        Returns:
            True if at least one Yandex Browser process is found, False otherwise.
        """
        try:
            for proc in psutil.process_iter(['pid', 'name']):
                proc_name = proc.info['name']
                if proc_name and any(
                    proc_name.lower() == name.lower()
                    for name in YANDEX_PROCESS_NAMES
                ):
                    logger.debug(f"Found Yandex Browser process: {proc_name} (PID: {proc.info['pid']})")
                    return True
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess) as e:
            logger.warning(f"Error checking browser processes: {e}")

        logger.debug("Yandex Browser process not found")
        return False

    def find_browser_window(self) -> Optional[Any]:
        """
        Find the Yandex Browser window using pygetwindow.

        Returns:
            Window object if found, None otherwise.
        """
        try:
            import pygetwindow as gw

            all_windows = gw.getAllWindows()
            for window in all_windows:
                title = window.title.lower()
                if any(keyword in title for keyword in YANDEX_WINDOW_KEYWORDS):
                    logger.debug(f"Found Yandex Browser window: '{window.title}'")
                    return window
        except Exception as e:
            logger.warning(f"Error finding browser window: {e}")

        logger.debug("Yandex Browser window not found")
        return None

    def focus_browser_window(self) -> bool:
        """
        Activate and bring focus to the existing Yandex Browser window.

        If the window is minimized, it will be restored first.

        Returns:
            True if the window was successfully activated, False otherwise.
        """
        window = self.find_browser_window()

        if not window:
            logger.warning("Cannot focus browser: window not found")
            return False

        try:
            # Restore if minimized
            if window.isMinimized:
                window.restore()
                time.sleep(0.2)

            # Activate / bring to front
            window.activate()
            time.sleep(0.3)

            logger.info(f"Focused Yandex Browser window: '{window.title}'")
            return True

        except Exception as e:
            logger.error(f"Failed to focus browser window: {e}")
            return False

    async def launch_or_focus(self) -> Dict[str, Any]:
        """
        Main entry point for launching or focusing Yandex Browser.

        Behaviour:
        - If Yandex Browser is already running → activate its window and return success.
        - If not running → start a new instance, wait for it to be ready, and return success.

        Returns:
            Dict with keys:
                'success'   : bool
                'action'    : 'focused' | 'launched' | 'failed'
                'message'   : human-readable description
        """
        logger.info("launch_or_focus() called")

        # Step 1: Check if the browser process is already running
        if self.is_browser_running():
            logger.info("Yandex Browser is already running — attempting to focus window")

            # Try to activate the existing window
            if self.focus_browser_window():
                return {
                    'success': True,
                    'action': 'focused',
                    'message': 'Яндекс Браузер уже запущен, переключаю фокус на окно.',
                }

            # Window activation failed — fall through to re-launch
            logger.warning("Process is running but window activation failed, will try to reconnect")

        # Step 2: Try to connect to an already-running browser via CDP
        try:
            options = Options()
            options.add_experimental_option("debuggerAddress", f"localhost:{self.debug_port}")

            self.driver = webdriver.Chrome(options=options)
            logger.info("Connected to existing Yandex Browser via CDP")

            # Try to focus the window even after CDP connection
            self.focus_browser_window()

            return {
                'success': True,
                'action': 'focused',
                'message': 'Яндекс Браузер уже запущен, подключился и переключил фокус.',
            }

        except Exception as e:
            logger.info(f"Could not connect via CDP ({e}), starting new browser instance")

        # Step 3: Start a fresh browser instance
        try:
            await self._start_browser()

            # Wait a moment for the process to appear and the window to be created
            await asyncio.sleep(2)

            # Try to connect via CDP
            options = Options()
            options.add_experimental_option("debuggerAddress", f"localhost:{self.debug_port}")
            self.driver = webdriver.Chrome(options=options)

            # Focus the newly started window
            self.focus_browser_window()

            # Get CDP WebSocket URL
            await self._connect_cdp()

            # Update tabs list
            await self._update_tabs()

            return {
                'success': True,
                'action': 'launched',
                'message': 'Яндекс Браузер запущен.',
            }

        except Exception as e:
            logger.error(f"Failed to launch Yandex Browser: {e}", exc_info=True)
            return {
                'success': False,
                'action': 'failed',
                'message': f'Не удалось запустить Яндекс Браузер: {e}',
            }

    async def initialize(self):
        """Initialize browser connection"""
        try:
            # Setup Chrome options for Yandex Browser
            options = Options()
            options.add_experimental_option("debuggerAddress", f"localhost:{self.debug_port}")

            # Try to connect to existing browser
            try:
                self.driver = webdriver.Chrome(options=options)
                logger.info("Connected to existing Yandex Browser instance")
            except:
                # Start new browser instance
                logger.info("Starting new Yandex Browser instance...")
                await self._start_browser()
                self.driver = webdriver.Chrome(options=options)

            # Get CDP WebSocket URL
            await self._connect_cdp()

            # Update tabs list
            await self._update_tabs()

            return True

        except Exception as e:
            logger.error(f"Failed to initialize browser: {e}")
            return False
    
    async def _start_browser(self):
        """Start Yandex Browser with debug port.

        Supports both direct .exe paths and .lnk shortcut files.
        Priority:
          1. YANDEX_BROWSER_LNK_PATH from config (user-specified .lnk)
          2. YANDEX_BROWSER_PATH from config (direct .exe)
          3. Well-known default installation paths
        """
        import subprocess
        import os

        # --- Candidate paths in priority order ---
        candidate_paths: List[str] = []

        # 1. User-specified .lnk shortcut
        lnk = YANDEX_BROWSER_LNK_PATH
        if lnk and Path(lnk).exists():
            candidate_paths.append(lnk)

        # 2. Direct .exe from config
        exe = YANDEX_BROWSER_PATH
        if exe and Path(exe).exists():
            candidate_paths.append(exe)

        # 3. Well-known default installation paths
        default_exe_paths = [
            r"C:\Program Files\Yandex\YandexBrowser\Application\browser.exe",
            r"C:\Program Files (x86)\Yandex\YandexBrowser\Application\browser.exe",
            os.path.expanduser(r"~\AppData\Local\Yandex\YandexBrowser\Application\browser.exe"),
        ]
        for path in default_exe_paths:
            if Path(path).exists() and path not in candidate_paths:
                candidate_paths.append(path)

        if not candidate_paths:
            raise RuntimeError(
                "Yandex Browser not found. "
                "Check YANDEX_BROWSER_LNK_PATH or YANDEX_BROWSER_PATH in config."
            )

        # --- Pick the first available candidate ---
        launch_target = candidate_paths[0]
        is_lnk = launch_target.lower().endswith('.lnk')

        if is_lnk:
            # Launch via Windows Shell so the .lnk is resolved correctly
            cmd = [
                'cmd', '/c', 'start', '', launch_target,
            ]
            logger.info(f"Launching Yandex Browser via .lnk shortcut: {launch_target}")
        else:
            cmd = [
                launch_target,
                f"--remote-debugging-port={self.debug_port}",
                "--no-first-run",
                "--no-default-browser-check",
            ]
            logger.info(f"Launching Yandex Browser via .exe: {launch_target}")

        subprocess.Popen(cmd)
        await asyncio.sleep(3)  # Wait for browser to start
    
    async def _connect_cdp(self):
        """Connect to Chrome DevTools Protocol"""
        import aiohttp
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"http://localhost:{self.debug_port}/json") as resp:
                    pages = await resp.json()
                    
                    if pages:
                        self.ws_url = pages[0].get('webSocketDebuggerUrl')
                        logger.info(f"CDP WebSocket URL: {self.ws_url}")
        except Exception as e:
            logger.error(f"Failed to connect to CDP: {e}")
    
    async def _update_tabs(self):
        """Update list of open tabs"""
        if not self.driver:
            return
        
        try:
            # Get all window handles
            handles = self.driver.window_handles
            self.tabs = []
            
            for handle in handles:
                self.driver.switch_to.window(handle)
                tab = TabInfo(
                    id=handle,
                    title=self.driver.title,
                    url=self.driver.current_url
                )
                self.tabs.append(tab)
                
        except Exception as e:
            logger.error(f"Failed to update tabs: {e}")
    
    async def open_url(self, url: str) -> bool:
        """Open URL in new tab"""
        if not self.driver:
            if not await self.initialize():
                return False
        
        try:
            # Open new tab
            self.driver.execute_script(f"window.open('{url}', '_blank');")
            
            # Switch to new tab
            self.driver.switch_to.window(self.driver.window_handles[-1])
            
            # Wait for page load
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            
            await self._update_tabs()
            logger.info(f"Opened URL: {url}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to open URL: {e}")
            return False
    
    async def close_tab_by_name(self, name: str) -> bool:
        """Close tab by name/title"""
        if not self.driver:
            return False
        
        try:
            await self._update_tabs()
            
            # Find tab by name (partial match)
            name_lower = name.lower()
            for tab in self.tabs:
                if name_lower in tab.title.lower() or name_lower in tab.url.lower():
                    # Switch to tab and close it
                    self.driver.switch_to.window(tab.id)
                    self.driver.close()
                    
                    # Switch back to first tab
                    if self.driver.window_handles:
                        self.driver.switch_to.window(self.driver.window_handles[0])
                    
                    await self._update_tabs()
                    logger.info(f"Closed tab: {tab.title}")
                    return True
            
            logger.warning(f"Tab not found: {name}")
            return False
            
        except Exception as e:
            logger.error(f"Failed to close tab: {e}")
            return False
    
    async def switch_to_tab(self, name: str) -> bool:
        """Switch to tab by name/title"""
        if not self.driver:
            return False
        
        try:
            await self._update_tabs()
            
            name_lower = name.lower()
            for tab in self.tabs:
                if name_lower in tab.title.lower() or name_lower in tab.url.lower():
                    self.driver.switch_to.window(tab.id)
                    logger.info(f"Switched to tab: {tab.title}")
                    return True
            
            logger.warning(f"Tab not found: {name}")
            return False
            
        except Exception as e:
            logger.error(f"Failed to switch tab: {e}")
            return False
    
    async def get_headlines(self, source: str = 'yandex') -> List[str]:
        """Get news headlines from current page"""
        if not self.driver:
            return []
        
        try:
            # Navigate to news if needed
            current_url = self.driver.current_url
            if 'news' not in current_url and source == 'yandex':
                await self.open_url('https://yandex.ru/news')
                await asyncio.sleep(2)
            
            # Extract headlines
            headlines = []
            
            # Common headline selectors
            selectors = [
                'h1', 'h2', 'h3',
                '[class*="title"]',
                '[class*="headline"]',
                '[class*="news"]',
                'article h2',
                '.mg-card__title'
            ]
            
            for selector in selectors:
                try:
                    elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    for elem in elements[:10]:  # Limit to 10 headlines
                        text = elem.text.strip()
                        if text and len(text) > 10 and text not in headlines:
                            headlines.append(text)
                except:
                    continue
            
            return headlines[:5]  # Return top 5
            
        except Exception as e:
            logger.error(f"Failed to get headlines: {e}")
            return []
    
    async def save_current_page(self, save_type: str = 'bookmark') -> bool:
        """Save current page as bookmark or to Notion"""
        if not self.driver:
            return False
        
        try:
            title = self.driver.title
            url = self.driver.current_url
            
            if save_type == 'bookmark':
                # Save to local bookmarks file
                bookmarks_file = Path('data/bookmarks.json')
                bookmarks_file.parent.mkdir(exist_ok=True)
                
                bookmarks = []
                if bookmarks_file.exists():
                    with open(bookmarks_file, 'r', encoding='utf-8') as f:
                        bookmarks = json.load(f)
                
                bookmark = {
                    'title': title,
                    'url': url,
                    'saved_at': datetime.now().isoformat()
                }
                bookmarks.append(bookmark)
                
                with open(bookmarks_file, 'w', encoding='utf-8') as f:
                    json.dump(bookmarks, f, ensure_ascii=False, indent=2)
                
                logger.info(f"Saved bookmark: {title}")
                return True
            
            elif save_type == 'notion':
                # TODO: Implement Notion integration
                logger.info("Notion integration not yet implemented")
                return False
            
            return False
            
        except Exception as e:
            logger.error(f"Failed to save page: {e}")
            return False
    
    async def get_page_content(self) -> str:
        """Get text content of current page"""
        if not self.driver:
            return ""
        
        try:
            # Get main content
            body = self.driver.find_element(By.TAG_NAME, 'body')
            return body.text[:2000]  # Limit to 2000 chars
        except Exception as e:
            logger.error(f"Failed to get page content: {e}")
            return ""
    
    async def execute_script(self, script: str) -> Any:
        """Execute JavaScript in browser"""
        if not self.driver:
            return None
        
        try:
            return self.driver.execute_script(script)
        except Exception as e:
            logger.error(f"Script execution error: {e}")
            return None
    
    async def scroll_page(self, direction: str = 'down', amount: int = 500):
        """Scroll page up or down"""
        script = f"window.scrollBy(0, {'-' if direction == 'up' else ''}{amount});"
        await self.execute_script(script)
    
    async def find_and_click(self, text: str) -> bool:
        """Find element by text and click it"""
        if not self.driver:
            return False
        
        try:
            # Try different strategies
            strategies = [
                (By.LINK_TEXT, text),
                (By.PARTIAL_LINK_TEXT, text),
                (By.XPATH, f"//*[contains(text(), '{text}')]"),
            ]
            
            for by, value in strategies:
                try:
                    element = self.driver.find_element(by, value)
                    element.click()
                    return True
                except:
                    continue
            
            return False
            
        except Exception as e:
            logger.error(f"Failed to find and click: {e}")
            return False
    
    async def get_tabs_info(self) -> List[Dict]:
        """Get information about all open tabs"""
        await self._update_tabs()
        return [tab.to_dict() for tab in self.tabs]
    
    def close(self):
        """Close browser connection"""
        if self.driver:
            try:
                self.driver.quit()
                logger.info("Browser connection closed")
            except:
                pass
