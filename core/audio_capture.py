"""
音频采集模块
基于 pyaudiowpatch，支持：
1. 麦克风输入
2. 扬声器/系统音频 (WASAPI Loopback)
参考 interview-assistant 项目实现
"""

import struct
import threading
import logging
from typing import Callable, Optional, List, Dict

import pyaudiowpatch as pyaudio

logger = logging.getLogger(__name__)

# 音频源类型
SOURCE_MIC = "mic"
SOURCE_SPEAKER = "speaker"


class AudioCapture:
    """Windows 音频采集，支持麦克风和 WASAPI Loopback"""

    def __init__(self, sample_rate=16000, output_format='pcm', device_index=None):
        self.sample_rate = sample_rate
        self.output_format = output_format.lower()
        self.is_running = False
        self.callback: Optional[Callable[[bytes], None]] = None
        self._thread: Optional[threading.Thread] = None
        self.p = pyaudio.PyAudio()
        self.device_info = None

        # PCM 模式：每次输出 3200 bytes = 1600 帧 @16kHz ≈ 100ms
        self.pcm_chunk_frames = 1600

    def find_device(self, source_type=SOURCE_MIC, device_index=None) -> Optional[Dict]:
        """
        查找音频设备
        source_type: "mic" 用默认麦克风, "speaker" 用 WASAPI Loopback
        device_index: 指定设备索引（优先）
        """
        # 1. 用户指定设备
        if device_index is not None:
            try:
                info = self.p.get_device_info_by_index(device_index)
                logger.info(f"Using specified device: [{device_index}] {info['name']}")
                self.device_info = info
                return info
            except Exception:
                logger.warning(f"Specified device {device_index} unavailable, auto-selecting...")

        if source_type == SOURCE_SPEAKER:
            # 2. WASAPI Loopback
            return self._find_wasapi_loopback()
        else:
            # 3. 默认麦克风
            return self._find_default_mic()

    def _find_default_mic(self) -> Optional[Dict]:
        """查找默认麦克风"""
        try:
            info = self.p.get_default_input_device_info()
            logger.info(f"Default microphone: {info['name']}")
            self.device_info = info
            return info
        except Exception as e:
            logger.error(f"No default microphone: {e}")
            return None

    def _find_wasapi_loopback(self) -> Optional[Dict]:
        """查找 WASAPI Loopback 设备（当前默认输出设备的回环）"""
        try:
            wasapi_info = self.p.get_host_api_info_by_type(pyaudio.paWASAPI)
            default_output_index = wasapi_info['defaultOutputDevice']
            default_output = self.p.get_device_info_by_index(default_output_index)
            logger.info(f"Default output device: {default_output['name']}")

            # 精确匹配
            for loopback in self.p.get_loopback_device_info_generator():
                if default_output['name'] in loopback['name']:
                    logger.info(f"Found loopback: {loopback['name']}")
                    self.device_info = loopback
                    return loopback

            # 模糊匹配
            for loopback in self.p.get_loopback_device_info_generator():
                short_name = default_output['name'][:15]
                if short_name in loopback['name']:
                    logger.info(f"Found loopback (fuzzy): {loopback['name']}")
                    self.device_info = loopback
                    return loopback

            logger.warning("No WASAPI Loopback device found")
        except Exception as e:
            logger.error(f"WASAPI Loopback search failed: {e}")
        return None

    @staticmethod
    def list_devices() -> List[Dict]:
        """列出所有可用音频设备"""
        p = pyaudio.PyAudio()
        devices = []

        # 普通输入设备（麦克风）
        for i in range(p.get_device_count()):
            info = p.get_device_info_by_index(i)
            if info['maxInputChannels'] > 0:
                devices.append({
                    'index': i,
                    'name': info['name'],
                    'channels': info['maxInputChannels'],
                    'sample_rate': int(info['defaultSampleRate']),
                    'type': SOURCE_MIC,
                    'is_loopback': False,
                })

        # WASAPI Loopback 设备
        try:
            for loopback in p.get_loopback_device_info_generator():
                devices.append({
                    'index': loopback['index'],
                    'name': loopback['name'],
                    'channels': loopback['maxInputChannels'],
                    'sample_rate': int(loopback['defaultSampleRate']),
                    'type': SOURCE_SPEAKER,
                    'is_loopback': True,
                })
        except Exception as e:
            logger.warning(f"Cannot enumerate loopback devices: {e}")

        p.terminate()
        return devices

    def start(self, source_type=SOURCE_MIC, device_index=None, callback=None):
        """
        开始采集
        Args:
            source_type: "mic" or "speaker"
            device_index: 指定设备索引（None=自动）
            callback: 回调函数 callback(pcm_bytes)
        """
        if self.is_running:
            logger.warning("Audio capture already running")
            return

        self.callback = callback

        # 查找设备
        device = self.find_device(source_type, device_index)
        if not device:
            raise RuntimeError(f"No audio device found for source_type={source_type}")

        self.is_running = True
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()

    def _capture_loop(self):
        """音频采集循环"""
        device_rate = int(self.device_info['defaultSampleRate'])
        device_channels = max(1, int(self.device_info['maxInputChannels']))
        need_resample = (device_rate != self.sample_rate) or (device_channels != 1)

        if need_resample:
            logger.info(f"Resampling: {device_rate}Hz/{device_channels}ch → {self.sample_rate}Hz/1ch")

        # 计算设备端每次读取的帧数
        device_frames = int(self.pcm_chunk_frames * device_rate / self.sample_rate)

        stream = None
        try:
            stream = self.p.open(
                format=pyaudio.paInt16,
                channels=device_channels,
                rate=device_rate,
                input=True,
                input_device_index=self.device_info['index'],
                frames_per_buffer=device_frames,
            )
            logger.info(f"Audio stream opened: {self.device_info['name']}")

            while self.is_running:
                try:
                    raw_data = stream.read(device_frames, exception_on_overflow=False)

                    if need_resample:
                        pcm_data = self._resample(raw_data, device_rate, device_channels)
                    else:
                        pcm_data = raw_data

                    if self.callback and pcm_data:
                        self.callback(pcm_data)
                except Exception as e:
                    if self.is_running:
                        logger.error(f"Audio read error: {e}")
                    break
        except Exception as e:
            logger.error(f"Audio stream init error: {e}")
        finally:
            if stream:
                try:
                    stream.stop_stream()
                    stream.close()
                except Exception:
                    pass
            logger.info("Audio stream closed")

    def _resample(self, raw_data: bytes, source_rate: int, source_channels: int) -> bytes:
        """重采样：任意采样率/声道 → 16kHz/单声道"""
        samples = struct.unpack(f'<{len(raw_data) // 2}h', raw_data)

        # 多声道 → 单声道（取平均）
        if source_channels > 1:
            mono = []
            for i in range(0, len(samples), source_channels):
                chunk = samples[i:i + source_channels]
                mono.append(sum(chunk) // len(chunk))
            samples = mono

        # 重采样（线性插值）
        if source_rate != self.sample_rate:
            ratio = self.sample_rate / source_rate
            new_length = int(len(samples) * ratio)
            resampled = []
            for i in range(new_length):
                src_pos = i / ratio
                idx = int(src_pos)
                frac = src_pos - idx
                if idx + 1 < len(samples):
                    value = int(samples[idx] * (1 - frac) + samples[idx + 1] * frac)
                elif idx < len(samples):
                    value = samples[idx]
                else:
                    break
                resampled.append(max(-32768, min(32767, value)))
            samples = resampled

        return struct.pack(f'<{len(samples)}h', *samples)

    def stop(self):
        """停止采集"""
        if not self.is_running:
            return
        self.is_running = False
        if self._thread:
            self._thread.join(timeout=3)
            self._thread = None
        logger.info("Audio capture stopped")

    def get_device_name(self) -> str:
        if self.device_info:
            return self.device_info['name']
        return "未知"

    def __del__(self):
        self.stop()
        if self.p:
            try:
                self.p.terminate()
            except Exception:
                pass
