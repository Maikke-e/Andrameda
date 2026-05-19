# ============================================
# TTS Engine with Caching and Streaming
# ============================================

import asyncio
import hashlib
import json
import logging
import tempfile
from pathlib import Path
from typing import Optional, Dict, List, AsyncGenerator
from dataclasses import dataclass
from datetime import datetime
import threading

import torch
import torchaudio
import aiofiles

from config import (
    TTS_CACHE_ENABLED, 
    TTS_CACHE_DIR, 
    TTS_STREAMING_ENABLED,
    TTS_STREAMING_CHUNK_SIZE,
    DATA_DIR
)

logger = logging.getLogger(__name__)


@dataclass
class TTSCacheEntry:
    """TTS cache entry"""
    text_hash: str
    file_path: str
    created_at: datetime
    access_count: int
    last_accessed: datetime
    
    def to_dict(self) -> Dict:
        return {
            'text_hash': self.text_hash,
            'file_path': self.file_path,
            'created_at': self.created_at.isoformat(),
            'access_count': self.access_count,
            'last_accessed': self.last_accessed.isoformat()
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'TTSCacheEntry':
        return cls(
            text_hash=data['text_hash'],
            file_path=data['file_path'],
            created_at=datetime.fromisoformat(data['created_at']),
            access_count=data['access_count'],
            last_accessed=datetime.fromisoformat(data['last_accessed'])
        )


class TTSEngine:
    """
    Text-to-Speech Engine with caching and streaming support
    
    Features:
    - Silero TTS model
    - File-based caching
    - Streaming audio generation
    - Emotion-aware speech
    """
    
    def __init__(self):
        self.cache_enabled = TTS_CACHE_ENABLED
        self.cache_dir = Path(TTS_CACHE_DIR)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        self.streaming_enabled = TTS_STREAMING_ENABLED
        self.chunk_size = TTS_STREAMING_CHUNK_SIZE
        
        self.model = None
        self.speaker = None
        self.sample_rate = 48000
        
        self.cache: Dict[str, TTSCacheEntry] = {}
        self.cache_index_file = DATA_DIR / 'tts_cache_index.json'
        self.cache_lock = threading.Lock()
        
        self.emotion_enabled = True
        
        self._load_model()
        self._load_cache_index()
        
        logger.info(f"TTS Engine initialized (cache={self.cache_enabled}, streaming={self.streaming_enabled})")
    
    def _load_model(self):
        """Load Silero TTS model"""
        try:
            model_url = 'https://models.silero.ai/models/tts/ru/v3_1_ru.pt'
            
            # Download model if not exists
            model_path = DATA_DIR / 'tts_model.pt'
            if not model_path.exists():
                logger.info("Downloading Silero TTS model...")
                torch.hub.download_url_to_file(model_url, model_path)
            
            # Load model
            self.model = torch.package.PackageImporter(model_path).load_pickle("tts_models", "model")
            self.model.to(torch.device('cpu'))
            
            # Default speaker
            self.speaker = 'xenia'  # Female Russian voice
            
            logger.info("Silero TTS model loaded")
            
        except Exception as e:
            logger.error(f"Failed to load TTS model: {e}")
            self.model = None
    
    def _load_cache_index(self):
        """Load cache index from file"""
        if not self.cache_index_file.exists():
            return
        
        try:
            with open(self.cache_index_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            for text_hash, entry_data in data.items():
                self.cache[text_hash] = TTSCacheEntry.from_dict(entry_data)
            
            logger.info(f"Loaded {len(self.cache)} TTS cache entries")
            
        except Exception as e:
            logger.error(f"Failed to load cache index: {e}")
    
    def _save_cache_index(self):
        """Save cache index to file"""
        try:
            data = {k: v.to_dict() for k, v in self.cache.items()}
            
            with open(self.cache_index_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
        except Exception as e:
            logger.error(f"Failed to save cache index: {e}")
    
    def _get_text_hash(self, text: str) -> str:
        """Get hash of text for caching"""
        return hashlib.md5(text.encode('utf-8')).hexdigest()
    
    def _get_cache_path(self, text_hash: str) -> Path:
        """Get cache file path for text hash"""
        return self.cache_dir / f"{text_hash}.wav"
    
    def _check_cache(self, text: str) -> Optional[str]:
        """Check if text is in cache"""
        if not self.cache_enabled:
            return None
        
        text_hash = self._get_text_hash(text)
        
        with self.cache_lock:
            if text_hash in self.cache:
                entry = self.cache[text_hash]
                
                # Check if file still exists
                if Path(entry.file_path).exists():
                    # Update access stats
                    entry.access_count += 1
                    entry.last_accessed = datetime.now()
                    
                    logger.debug(f"Cache hit for: {text[:30]}...")
                    return entry.file_path
                else:
                    # File deleted, remove from cache
                    del self.cache[text_hash]
        
        return None
    
    def _add_to_cache(self, text: str, file_path: str):
        """Add audio file to cache"""
        if not self.cache_enabled:
            return
        
        text_hash = self._get_text_hash(text)
        
        with self.cache_lock:
            self.cache[text_hash] = TTSCacheEntry(
                text_hash=text_hash,
                file_path=file_path,
                created_at=datetime.now(),
                access_count=1,
                last_accessed=datetime.now()
            )
        
        self._save_cache_index()
        logger.debug(f"Added to cache: {text[:30]}...")
    
    def _apply_emotion(self, text: str, emotion: str) -> str:
        """Apply emotion to text for TTS"""
        # Emotion markers for Silero TTS
        emotion_markers = {
            'happy': '<speak><prosody rate="fast" pitch="+10%">',
            'sad': '<speak><prosody rate="slow" pitch="-10%">',
            'excited': '<speak><prosody rate="fast" pitch="+20%">',
            'calm': '<speak><prosody rate="slow" pitch="-5%">',
            'neutral': '<speak>',
        }
        
        if not self.emotion_enabled:
            return text
        
        marker = emotion_markers.get(emotion, emotion_markers['neutral'])
        return f"{marker}{text}</prosody></speak>"
    
    async def speak(self, text: str, user_id: int = 0, 
                   emotion: str = 'neutral') -> Optional[str]:
        """
        Generate speech from text
        
        Returns path to audio file
        """
        if not self.model:
            logger.error("TTS model not loaded")
            return None
        
        # Check cache first
        cached_path = self._check_cache(text)
        if cached_path:
            return cached_path
        
        try:
            # Run TTS in thread pool
            loop = asyncio.get_event_loop()
            audio_path = await loop.run_in_executor(
                None, self._generate_speech_sync, text, emotion
            )
            
            if audio_path:
                self._add_to_cache(text, audio_path)
            
            return audio_path
            
        except Exception as e:
            logger.error(f"TTS generation error: {e}")
            return None
    
    def _generate_speech_sync(self, text: str, emotion: str) -> Optional[str]:
        """Synchronous speech generation"""
        try:
            # Apply emotion
            text_with_emotion = self._apply_emotion(text, emotion)
            
            # Generate audio
            audio = self.model.apply_tts(
                text=text_with_emotion,
                speaker=self.speaker,
                sample_rate=self.sample_rate
            )
            
            # Save to temp file
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
                torchaudio.save(f.name, audio.unsqueeze(0), self.sample_rate)
                return f.name
            
        except Exception as e:
            logger.error(f"Speech generation error: {e}")
            return None
    
    async def speak_streaming(self, text: str, emotion: str = 'neutral') -> AsyncGenerator[bytes, None]:
        """
        Stream audio chunks as they are generated
        
        Yields audio chunks for real-time playback
        """
        if not self.model or not self.streaming_enabled:
            # Fall back to non-streaming
            audio_path = await self.speak(text, emotion=emotion)
            if audio_path:
                async with aiofiles.open(audio_path, 'rb') as f:
                    while chunk := await f.read(self.chunk_size):
                        yield chunk
            return
        
        try:
            # Split text into sentences for streaming
            sentences = self._split_into_sentences(text)
            
            for sentence in sentences:
                if not sentence.strip():
                    continue
                
                # Generate audio for sentence
                loop = asyncio.get_event_loop()
                audio = await loop.run_in_executor(
                    None, self._generate_sentence_audio, sentence, emotion
                )
                
                if audio is not None:
                    # Convert to bytes
                    audio_bytes = self._tensor_to_bytes(audio)
                    
                    # Yield chunks
                    for i in range(0, len(audio_bytes), self.chunk_size):
                        chunk = audio_bytes[i:i + self.chunk_size]
                        yield chunk
                        
                        # Small delay for streaming effect
                        await asyncio.sleep(0.01)
        
        except Exception as e:
            logger.error(f"Streaming TTS error: {e}")
    
    def _split_into_sentences(self, text: str) -> List[str]:
        """Split text into sentences for streaming"""
        import re
        
        # Split by sentence endings
        sentences = re.split(r'(?<=[.!?])\s+', text)
        return [s.strip() for s in sentences if s.strip()]
    
    def _generate_sentence_audio(self, text: str, emotion: str):
        """Generate audio for a single sentence"""
        try:
            text_with_emotion = self._apply_emotion(text, emotion)
            
            audio = self.model.apply_tts(
                text=text_with_emotion,
                speaker=self.speaker,
                sample_rate=self.sample_rate
            )
            
            return audio
            
        except Exception as e:
            logger.error(f"Sentence generation error: {e}")
            return None
    
    def _tensor_to_bytes(self, tensor) -> bytes:
        """Convert audio tensor to bytes"""
        import io
        
        buffer = io.BytesIO()
        torchaudio.save(buffer, tensor.unsqueeze(0), self.sample_rate, format='wav')
        buffer.seek(0)
        return buffer.read()
    
    def prewarm_cache(self, common_phrases: List[str]):
        """Prewarm cache with common phrases"""
        logger.info(f"Prewarming TTS cache with {len(common_phrases)} phrases...")
        
        for phrase in common_phrases:
            if not self._check_cache(phrase):
                try:
                    audio_path = self._generate_speech_sync(phrase, 'neutral')
                    if audio_path:
                        self._add_to_cache(phrase, audio_path)
                except Exception as e:
                    logger.error(f"Failed to prewarm cache for '{phrase}': {e}")
        
        logger.info("TTS cache prewarm complete")
    
    def get_cache_stats(self) -> Dict:
        """Get cache statistics"""
        total_entries = len(self.cache)
        total_size = sum(
            Path(e.file_path).stat().st_size 
            for e in self.cache.values() 
            if Path(e.file_path).exists()
        )
        
        most_accessed = sorted(
            self.cache.values(), 
            key=lambda x: x.access_count, 
            reverse=True
        )[:5]
        
        return {
            'total_entries': total_entries,
            'total_size_mb': round(total_size / (1024 * 1024), 2),
            'most_accessed': [
                {'hash': e.text_hash, 'access_count': e.access_count}
                for e in most_accessed
            ]
        }
    
    def clear_cache(self):
        """Clear TTS cache"""
        with self.cache_lock:
            for entry in self.cache.values():
                try:
                    Path(entry.file_path).unlink(missing_ok=True)
                except:
                    pass
            
            self.cache.clear()
            self._save_cache_index()
        
        logger.info("TTS cache cleared")
    
    def cleanup_old_entries(self, max_age_days: int = 30):
        """Remove old cache entries"""
        from datetime import timedelta
        
        cutoff = datetime.now() - timedelta(days=max_age_days)
        
        with self.cache_lock:
            to_remove = [
                k for k, v in self.cache.items() 
                if v.last_accessed < cutoff
            ]
            
            for key in to_remove:
                entry = self.cache[key]
                try:
                    Path(entry.file_path).unlink(missing_ok=True)
                except:
                    pass
                del self.cache[key]
            
            if to_remove:
                self._save_cache_index()
                logger.info(f"Cleaned up {len(to_remove)} old cache entries")
