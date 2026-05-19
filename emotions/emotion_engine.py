# ============================================
# Emotion Engine - Emotional Intelligence
# ============================================

import json
import logging
import numpy as np
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
import threading

from config import EMOTION_DETECTION_ENABLED, EMOTION_MEMORY_FILE, DATA_DIR

logger = logging.getLogger(__name__)


@dataclass
class EmotionState:
    """User emotion state"""
    primary: str  # happy, sad, angry, neutral, excited, tired
    intensity: float  # 0.0 to 1.0
    confidence: float  # detection confidence
    timestamp: datetime
    
    def to_dict(self) -> Dict:
        return {
            'primary': self.primary,
            'intensity': self.intensity,
            'confidence': self.confidence,
            'timestamp': self.timestamp.isoformat()
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'EmotionState':
        return cls(
            primary=data['primary'],
            intensity=data['intensity'],
            confidence=data['confidence'],
            timestamp=datetime.fromisoformat(data['timestamp'])
        )


@dataclass
class EmotionalMemory:
    """Memory of emotional interactions"""
    trigger: str  # What caused the emotion
    emotion: str  # The emotion detected
    assistant_response: str  # How assistant responded
    user_reaction: str  # positive, negative, neutral
    timestamp: datetime
    context: str  # Additional context
    
    def to_dict(self) -> Dict:
        return {
            'trigger': self.trigger,
            'emotion': self.emotion,
            'assistant_response': self.assistant_response,
            'user_reaction': self.user_reaction,
            'timestamp': self.timestamp.isoformat(),
            'context': self.context
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'EmotionalMemory':
        return cls(
            trigger=data['trigger'],
            emotion=data['emotion'],
            assistant_response=data['assistant_response'],
            user_reaction=data['user_reaction'],
            timestamp=datetime.fromisoformat(data['timestamp']),
            context=data.get('context', '')
        )


class EmotionEngine:
    """
    Emotional Intelligence Engine
    
    Features:
    - Voice emotion detection
    - Adaptive responses based on mood
    - Character adaptation to user
    - Emotional memory (avoid failed jokes)
    """
    
    def __init__(self):
        self.enabled = EMOTION_DETECTION_ENABLED
        self.memory_file = Path(EMOTION_MEMORY_FILE)
        self.memory_file.parent.mkdir(parents=True, exist_ok=True)
        
        self.current_emotion: Optional[EmotionState] = None
        self.emotional_memory: List[EmotionalMemory] = []
        self.user_emotion_history: List[EmotionState] = []
        
        # Character adaptation
        self.character_traits = {
            'humor': 0.5,  # 0 = serious, 1 = very funny
            'formality': 0.3,  # 0 = casual, 1 = formal
            'enthusiasm': 0.6,  # 0 = calm, 1 = very enthusiastic
            'empathy': 0.7,  # 0 = detached, 1 = very empathetic
        }
        
        self.lock = threading.Lock()
        
        self._load_memory()
        
        logger.info(f"EmotionEngine initialized (enabled={self.enabled})")
    
    def _load_memory(self):
        """Load emotional memory from file"""
        if not self.memory_file.exists():
            return
        
        try:
            with open(self.memory_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            self.emotional_memory = [
                EmotionalMemory.from_dict(m) 
                for m in data.get('memories', [])
            ]
            
            self.character_traits = data.get('character_traits', self.character_traits)
            
            logger.info(f"Loaded {len(self.emotional_memory)} emotional memories")
            
        except Exception as e:
            logger.error(f"Failed to load emotional memory: {e}")
    
    def _save_memory(self):
        """Save emotional memory to file"""
        try:
            data = {
                'memories': [m.to_dict() for m in self.emotional_memory],
                'character_traits': self.character_traits,
                'saved_at': datetime.now().isoformat()
            }
            
            with open(self.memory_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
        except Exception as e:
            logger.error(f"Failed to save emotional memory: {e}")
    
    def detect_emotion_from_voice(self, audio_features: Dict) -> EmotionState:
        """
        Detect emotion from voice features
        
        Features expected:
        - pitch_mean, pitch_std
        - energy_mean, energy_std
        - speech_rate
        - pause_ratio
        """
        if not self.enabled:
            return EmotionState('neutral', 0.5, 1.0, datetime.now())
        
        try:
            # Simple rule-based emotion detection
            # In production, use a trained model
            
            pitch_mean = audio_features.get('pitch_mean', 150)
            energy_mean = audio_features.get('energy_mean', 0.5)
            speech_rate = audio_features.get('speech_rate', 1.0)
            
            # Determine emotion based on features
            if energy_mean > 0.7 and pitch_mean > 180 and speech_rate > 1.2:
                emotion = 'excited'
                intensity = min(1.0, (energy_mean + speech_rate) / 2)
            elif energy_mean > 0.6 and pitch_mean > 160:
                emotion = 'happy'
                intensity = energy_mean
            elif energy_mean < 0.3 and pitch_mean < 130:
                emotion = 'sad'
                intensity = 1.0 - energy_mean
            elif energy_mean > 0.7 and pitch_mean > 200:
                emotion = 'angry'
                intensity = min(1.0, energy_mean * 1.2)
            elif speech_rate < 0.7 and energy_mean < 0.4:
                emotion = 'tired'
                intensity = 0.6
            else:
                emotion = 'neutral'
                intensity = 0.5
            
            state = EmotionState(
                primary=emotion,
                intensity=intensity,
                confidence=0.7,
                timestamp=datetime.now()
            )
            
            with self.lock:
                self.current_emotion = state
                self.user_emotion_history.append(state)
                
                # Keep only last 100 emotions
                if len(self.user_emotion_history) > 100:
                    self.user_emotion_history = self.user_emotion_history[-100:]
            
            logger.debug(f"Detected emotion: {emotion} (intensity={intensity:.2f})")
            return state
            
        except Exception as e:
            logger.error(f"Emotion detection error: {e}")
            return EmotionState('neutral', 0.5, 0.0, datetime.now())
    
    def detect_emotion_from_text(self, text: str) -> EmotionState:
        """Detect emotion from text (fallback when voice not available)"""
        if not self.enabled:
            return EmotionState('neutral', 0.5, 1.0, datetime.now())
        
        # Simple keyword-based detection
        text_lower = text.lower()
        
        emotion_keywords = {
            'happy': ['рад', 'отлично', 'круто', 'супер', 'весело', 'хорошо', 'спасибо', '👍'],
            'sad': ['грустно', 'плохо', 'жаль', 'неудача', 'проблема', '😢', '😞'],
            'angry': ['зол', 'бесит', 'раздражает', 'ненавижу', 'ужасно', '😠', '😡'],
            'excited': ['вау', 'невероятно', 'офигеть', 'класс', '🔥', '🤩'],
            'tired': ['устал', 'сонно', 'лень', 'спать', '😴'],
        }
        
        detected_emotion = 'neutral'
        max_count = 0
        
        for emotion, keywords in emotion_keywords.items():
            count = sum(1 for kw in keywords if kw in text_lower)
            if count > max_count:
                max_count = count
                detected_emotion = emotion
        
        intensity = min(1.0, 0.5 + max_count * 0.2)
        
        state = EmotionState(
            primary=detected_emotion,
            intensity=intensity,
            confidence=0.6 if max_count > 0 else 0.3,
            timestamp=datetime.now()
        )
        
        with self.lock:
            self.current_emotion = state
            self.user_emotion_history.append(state)
        
        return state
    
    def get_adaptive_response_style(self) -> Dict:
        """Get response style adapted to current emotion"""
        if not self.current_emotion:
            return self.character_traits
        
        emotion = self.current_emotion.primary
        intensity = self.current_emotion.intensity
        
        # Adjust traits based on emotion
        adapted_traits = self.character_traits.copy()
        
        if emotion == 'happy':
            adapted_traits['humor'] = min(1.0, self.character_traits['humor'] + 0.2)
            adapted_traits['enthusiasm'] = min(1.0, self.character_traits['enthusiasm'] + 0.2)
        
        elif emotion == 'sad':
            adapted_traits['empathy'] = min(1.0, self.character_traits['empathy'] + 0.3)
            adapted_traits['humor'] = max(0.0, self.character_traits['humor'] - 0.3)
            adapted_traits['formality'] = min(1.0, self.character_traits['formality'] + 0.2)
        
        elif emotion == 'angry':
            adapted_traits['formality'] = min(1.0, self.character_traits['formality'] + 0.3)
            adapted_traits['humor'] = max(0.0, self.character_traits['humor'] - 0.4)
            adapted_traits['empathy'] = min(1.0, self.character_traits['empathy'] + 0.2)
        
        elif emotion == 'excited':
            adapted_traits['enthusiasm'] = min(1.0, self.character_traits['enthusiasm'] + 0.3)
            adapted_traits['humor'] = min(1.0, self.character_traits['humor'] + 0.1)
        
        elif emotion == 'tired':
            adapted_traits['enthusiasm'] = max(0.0, self.character_traits['enthusiasm'] - 0.3)
            adapted_traits['formality'] = min(1.0, self.character_traits['formality'] + 0.1)
        
        return adapted_traits
    
    def get_emotion_aware_prompt(self, base_prompt: str) -> str:
        """Modify prompt based on current emotion"""
        if not self.current_emotion:
            return base_prompt
        
        emotion = self.current_emotion.primary
        intensity = self.current_emotion.intensity
        
        emotion_modifiers = {
            'happy': "Пользователь в хорошем настроении. Отвечай весело и энергично! 🎉",
            'sad': "Пользователь грустный. Отвечай с сочувствием и поддержкой. 💙",
            'angry': "Пользователь раздражён. Отвечай спокойно и по делу. 🧘",
            'excited': "Пользователь в восторге! Поддержи его энтузиазм! 🔥",
            'tired': "Пользователь устал. Отвечай кратко и по существу. 😌",
            'neutral': ""
        }
        
        modifier = emotion_modifiers.get(emotion, "")
        
        if modifier:
            return f"{modifier}\n\n{base_prompt}"
        
        return base_prompt
    
    def should_avoid_joke(self, joke_type: str = 'general') -> bool:
        """Check if we should avoid certain jokes based on emotional memory"""
        # Check recent emotional memory for failed jokes
        recent_memories = [
            m for m in self.emotional_memory[-20:]
            if 'шутк' in m.assistant_response.lower() or 'юмор' in m.context.lower()
        ]
        
        failed_jokes = sum(1 for m in recent_memories if m.user_reaction == 'negative')
        
        # If more than 50% of recent jokes failed, avoid them
        if recent_memories and failed_jokes / len(recent_memories) > 0.5:
            return True
        
        # Also avoid jokes if user is sad or angry
        if self.current_emotion and self.current_emotion.primary in ['sad', 'angry']:
            return True
        
        return False
    
    def record_interaction(self, trigger: str, assistant_response: str, 
                          user_feedback: str = '', context: str = ''):
        """Record emotional interaction for learning"""
        emotion = self.current_emotion.primary if self.current_emotion else 'neutral'
        
        # Determine user reaction
        user_reaction = 'neutral'
        if user_feedback:
            feedback_lower = user_feedback.lower()
            if any(w in feedback_lower for w in ['спасибо', 'круто', 'отлично', '👍', 'хорошо']):
                user_reaction = 'positive'
            elif any(w in feedback_lower for w in ['не так', 'неправильно', 'плохо', 'не то', '👎']):
                user_reaction = 'negative'
        
        memory = EmotionalMemory(
            trigger=trigger,
            emotion=emotion,
            assistant_response=assistant_response,
            user_reaction=user_reaction,
            timestamp=datetime.now(),
            context=context
        )
        
        with self.lock:
            self.emotional_memory.append(memory)
            
            # Keep only last 200 memories
            if len(self.emotional_memory) > 200:
                self.emotional_memory = self.emotional_memory[-200:]
        
        # Adapt character based on feedback
        self._adapt_character(memory)
        
        self._save_memory()
        
        logger.debug(f"Recorded interaction: {user_reaction} reaction")
    
    def _adapt_character(self, memory: EmotionalMemory):
        """Adapt character traits based on user feedback"""
        if memory.user_reaction == 'positive':
            # Reinforce current traits
            if 'шутк' in memory.assistant_response.lower():
                self.character_traits['humor'] = min(1.0, self.character_traits['humor'] + 0.05)
            if 'формально' in memory.context.lower():
                self.character_traits['formality'] = min(1.0, self.character_traits['formality'] + 0.05)
        
        elif memory.user_reaction == 'negative':
            # Adjust traits
            if 'шутк' in memory.assistant_response.lower():
                self.character_traits['humor'] = max(0.0, self.character_traits['humor'] - 0.1)
            if memory.emotion in ['sad', 'angry']:
                self.character_traits['empathy'] = min(1.0, self.character_traits['empathy'] + 0.05)
    
    def get_emotion_summary(self) -> Dict:
        """Get summary of user's emotional state"""
        if not self.user_emotion_history:
            return {'dominant_emotion': 'unknown', 'variability': 0}
        
        # Count emotions
        emotion_counts = {}
        for state in self.user_emotion_history[-50:]:  # Last 50
            emotion_counts[state.primary] = emotion_counts.get(state.primary, 0) + 1
        
        dominant = max(emotion_counts, key=emotion_counts.get)
        total = sum(emotion_counts.values())
        
        # Calculate variability
        proportions = [c / total for c in emotion_counts.values()]
        variability = 1 - max(proportions)  # Higher = more variable
        
        return {
            'dominant_emotion': dominant,
            'emotion_distribution': emotion_counts,
            'variability': round(variability, 2),
            'current_emotion': self.current_emotion.primary if self.current_emotion else 'unknown'
        }
    
    def get_character_profile(self) -> Dict:
        """Get adapted character profile"""
        return {
            'traits': self.character_traits,
            'adaptation_summary': self._generate_adaptation_summary()
        }
    
    def _generate_adaptation_summary(self) -> str:
        """Generate human-readable adaptation summary"""
        traits = self.character_traits
        
        if traits['humor'] > 0.7:
            humor_desc = "весёлая и любит шутить"
        elif traits['humor'] > 0.4:
            humor_desc = "с чувством юмора"
        else:
            humor_desc = "серьёзная"
        
        if traits['empathy'] > 0.7:
            empathy_desc = "очень эмпатичная"
        elif traits['empathy'] > 0.4:
            empathy_desc = "внимательная"
        else:
            empathy_desc = "деловая"
        
        return f"{VA_NAME} стала {humor_desc} и {empathy_desc}, адаптируясь под ваш стиль общения."


# Import VA_NAME
from config import VA_NAME
