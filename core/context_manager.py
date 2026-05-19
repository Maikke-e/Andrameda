# ============================================
# Context Manager - Multi-modal Context System
# ============================================

import json
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from collections import defaultdict
import threading

from config import CONTEXT_MAX_COMMANDS, CONTEXT_TTL, DATA_DIR

logger = logging.getLogger(__name__)


@dataclass
class ContextEntry:
    """Single context entry"""
    command: str
    timestamp: datetime
    response: str = ""
    emotion: str = "neutral"
    location: str = "home"  # Could be extended with actual location
    action_type: str = ""
    success: bool = True
    
    def to_dict(self) -> Dict:
        return {
            'command': self.command,
            'timestamp': self.timestamp.isoformat(),
            'response': self.response,
            'emotion': self.emotion,
            'location': self.location,
            'action_type': self.action_type,
            'success': self.success
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'ContextEntry':
        return cls(
            command=data.get('command', ''),
            timestamp=datetime.fromisoformat(data['timestamp']),
            response=data.get('response', ''),
            emotion=data.get('emotion', 'neutral'),
            location=data.get('location', 'home'),
            action_type=data.get('action_type', ''),
            success=data.get('success', True)
        )


@dataclass
class MultimodalContext:
    """Multi-modal context including time, location, previous actions"""
    time_of_day: str  # morning, afternoon, evening, night
    day_of_week: str
    previous_actions: List[str]
    current_app: str
    user_mood: str
    command_frequency: Dict[str, int]  # How often user uses certain commands
    
    def to_dict(self) -> Dict:
        return {
            'time_of_day': self.time_of_day,
            'day_of_week': self.day_of_week,
            'previous_actions': self.previous_actions,
            'current_app': self.current_app,
            'user_mood': self.user_mood,
            'command_frequency': self.command_frequency
        }


class ContextManager:
    """
    Advanced Context Manager with multi-modal context support
    
    Features:
    - Extended command history (configurable, default 10)
    - Time-based context (morning/evening commands)
    - Location awareness
    - Command frequency analysis
    - Context-dependent command interpretation
    """
    
    def __init__(self):
        self.contexts: Dict[int, List[ContextEntry]] = defaultdict(list)
        self.multimodal_contexts: Dict[int, MultimodalContext] = {}
        self.lock = threading.Lock()
        self.max_commands = CONTEXT_MAX_COMMANDS
        self.ttl = CONTEXT_TTL
        
        # Command patterns for context-dependent interpretation
        self.context_patterns = {
            'morning': ['будильник', 'утро', 'проснулся', 'завтрак'],
            'evening': ['вечер', 'спать', 'ночь', 'завтра'],
            'work': ['работа', 'документ', 'встреча', 'звонок'],
            'entertainment': ['музыка', 'видео', 'youtube', 'игра', 'фильм']
        }
        
        logger.info(f"ContextManager initialized (max_commands={self.max_commands})")
    
    def add_command(self, user_id: int, command: str, 
                   response: str = "", emotion: str = "neutral",
                   action_type: str = "", success: bool = True):
        """Add command to user's context"""
        with self.lock:
            entry = ContextEntry(
                command=command,
                timestamp=datetime.now(),
                response=response,
                emotion=emotion,
                action_type=action_type,
                success=success
            )
            
            self.contexts[user_id].append(entry)
            
            # Keep only last N commands
            if len(self.contexts[user_id]) > self.max_commands:
                self.contexts[user_id] = self.contexts[user_id][-self.max_commands:]
            
            # Update multimodal context
            self._update_multimodal_context(user_id, command)
            
            logger.debug(f"Added command to context for user {user_id}: {command}")
    
    def _update_multimodal_context(self, user_id: int, command: str):
        """Update multimodal context for user"""
        now = datetime.now()
        
        # Determine time of day
        hour = now.hour
        if 5 <= hour < 12:
            time_of_day = 'morning'
        elif 12 <= hour < 17:
            time_of_day = 'afternoon'
        elif 17 <= hour < 22:
            time_of_day = 'evening'
        else:
            time_of_day = 'night'
        
        # Get previous actions
        previous_actions = []
        if user_id in self.contexts:
            previous_actions = [
                e.command for e in self.contexts[user_id][-3:]
            ]
        
        # Update command frequency
        command_freq = defaultdict(int)
        if user_id in self.multimodal_contexts:
            command_freq = defaultdict(int, 
                self.multimodal_contexts[user_id].command_frequency)
        
        # Categorize command
        command_category = self._categorize_command(command)
        if command_category:
            command_freq[command_category] += 1
        
        self.multimodal_contexts[user_id] = MultimodalContext(
            time_of_day=time_of_day,
            day_of_week=now.strftime('%A'),
            previous_actions=previous_actions,
            current_app=self._get_current_app(),
            user_mood=self._infer_user_mood(user_id),
            command_frequency=dict(command_freq)
        )
    
    def _categorize_command(self, command: str) -> Optional[str]:
        """Categorize command by type"""
        command_lower = command.lower()
        
        for category, patterns in self.context_patterns.items():
            for pattern in patterns:
                if pattern in command_lower:
                    return category
        
        return None
    
    def _get_current_app(self) -> str:
        """Get currently active application"""
        try:
            import pygetwindow as gw
            active = gw.getActiveWindow()
            return active.title if active else "unknown"
        except:
            return "unknown"
    
    def _infer_user_mood(self, user_id: int) -> str:
        """Infer user mood from recent commands"""
        if user_id not in self.contexts or not self.contexts[user_id]:
            return "neutral"
        
        # Analyze recent emotions
        recent_emotions = [e.emotion for e in self.contexts[user_id][-5:]]
        
        # Simple mood inference
        emotion_counts = {}
        for e in recent_emotions:
            emotion_counts[e] = emotion_counts.get(e, 0) + 1
        
        return max(emotion_counts, key=emotion_counts.get) if emotion_counts else "neutral"
    
    def get_context(self, user_id: int, include_expired: bool = False) -> List[Dict]:
        """Get user's command context"""
        with self.lock:
            if user_id not in self.contexts:
                return []
            
            now = datetime.now()
            ttl_delta = timedelta(minutes=self.ttl)
            
            valid_entries = []
            for entry in self.contexts[user_id]:
                # Check if entry is still valid
                if include_expired or (now - entry.timestamp) <= ttl_delta:
                    valid_entries.append({
                        'command': entry.command,
                        'timestamp': entry.timestamp.strftime('%H:%M:%S'),
                        'response': entry.response,
                        'emotion': entry.emotion,
                        'action_type': entry.action_type
                    })
            
            return valid_entries
    
    def get_multimodal_context(self, user_id: int) -> Optional[Dict]:
        """Get multi-modal context for user"""
        if user_id not in self.multimodal_contexts:
            return None
        
        return self.multimodal_contexts[user_id].to_dict()
    
    def get_context_aware_interpretation(self, user_id: int, command: str) -> Dict:
        """
        Get context-aware interpretation of command
        
        Returns dict with:
        - original_command: original text
        - interpreted_command: context-adjusted interpretation
        - confidence: confidence score
        - context_factors: which context factors influenced interpretation
        """
        multimodal = self.get_multimodal_context(user_id)
        recent_commands = self.get_context(user_id)
        
        interpretation = {
            'original_command': command,
            'interpreted_command': command,
            'confidence': 1.0,
            'context_factors': []
        }
        
        if not multimodal:
            return interpretation
        
        # Time-based interpretation
        time_of_day = multimodal.get('time_of_day', 'unknown')
        
        # Example: "включи музыку" in morning might mean "включи бодрую музыку"
        if 'музыка' in command.lower():
            if time_of_day == 'morning':
                interpretation['interpreted_command'] = command + " (бодрая)"
                interpretation['context_factors'].append('morning_music')
            elif time_of_day == 'evening':
                interpretation['interpreted_command'] = command + " (спокойная)"
                interpretation['context_factors'].append('evening_music')
        
        # Previous action-based interpretation
        previous = multimodal.get('previous_actions', [])
        
        # Example: "продолжи" after "открой youtube" means "продолжи видео"
        if 'продолжи' in command.lower() and previous:
            last_action = previous[-1] if previous else ''
            if 'youtube' in last_action or 'видео' in last_action:
                interpretation['interpreted_command'] = "продолжи видео"
                interpretation['context_factors'].append('previous_video')
        
        # Command frequency-based interpretation
        freq = multimodal.get('command_frequency', {})
        
        # If user frequently uses work-related commands during work hours
        if time_of_day in ['morning', 'afternoon'] and freq.get('work', 0) > 5:
            if 'открой' in command.lower() and 'документ' in command.lower():
                interpretation['interpreted_command'] = command + " (рабочий)"
                interpretation['context_factors'].append('work_context')
        
        interpretation['confidence'] = 0.7 + (0.05 * len(interpretation['context_factors']))
        
        return interpretation
    
    def clear_context(self, user_id: int):
        """Clear user's context"""
        with self.lock:
            if user_id in self.contexts:
                del self.contexts[user_id]
            if user_id in self.multimodal_contexts:
                del self.multimodal_contexts[user_id]
            logger.info(f"Cleared context for user {user_id}")
    
    def get_command_statistics(self, user_id: int) -> Dict:
        """Get command statistics for user"""
        if user_id not in self.contexts:
            return {}
        
        entries = self.contexts[user_id]
        
        stats = {
            'total_commands': len(entries),
            'successful_commands': sum(1 for e in entries if e.success),
            'failed_commands': sum(1 for e in entries if not e.success),
            'most_common_emotion': self._get_most_common(entries, 'emotion'),
            'command_types': {}
        }
        
        for entry in entries:
            action_type = entry.action_type or 'unknown'
            stats['command_types'][action_type] = \
                stats['command_types'].get(action_type, 0) + 1
        
        return stats
    
    def _get_most_common(self, entries: List[ContextEntry], field: str) -> str:
        """Get most common value for a field"""
        values = [getattr(e, field) for e in entries]
        if not values:
            return 'unknown'
        
        from collections import Counter
        counter = Counter(values)
        return counter.most_common(1)[0][0]
    
    def save_to_file(self, filepath: str = None):
        """Save contexts to file"""
        if filepath is None:
            filepath = DATA_DIR / 'contexts.json'
        
        data = {
            str(user_id): {
                'entries': [e.to_dict() for e in entries],
                'multimodal': self.multimodal_contexts.get(user_id, {}).to_dict() 
                              if user_id in self.multimodal_contexts else {}
            }
            for user_id, entries in self.contexts.items()
        }
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"Contexts saved to {filepath}")
    
    def load_from_file(self, filepath: str = None):
        """Load contexts from file"""
        if filepath is None:
            filepath = DATA_DIR / 'contexts.json'
        
        if not Path(filepath).exists():
            logger.warning(f"Context file not found: {filepath}")
            return
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            for user_id_str, user_data in data.items():
                user_id = int(user_id_str)
                
                # Load entries
                entries = [
                    ContextEntry.from_dict(e) 
                    for e in user_data.get('entries', [])
                ]
                self.contexts[user_id] = entries
                
                # Load multimodal context
                mm_data = user_data.get('multimodal', {})
                if mm_data:
                    self.multimodal_contexts[user_id] = MultimodalContext(**mm_data)
            
            logger.info(f"Contexts loaded from {filepath}")
            
        except Exception as e:
            logger.error(f"Failed to load contexts: {e}")
