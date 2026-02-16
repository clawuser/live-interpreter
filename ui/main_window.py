"""
主窗口 - 同声传译 UI
左栏原文 + 右栏译文 + 设置入口
"""

import sys
import yaml
import logging
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTextEdit, QLabel, QPushButton, QComboBox,
    QSplitter, QStatusBar, QGroupBox, QSystemTrayIcon, QMenu
)
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot, QTimer
from PyQt6.QtGui import QFont, QColor, QTextCursor, QIcon, QAction

from ui.language_selector import LanguageSelector
from ui.settings_dialog import SettingsDialog
from core.interpreter import Interpreter, ChannelConfig
from core.asr_translator import TranslationResult
from core.audio_capture import AudioCapture

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """同声传译主窗口"""

    # 线程安全的信号
    result_signal = pyqtSignal(str, object)  # (channel_name, TranslationResult)

    def __init__(self, config: dict):
        super().__init__()
        self.config = config
        self.interpreter = Interpreter(config)
        self._is_interpreting = False

        self._init_ui()
        self._connect_signals()
        self._load_devices()

    def _init_ui(self):
        ui_config = self.config.get("ui", {})
        self.setWindowTitle("🎙️ Live Interpreter - 同声传译")
        self.resize(
            ui_config.get("window_width", 900),
            ui_config.get("window_height", 600)
        )

        if ui_config.get("always_on_top", False):
            self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)

        # 中心布局
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)

        # === 顶部：语言选择 + 设备选择 + 设置 ===
        top_layout = QHBoxLayout()

        # 语言选择器
        self.lang_selector = LanguageSelector()
        top_layout.addWidget(self.lang_selector)

        top_layout.addStretch()

        # 音频设备选择
        top_layout.addWidget(QLabel("音频源:"))
        self.device_combo = QComboBox()
        self.device_combo.setMinimumWidth(200)
        top_layout.addWidget(self.device_combo)

        # 设置按钮
        self.settings_btn = QPushButton("⚙️ 设置")
        self.settings_btn.setFixedHeight(32)
        self.settings_btn.setStyleSheet("""
            QPushButton {
                background-color: #9E9E9E;
                color: white;
                font-size: 13px;
                border-radius: 6px;
                padding: 0 14px;
            }
            QPushButton:hover { background-color: #757575; }
        """)
        top_layout.addWidget(self.settings_btn)

        main_layout.addLayout(top_layout)

        # === 中部：双栏显示 ===
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # 左栏 - 原文
        left_group = QGroupBox("📝 原文 (Source)")
        left_layout = QVBoxLayout(left_group)
        self.source_text = QTextEdit()
        self.source_text.setReadOnly(True)
        self.source_text.setFont(QFont("Microsoft YaHei", ui_config.get("font_size", 14)))
        left_layout.addWidget(self.source_text)
        splitter.addWidget(left_group)

        # 右栏 - 译文
        right_group = QGroupBox("🌍 译文 (Translation)")
        right_layout = QVBoxLayout(right_group)
        self.translated_text = QTextEdit()
        self.translated_text.setReadOnly(True)
        self.translated_text.setFont(QFont("Microsoft YaHei", ui_config.get("font_size", 14)))
        right_layout.addWidget(self.translated_text)
        splitter.addWidget(right_group)

        main_layout.addWidget(splitter)

        # === 底部：控制按钮 ===
        bottom_layout = QHBoxLayout()

        self.start_btn = QPushButton("▶️ 开始同传")
        self.start_btn.setFixedHeight(40)
        self.start_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                font-size: 16px;
                border-radius: 8px;
                padding: 0 20px;
            }
            QPushButton:hover { background-color: #45a049; }
        """)
        bottom_layout.addWidget(self.start_btn)

        self.stop_btn = QPushButton("⏹️ 停止")
        self.stop_btn.setFixedHeight(40)
        self.stop_btn.setEnabled(False)
        self.stop_btn.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                font-size: 16px;
                border-radius: 8px;
                padding: 0 20px;
            }
            QPushButton:hover { background-color: #da190b; }
        """)
        bottom_layout.addWidget(self.stop_btn)

        self.clear_btn = QPushButton("🗑️ 清空")
        self.clear_btn.setFixedHeight(40)
        self.clear_btn.setStyleSheet("""
            QPushButton {
                background-color: #607D8B;
                color: white;
                font-size: 16px;
                border-radius: 8px;
                padding: 0 20px;
            }
        """)
        bottom_layout.addWidget(self.clear_btn)

        main_layout.addLayout(bottom_layout)

        # 状态栏
        self.statusBar().showMessage("就绪 - 选择音频源并点击开始")

    def _connect_signals(self):
        """连接信号"""
        self.start_btn.clicked.connect(self._on_start)
        self.stop_btn.clicked.connect(self._on_stop)
        self.clear_btn.clicked.connect(self._on_clear)
        self.settings_btn.clicked.connect(self._on_settings)
        self.lang_selector.language_changed.connect(self._on_language_changed)
        self.result_signal.connect(self._on_result)

    def _load_devices(self):
        """加载音频设备列表"""
        try:
            ac = AudioCapture()
            devices = ac.list_input_devices()
            self.device_combo.clear()
            self.device_combo.addItem("🎤 默认麦克风", None)
            for d in devices:
                icon = "🔊" if d.get("is_loopback") else "🎤"
                self.device_combo.addItem(f"{icon} {d['name']}", d["index"])
        except Exception as e:
            logger.error(f"Failed to load devices: {e}")
            self.device_combo.addItem("🎤 默认麦克风", None)

    def _on_settings(self):
        """打开设置对话框"""
        dialog = SettingsDialog(self.config, parent=self)
        if dialog.exec():
            # 设置保存成功，更新配置
            new_config = dialog.get_config()
            self.config.update(new_config)

            # 应用 UI 设置
            ui_config = new_config.get("ui", {})
            font_size = ui_config.get("font_size", 14)
            self.source_text.setFont(QFont("Microsoft YaHei", font_size))
            self.translated_text.setFont(QFont("Microsoft YaHei", font_size))

            if ui_config.get("always_on_top", False):
                self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
            else:
                self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowStaysOnTopHint)
            self.show()  # 需要重新 show

            opacity = ui_config.get("opacity", 0.95)
            self.setWindowOpacity(opacity)

            self.statusBar().showMessage("✅ 设置已更新")

    def _on_start(self):
        """开始同传"""
        if self._is_interpreting:
            return

        # 检查 API Key
        api_key = self.config.get("dashscope", {}).get("api_key", "")
        if not api_key:
            import os
            api_key = os.environ.get("DASHSCOPE_API_KEY", "")
        if not api_key:
            self.statusBar().showMessage("❌ 请先在设置中配置百炼 API Key")
            self._on_settings()
            return

        target_lang = self.lang_selector.get_target_lang()
        device_index = self.device_combo.currentData()

        # 添加通道
        self.interpreter = Interpreter(self.config)
        self.interpreter.add_channel(ChannelConfig(
            name="main",
            device_index=device_index,
            target_lang=target_lang
        ))

        # 设置回调
        self.interpreter.set_result_callback(
            lambda ch, result: self.result_signal.emit(ch, result)
        )

        try:
            self.interpreter.start()
            self._is_interpreting = True
            self.start_btn.setEnabled(False)
            self.stop_btn.setEnabled(True)
            self.settings_btn.setEnabled(False)  # 同传中禁用设置
            self.statusBar().showMessage(f"🔴 同传中... (→ {target_lang})")
        except Exception as e:
            logger.error(f"Start failed: {e}")
            self.statusBar().showMessage(f"❌ 启动失败: {e}")

    def _on_stop(self):
        """停止同传"""
        if not self._is_interpreting:
            return

        self.interpreter.stop()
        self._is_interpreting = False
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.settings_btn.setEnabled(True)
        self.statusBar().showMessage("⏹️ 已停止")

    def _on_clear(self):
        """清空文本"""
        self.source_text.clear()
        self.translated_text.clear()

    def _on_language_changed(self, source_lang, target_lang):
        """语言切换"""
        if self._is_interpreting:
            self.interpreter.switch_language("main", target_lang)
            self.statusBar().showMessage(f"🔴 同传中... (→ {target_lang})")

    @pyqtSlot(str, object)
    def _on_result(self, channel_name: str, result: TranslationResult):
        """处理翻译结果（UI线程）"""
        if result.is_final:
            if result.source_text:
                self.source_text.append(result.source_text)
            if result.translated_text:
                self.translated_text.append(result.translated_text)
        else:
            if result.source_text:
                cursor = self.source_text.textCursor()
                cursor.movePosition(QTextCursor.MoveOperation.End)
                self.source_text.setTextCursor(cursor)

        # 自动滚动
        self.source_text.verticalScrollBar().setValue(
            self.source_text.verticalScrollBar().maximum()
        )
        self.translated_text.verticalScrollBar().setValue(
            self.translated_text.verticalScrollBar().maximum()
        )

    def closeEvent(self, event):
        """窗口关闭时停止"""
        if self._is_interpreting:
            self.interpreter.stop()
        event.accept()
