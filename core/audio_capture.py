"""
音频采集模块
支持三种模式：
1. 麦克风输入 (pyaudio)
2. 扬声器/系统音频 (soundcard loopback)
3. 麦克风 + 扬声器混合
"""

import threading
import struct
import logging

logger = logging.getLogger(__name__)

# 音频源类型
SOURCE_MIC = "mic"
SOURCE_SPEAKER = "speaker"
SOURCE_BOTH = "both"


class AudioCapture:
    """音频采集器，支持麦克风和系统扬声器"""

    def __init__(self, sample_rate=16000, channels=1, block_size=3200):
        self.sample_rate = sample_rate
        self.channels = channels
        self.block_size = block_size
        self.is_running = False
        self._lock = threading.Lock()
        self._threads = []

    @staticmethod
    def list_microphones():
        """列出麦克风设备"""
        import pyaudio
        pa = pyaudio.PyAudio()
        devices = []
        for i in range(pa.get_device_count()):
            info = pa.get_device_info_by_index(i)
            if info["maxInputChannels"] > 0:
                devices.append({
                    "index": i,
                    "name": info["name"],
                    "channels": info["maxInputChannels"],
                    "sample_rate": int(info["defaultSampleRate"]),
                    "type": SOURCE_MIC,
                })
        pa.terminate()
        return devices

    @staticmethod
    def list_speakers():
        """列出扬声器设备（可用于 loopback 录制）"""
        try:
            import soundcard as sc
            speakers = []
            for s in sc.all_speakers():
                speakers.append({
                    "id": s.id,
                    "name": s.name,
                    "type": SOURCE_SPEAKER,
                })
            return speakers
        except ImportError:
            logger.warning("soundcard not installed, speaker capture unavailable. pip install soundcard")
            return []
        except Exception as e:
            logger.error(f"Failed to list speakers: {e}")
            return []

    def start(self, source_type=SOURCE_MIC, mic_index=None, speaker_id=None, callback=None):
        """
        开始音频采集
        Args:
            source_type: "mic" / "speaker" / "both"
            mic_index: 麦克风设备索引
            speaker_id: 扬声器设备 ID
            callback: 音频数据回调 callback(audio_data: bytes)
        """
        with self._lock:
            if self.is_running:
                logger.warning("Audio capture already running")
                return
            self._callback = callback
            self.is_running = True
            self._threads = []

        if source_type in (SOURCE_MIC, SOURCE_BOTH):
            t = threading.Thread(
                target=self._mic_loop, args=(mic_index,), daemon=True
            )
            self._threads.append(t)
            t.start()

        if source_type in (SOURCE_SPEAKER, SOURCE_BOTH):
            t = threading.Thread(
                target=self._speaker_loop, args=(speaker_id,), daemon=True
            )
            self._threads.append(t)
            t.start()

        logger.info(f"Audio capture started (source={source_type}, mic={mic_index}, speaker={speaker_id})")

    def _mic_loop(self, device_index):
        """麦克风采集循环 (pyaudio)"""
        import pyaudio
        pa = None
        stream = None
        try:
            pa = pyaudio.PyAudio()
            kwargs = {
                "format": pyaudio.paInt16,
                "channels": self.channels,
                "rate": self.sample_rate,
                "input": True,
                "frames_per_buffer": self.block_size,
            }
            if device_index is not None:
                kwargs["input_device_index"] = device_index

            stream = pa.open(**kwargs)
            logger.info(f"Microphone stream opened (device={device_index})")

            while self.is_running:
                try:
                    data = stream.read(self.block_size, exception_on_overflow=False)
                    if self._callback:
                        self._callback(data)
                except Exception as e:
                    if self.is_running:
                        logger.error(f"Mic read error: {e}")
                    break
        except Exception as e:
            logger.error(f"Mic init error: {e}")
        finally:
            if stream:
                try:
                    stream.stop_stream()
                    stream.close()
                except Exception:
                    pass
            if pa:
                pa.terminate()
            logger.info("Microphone stream closed")

    def _speaker_loop(self, speaker_id):
        """扬声器 Loopback 采集循环 (soundcard)"""
        try:
            import soundcard as sc
            import numpy as np
        except ImportError:
            logger.error("soundcard or numpy not installed. pip install soundcard numpy")
            return

        try:
            # 获取扬声器设备
            if speaker_id:
                speaker = sc.get_speaker(speaker_id)
            else:
                speaker = sc.default_speaker()

            logger.info(f"Speaker loopback opened: {speaker.name}")

            # soundcard 的 loopback 录制
            # numframes = block_size 对应采样点数
            with speaker.recorder(
                samplerate=self.sample_rate,
                channels=self.channels,
                blocksize=self.block_size
            ) as recorder:
                while self.is_running:
                    try:
                        # 录制一块数据，返回 numpy float32 数组
                        audio_np = recorder.record(numframes=self.block_size)

                        # float32 [-1, 1] → int16 PCM bytes
                        audio_int16 = (audio_np * 32767).clip(-32768, 32767).astype(np.int16)
                        pcm_bytes = audio_int16.tobytes()

                        if self._callback:
                            self._callback(pcm_bytes)
                    except Exception as e:
                        if self.is_running:
                            logger.error(f"Speaker read error: {e}")
                        break

        except Exception as e:
            logger.error(f"Speaker loopback init error: {e}")
        finally:
            logger.info("Speaker loopback closed")

    def stop(self):
        """停止所有采集"""
        with self._lock:
            self.is_running = False
        # 等待线程结束
        for t in self._threads:
            t.join(timeout=2)
        self._threads = []
        logger.info("Audio capture stopped")

    def __del__(self):
        self.stop()
