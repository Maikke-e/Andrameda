# ============================================
# Reminder System - Reminders, Timers, Alarms
# ============================================

import asyncio
import json
import logging
import threading
import time
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path
import uuid

import schedule

from config import DATA_DIR

logger = logging.getLogger(__name__)


def run_async_from_thread(coro, loop=None):
    """Run async coroutine from a sync thread safely"""
    if loop is None:
        loop = asyncio.get_event_loop()
    if loop.is_running():
        asyncio.run_coroutine_threadsafe(coro, loop)
    else:
        loop.run_until_complete(coro)


@dataclass
class Reminder:
    """Reminder/Timers/Alarm data"""
    id: str
    user_id: int
    message: str
    trigger_time: datetime
    reminder_type: str  # 'reminder', 'timer', 'alarm'
    repeat: str  # 'once', 'daily', 'weekly', 'none'
    is_active: bool = True
    created_at: datetime = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()
    
    def to_dict(self) -> Dict:
        return {
            'id': self.id,
            'user_id': self.user_id,
            'message': self.message,
            'trigger_time': self.trigger_time.isoformat(),
            'reminder_type': self.reminder_type,
            'repeat': self.repeat,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'Reminder':
        return cls(
            id=data['id'],
            user_id=data['user_id'],
            message=data['message'],
            trigger_time=datetime.fromisoformat(data['trigger_time']),
            reminder_type=data['reminder_type'],
            repeat=data.get('repeat', 'once'),
            is_active=data.get('is_active', True),
            created_at=datetime.fromisoformat(data['created_at']) if data.get('created_at') else None
        )
    
    def is_due(self) -> bool:
        """Check if reminder is due"""
        return datetime.now() >= self.trigger_time and self.is_active
    
    def time_until(self) -> timedelta:
        """Get time until reminder triggers"""
        return self.trigger_time - datetime.now()


class ReminderSystem:
    """
    Reminder, Timer, and Alarm System
    
    Features:
    - One-time and recurring reminders
    - Countdown timers
    - Daily alarms
    - Notification callbacks
    """
    
    def __init__(self, notification_callback: Callable = None, event_loop: asyncio.AbstractEventLoop = None):
        self.reminders: Dict[str, Reminder] = {}
        self.notification_callback = notification_callback
        self.event_loop = event_loop
        self.lock = threading.Lock()
        self.running = False
        self.check_thread = None
        
        self.data_file = DATA_DIR / 'reminders.json'
        self.data_file.parent.mkdir(parents=True, exist_ok=True)
        
        self._load_reminders()
        self._start_scheduler()
        
        logger.info(f"ReminderSystem initialized with {len(self.reminders)} reminders")
    
    def _load_reminders(self):
        """Load reminders from file"""
        if not self.data_file.exists():
            return
        
        try:
            with open(self.data_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            for reminder_data in data.get('reminders', []):
                reminder = Reminder.from_dict(reminder_data)
                self.reminders[reminder.id] = reminder
            
            logger.info(f"Loaded {len(self.reminders)} reminders")
            
        except Exception as e:
            logger.error(f"Failed to load reminders: {e}")
    
    def _save_reminders(self):
        """Save reminders to file"""
        try:
            data = {
                'reminders': [r.to_dict() for r in self.reminders.values()],
                'saved_at': datetime.now().isoformat()
            }
            
            with open(self.data_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
        except Exception as e:
            logger.error(f"Failed to save reminders: {e}")
    
    def _start_scheduler(self):
        """Start the reminder checking scheduler"""
        self.running = True
        self.check_thread = threading.Thread(target=self._check_loop, daemon=True)
        self.check_thread.start()
        logger.info("Reminder scheduler started")
    
    def _check_loop(self):
        """Main checking loop"""
        while self.running:
            try:
                self._check_reminders()
                time.sleep(1)  # Check every second
            except Exception as e:
                logger.error(f"Reminder check error: {e}")
                time.sleep(5)
    
    def _check_reminders(self):
        """Check and trigger due reminders"""
        with self.lock:
            due_reminders = [
                r for r in self.reminders.values() 
                if r.is_due()
            ]
            
            for reminder in due_reminders:
                self._trigger_reminder(reminder)
    
    def _trigger_reminder(self, reminder: Reminder):
        """Trigger a reminder"""
        logger.info(f"Triggering reminder: {reminder.message}")
        
        # Send notification
        if self.notification_callback:
            try:
                # Use run_async_from_thread for thread-safe async call
                coro = self.notification_callback(reminder.user_id, reminder.message)
                run_async_from_thread(coro, self.event_loop)
            except Exception as e:
                logger.error(f"Notification error: {e}")
        
        # Handle repeat
        if reminder.repeat == 'once' or reminder.repeat == 'none':
            reminder.is_active = False
        elif reminder.repeat == 'daily':
            reminder.trigger_time = reminder.trigger_time + timedelta(days=1)
        elif reminder.repeat == 'weekly':
            reminder.trigger_time = reminder.trigger_time + timedelta(weeks=1)
        
        self._save_reminders()
    
    # ============== Public API ==============
    
    def add_reminder(self, user_id: int, message: str, 
                    minutes: int = 0, hours: int = 0, days: int = 0,
                    repeat: str = 'once') -> str:
        """
        Add a new reminder
        
        Args:
            user_id: User ID
            message: Reminder message
            minutes/hours/days: Time until reminder
            repeat: 'once', 'daily', 'weekly'
        """
        reminder_id = str(uuid.uuid4())[:8]
        
        trigger_time = datetime.now() + timedelta(
            minutes=minutes, hours=hours, days=days
        )
        
        reminder = Reminder(
            id=reminder_id,
            user_id=user_id,
            message=message,
            trigger_time=trigger_time,
            reminder_type='reminder',
            repeat=repeat
        )
        
        with self.lock:
            self.reminders[reminder_id] = reminder
        
        self._save_reminders()
        
        logger.info(f"Added reminder '{message}' for {trigger_time}")
        return reminder_id
    
    def add_timer(self, user_id: int, minutes: int, 
                 message: str = None) -> str:
        """Add a countdown timer"""
        if message is None:
            message = f"⏱️ Таймер на {minutes} минут истёк!"
        
        reminder_id = str(uuid.uuid4())[:8]
        
        trigger_time = datetime.now() + timedelta(minutes=minutes)
        
        reminder = Reminder(
            id=reminder_id,
            user_id=user_id,
            message=message,
            trigger_time=trigger_time,
            reminder_type='timer',
            repeat='none'
        )
        
        with self.lock:
            self.reminders[reminder_id] = reminder
        
        self._save_reminders()
        
        logger.info(f"Added timer for {minutes} minutes")
        return reminder_id
    
    def add_alarm(self, user_id: int, hour: int, minute: int,
                 message: str = None, repeat: str = 'daily') -> str:
        """
        Add an alarm
        
        Args:
            hour: Hour (0-23)
            minute: Minute (0-59)
            message: Alarm message
            repeat: 'once', 'daily'
        """
        if message is None:
            message = f"🕐 Будильник! Время {hour:02d}:{minute:02d}"
        
        reminder_id = str(uuid.uuid4())[:8]
        
        # Calculate next occurrence
        now = datetime.now()
        alarm_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        
        if alarm_time <= now:
            alarm_time = alarm_time + timedelta(days=1)
        
        reminder = Reminder(
            id=reminder_id,
            user_id=user_id,
            message=message,
            trigger_time=alarm_time,
            reminder_type='alarm',
            repeat=repeat
        )
        
        with self.lock:
            self.reminders[reminder_id] = reminder
        
        self._save_reminders()
        
        logger.info(f"Added alarm for {hour:02d}:{minute:02d}")
        return reminder_id
    
    def cancel_reminder(self, reminder_id: str) -> bool:
        """Cancel a reminder by ID"""
        with self.lock:
            if reminder_id in self.reminders:
                self.reminders[reminder_id].is_active = False
                self._save_reminders()
                logger.info(f"Cancelled reminder {reminder_id}")
                return True
        
        return False
    
    def delete_reminder(self, reminder_id: str) -> bool:
        """Permanently delete a reminder"""
        with self.lock:
            if reminder_id in self.reminders:
                del self.reminders[reminder_id]
                self._save_reminders()
                logger.info(f"Deleted reminder {reminder_id}")
                return True
        
        return False
    
    def get_user_reminders(self, user_id: int, active_only: bool = True) -> List[Dict]:
        """Get all reminders for a user"""
        with self.lock:
            user_reminders = [
                r for r in self.reminders.values() 
                if r.user_id == user_id
                and (not active_only or r.is_active)
            ]
        
        # Sort by trigger time
        user_reminders.sort(key=lambda r: r.trigger_time)
        
        return [
            {
                'id': r.id,
                'message': r.message,
                'time': r.trigger_time.strftime('%H:%M %d.%m.%Y'),
                'type': r.reminder_type,
                'time_until': self._format_timedelta(r.time_until())
            }
            for r in user_reminders
        ]
    
    def get_reminder(self, reminder_id: str) -> Optional[Reminder]:
        """Get a specific reminder"""
        return self.reminders.get(reminder_id)
    
    def _format_timedelta(self, td: timedelta) -> str:
        """Format timedelta for display"""
        total_seconds = int(td.total_seconds())
        
        if total_seconds < 0:
            return "просрочено"
        
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        
        parts = []
        if hours > 0:
            parts.append(f"{hours}ч")
        if minutes > 0:
            parts.append(f"{minutes}м")
        if seconds > 0 and hours == 0:
            parts.append(f"{seconds}с")
        
        return " ".join(parts) if parts else "сейчас"
    
    def snooze_reminder(self, reminder_id: str, minutes: int = 5) -> bool:
        """Snooze a reminder for N minutes"""
        with self.lock:
            if reminder_id not in self.reminders:
                return False
            
            reminder = self.reminders[reminder_id]
            reminder.trigger_time = datetime.now() + timedelta(minutes=minutes)
            reminder.is_active = True
        
        self._save_reminders()
        logger.info(f"Snoozed reminder {reminder_id} for {minutes} minutes")
        return True
    
    def get_upcoming(self, user_id: int, limit: int = 5) -> List[Dict]:
        """Get upcoming reminders for user"""
        reminders = self.get_user_reminders(user_id, active_only=True)
        
        # Filter to only future reminders
        future = [
            r for r in reminders 
            if 'просрочено' not in r['time_until']
        ]
        
        return future[:limit]
    
    def clear_old_reminders(self, max_age_days: int = 7):
        """Clear old completed reminders"""
        cutoff = datetime.now() - timedelta(days=max_age_days)
        
        with self.lock:
            to_delete = [
                rid for rid, r in self.reminders.items()
                if not r.is_active and r.trigger_time < cutoff
            ]
            
            for rid in to_delete:
                del self.reminders[rid]
        
        if to_delete:
            self._save_reminders()
            logger.info(f"Cleared {len(to_delete)} old reminders")
    
    def stop(self):
        """Stop the reminder scheduler"""
        self.running = False
        if self.check_thread:
            self.check_thread.join(timeout=2)
        logger.info("Reminder scheduler stopped")


# ============== Quick Commands ==============

def quick_timer(minutes: int, message: str = None):
    """Quick function to set a timer"""
    rs = ReminderSystem()
    return rs.add_timer(0, minutes, message)


def quick_alarm(hour: int, minute: int, message: str = None):
    """Quick function to set an alarm"""
    rs = ReminderSystem()
    return rs.add_alarm(0, hour, minute, message)


def quick_reminder(minutes: int, message: str):
    """Quick function to set a reminder"""
    rs = ReminderSystem()
    return rs.add_reminder(0, message, minutes=minutes)
