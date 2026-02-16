"""
设置对话框
配置 AI 模型、API Key、音频参数等
"""

import os
import yaml
import logging
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox,
    QCheckBox, QPushButton, QTabWidget, QWidget,
    QLabel, QGroupBox, QMessageBox, QFileDialog
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

logger = logging.getLogger(__name__)

# 默认配置路径
CONFIG_PATH = "config.yaml"
USER_SETTINGS_PATH = "user_settings.yaml"


class SettingsDialog(QDialog):
    """设置对话框"""

    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        self.config = config
        self._init_ui()
        self._load_from_config()

    def _init_ui(self):
        self.setWindowTitle("⚙️ 设置")
        self.setMinimumSize(550, 480)
        layout = QVBoxLayout(self)

        # Tab 页
        tabs = QTabWidget()

        # === Tab 1: AI 模型 ===
        model_tab = QWidget()
        model_layout = QVBoxLayout(model_tab)

        # API Key
        api_group = QGroupBox("🔑 百炼 API 配置")
        api_form = QFormLayout(api_group)

        self.api_key_edit = QLineEdit()
        self.api_key_edit.setPlaceholderText("sk-xxxxxxxx 或设置环境变量 DASHSCOPE_API_KEY")
        self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        api_form.addRow("API Key:", self.api_key_edit)

        self.show_key_btn = QPushButton("👁 显示")
        self.show_key_btn.setCheckable(True)
        self.show_key_btn.setFixedWidth(60)
        self.show_key_btn.toggled.connect(self._toggle_key_visibility)
        api_form.addRow("", self.show_key_btn)

        self.ws_url_edit = QLineEdit()
        self.ws_url_edit.setPlaceholderText("wss://dashscope.aliyuncs.com/api-ws/v1/realtime")
        api_form.addRow("WebSocket URL:", self.ws_url_edit)

        model_layout.addWidget(api_group)

        # 模型选择
        model_group = QGroupBox("🤖 模型配置")
        model_form = QFormLayout(model_group)

        self.model_combo = QComboBox()
        self.model_combo.setEditable(True)
        self.model_combo.addItems([
            "qwen3-livetranslate-flash-realtime",
            "qwen3-livetranslate-realtime",
        ])
        model_form.addRow("ASR+翻译模型:", self.model_combo)

        model_layout.addWidget(model_group)

        # VAD 设置
        vad_group = QGroupBox("🎙️ VAD 语音检测")
        vad_form = QFormLayout(vad_group)

        self.vad_enabled = QCheckBox("启用服务端 VAD")
        self.vad_enabled.setChecked(True)
        vad_form.addRow("", self.vad_enabled)

        self.vad_threshold = QDoubleSpinBox()
        self.vad_threshold.setRange(-1.0, 1.0)
        self.vad_threshold.setSingleStep(0.1)
        self.vad_threshold.setValue(0.0)
        self.vad_threshold.setToolTip("越低越灵敏，可能误触；越高越稳，可能漏检")
        vad_form.addRow("检测阈值:", self.vad_threshold)

        self.vad_silence = QSpinBox()
        self.vad_silence.setRange(200, 6000)
        self.vad_silence.setSingleStep(100)
        self.vad_silence.setValue(400)
        self.vad_silence.setSuffix(" ms")
        self.vad_silence.setToolTip("静音多久算断句，越小响应越快但可能断句不自然")
        vad_form.addRow("断句静音时长:", self.vad_silence)

        model_layout.addWidget(vad_group)
        model_layout.addStretch()
        tabs.addTab(model_tab, "🤖 AI 模型")

        # === Tab 2: 音频 ===
        audio_tab = QWidget()
        audio_layout = QVBoxLayout(audio_tab)

        audio_group = QGroupBox("🔊 音频参数")
        audio_form = QFormLayout(audio_group)

        self.sample_rate_combo = QComboBox()
        self.sample_rate_combo.addItem("16000 Hz (推荐)", 16000)
        self.sample_rate_combo.addItem("8000 Hz (电话)", 8000)
        audio_form.addRow("采样率:", self.sample_rate_combo)

        self.audio_format_combo = QComboBox()
        self.audio_format_combo.addItems(["pcm", "wav", "opus", "mp3"])
        audio_form.addRow("音频格式:", self.audio_format_combo)

        self.block_size_spin = QSpinBox()
        self.block_size_spin.setRange(1600, 16000)
        self.block_size_spin.setSingleStep(1600)
        self.block_size_spin.setValue(3200)
        self.block_size_spin.setToolTip("每次发送的帧数，3200≈100ms")
        audio_form.addRow("缓冲帧数:", self.block_size_spin)

        audio_layout.addWidget(audio_group)
        audio_layout.addStretch()
        tabs.addTab(audio_tab, "🔊 音频")

        # === Tab 3: 界面 ===
        ui_tab = QWidget()
        ui_layout = QVBoxLayout(ui_tab)

        ui_group = QGroupBox("💻 界面设置")
        ui_form = QFormLayout(ui_group)

        self.font_size_spin = QSpinBox()
        self.font_size_spin.setRange(10, 30)
        self.font_size_spin.setValue(14)
        ui_form.addRow("字体大小:", self.font_size_spin)

        self.always_on_top_cb = QCheckBox("窗口置顶")
        ui_form.addRow("", self.always_on_top_cb)

        self.opacity_spin = QDoubleSpinBox()
        self.opacity_spin.setRange(0.3, 1.0)
        self.opacity_spin.setSingleStep(0.05)
        self.opacity_spin.setValue(0.95)
        ui_form.addRow("窗口透明度:", self.opacity_spin)

        ui_layout.addWidget(ui_group)
        ui_layout.addStretch()
        tabs.addTab(ui_tab, "💻 界面")

        layout.addWidget(tabs)

        # === 底部按钮 ===
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.save_btn = QPushButton("💾 保存")
        self.save_btn.setFixedHeight(36)
        self.save_btn.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                font-size: 14px;
                border-radius: 6px;
                padding: 0 24px;
            }
            QPushButton:hover { background-color: #1976D2; }
        """)
        self.save_btn.clicked.connect(self._on_save)
        btn_layout.addWidget(self.save_btn)

        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.setFixedHeight(36)
        self.cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.cancel_btn)

        layout.addLayout(btn_layout)

    def _toggle_key_visibility(self, checked):
        if checked:
            self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Normal)
            self.show_key_btn.setText("🙈 隐藏")
        else:
            self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
            self.show_key_btn.setText("👁 显示")

    def _load_from_config(self):
        """从配置加载到 UI"""
        ds = self.config.get("dashscope", {})
        self.api_key_edit.setText(ds.get("api_key", ""))
        self.ws_url_edit.setText(ds.get("websocket_url", "wss://dashscope.aliyuncs.com/api-ws/v1/realtime"))

        model = self.config.get("model", {})
        model_name = model.get("name", "qwen3-livetranslate-flash-realtime")
        idx = self.model_combo.findText(model_name)
        if idx >= 0:
            self.model_combo.setCurrentIndex(idx)
        else:
            self.model_combo.setCurrentText(model_name)

        self.vad_enabled.setChecked(model.get("vad_enabled", True))
        self.vad_threshold.setValue(model.get("vad_threshold", 0.0))
        self.vad_silence.setValue(model.get("vad_silence_duration_ms", 400))

        audio = self.config.get("audio", {})
        sr = audio.get("sample_rate", 16000)
        for i in range(self.sample_rate_combo.count()):
            if self.sample_rate_combo.itemData(i) == sr:
                self.sample_rate_combo.setCurrentIndex(i)
                break

        fmt = audio.get("format", "pcm")
        idx = self.audio_format_combo.findText(fmt)
        if idx >= 0:
            self.audio_format_combo.setCurrentIndex(idx)

        self.block_size_spin.setValue(audio.get("block_size", 3200))

        ui = self.config.get("ui", {})
        self.font_size_spin.setValue(ui.get("font_size", 14))
        self.always_on_top_cb.setChecked(ui.get("always_on_top", False))
        self.opacity_spin.setValue(ui.get("opacity", 0.95))

    def get_config(self) -> dict:
        """从 UI 收集配置"""
        return {
            "dashscope": {
                "api_key": self.api_key_edit.text().strip(),
                "websocket_url": self.ws_url_edit.text().strip() or "wss://dashscope.aliyuncs.com/api-ws/v1/realtime",
            },
            "model": {
                "name": self.model_combo.currentText().strip(),
                "vad_enabled": self.vad_enabled.isChecked(),
                "vad_threshold": self.vad_threshold.value(),
                "vad_silence_duration_ms": self.vad_silence.value(),
            },
            "audio": {
                "sample_rate": self.sample_rate_combo.currentData() or 16000,
                "channels": 1,
                "format": self.audio_format_combo.currentText(),
                "block_size": self.block_size_spin.value(),
            },
            "ui": {
                "font_size": self.font_size_spin.value(),
                "always_on_top": self.always_on_top_cb.isChecked(),
                "opacity": self.opacity_spin.value(),
                "window_width": self.config.get("ui", {}).get("window_width", 900),
                "window_height": self.config.get("ui", {}).get("window_height", 600),
            },
            "languages": self.config.get("languages", {}),
        }

    def _on_save(self):
        """保存配置"""
        new_config = self.get_config()

        # 验证 API Key
        api_key = new_config["dashscope"]["api_key"]
        if not api_key and not os.environ.get("DASHSCOPE_API_KEY"):
            QMessageBox.warning(self, "提示", "请填写百炼 API Key 或设置环境变量 DASHSCOPE_API_KEY")
            return

        # 保存到 user_settings.yaml
        try:
            with open(USER_SETTINGS_PATH, "w", encoding="utf-8") as f:
                yaml.dump(new_config, f, allow_unicode=True, default_flow_style=False)
            logger.info(f"Settings saved to {USER_SETTINGS_PATH}")
        except Exception as e:
            logger.error(f"Save settings failed: {e}")
            QMessageBox.critical(self, "错误", f"保存失败: {e}")
            return

        # 更新内存中的配置
        self.config.update(new_config)

        QMessageBox.information(self, "成功", "设置已保存！\n部分设置需要重新开始同传生效。")
        self.accept()
