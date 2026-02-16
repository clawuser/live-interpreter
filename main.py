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


def load_config(path="config.yaml"):
    """加载配置文件"""
    if not os.path.exists(path):
        logger.error(f"Config file not found: {path}")
        sys.exit(1)

    with open(path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    # 优先使用环境变量中的 API Key
    if not config.get("dashscope", {}).get("api_key") and os.environ.get("DASHSCOPE_API_KEY"):
        config.setdefault("dashscope", {})["api_key"] = os.environ["DASHSCOPE_API_KEY"]

    return config


def main():
    from PyQt6.QtWidgets import QApplication
    from ui.main_window import MainWindow

    # 加载配置
    config = load_config()

    # 检查 API Key
    api_key = config.get("dashscope", {}).get("api_key", "")
    if not api_key:
        logger.error("请设置百炼 API Key:")
        logger.error("  方式1: 编辑 config.yaml 中的 dashscope.api_key")
        logger.error("  方式2: 设置环境变量 export DASHSCOPE_API_KEY=sk-xxx")
        sys.exit(1)

    # 启动 Qt 应用
    app = QApplication(sys.argv)
    app.setApplicationName("Live Interpreter")

    window = MainWindow(config)
    window.show()

    logger.info("Live Interpreter started")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
