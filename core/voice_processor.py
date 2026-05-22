# ============================================
# Voice Processor - Speech-to-Text
# ============================================

import asyncio
import logging
from pathlib import Path
from typing import Optional

import vosk
import soundfile as sf
import numpy as np

from config import VOSK_MODEL_PATH

logger = logging.getLogger(__name__)


class VoiceProcessor:
    """Speech-to-Text processor using Vosk"""
    
    def __init__(self):
        self.model = None
        self._load_model()
    
    def create_stream_recognizer(self, sample_rate: int = 16000):
        """Create a streaming recognizer for microphone input"""
        if not self.model:
            logger.error("Cannot create stream recognizer: model not loaded")
            return None
        rec = vosk.KaldiRecognizer(self.model, sample_rate)
        rec.SetWords(True)
        return rec
    
    def _load_model(self):
        """Load Vosk model"""
        try:
            model_path = Path(VOSK_MODEL_PATH)
            if not model_path.exists():
                logger.error(f"Vosk model not found at {model_path}")
                return
            
            self.model = vosk.Model(str(model_path))
            logger.info("Vosk model loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load Vosk model: {e}")
    
    async def transcribe(self, audio_path: str) -> Optional[str]:
        """Transcribe audio file to text"""
        if not self.model:
            logger.error("Vosk model not loaded")
            return None
        
        try:
            # Run in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, self._transcribe_sync, audio_path)
        except Exception as e:
            logger.error(f"Transcription error: {e}")
            return None
    
    def _transcribe_sync(self, audio_path: str) -> Optional[str]:
        """Synchronous transcription"""
        try:
            # Read audio file
            data, samplerate = sf.read(audio_path)
            
            # Convert to mono if stereo
            if len(data.shape) > 1:
                data = data.mean(axis=1)
            
            # Convert to 16-bit PCM
            data = (data * 32767).astype(np.int16)
            
            # Create recognizer
            rec = vosk.KaldiRecognizer(self.model, samplerate)
            
            # Process audio
            chunk_size = 4000
            for i in range(0, len(data), chunk_size):
                chunk = data[i:i + chunk_size].tobytes()
                rec.AcceptWaveform(chunk)
            
            # Get final result
            import json
            result = json.loads(rec.FinalResult())
            text = result.get('text', '').strip()
            
            logger.info(f"Transcribed: {text}")
            return text if text else None
            
        except Exception as e:
            logger.error(f"Transcription sync error: {e}")
            return None
    
    async def transcribe_stream(self, audio_stream) -> Optional[str]:
        """Transcribe from audio stream (for real-time)"""
        if not self.model:
            return None
        
        try:
            rec = vosk.KaldiRecognizer(self.model, 16000)
            
            async for chunk in audio_stream:
                rec.AcceptWaveform(chunk)
            
            import json
            result = json.loads(rec.FinalResult())
            return result.get('text', '').strip() or None
            
        except Exception as e:
            logger.error(f"Stream transcription error: {e}")
            return None
