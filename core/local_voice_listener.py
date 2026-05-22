# ============================================
# Local Voice Listener - Wake Word + Voice Commands
# ============================================
#
# Непрерывно слушает микрофон через PyAudio,
# детектирует wake-word через Vosk,
# записывает команду, обрабатывает через CommandRouter,
# и отвечает голосом через Silero TTS.
# ============================================

import asyncio
import json
import logging
import struct
import math
import threading
import time
import queue
from enum import Enum
from typing import Optional

import pyaudio
import numpy as np

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from config import (
    VA_NAME, VA_ALIAS,
    VOSK_MODEL_PATH,
    SILENCE_THRESHOLD, SILENCE_DURATION,
    ACTIVATION_SOUND,
    LOCAL_VOICE_DEVICE_INDEX,
    MIC_SAMPLE_RATE, MIC_CHUNK_SIZE,
)
from core.voice_processor import VoiceProcessor
from core.command_router import CommandRouter
from core.context_manager import ContextManager
from core.timing_analyzer import TimingAnalyzer
from core.audio_player import AudioPlayer
from tts.tts_engine import TTSEngine
from reminders.reminder_system import ReminderSystem

logger = logging.getLogger(__name__)


class ListenerState(Enum):
    """Voice listener states"""
    IDLE = "idle"             # Listening for wake word
    LISTENING = "listening"   # Recording user command
    PROCESSING = "processing" # Processing command
    SPEAKING = "speaking"     # Playing TTS response


