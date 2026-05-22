# ============================================
# Audio Player - WAV playback + activation beep
# ============================================

import logging
import threading
import numpy as np
import wave
import io
from typing import Optional

import pyaudio

logger = logging.getLogger(__name__)


class AudioPlayer:
    """
    Audio playback engine using PyAudio
    
    Features:
    - WAV file playback (non-blocking)
    - Tone generation (activation beep)
    - Playback status tracking
    """
    
    def __init__(self):
        self._pa = pyaudio.PyAudio()
        self._playing = False
        self._stop_event = threading.Event()
        self._play_thread: Optional[threading.Thread] = None
        logger.info("AudioPlayer initialized")
    
    def play_file(self, filepath: str, blocking: bool = False):
        """
        Play a WAV file
        
        Args:
            filepath: Path to WAV file
            blocking: If True, wait for playback to finish
        """
        if self._playing:
            self.stop()
        
        self._stop_event.clear()
        
        if blocking:
            self._play_wav(filepath)
        else:
            self._play_thread = threading.Thread(
                target=self._play_wav, args=(filepath,), daemon=True
            )
            self._play_thread.start()
    
    def _play_wav(self, filepath: str):
        """Internal WAV playback"""
        stream = None
        wf = None
        try:
            self._playing = True
            wf = wave.open(filepath, 'rb')
            
            stream = self._pa.open(
                format=self._pa.get_format_from_width(wf.getsampwidth()),
                channels=wf.getnchannels(),
                rate=wf.getframerate(),
                output=True
            )
            
            chunk_size = 1024
            data = wf.readframes(chunk_size)
            
            while data and not self._stop_event.is_set():
                stream.write(data)
                data = wf.readframes(chunk_size)
            
        except Exception as e:
            logger.error(f"Playback error: {e}")
        finally:
            self._playing = False
            if stream:
                try:
                    stream.stop_stream()
                    stream.close()
                except Exception:
                    pass
            if wf:
                wf.close()
    
    def play_beep(self, frequency: int = 800, duration: float = 0.15,
                  sample_rate: int = 16000, volume: float = 0.3):
        """
        Play a short beep tone for activation feedback
        
        Args:
            frequency: Tone frequency in Hz
            duration: Duration in seconds
            sample_rate: Audio sample rate
            volume: Volume (0.0 - 1.0)
        """
        if self._playing:
            self.stop()
        
        self._stop_event.clear()
        
        thread = threading.Thread(
            target=self._play_tone,
            args=(frequency, duration, sample_rate, volume),
            daemon=True
        )
        thread.start()
    
    def play_double_beep(self, frequency: int = 800, duration: float = 0.1,
                         sample_rate: int = 16000, volume: float = 0.3):
        """Play a double beep for deactivation/ready signal"""
        if self._playing:
            self.stop()
        
        self._stop_event.clear()
        
        thread = threading.Thread(
            target=self._play_double_tone,
            args=(frequency, duration, sample_rate, volume),
            daemon=True
        )
        thread.start()
    
    def _play_tone(self, frequency: int, duration: float,
                   sample_rate: int, volume: float):
        """Internal tone generation and playback"""
        stream = None
        try:
            self._playing = True
            
            # Generate sine wave
            t = np.linspace(0, duration, int(sample_rate * duration), dtype=np.float32)
            # Apply fade-in/fade-out envelope to avoid clicks
            envelope = np.ones_like(t)
            fade_samples = int(sample_rate * 0.01)  # 10ms fade
            if fade_samples > 0 and len(t) > 2 * fade_samples:
                envelope[:fade_samples] = np.linspace(0, 1, fade_samples)
                envelope[-fade_samples:] = np.linspace(1, 0, fade_samples)
            
            tone = (volume * np.sin(2 * np.pi * frequency * t) * envelope).astype(np.float32)
            audio_data = (tone * 32767).astype(np.int16).tobytes()
            
            stream = self._pa.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=sample_rate,
                output=True
            )
            
            stream.write(audio_data)
            
        except Exception as e:
            logger.error(f"Beep playback error: {e}")
        finally:
            self._playing = False
            if stream:
                try:
                    stream.stop_stream()
                    stream.close()
                except Exception:
                    pass
    
    def _play_double_tone(self, frequency: int, duration: float,
                          sample_rate: int, volume: float):
        """Play two short beeps with a gap"""
        self._play_tone(frequency, duration, sample_rate, volume)
        import time
        time.sleep(0.05)
        self._play_tone(int(frequency * 1.2), duration, sample_rate, volume)
    
    def stop(self):
        """Stop current playback"""
        self._stop_event.set()
        if self._play_thread and self._play_thread.is_alive():
            self._play_thread.join(timeout=1.0)
        self._playing = False
    
    def is_playing(self) -> bool:
        """Check if audio is currently playing"""
        return self._playing
    
    def close(self):
        """Clean up PyAudio resources"""
        self.stop()
        try:
            self._pa.terminate()
        except Exception:
            pass
        logger.info("AudioPlayer closed")
