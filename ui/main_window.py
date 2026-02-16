"""
主窗口 - 同声传译 UI
左栏原文 + 右栏译文 + 设置
"""

import logging
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTextEdit, QLabel, QPushButton, QComboBox,
    QSplitter, QGroupBox
)
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QFont, QTextCursor

from ui.language_selector import LanguageSelector
from ui.settings_dialog import SettingsDialog
from core.interpreter import Interpreter, ChannelConfig
from core.asr_translator import TranslationResult
from core.audio_capture import AudioCapture, SOURCE_MIC, SOURCE_SPEAKER

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """同声传译主窗口"""

    result_signal = pyqtSignal(str, object)

    def __init__(self, config: dict):
        super().__init__()
        self.config = config
        self.interpreter = None
        self._is_interpreting = False
        self._devices = []

        self._init_ui()
        self._connect_signals()
        self._load_devices()

    def _init_ui(self):
        ui_config = self.config.get("ui", {})
        self.setWindowTitle("🎙️ Live Interpreter - 同声传译")
        self.resize(ui_config.get("window_width", 900), ui_config.get("window_height", 600))

        if ui_config.get("always_on_top", False):
            self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)

        # === 顶部行1：语言 + 设置 ===
        row1 = QHBoxLayout()
        self.lang_selector = LanguageSelector()
        row1.addWidget(self.lang_selector)
        row1.addStretch()

        self.settings_btn = QPushButton("⚙️ 设置")
        self.settings_btn.setFixedHeight(32)
        self.settings_btn.setStyleSheet("""
            QPushButton { background-color: #9E9E9E; color: white; font-size: 13px; border-radius: 6px; padding: 0 14px; }
            QPushButton:hover { background-color: #757575; }
        """)
        row1.addWidget(self.settings_btn)
        main_layout.addLayout(row1)

        # === 顶部行2：音频源选择 ===
        row2 = QHBoxLayout()

        row2.addWidget(QLabel("音频源:"))
        self.source_combo = QComboBox()
        self.source_combo.addItem("🎤 麦克风", SOURCE_MIC)
        self.source_combo.addItem("🔊 扬声器 (系统音频)", SOURCE_SPEAKER)
        self.source_combo.setMinimumWidth(180)
        self.source_combo.currentIndexChanged.connect(self._on_source_changed)
        row2.addWidget(self.source_combo)

        row2.addWidget(QLabel("设备:"))
        self.device_combo = QComboBox()
        self.device_combo.setMinimumWidth(250)
        row2.addWidget(self.device_combo)

        row2.addStretch()
        main_layout.addLayout(row2)

        # === 中部：双栏 ===
        splitter = QSplitter(Qt.Orientation.Horizontal)
        font_size = ui_config.get("font_size", 14)

        left_group = QGroupBox("📝 原文 (Source)")
        left_layout = QVBoxLayout(left_group)
        self.source_text = QTextEdit()
        self.source_text.setReadOnly(True)
        self.source_text.setFont(QFont("Microsoft YaHei", font_size))
        left_layout.addWidget(self.source_text)
        splitter.addWidget(left_group)

        right_group = QGroupBox("🌍 译文 (Translation)")
        right_layout = QVBoxLayout(right_group)
        self.translated_text = QTextEdit()
        self.translated_text.setReadOnly(True)
        self.translated_text.setFont(QFont("Microsoft YaHei", font_size))
        right_layout.addWidget(self.translated_text)
        splitter.addWidget(right_group)

        main_layout.addWidget(splitter)

        # === 底部按钮 ===
        bottom = QHBoxLayout()

        self.start_btn = QPushButton("▶️ 开始同传")
        self.start_btn.setFixedHeight(40)
        self.start_btn.setStyleSheet("""
            QPushButton { background-color: #4CAF50; color: white; font-size: 16px; border-radius: 8px; padding: 0 20px; }
            QPushButton:hover { background-color: #45a049; }
        """)
        bottom.addWidget(self.start_btn)

        self.stop_btn = QPushButton("⏹️ 停止")
        self.stop_btn.setFixedHeight(40)
        self.stop_btn.setEnabled(False)
        self.stop_btn.setStyleSheet("""
            QPushButton { background-color: #f44336; color: white; font-size: 16px; border-radius: 8px; padding: 0 20px; }
            QPushButton:hover { background-color: #da190b; }
        """)
        bottom.addWidget(self.stop_btn)

        self.clear_btn = QPushButton("🗑️ 清空")
        self.clear_btn.setFixedHeight(40)
        self.clear_btn.setStyleSheet("""
            QPushButton { background-color: #607D8B; color: white; font-size: 16px; border-radius: 8px; padding: 0 20px; }
        """)
        bottom.addWidget(self.clear_btn)

        main_layout.addLayout(bottom)
        self.statusBar().showMessage("就绪 - 选择音频源并点击开始")

    def _connect_signals(self):
        self.start_btn.clicked.connect(self._on_start)
        self.stop_btn.clicked.connect(self._on_stop)
        self.clear_btn.clicked.connect(self._on_clear)
        self.settings_btn.clicked.connect(self._on_settings)
        self.lang_selector.language_changed.connect(self._on_language_changed)
        self.result_signal.connect(self._on_result)

    def _load_devices(self):
        """加载设备列表"""
        try:
            self._devices = AudioCapture.list_devices()
        except Exception as e:
            logger.error(f"Failed to list devices: {e}")
            self._devices = []
        self._refresh_device_combo()

    def _on_source_changed(self):
        """音频源类型切换时刷新设备列表"""
        self._refresh_device_combo()

    def _refresh_device_combo(self):
        """根据当前音频源类型刷新设备下拉框"""
        source_type = self.source_combo.currentData()
        self.device_combo.clear()

        if source_type == SOURCE_MIC:
            self.device_combo.addItem("🎤 默认麦克风", None)
            for d in self._devices:
                if not d.get('is_loopback'):
                    self.device_combo.addItem(f"🎤 {d['name']}", d['index'])
        else:
            self.device_combo.addItem("🔊 默认扬声器", None)
            for d in self._devices:
                if d.get('is_loopback'):
                    self.device_combo.addItem(f"🔊 {d['name']}", d['index'])

    def _on_settings(self):
        dialog = SettingsDialog(self.config, parent=self)
        if dialog.exec():
            new_config = dialog.get_config()
            self.config.update(new_config)

            ui_config = new_config.get("ui", {})
            font_size = ui_config.get("font_size", 14)
            self.source_text.setFont(QFont("Microsoft YaHei", font_size))
            self.translated_text.setFont(QFont("Microsoft YaHei", font_size))

            if ui_config.get("always_on_top", False):
                self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
            else:
                self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowStaysOnTopHint)
            self.show()
            self.setWindowOpacity(ui_config.get("opacity", 0.95))
            self.statusBar().showMessage("✅ 设置已更新")

    def _on_start(self):
        if self._is_interpreting:
            return

        # 检查 API Key
        import os
        api_key = self.config.get("dashscope", {}).get("api_key", "") or os.environ.get("DASHSCOPE_API_KEY", "")
        if not api_key:
            self.statusBar().showMessage("❌ 请先在设置中配置百炼 API Key")
            self._on_settings()
            return

        source_type = self.source_combo.currentData()
        device_index = self.device_combo.currentData()
        target_lang = self.lang_selector.get_target_lang()

        self.interpreter = Interpreter(self.config)
        self.interpreter.add_channel(ChannelConfig(
            name="main",
            target_lang=target_lang,
            source_type=source_type,
            device_index=device_index,
        ))
        self.interpreter.set_result_callback(
            lambda ch, result: self.result_signal.emit(ch, result)
        )

        try:
            self.interpreter.start()
            self._is_interpreting = True
            self.start_btn.setEnabled(False)
            self.stop_btn.setEnabled(True)
            self.settings_btn.setEnabled(False)
            self.source_combo.setEnabled(False)
            self.device_combo.setEnabled(False)
            source_name = "🎤 麦克风" if source_type == SOURCE_MIC else "🔊 扬声器"
            self.statusBar().showMessage(f"🔴 同传中... ({source_name} → {target_lang})")
        except Exception as e:
            logger.error(f"Start failed: {e}")
            self.statusBar().showMessage(f"❌ 启动失败: {e}")

    def _on_stop(self):
        if not self._is_interpreting:
            return
        self.interpreter.stop()
        self._is_interpreting = False
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.settings_btn.setEnabled(True)
        self.source_combo.setEnabled(True)
        self.device_combo.setEnabled(True)
        self.statusBar().showMessage("⏹️ 已停止")

    def _on_clear(self):
        self.source_text.clear()
        self.translated_text.clear()

    def _on_language_changed(self, source_lang, target_lang):
        if self._is_interpreting and self.interpreter:
            self.interpreter.switch_language("main", target_lang)
            self.statusBar().showMessage(f"🔴 同传中... (→ {target_lang})")

    @pyqtSlot(str, object)
    def _on_result(self, channel_name: str, result: TranslationResult):
        if result.is_final:
            if result.source_text:
                self.source_text.append(result.source_text)
            if result.translated_text:
                self.translated_text.append(result.translated_text)
        else:
            if result.source_text:
                cursor = self.source_text.textCursor()
                cursor.movePosition(QTextCursor.MoveOperation.End)
                cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock, QTextCursor.MoveMode.KeepAnchor)
                cursor.removeSelectedText()
                cursor.insertText(f"💬 {result.source_text}")
                self.source_text.setTextCursor(cursor)
            if result.translated_text:
                cursor = self.translated_text.textCursor()
                cursor.movePosition(QTextCursor.MoveOperation.End)
                cursor.insertText(result.translated_text)
                self.translated_text.setTextCursor(cursor)

        self.source_text.verticalScrollBar().setValue(self.source_text.verticalScrollBar().maximum())
        self.translated_text.verticalScrollBar().setValue(self.translated_text.verticalScrollBar().maximum())

    def closeEvent(self, event):
        if self._is_interpreting and self.interpreter:
            self.interpreter.stop()
        event.accept()
