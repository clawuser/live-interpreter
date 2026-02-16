"""
百炼 LiveTranslate ASR 引擎
基于 qwen3-livetranslate-flash-realtime 模型
一步完成：语音识别 + 实时翻译
"""

import os
import logging
import threading
from dataclasses import dataclass
from typing import Callable, Optional

import dashscope
from dashscope.audio.qwen_omni import OmniRealtimeConversation, OmniRealtimeCallback

logger = logging.getLogger(__name__)


@dataclass
class TranslationResult:
    """翻译结果"""
    source_text: str       # 原文
    translated_text: str   # 译文
    source_lang: str       # 源语言
    target_lang: str       # 目标语言
    is_final: bool         # 是否为最终结果（句子结束）


class LiveTranslateCallback(OmniRealtimeCallback):
    """百炼 LiveTranslate 实时回调"""

    def __init__(self, on_result: Callable[[TranslationResult], None],
                 target_lang: str = "en"):
        self.on_result = on_result
        self.target_lang = target_lang
        self.conversation = None
        self._current_source = ""
        self._current_translated = ""

    def on_open(self):
        logger.info("LiveTranslate WebSocket connected")

    def on_close(self, code, msg):
        logger.info(f"LiveTranslate WebSocket closed: code={code}, msg={msg}")

    def on_event(self, response):
        try:
            event_type = response.get("type", "")

            if event_type == "session.created":
                session_id = response.get("session", {}).get("id", "unknown")
                logger.info(f"Session created: {session_id}")

            elif event_type == "conversation.item.input_audio_transcription.text":
                # 中间结果（实时识别）
                stash = response.get("stash", "")
                if stash:
                    self._current_source = stash
                    result = TranslationResult(
                        source_text=stash,
                        translated_text="",
                        source_lang="auto",
                        target_lang=self.target_lang,
                        is_final=False
                    )
                    self.on_result(result)

            elif event_type == "conversation.item.input_audio_transcription.completed":
                # 最终结果
                transcript = response.get("transcript", "")
                translation = response.get("translation", "")
                if transcript or translation:
                    result = TranslationResult(
                        source_text=transcript,
                        translated_text=translation,
                        source_lang="auto",
                        target_lang=self.target_lang,
                        is_final=True
                    )
                    self.on_result(result)

            elif event_type == "input_audio_buffer.speech_started":
                logger.debug("Speech started")

            elif event_type == "input_audio_buffer.speech_stopped":
                logger.debug("Speech stopped")

        except Exception as e:
            logger.error(f"Callback error: {e}")

    def on_error(self, error):
        logger.error(f"LiveTranslate error: {error}")


class ASRTranslator:
    """
    百炼 LiveTranslate ASR+翻译引擎
    使用 qwen3-livetranslate-flash-realtime 模型
    """

    def __init__(self, config: dict):
        self.config = config
        self.conversation: Optional[OmniRealtimeConversation] = None
        self._is_running = False
        self._lock = threading.Lock()

        # 配置 API Key
        api_key = config.get("dashscope", {}).get("api_key", "")
        if api_key:
            dashscope.api_key = api_key
        elif os.environ.get("DASHSCOPE_API_KEY"):
            dashscope.api_key = os.environ["DASHSCOPE_API_KEY"]
        else:
            raise ValueError("No API Key configured. Set DASHSCOPE_API_KEY or config.dashscope.api_key")

    def start(self, target_lang: str, on_result: Callable[[TranslationResult], None]):
        """
        启动 ASR + 翻译
        Args:
            target_lang: 目标语言代码 (en, zh, ja, ko, ...)
            on_result: 结果回调
        """
        with self._lock:
            if self._is_running:
                logger.warning("ASR Translator already running")
                return

            model_config = self.config.get("model", {})
            model_name = model_config.get("name", "qwen3-livetranslate-flash-realtime")
            ws_url = self.config.get("dashscope", {}).get(
                "websocket_url", "wss://dashscope.aliyuncs.com/api-ws/v1/realtime"
            )

            # 创建回调
            self._callback = LiveTranslateCallback(
                on_result=on_result,
                target_lang=target_lang
            )

            # 创建会话
            self.conversation = OmniRealtimeConversation(
                model=model_name,
                url=ws_url,
                callback=self._callback
            )
            self._callback.conversation = self.conversation

            # 连接
            self.conversation.connect()

            # 配置 session
            audio_config = self.config.get("audio", {})
            vad_config = model_config

            from dashscope.audio.qwen_omni import MultiModality, TranscriptionParams

            transcription_params = TranscriptionParams(
                language="auto",
                sample_rate=audio_config.get("sample_rate", 16000),
                input_audio_format=audio_config.get("format", "pcm")
            )

            self.conversation.update_session(
                output_modalities=[MultiModality.TEXT],
                enable_turn_detection=vad_config.get("vad_enabled", True),
                turn_detection_type="server_vad",
                turn_detection_threshold=vad_config.get("vad_threshold", 0.0),
                turn_detection_silence_duration_ms=vad_config.get("vad_silence_duration_ms", 400),
                enable_input_audio_transcription=True,
                transcription_params=transcription_params,
                translation={
                    "language": target_lang
                }
            )

            self._is_running = True
            logger.info(f"ASR Translator started (target_lang={target_lang})")

    def send_audio(self, audio_data: bytes):
        """发送音频数据"""
        if self._is_running and self.conversation:
            try:
                self.conversation.send_audio(audio_data)
            except Exception as e:
                logger.error(f"Send audio error: {e}")

    def switch_language(self, target_lang: str):
        """切换目标语言（需要重建 session）"""
        on_result = self._callback.on_result if self._callback else None
        self.stop()
        if on_result:
            self.start(target_lang=target_lang, on_result=on_result)

    def stop(self):
        """停止"""
        with self._lock:
            self._is_running = False
            if self.conversation:
                try:
                    self.conversation.close()
                except Exception:
                    pass
                self.conversation = None
            logger.info("ASR Translator stopped")

    @property
    def is_running(self):
        return self._is_running