class LocalVoiceListener:
    """
    Local voice assistant with wake-word activation via Vosk.
    
    Runs in a separate thread alongside the Telegram bot.
    
    Flow:
    1. IDLE: Continuously stream audio to Vosk, check for wake-word
    2. LISTENING: Wake-word detected → beep → record command until silence
    3. PROCESSING: Send recognized text to CommandRouter
    4. SPEAKING: Play TTS response through speakers
    5. → Back to IDLE
    """
    
    # Local user_id for context tracking (not a real Telegram user)
    LOCAL_USER_ID = 0
    
    def __init__(self):
        self.state = ListenerState.IDLE
        self.running = False
        
        # Audio settings
        self.sample_rate = MIC_SAMPLE_RATE
        self.chunk_size = MIC_CHUNK_SIZE
        self.device_index = LOCAL_VOICE_DEVICE_INDEX if LOCAL_VOICE_DEVICE_INDEX >= 0 else None
        
        # Silence detection
        self.silence_threshold = SILENCE_THRESHOLD
        self.silence_duration = SILENCE_DURATION
        
        # Wake words (lowercase)
        self.wake_words = [VA_NAME.lower()] + [a.lower() for a in VA_ALIAS]
        
        # Components (shared with Telegram bot where possible)
        self.voice_processor = VoiceProcessor()
        self.command_router = CommandRouter()
        self.context_manager = ContextManager()
        self.timing_analyzer = TimingAnalyzer()
        self.tts_engine = TTSEngine()
        self.audio_player = AudioPlayer()
        self.reminder_system = ReminderSystem()
        
        # PyAudio
        self._pa: Optional[pyaudio.PyAudio] = None
        self._stream = None
        
        # Thread
        self._thread: Optional[threading.Thread] = None
        self._async_loop: Optional[asyncio.AbstractEventLoop] = None
        
        logger.info(
            f"LocalVoiceListener initialized "
            f"(wake_words={self.wake_words}, "
            f"sample_rate={self.sample_rate}, "
            f"silence_threshold={self.silence_threshold})"
        )
    
    def start(self):
        """Start the voice listener in a background thread"""
        if self.running:
            logger.warning("Voice listener is already running")
            return
        
        self.running = True
        self._thread = threading.Thread(target=self._run, daemon=True, name="VoiceListener")
        self._thread.start()
        logger.info("Local voice listener started")
    
    def stop(self):
        """Stop the voice listener"""
        self.running = False
        
        if self._stream:
            try:
                self._stream.stop_stream()
                self._stream.close()
            except Exception:
                pass
        
        if self._pa:
            try:
                self._pa.terminate()
            except Exception:
                pass
        
        if self.audio_player:
            self.audio_player.close()
        
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)
        
        logger.info("Local voice listener stopped")
    
    def _run(self):
        """Main thread entry point"""
        # Create a dedicated event loop for async operations
        self._async_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._async_loop)
        
        # Set event loop for reminder system
        self.reminder_system.event_loop = self._async_loop
        
        try:
            self._init_audio()
            self._listen_loop()
        except Exception as e:
            logger.error(f"Voice listener fatal error: {e}", exc_info=True)
        finally:
            self._async_loop.close()
    
    def _init_audio(self):
        """Initialize PyAudio microphone stream"""
        self._pa = pyaudio.PyAudio()
        
        # Log available devices
        device_count = self._pa.get_device_count()
        logger.info(f"Available audio devices: {device_count}")
        
        default_input = self._pa.get_default_input_device_info()
        logger.info(f"Default input device: {default_input['name']} (index={default_input['index']})")
        
        # Open microphone stream
        stream_kwargs = {
            'format': pyaudio.paInt16,
            'channels': 1,
            'rate': self.sample_rate,
            'input': True,
            'frames_per_buffer': self.chunk_size,
        }
        
        if self.device_index is not None:
            stream_kwargs['input_device_index'] = self.device_index
            logger.info(f"Using audio device index: {self.device_index}")
        
        self._stream = self._pa.open(**stream_kwargs)
        logger.info("Microphone stream opened")
    
    def _listen_loop(self):
        """Main listening loop — wake-word detection → command recording"""
        # Create Vosk recognizer for streaming
        recognizer = self.voice_processor.create_stream_recognizer(self.sample_rate)
        
        if not recognizer:
            logger.error("Failed to create Vosk recognizer, cannot start voice listener")
            return
        
        logger.info(f"🎙️ Андромеда слушает... (wake-words: {', '.join(self.wake_words)})")
        
        while self.running:
            try:
                # Read audio chunk from microphone
                data = self._stream.read(self.chunk_size, exception_on_overflow=False)
                
                if self.state == ListenerState.IDLE:
                    self._process_idle(data, recognizer)
                    
                elif self.state == ListenerState.SPEAKING:
                    # Wait for playback to finish
                    if not self.audio_player.is_playing():
                        self.state = ListenerState.IDLE
                        # Reset recognizer for clean slate
                        recognizer = self.voice_processor.create_stream_recognizer(self.sample_rate)
                        logger.debug("Playback finished, returning to IDLE")
                    
            except IOError as e:
                # Buffer overflow — skip and continue
                logger.debug(f"Audio buffer overflow: {e}")
                continue
            except Exception as e:
                logger.error(f"Listen loop error: {e}", exc_info=True)
                time.sleep(0.1)
    
    def _process_idle(self, data: bytes, recognizer):
        """Process audio in IDLE state — look for wake word"""
        # Feed audio to Vosk
        if recognizer.AcceptWaveform(data):
            result = json.loads(recognizer.Result())
            text = result.get('text', '').lower().strip()
            
            if text:
                logger.debug(f"Heard (idle): {text}")
                
                # Check for wake word
                if self._contains_wake_word(text):
                    logger.info(f"🔔 Wake word detected in: '{text}'")
                    self._on_wake_word_detected(text)
        else:
            # Check partial results too for faster wake-word detection
            partial = json.loads(recognizer.PartialResult())
            partial_text = partial.get('partial', '').lower().strip()
            
            if partial_text and self._contains_wake_word(partial_text):
                logger.info(f"🔔 Wake word detected (partial): '{partial_text}'")
                # Reset recognizer to clear the buffer
                recognizer.Reset()
                self._on_wake_word_detected(partial_text)
    
    def _contains_wake_word(self, text: str) -> bool:
        """Check if text contains any wake word"""
        text_lower = text.lower()
        for word in self.wake_words:
            if word in text_lower:
                return True
        return False
    
    def _extract_command_after_wake_word(self, text: str) -> str:
        """Extract command text that may follow the wake word in the same utterance"""
        text_lower = text.lower()
        for word in self.wake_words:
            idx = text_lower.find(word)
            if idx >= 0:
                after = text[idx + len(word):].strip()
                # Remove common filler words after wake word
                fillers = ['пожалуйста', 'слушай', 'эй', 'привет']
                for filler in fillers:
                    if after.lower().startswith(filler):
                        after = after[len(filler):].strip()
                return after
        return ""
    
    def _on_wake_word_detected(self, wake_text: str):
        """Handle wake word detection"""
        # Check if there's already a command after the wake word
        inline_command = self._extract_command_after_wake_word(wake_text)
        
        if inline_command and len(inline_command) > 2:
            # Command was said together with wake word
            logger.info(f"Inline command detected: '{inline_command}'")
            if ACTIVATION_SOUND:
                self.audio_player.play_beep(frequency=800, duration=0.1)
                time.sleep(0.15)
            self._process_command(inline_command)
            return
        
        # Play activation beep
        if ACTIVATION_SOUND:
            self.audio_player.play_beep(frequency=800, duration=0.15)
            time.sleep(0.2)
        
        # Record command
        self.state = ListenerState.LISTENING
        command_text = self._record_command()
        
        if command_text:
            self._process_command(command_text)
        else:
            logger.info("No command detected after wake word")
            self.state = ListenerState.IDLE
    
    def _record_command(self) -> Optional[str]:
        """
        Record user command after wake word activation.
        
        Listens until silence is detected (no speech for SILENCE_DURATION seconds).
        Returns recognized text or None.
        """
        logger.info("📢 Recording command...")
        
        # Create fresh recognizer for the command
        rec = self.voice_processor.create_stream_recognizer(self.sample_rate)
        if not rec:
            return None
        
        silence_start = None
        has_speech = False
        max_duration = 15.0  # Max recording duration (seconds)
        start_time = time.time()
        
        while self.running:
            elapsed = time.time() - start_time
            
            # Timeout protection
            if elapsed > max_duration:
                logger.warning("Command recording timeout")
                break
            
            try:
                data = self._stream.read(self.chunk_size, exception_on_overflow=False)
            except IOError:
                continue
            
            # Calculate RMS for silence detection
            rms = self._calculate_rms(data)
            
            if rms > self.silence_threshold:
                # Speech detected
                has_speech = True
                silence_start = None
            else:
                # Silence
                if has_speech and silence_start is None:
                    silence_start = time.time()
                elif has_speech and silence_start is not None:
                    silence_elapsed = time.time() - silence_start
                    if silence_elapsed >= self.silence_duration:
                        logger.debug(f"Silence detected for {silence_elapsed:.1f}s, stopping recording")
                        break
            
            # Feed to Vosk
            rec.AcceptWaveform(data)
        
        # Get final result
        result = json.loads(rec.FinalResult())
        text = result.get('text', '').strip()
        
        if text:
            logger.info(f"🎙️ Recognized command: '{text}'")
        else:
            logger.info("No speech recognized")
        
        return text if text else None
    
    def _calculate_rms(self, data: bytes) -> float:
        """Calculate RMS (Root Mean Square) level of audio data"""
        try:
            # Convert bytes to int16 array
            count = len(data) // 2
            if count == 0:
                return 0.0
            shorts = struct.unpack(f'{count}h', data)
            # Calculate RMS
            sum_squares = sum(s * s for s in shorts)
            rms = math.sqrt(sum_squares / count)
            return rms
        except Exception:
            return 0.0
    
    def _process_command(self, text: str):
        """Process recognized command through CommandRouter"""
        self.state = ListenerState.PROCESSING
        logger.info(f"⚙️ Processing command: '{text}'")
        
        try:
            # Add to context
            self.context_manager.add_command(self.LOCAL_USER_ID, text)
            context = self.context_manager.get_context(self.LOCAL_USER_ID)
            
            # Start timing
            self.timing_analyzer.start_timer(self.LOCAL_USER_ID)
            
            # Route command (run async in our event loop)
            response, action_type = self._async_loop.run_until_complete(
                self.command_router.route(
                    text=text,
                    context=context,
                    user_id=self.LOCAL_USER_ID,
                    reminder_system=self.reminder_system
                )
            )
            
            self.timing_analyzer.record_llm(self.LOCAL_USER_ID)
            
            logger.info(f"💬 Response: {response[:100]}...")
            
            # Add response to context
            self.context_manager.add_assistant_response(
                user_id=self.LOCAL_USER_ID,
                response=response,
                action_type=action_type
            )
            
            # Generate and play TTS response
            self._speak_response(response)
            
            # Record total time
            self.timing_analyzer.record_total(self.LOCAL_USER_ID)
            
        except Exception as e:
            logger.error(f"Command processing error: {e}", exc_info=True)
            # Try to speak error message
            self._speak_response(f"Произошла ошибка: {e}")
    
    def _speak_response(self, text: str):
        """Generate TTS and play through speakers"""
        self.state = ListenerState.SPEAKING
        
        try:
            # Strip HTML tags for TTS
            clean_text = self._strip_html(text)
            
            if not clean_text.strip():
                self.state = ListenerState.IDLE
                return
            
            # Generate TTS audio
            audio_path = self._async_loop.run_until_complete(
                self.tts_engine.speak(clean_text, user_id=self.LOCAL_USER_ID)
            )
            
            self.timing_analyzer.record_tts(self.LOCAL_USER_ID)
            
            if audio_path:
                logger.info(f"🔊 Playing TTS response: {audio_path}")
                # Play and wait for completion
                self.audio_player.play_file(audio_path, blocking=True)
            else:
                logger.warning("TTS generation returned no audio")
            
        except Exception as e:
            logger.error(f"TTS playback error: {e}", exc_info=True)
        finally:
            self.state = ListenerState.IDLE
    
    @staticmethod
    def _strip_html(text: str) -> str:
        """Remove HTML tags from text for TTS"""
        import re
        # Remove HTML tags
        clean = re.sub(r'<[^>]+>', '', text)
        # Remove multiple spaces
        clean = re.sub(r'\s+', ' ', clean)
        # Remove emoji (optional — Silero handles some)
        # clean = re.sub(r'[^\w\s.,!?;:\-\'"()]', '', clean)
        return clean.strip()
