"""
同声传译核心调度器
"""

import logging
from typing import Callable, Optional
from dataclasses import dataclass

from core.audio_capture import AudioCapture, SOURCE_MIC, SOURCE_SPEAKER
from core.asr_translator import ASRTranslator, TranslationResult

logger = logging.getLogger(__name__)


@dataclass
class ChannelConfig:
    """通道配置"""
    name: str
    target_lang: str
    source_type: str = SOURCE_MIC     # "mic" / "speaker"
    device_index: Optional[int] = None


class Interpreter:
    """同声传译调度器"""

    def __init__(self, config: dict):
        self.config = config
        self.channels = {}
        self._on_result_callback = None
        self._is_running = False

    def set_result_callback(self, callback: Callable[[str, TranslationResult], None]):
        self._on_result_callback = callback

    def add_channel(self, channel_config: ChannelConfig):
        audio = AudioCapture(
            sample_rate=self.config.get("audio", {}).get("sample_rate", 16000),
        )
        translator = ASRTranslator(self.config)
        self.channels[channel_config.name] = {
            "audio": audio,
            "translator": translator,
            "config": channel_config,
        }
        logger.info(f"Channel added: {channel_config.name} ({channel_config.source_type}) → {channel_config.target_lang}")

    def start(self):
        if self._is_running:
            return

        for name, ch in self.channels.items():
            config = ch["config"]

            def make_callback(ch_name):
                def on_result(result: TranslationResult):
                    if self._on_result_callback:
                        self._on_result_callback(ch_name, result)
                return on_result

            ch["translator"].start(
                target_lang=config.target_lang,
                on_result=make_callback(name)
            )

            ch["audio"].start(
                source_type=config.source_type,
                device_index=config.device_index,
                callback=ch["translator"].send_audio
            )

        self._is_running = True
        logger.info("Interpreter started")

    def stop(self):
        for name, ch in self.channels.items():
            ch["audio"].stop()
            ch["translator"].stop()
        self._is_running = False
        logger.info("Interpreter stopped")

    def switch_language(self, channel_name: str, target_lang: str):
        if channel_name in self.channels:
            ch = self.channels[channel_name]
            ch["translator"].switch_language(target_lang)
            ch["config"].target_lang = target_lang

    @staticmethod
    def list_devices():
        return AudioCapture.list_devices()

    @property
    def is_running(self):
        return self._is_running
