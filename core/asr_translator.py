"""
百炼 LiveTranslate ASR 引擎
基于 qwen3-livetranslate-flash-realtime 模型
使用原生 WebSocket 调用（官方推荐方式）
"""

import os
import json
import base64
import logging
import threading
from dataclasses import dataclass
from typing import Callable, Optional

import websocket

logger = logging.getLogger(__name__)


@dataclass
class TranslationResult:
    """翻译结果"""
    source_text: str       # 原文
    translated_text: str   # 译文
    source_lang: str       # 源语言
    target_lang: str       # 目标语言
    is_final: bool         # 是否为最终结果（句子结束）


class ASRTranslator:
    """
    百炼 LiveTranslate ASR+翻译引擎
    使用 qwen3-livetranslate-flash-realtime 模型
    原生 WebSocket 实现
    """

    def __init__(self, config: dict):
        self.config = config
        self.ws: Optional[websocket.WebSocketApp] = None
        self._is_running = False
        self._lock = threading.Lock()
        self._ws_thread: Optional[threading.Thread] = None
        self._on_result: Optional[Callable] = None
        self._target_lang = "en"
        self._session_id = None

        # API Key
        api_key = config.get("dashscope", {}).get("api_key", "")
        if not api_key:
            api_key = os.environ.get("DASHSCOPE_API_KEY", "")
        if not api_key:
            raise ValueError("No API Key. Set DASHSCOPE_API_KEY or config.dashscope.api_key")
        self._api_key = api_key

    def _build_url(self):
        """构建 WebSocket URL"""
        model = self.config.get("model", {}).get("name", "qwen3-livetranslate-flash-realtime")
        base_url = self.config.get("dashscope", {}).get(
            "websocket_url", "wss://dashscope.aliyuncs.com/api-ws/v1/realtime"
        )
        return f"{base_url}?model={model}"

    def start(self, target_lang: str, on_result: Callable[[TranslationResult], None]):
        """启动 ASR + 翻译"""
        with self._lock:
            if self._is_running:
                logger.warning("ASR Translator already running")
                return

            self._target_lang = target_lang
            self._on_result = on_result
            self._is_running = True

        url = self._build_url()
        headers = [f"Authorization: Bearer {self._api_key}"]

        self.ws = websocket.WebSocketApp(
            url,
            header=headers,
            on_open=self._on_open,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close,
        )

        self._ws_thread = threading.Thread(target=self._run_ws, daemon=True)
        self._ws_thread.start()
        logger.info(f"ASR Translator starting (target_lang={target_lang})")

    def _run_ws(self):
        """运行 WebSocket 事件循环"""
        try:
            self.ws.run_forever()
        except Exception as e:
            logger.error(f"WebSocket run error: {e}")
        finally:
            self._is_running = False

    def _on_open(self, ws):
        """WebSocket 连接建立"""
        logger.info("LiveTranslate WebSocket connected")

        # 发送 session.update 配置翻译参数
        audio_config = self.config.get("audio", {})
        model_config = self.config.get("model", {})

        update_event = {
            "event_id": "evt_update_session",
            "type": "session.update",
            "session": {
                "modalities": ["text"],
                "input_audio_format": "pcm16",
                "input_audio_transcription": {
                    "model": "qwen3-asr-flash-realtime",
                },
                "translation": {
                    "language": self._target_lang,
                },
            }
        }
        ws.send(json.dumps(update_event))
        logger.info(f"Session update sent (target={self._target_lang})")

    def _on_message(self, ws, message):
        """处理服务端消息"""
        try:
            data = json.loads(message)
            event_type = data.get("type", "")

            if event_type == "session.created":
                self._session_id = data.get("session", {}).get("id", "")
                logger.info(f"Session created: {self._session_id}")

            elif event_type == "session.updated":
                logger.info("Session updated successfully")

            elif event_type == "input_audio_buffer.speech_started":
                logger.debug("Speech started")

            elif event_type == "input_audio_buffer.speech_stopped":
                logger.debug("Speech stopped")

            elif event_type == "conversation.item.input_audio_transcription.text":
                # 原文中间识别结果（流式）
                stash = data.get("stash", "")
                if stash and self._on_result:
                    self._on_result(TranslationResult(
                        source_text=stash,
                        translated_text="",
                        source_lang="auto",
                        target_lang=self._target_lang,
                        is_final=False,
                    ))

            elif event_type == "conversation.item.input_audio_transcription.completed":
                # 原文最终识别结果
                transcript = data.get("transcript", "")
                if transcript and self._on_result:
                    self._on_result(TranslationResult(
                        source_text=transcript,
                        translated_text="",
                        source_lang="auto",
                        target_lang=self._target_lang,
                        is_final=True,
                    ))

            elif event_type == "response.text.done":
                # 翻译最终结果
                text = data.get("text", "")
                if text and self._on_result:
                    self._on_result(TranslationResult(
                        source_text="",
                        translated_text=text,
                        source_lang="auto",
                        target_lang=self._target_lang,
                        is_final=True,
                    ))

            elif event_type == "response.text.delta":
                # 翻译中间结果（流式）
                delta = data.get("delta", "")
                if delta and self._on_result:
                    self._on_result(TranslationResult(
                        source_text="",
                        translated_text=delta,
                        source_lang="auto",
                        target_lang=self._target_lang,
                        is_final=False,
                    ))

            elif event_type == "error":
                error_msg = data.get("error", {}).get("message", str(data))
                logger.error(f"Server error: {error_msg}")

        except Exception as e:
            logger.error(f"Message parse error: {e}")

    def _on_error(self, ws, error):
        """WebSocket 错误"""
        logger.error(f"WebSocket error: {error}")

    def _on_close(self, ws, close_status_code, close_msg):
        """WebSocket 关闭"""
        logger.info(f"WebSocket closed: code={close_status_code}, msg={close_msg}")
        self._is_running = False

    def send_audio(self, audio_data: bytes):
        """发送音频数据（PCM bytes → base64）"""
        if self._is_running and self.ws and self.ws.sock and self.ws.sock.connected:
            try:
                audio_b64 = base64.b64encode(audio_data).decode("utf-8")
                event = {
                    "type": "input_audio_buffer.append",
                    "audio": audio_b64,
                }
                self.ws.send(json.dumps(event))
            except Exception as e:
                logger.error(f"Send audio error: {e}")

    def switch_language(self, target_lang: str):
        """切换目标语言（重建连接）"""
        on_result = self._on_result
        self.stop()
        if on_result:
            self.start(target_lang=target_lang, on_result=on_result)

    def stop(self):
        """停止"""
        with self._lock:
            self._is_running = False
            if self.ws:
                try:
                    self.ws.close()
                except Exception:
                    pass
                self.ws = None
            logger.info("ASR Translator stopped")

    @property
    def is_running(self):
        return self._is_running
