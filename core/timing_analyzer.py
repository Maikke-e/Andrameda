# ============================================
# Timing Analyzer - Response Time Analysis
# ============================================

import json
import logging
import statistics
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
import threading

from config import DATA_DIR, TIMING_LOG_FILE

logger = logging.getLogger(__name__)


@dataclass
class TimingRecord:
    """Single timing record"""
    user_id: int
    timestamp: datetime
    stt_time: float = 0.0  # Speech-to-text time
    llm_time: float = 0.0  # LLM processing time
    tts_time: float = 0.0  # TTS generation time
    playback_time: float = 0.0  # Audio playback time
    total_time: float = 0.0  # Total time
    
    def to_dict(self) -> Dict:
        return {
            'user_id': self.user_id,
            'timestamp': self.timestamp.isoformat(),
            'stt_time': self.stt_time,
            'llm_time': self.llm_time,
            'tts_time': self.tts_time,
            'playback_time': self.playback_time,
            'total_time': self.total_time
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'TimingRecord':
        return cls(
            user_id=data['user_id'],
            timestamp=datetime.fromisoformat(data['timestamp']),
            stt_time=data.get('stt_time', 0.0),
            llm_time=data.get('llm_time', 0.0),
            tts_time=data.get('tts_time', 0.0),
            playback_time=data.get('playback_time', 0.0),
            total_time=data.get('total_time', 0.0)
        )


class TimingAnalyzer:
    """
    Analyzes response times for voice assistant
    
    Tracks:
    - STT (Speech-to-Text) time
    - LLM processing time
    - TTS generation time
    - Audio playback time
    - Total response time
    
    Provides statistics and optimization recommendations
    """
    
    def __init__(self):
        self.active_timers: Dict[int, Dict] = {}
        self.records: List[TimingRecord] = []
        self.lock = threading.Lock()
        self.max_records = 1000
        
        # Performance thresholds (in seconds)
        self.thresholds = {
            'stt': {'good': 1.0, 'acceptable': 2.0, 'poor': 3.0},
            'llm': {'good': 1.5, 'acceptable': 3.0, 'poor': 5.0},
            'tts': {'good': 0.5, 'acceptable': 1.0, 'poor': 2.0},
            'total': {'good': 3.0, 'acceptable': 5.0, 'poor': 8.0}
        }
        
        self.load_records()
        logger.info("TimingAnalyzer initialized")
    
    def start_timer(self, user_id: int):
        """Start timing for a user"""
        with self.lock:
            self.active_timers[user_id] = {
                'start_time': datetime.now(),
                'stt_end': None,
                'llm_end': None,
                'tts_end': None,
                'playback_end': None
            }
    
    def record_stt(self, user_id: int):
        """Record STT completion time"""
        with self.lock:
            if user_id in self.active_timers:
                self.active_timers[user_id]['stt_end'] = datetime.now()
    
    def record_llm(self, user_id: int):
        """Record LLM completion time"""
        with self.lock:
            if user_id in self.active_timers:
                self.active_timers[user_id]['llm_end'] = datetime.now()
    
    def record_tts(self, user_id: int):
        """Record TTS completion time"""
        with self.lock:
            if user_id in self.active_timers:
                self.active_timers[user_id]['tts_end'] = datetime.now()
    
    def record_playback(self, user_id: int):
        """Record playback completion time"""
        with self.lock:
            if user_id in self.active_timers:
                self.active_timers[user_id]['playback_end'] = datetime.now()
    
    def record_total(self, user_id: int):
        """Record total time and save record"""
        with self.lock:
            if user_id not in self.active_timers:
                return
            
            timer = self.active_timers[user_id]
            end_time = datetime.now()
            start_time = timer['start_time']
            
            # Calculate durations
            stt_time = self._calc_duration(timer['start_time'], timer.get('stt_end'))
            llm_time = self._calc_duration(timer.get('stt_end'), timer.get('llm_end'))
            tts_time = self._calc_duration(timer.get('llm_end'), timer.get('tts_end'))
            playback_time = self._calc_duration(timer.get('tts_end'), timer.get('playback_end'))
            total_time = (end_time - start_time).total_seconds()
            
            record = TimingRecord(
                user_id=user_id,
                timestamp=start_time,
                stt_time=stt_time,
                llm_time=llm_time,
                tts_time=tts_time,
                playback_time=playback_time,
                total_time=total_time
            )
            
            self.records.append(record)
            
            # Keep only last N records
            if len(self.records) > self.max_records:
                self.records = self.records[-self.max_records:]
            
            # Clean up timer
            del self.active_timers[user_id]
            
            # Log timing
            logger.info(
                f"Timing for user {user_id}: "
                f"STT={stt_time:.2f}s, LLM={llm_time:.2f}s, "
                f"TTS={tts_time:.2f}s, Total={total_time:.2f}s"
            )
            
            # Save to file periodically
            if len(self.records) % 10 == 0:
                self.save_records()
    
    def _calc_duration(self, start: Optional[datetime], end: Optional[datetime]) -> float:
        """Calculate duration between two timestamps"""
        if start and end:
            return (end - start).total_seconds()
        return 0.0
    
    def get_stats(self) -> Dict:
        """Get timing statistics"""
        if not self.records:
            return {
                'count': 0,
                'avg_total': 0,
                'min_total': 0,
                'max_total': 0,
                'avg_stt': 0,
                'avg_llm': 0,
                'avg_tts': 0,
                'avg_playback': 0
            }
        
        totals = [r.total_time for r in self.records]
        stt_times = [r.stt_time for r in self.records if r.stt_time > 0]
        llm_times = [r.llm_time for r in self.records if r.llm_time > 0]
        tts_times = [r.tts_time for r in self.records if r.tts_time > 0]
        playback_times = [r.playback_time for r in self.records if r.playback_time > 0]
        
        stats = {
            'count': len(self.records),
            'avg_total': statistics.mean(totals),
            'min_total': min(totals),
            'max_total': max(totals),
            'median_total': statistics.median(totals),
            'avg_stt': statistics.mean(stt_times) if stt_times else 0,
            'avg_llm': statistics.mean(llm_times) if llm_times else 0,
            'avg_tts': statistics.mean(tts_times) if tts_times else 0,
            'avg_playback': statistics.mean(playback_times) if playback_times else 0,
        }
        
        # Add standard deviation if enough data
        if len(totals) > 1:
            stats['std_total'] = statistics.stdev(totals)
        
        return stats
    
    def get_detailed_stats(self) -> Dict:
        """Get detailed statistics with performance ratings"""
        stats = self.get_stats()
        
        detailed = {
            'summary': stats,
            'performance': {},
            'bottlenecks': [],
            'recommendations': []
        }
        
        # Rate each component
        for component, times in [
            ('stt', [r.stt_time for r in self.records if r.stt_time > 0]),
            ('llm', [r.llm_time for r in self.records if r.llm_time > 0]),
            ('tts', [r.tts_time for r in self.records if r.tts_time > 0]),
            ('total', [r.total_time for r in self.records])
        ]:
            if not times:
                continue
            
            avg = statistics.mean(times)
            thresholds = self.thresholds.get(component, {})
            
            if avg <= thresholds.get('good', 1.0):
                rating = 'excellent'
            elif avg <= thresholds.get('acceptable', 2.0):
                rating = 'good'
            elif avg <= thresholds.get('poor', 3.0):
                rating = 'acceptable'
            else:
                rating = 'poor'
            
            detailed['performance'][component] = {
                'average': avg,
                'rating': rating,
                'thresholds': thresholds
            }
            
            # Identify bottlenecks
            if rating == 'poor':
                detailed['bottlenecks'].append(component)
        
        # Generate recommendations
        detailed['recommendations'] = self._generate_recommendations(detailed)
        
        return detailed
    
    def _generate_recommendations(self, detailed: Dict) -> List[str]:
        """Generate optimization recommendations"""
        recommendations = []
        
        if 'stt' in detailed['bottlenecks']:
            recommendations.append(
                "🎙️ <b>STT слишком медленный:</b>\n"
                "• Используйте более лёгкую модель Vosk\n"
                "• Включите потоковое распознавание\n"
                "• Уменьшите качество аудио (16kHz достаточно)"
            )
        
        if 'llm' in detailed['bottlenecks']:
            recommendations.append(
                "🤖 <b>LLM слишком медленный:</b>\n"
                "• Используйте Groq с меньшей задержкой\n"
                "• Уменьшите max_tokens\n"
                "• Используйте кэширование частых запросов\n"
                "• Включите streaming ответы"
            )
        
        if 'tts' in detailed['bottlenecks']:
            recommendations.append(
                "🔊 <b>TTS слишком медленный:</b>\n"
                "• Включите кэширование фраз\n"
                "• Используйте предварительную генерацию\n"
                "• Уменьшите качество голоса\n"
                "• Используйте streaming TTS"
            )
        
        if not detailed['bottlenecks']:
            recommendations.append(
                "✅ <b>Все системы работают отлично!</b>\n"
                "• Среднее время ответа в пределах нормы\n"
                "• Продолжайте мониторинг производительности"
            )
        
        # General recommendations
        if detailed['summary']['count'] < 10:
            recommendations.append(
                "📊 <b>Недостаточно данных:</b>\n"
                "• Соберите больше данных для точного анализа\n"
                "• Минимум 50 запросов для надёжной статистики"
            )
        
        return recommendations
    
    def get_estimated_response_time(self, command_type: str = 'general') -> Dict:
        """
        Estimate response time for different command types
        
        Returns estimated times for:
        - Simple commands (status, volume)
        - Browser commands
        - LLM conversation
        - Full voice pipeline
        """
        stats = self.get_stats()
        
        estimates = {
            'simple_command': {
                'description': 'Простые команды (статус, громкость)',
                'estimated_time': stats.get('avg_stt', 0.5) + 0.2,
                'breakdown': {
                    'stt': stats.get('avg_stt', 0.5),
                    'processing': 0.2
                }
            },
            'browser_command': {
                'description': 'Команды браузера',
                'estimated_time': stats.get('avg_stt', 0.5) + 1.0,
                'breakdown': {
                    'stt': stats.get('avg_stt', 0.5),
                    'browser_operation': 1.0
                }
            },
            'llm_conversation': {
                'description': 'Разговор с LLM',
                'estimated_time': stats.get('avg_stt', 0.5) + 
                                 stats.get('avg_llm', 1.5) + 
                                 stats.get('avg_tts', 0.5),
                'breakdown': {
                    'stt': stats.get('avg_stt', 0.5),
                    'llm': stats.get('avg_llm', 1.5),
                    'tts': stats.get('avg_tts', 0.5)
                }
            },
            'full_voice_pipeline': {
                'description': 'Полный голосовой конвейер',
                'estimated_time': stats.get('avg_total', 3.0),
                'breakdown': {
                    'stt': stats.get('avg_stt', 0.5),
                    'llm': stats.get('avg_llm', 1.5),
                    'tts': stats.get('avg_tts', 0.5),
                    'playback': stats.get('avg_playback', 0.5),
                    'overhead': 0.5
                }
            }
        }
        
        # Add optimization potential
        for key, estimate in estimates.items():
            current = estimate['estimated_time']
            
            # Theoretical minimum with optimizations
            theoretical_min = current * 0.6  # 40% improvement potential
            
            estimate['optimization_potential'] = {
                'current': round(current, 2),
                'theoretical_min': round(theoretical_min, 2),
                'improvement_percent': 40
            }
        
        return estimates
    
    def save_records(self):
        """Save timing records to file"""
        try:
            data = {
                'records': [r.to_dict() for r in self.records],
                'saved_at': datetime.now().isoformat()
            }
            
            with open(TIMING_LOG_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            logger.debug(f"Timing records saved to {TIMING_LOG_FILE}")
            
        except Exception as e:
            logger.error(f"Failed to save timing records: {e}")
    
    def load_records(self):
        """Load timing records from file"""
        if not Path(TIMING_LOG_FILE).exists():
            return
        
        try:
            with open(TIMING_LOG_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            self.records = [
                TimingRecord.from_dict(r) 
                for r in data.get('records', [])
            ]
            
            logger.info(f"Loaded {len(self.records)} timing records")
            
        except Exception as e:
            logger.error(f"Failed to load timing records: {e}")
    
    def generate_report(self) -> str:
        """Generate a detailed timing report"""
        detailed = self.get_detailed_stats()
        estimates = self.get_estimated_response_time()
        
        report = f"""
╔══════════════════════════════════════════════════════════════╗
║           АНАЛИЗ ВРЕМЕНИ ОТВЕТА {VA_NAME}                   ║
╚══════════════════════════════════════════════════════════════╝

📊 <b>ОБЩАЯ СТАТИСТИКА</b>
┌─────────────────────────────────────────────────────────────┐
• Всего запросов: {detailed['summary']['count']}
• Среднее время ответа: {detailed['summary']['avg_total']:.2f}с
• Минимальное: {detailed['summary']['min_total']:.2f}с
• Максимальное: {detailed['summary']['max_total']:.2f}с
• Медиана: {detailed['summary']['median_total']:.2f}с
"""
        
        if 'std_total' in detailed['summary']:
            report += f"• Стандартное отклонение: {detailed['summary']['std_total']:.2f}с\n"
        
        report += "\n🔍 <b>ПРОИЗВОДИТЕЛЬНОСТЬ ПО КОМПОНЕНТАМ</b>\n"
        report += "┌─────────────────────────────────────────────────────────────┐\n"
        
        for component, perf in detailed['performance'].items():
            emoji = {'excellent': '🟢', 'good': '🟡', 'acceptable': '🟠', 'poor': '🔴'}
            report += f"• {emoji.get(perf['rating'], '⚪')} {component.upper()}: "
            report += f"{perf['average']:.2f}с ({perf['rating']})\n"
        
        report += "\n⏱️ <b>ОЦЕНКА ВРЕМЕНИ ДЛЯ РАЗНЫХ ТИПОВ КОМАНД</b>\n"
        report += "┌─────────────────────────────────────────────────────────────┐\n"
        
        for key, estimate in estimates.items():
            report += f"\n<b>{estimate['description']}</b>\n"
            report += f"  Общее время: ~{estimate['estimated_time']:.2f}с\n"
            report += f"  Потенциал оптимизации: {estimate['optimization_potential']['improvement_percent']}%\n"
        
        report += "\n💡 <b>РЕКОМЕНДАЦИИ ПО ОПТИМИЗАЦИИ</b>\n"
        report += "┌─────────────────────────────────────────────────────────────┐\n\n"
        
        for rec in detailed['recommendations']:
            report += rec + "\n\n"
        
        return report


# Import VA_NAME for report
from config import VA_NAME
