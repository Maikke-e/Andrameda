# ============================================
# Window Manager - Advanced Window Control
# ============================================

import logging
import time
from typing import List, Optional, Tuple, Dict
from dataclasses import dataclass

import pyautogui
import pygetwindow as gw

logger = logging.getLogger(__name__)


@dataclass
class WindowInfo:
    """Window information"""
    title: str
    handle: int
    is_minimized: bool
    is_maximized: bool
    position: Tuple[int, int]
    size: Tuple[int, int]
    
    def to_dict(self) -> Dict:
        return {
            'title': self.title,
            'handle': self.handle,
            'is_minimized': self.is_minimized,
            'is_maximized': self.is_maximized,
            'position': self.position,
            'size': self.size
        }


class WindowManager:
    """
    Advanced Window Manager
    
    Features:
    - Switch between windows by name
    - Minimize/maximize windows
    - Snap windows (left, right, fullscreen)
    - Get window information
    - Window arrangement
    """
    
    def __init__(self):
        self.screen_size = pyautogui.size()
        logger.info(f"WindowManager initialized (screen: {self.screen_size})")
    
    def get_all_windows(self) -> List[WindowInfo]:
        """Get list of all visible windows"""
        windows = []
        
        try:
            for window in gw.getAllWindows():
                if window.title and not window.isMinimized:
                    info = WindowInfo(
                        title=window.title,
                        handle=window._hWnd,
                        is_minimized=window.isMinimized,
                        is_maximized=window.isMaximized,
                        position=(window.left, window.top),
                        size=(window.width, window.height)
                    )
                    windows.append(info)
        except Exception as e:
            logger.error(f"Failed to get windows: {e}")
        
        return windows
    
    def find_window(self, name: str) -> Optional[gw.Window]:
        """Find window by name (partial match)"""
        name_lower = name.lower()
        
        try:
            # Try exact match first
            try:
                return gw.getWindowsWithTitle(name)[0]
            except:
                pass
            
            # Try partial match
            for window in gw.getAllWindows():
                if name_lower in window.title.lower():
                    return window
            
            # Try matching common app names
            app_aliases = {
                'браузер': ['yandex', 'chrome', 'firefox', 'edge'],
                'телеграм': ['telegram', 'telegra'],
                'код': ['code', 'vscode', 'visual studio code'],
                'проводник': ['проводник', 'explorer'],
                'консоль': ['cmd', 'powershell', 'terminal'],
            }
            
            if name_lower in app_aliases:
                for alias in app_aliases[name_lower]:
                    for window in gw.getAllWindows():
                        if alias in window.title.lower():
                            return window
            
        except Exception as e:
            logger.error(f"Failed to find window: {e}")
        
        return None
    
    def switch_to_window(self, name: str) -> bool:
        """Switch to window by name"""
        window = self.find_window(name)
        
        if not window:
            logger.warning(f"Window not found: {name}")
            return False
        
        try:
            # Restore if minimized
            if window.isMinimized:
                window.restore()
            
            # Activate window
            window.activate()
            time.sleep(0.3)
            
            logger.info(f"Switched to window: {window.title}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to switch window: {e}")
            return False
    
    def minimize_window(self, name: str) -> bool:
        """Minimize window by name"""
        window = self.find_window(name)
        
        if not window:
            return False
        
        try:
            window.minimize()
            logger.info(f"Minimized window: {window.title}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to minimize window: {e}")
            return False
    
    def maximize_window(self, name: str) -> bool:
        """Maximize window by name"""
        window = self.find_window(name)
        
        if not window:
            return False
        
        try:
            window.maximize()
            logger.info(f"Maximized window: {window.title}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to maximize window: {e}")
            return False
    
    def restore_window(self, name: str) -> bool:
        """Restore minimized window"""
        window = self.find_window(name)
        
        if not window:
            return False
        
        try:
            window.restore()
            logger.info(f"Restored window: {window.title}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to restore window: {e}")
            return False
    
    def close_window(self, name: str) -> bool:
        """Close window by name"""
        window = self.find_window(name)
        
        if not window:
            return False
        
        try:
            window.close()
            logger.info(f"Closed window: {window.title}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to close window: {e}")
            return False
    
    def snap_window(self, name: str, position: str) -> bool:
        """
        Snap window to position
        
        Positions:
        - left: Left half of screen
        - right: Right half of screen
        - fullscreen: Full screen
        - top: Top half
        - bottom: Bottom half
        - top-left, top-right, bottom-left, bottom-right: Corners
        """
        window = self.find_window(name)
        
        if not window:
            return False
        
        try:
            # Restore if minimized
            if window.isMinimized:
                window.restore()
            
            screen_w, screen_h = self.screen_size
            
            # Calculate position and size
            positions = {
                'left': (0, 0, screen_w // 2, screen_h),
                'right': (screen_w // 2, 0, screen_w // 2, screen_h),
                'fullscreen': (0, 0, screen_w, screen_h),
                'top': (0, 0, screen_w, screen_h // 2),
                'bottom': (0, screen_h // 2, screen_w, screen_h // 2),
                'top-left': (0, 0, screen_w // 2, screen_h // 2),
                'top-right': (screen_w // 2, 0, screen_w // 2, screen_h // 2),
                'bottom-left': (0, screen_h // 2, screen_w // 2, screen_h // 2),
                'bottom-right': (screen_w // 2, screen_h // 2, screen_w // 2, screen_h // 2),
            }
            
            if position not in positions:
                logger.warning(f"Unknown position: {position}")
                return False
            
            x, y, w, h = positions[position]
            
            # Move and resize window
            window.moveTo(x, y)
            window.resizeTo(w, h)
            
            # Alternative: use Windows key + arrow shortcuts
            self._use_snap_shortcut(position)
            
            logger.info(f"Snapped window '{window.title}' to {position}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to snap window: {e}")
            return False
    
    def _use_snap_shortcut(self, position: str):
        """Use Windows keyboard shortcuts for snapping"""
        import pyautogui
        
        shortcuts = {
            'left': ['win', 'left'],
            'right': ['win', 'right'],
            'fullscreen': ['win', 'up'],
            'minimize': ['win', 'down'],
        }
        
        if position in shortcuts:
            pyautogui.hotkey(*shortcuts[position])
            time.sleep(0.2)
    
    def arrange_windows(self, layout: str = 'split') -> bool:
        """
        Arrange multiple windows
        
        Layouts:
        - split: Two windows side by side
        - triple: Three windows (left, top-right, bottom-right)
        - quad: Four windows in grid
        """
        try:
            windows = [w for w in gw.getAllWindows() 
                      if w.title and not w.isMinimized][:4]
            
            if len(windows) < 2:
                logger.warning("Not enough windows to arrange")
                return False
            
            screen_w, screen_h = self.screen_size
            
            if layout == 'split' and len(windows) >= 2:
                windows[0].moveTo(0, 0)
                windows[0].resizeTo(screen_w // 2, screen_h)
                windows[1].moveTo(screen_w // 2, 0)
                windows[1].resizeTo(screen_w // 2, screen_h)
                
            elif layout == 'triple' and len(windows) >= 3:
                windows[0].moveTo(0, 0)
                windows[0].resizeTo(screen_w // 2, screen_h)
                windows[1].moveTo(screen_w // 2, 0)
                windows[1].resizeTo(screen_w // 2, screen_h // 2)
                windows[2].moveTo(screen_w // 2, screen_h // 2)
                windows[2].resizeTo(screen_w // 2, screen_h // 2)
                
            elif layout == 'quad' and len(windows) >= 4:
                w, h = screen_w // 2, screen_h // 2
                windows[0].moveTo(0, 0)
                windows[0].resizeTo(w, h)
                windows[1].moveTo(w, 0)
                windows[1].resizeTo(w, h)
                windows[2].moveTo(0, h)
                windows[2].resizeTo(w, h)
                windows[3].moveTo(w, h)
                windows[3].resizeTo(w, h)
            
            logger.info(f"Arranged {len(windows)} windows in '{layout}' layout")
            return True
            
        except Exception as e:
            logger.error(f"Failed to arrange windows: {e}")
            return False
    
    def get_active_window(self) -> Optional[WindowInfo]:
        """Get currently active window"""
        try:
            window = gw.getActiveWindow()
            if window:
                return WindowInfo(
                    title=window.title,
                    handle=window._hWnd,
                    is_minimized=window.isMinimized,
                    is_maximized=window.isMaximized,
                    position=(window.left, window.top),
                    size=(window.width, window.height)
                )
        except Exception as e:
            logger.error(f"Failed to get active window: {e}")
        
        return None
    
    def list_windows(self) -> List[str]:
        """Get list of window titles"""
        windows = self.get_all_windows()
        return [w.title for w in windows]
    
    def cascade_windows(self):
        """Cascade all windows"""
        try:
            windows = [w for w in gw.getAllWindows() 
                      if w.title and not w.isMinimized]
            
            offset = 30
            for i, window in enumerate(windows[:10]):  # Limit to 10
                window.moveTo(i * offset, i * offset)
                
        except Exception as e:
            logger.error(f"Failed to cascade windows: {e}")
    
    def minimize_all(self):
        """Minimize all windows"""
        try:
            pyautogui.keyDown('win')
            pyautogui.keyDown('m')
            pyautogui.keyUp('m')
            pyautogui.keyUp('win')
            logger.info("Minimized all windows")
        except Exception as e:
            logger.error(f"Failed to minimize all: {e}")
    
    def show_desktop(self):
        """Show desktop (minimize all windows)"""
        try:
            pyautogui.keyDown('win')
            pyautogui.keyDown('d')
            pyautogui.keyUp('d')
            pyautogui.keyUp('win')
        except Exception as e:
            logger.error(f"Failed to show desktop: {e}")
