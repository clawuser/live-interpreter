"""
音频采集模块
支持麦克风输入和系统音频（WASAPI Loopback）捕获
"""

import threading
import pyaudio
import logging

logger = logging.getLogger(__name__)


class AudioCapture:
    """音频采集器，支持麦克风和系统音频"""

    def __init__(self, sample_rate=16000, channels=1, block_size=3200):
        self.sample_rate = sample_rate
        self.channels = channels
        self.block_size = block_size
        self.pa = None
        self.stream = None
        self.is_running = False
        self._lock = threading.Lock()

    def list_devices(self):
        """列出所有可用音频设备"""
        pa = pyaudio.PyAudio()
        devices = []
        for i in range(pa.get_device_count()):
            info = pa.get_device_info_by_index(i)
            devices.append({
                "index": i,
                "name": info["name"],
                "max_input_channels": info["maxInputChannels"],
                "max_output_channels": info["maxOutputChannels"],
                "default_sample_rate": info["defaultSampleRate"],
                "is_loopback": "loopback" in info["name"].lower()
            })
        pa.terminate()
        return devices

    def list_input_devices(self):
        """列出输入设备（麦克风）"""
        return [d for d in self.list_devices() if d["max_input_channels"] > 0]

    def list_loopback_devices(self):
        """列出系统音频回环设备"""
        return [d for d in self.list_devices()
                if d["max_output_channels"] > 0 or d.get("is_loopback")]

    def start(self, device_index=None, callback=None):
        """
        开始音频采集
        Args:
            device_index: 设备索引，None 为默认麦克风
            callback: 音频数据回调函数 callback(audio_data: bytes)
        """
        with self._lock:
            if self.is_running:
                logger.warning("Audio capture already running")
                return

            self.pa = pyaudio.PyAudio()
            self._callback = callback
            self.is_running = True

            kwargs = {
                "format": pyaudio.paInt16,
                "channels": self.channels,
                "rate": self.sample_rate,
                "input": True,
                "frames_per_buffer": self.block_size,
            }
            if device_index is not None:
                kwargs["input_device_index"] = device_index

            try:
                self.stream = self.pa.open(**kwargs)
                logger.info(f"Audio capture started (device={device_index})")
            except Exception as e:
                logger.error(f"Failed to open audio stream: {e}")
                self.is_running = False
                self.pa.terminate()
                raise

            # 启动采集线程
            self._thread = threading.Thread(target=self._capture_loop, daemon=True)
            self._thread.start()

    def _capture_loop(self):
        """音频采集循环"""
        while self.is_running:
            try:
                if self.stream and self.stream.is_active():
                    data = self.stream.read(self.block_size, exception_on_overflow=False)
                    if self._callback:
                        self._callback(data)
                else:
                    break
            except Exception as e:
                if self.is_running:
                    logger.error(f"Audio capture error: {e}")
                break

    def stop(self):
        """停止音频采集"""
        with self._lock:
            self.is_running = False
            if self.stream:
                try:
                    self.stream.stop_stream()
                    self.stream.close()
                except Exception:
                    pass
                self.stream = None
            if self.pa:
                self.pa.terminate()
                self.pa = None
            logger.info("Audio capture stopped")

    def __del__(self):
        self.stop()
