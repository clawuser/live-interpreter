"""
Live Interpreter - 同声传译
基于阿里云百炼 qwen3-livetranslate-flash-realtime 模型
"""

import sys
import os
import yaml
import logging

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("live-interpreter.log", encoding="utf-8")
    ]
)
logger = logging.getLogger(__name__)


def load_config():
    """加载配置：config.yaml (默认) + user_settings.yaml (用户覆盖)"""
    config = {}

    # 1. 加载默认配置
    if os.path.exists("config.yaml"):
        with open("config.yaml", "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}

    # 2. 加载用户设置（覆盖默认）
    if os.path.exists("user_settings.yaml"):
        with open("user_settings.yaml", "r", encoding="utf-8") as f:
            user = yaml.safe_load(f) or {}
        _deep_merge(config, user)

    # 3. 环境变量兜底
    if not config.get("dashscope", {}).get("api_key") and os.environ.get("DASHSCOPE_API_KEY"):
        config.setdefault("dashscope", {})["api_key"] = os.environ["DASHSCOPE_API_KEY"]

    return config


def _deep_merge(base: dict, override: dict):
    """深度合并配置"""
    for k, v in override.items():
        if k in base and isinstance(base[k], dict) and isinstance(v, dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v


def main():
    from PyQt6.QtWidgets import QApplication
    from ui.main_window import MainWindow

    config = load_config()

    app = QApplication(sys.argv)
    app.setApplicationName("Live Interpreter")

    window = MainWindow(config)
    window.show()

    logger.info("Live Interpreter started")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
