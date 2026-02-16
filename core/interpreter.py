"""
同声传译核心调度器
管理双路音频 + 双路翻译
"""

import logging
import threading
from typing import Callable, Optional
from dataclasses import dataclass

from core.audio_capture import AudioCapture
from core.asr_translator import ASRTranslator, TranslationResult

logger = logging.getLogger(__name__)


@dataclass
class ChannelConfig:
    """单路通道配置"""
    name: str              # 通道名称（如 "mic", "system"）
    device_index: Optional[int]  # 音频设备索引
    target_lang: str       # 目标翻译语言


class Interpreter:
    """
    同声传译调度器
    支持双路音频同时工作：
    - Channel A: 麦克风 → 中文识别 → 英文翻译
    - Channel B: 系统音频 → 英文识别 → 中文翻译
    """

    def __init__(self, config: dict):
        self.config = config
        self.channels = {}  # name -> (AudioCapture, ASRTranslator)
        self._on_result_callback = None
        self._is_running = False

    def set_result_callback(self, callback: Callable[[str, TranslationResult], None]):
        """
        设置结果回调
        Args:
            callback: callback(channel_name, result)
        """
        self._on_result_callback = callback

    def add_channel(self, channel_config: ChannelConfig):
        """添加一路音频通道"""
        audio = AudioCapture(
            sample_rate=self.config.get("audio", {}).get("sample_rate", 16000),
            channels=self.config.get("audio", {}).get("channels", 1),
            block_size=self.config.get("audio", {}).get("block_size", 3200),
        )
        translator = ASRTranslator(self.config)
        self.channels[channel_config.name] = {
            "audio": audio,
            "translator": translator,
            "config": channel_config
        }
        logger.info(f"Channel added: {channel_config.name} → {channel_config.target_lang}")

    def start(self):
        """启动所有通道"""
        if self._is_running:
            logger.warning("Interpreter already running")
            return

        for name, ch in self.channels.items():
            config = ch["config"]

            # 创建结果回调（闭包捕获 channel name）
            def make_callback(ch_name):
                def on_result(result: TranslationResult):
                    if self._on_result_callback:
                        self._on_result_callback(ch_name, result)
                return on_result

            # 启动翻译引擎
            ch["translator"].start(
                target_lang=config.target_lang,
                on_result=make_callback(name)
            )

            # 启动音频采集，数据直接喂给翻译引擎
            ch["audio"].start(
                device_index=config.device_index,
                callback=ch["translator"].send_audio
            )

            logger.info(f"Channel '{name}' started")

        self._is_running = True
        logger.info("Interpreter started")

    def stop(self):
        """停止所有通道"""
        for name, ch in self.channels.items():
            ch["audio"].stop()
            ch["translator"].stop()
            logger.info(f"Channel '{name}' stopped")

        self._is_running = False
        logger.info("Interpreter stopped")

    def switch_language(self, channel_name: str, target_lang: str):
        """切换某个通道的目标语言"""
        if channel_name in self.channels:
            ch = self.channels[channel_name]
            ch["translator"].switch_language(target_lang)
            ch["config"].target_lang = target_lang
            logger.info(f"Channel '{channel_name}' switched to {target_lang}")

    def list_audio_devices(self):
        """列出可用音频设备"""
        ac = AudioCapture()
        devices = ac.list_devices()
        ac.stop()
        return devices

    @property
    def is_running(self):
        return self._is_running
