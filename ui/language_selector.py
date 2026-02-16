"""
语言选择器组件
"""

from PyQt6.QtWidgets import QWidget, QHBoxLayout, QComboBox, QLabel, QPushButton
from PyQt6.QtCore import pyqtSignal


class LanguageSelector(QWidget):
    """语言选择器：源语言 → 目标语言"""

    language_changed = pyqtSignal(str, str)  # (source_lang, target_lang)

    LANGUAGES = [
        ("auto", "🌐 自动检测"),
        ("zh", "🇨🇳 中文"),
        ("en", "🇺🇸 English"),
        ("ja", "🇯🇵 日本語"),
        ("ko", "🇰🇷 한국어"),
        ("fr", "🇫🇷 Français"),
        ("de", "🇩🇪 Deutsch"),
        ("es", "🇪🇸 Español"),
    ]

    TARGET_LANGUAGES = [lang for lang in LANGUAGES if lang[0] != "auto"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # 源语言
        self.source_combo = QComboBox()
        for code, name in self.LANGUAGES:
            self.source_combo.addItem(name, code)
        self.source_combo.setCurrentIndex(0)  # 默认自动检测

        # 交换按钮
        self.swap_btn = QPushButton("⇄")
        self.swap_btn.setFixedWidth(40)
        self.swap_btn.setToolTip("交换语言")
        self.swap_btn.clicked.connect(self._swap_languages)

        # 目标语言
        self.target_combo = QComboBox()
        for code, name in self.TARGET_LANGUAGES:
            self.target_combo.addItem(name, code)
        self.target_combo.setCurrentIndex(1)  # 默认 English

        # 布局
        layout.addWidget(QLabel("源语言:"))
        layout.addWidget(self.source_combo)
        layout.addWidget(self.swap_btn)
        layout.addWidget(QLabel("目标语言:"))
        layout.addWidget(self.target_combo)

        # 信号连接
        self.source_combo.currentIndexChanged.connect(self._on_change)
        self.target_combo.currentIndexChanged.connect(self._on_change)

    def _swap_languages(self):
        """交换源语言和目标语言"""
        source = self.source_combo.currentData()
        target = self.target_combo.currentData()

        if source == "auto":
            return  # 自动检测不能交换

        # 在 source combo 中找 target
        for i in range(self.source_combo.count()):
            if self.source_combo.itemData(i) == target:
                self.source_combo.setCurrentIndex(i)
                break

        # 在 target combo 中找 source
        for i in range(self.target_combo.count()):
            if self.target_combo.itemData(i) == source:
                self.target_combo.setCurrentIndex(i)
                break

    def _on_change(self):
        source = self.source_combo.currentData()
        target = self.target_combo.currentData()
        self.language_changed.emit(source, target)

    def get_source_lang(self) -> str:
        return self.source_combo.currentData()

    def get_target_lang(self) -> str:
        return self.target_combo.currentData()
