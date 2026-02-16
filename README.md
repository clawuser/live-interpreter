# 🎙️ Live Interpreter - 同声传译

基于阿里云百炼 `qwen3-livetranslate-flash-realtime` 模型的实时同声传译工具。

## ✨ 特性

- 🎯 **一步到位**：ASR语音识别 + 翻译同时完成，延迟极低
- 🌐 **多语言**：中/英/日/韩/法/德/西，自动检测源语言
- 🎤 **双路音频**：支持麦克风 + 系统音频（WASAPI Loopback）
- 💻 **简洁UI**：左栏原文 + 右栏译文，实时滚动显示
- ⚡ **快速切换**：运行中可实时切换目标语言

## 🚀 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置 API Key

方式一：编辑 `config.yaml`
```yaml
dashscope:
  api_key: "sk-your-api-key"
```

方式二：设置环境变量
```bash
export DASHSCOPE_API_KEY=sk-your-api-key
```

### 3. 运行

```bash
python main.py
```

## 📐 架构

```
麦克风 ──→ WebSocket Session ──→ 原文识别 | 实时翻译
                                     ↓          ↓
                                 左栏显示    右栏显示
```

核心模型：`qwen3-livetranslate-flash-realtime`
- 输入：实时音频流
- 输出：源语言文字 + 目标语言翻译
- 特点：一个 WebSocket 连接同时完成 ASR + 翻译

## 📁 项目结构

```
live-interpreter/
├── main.py                 # 入口
├── config.yaml             # 配置文件
├── core/
│   ├── interpreter.py      # 核心调度器
│   ├── asr_translator.py   # 百炼 LiveTranslate 引擎
│   └── audio_capture.py    # 音频采集
├── ui/
│   ├── main_window.py      # 主窗口
│   └── language_selector.py # 语言选择器
├── requirements.txt
└── README.md
```

## 🔧 配置说明

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `dashscope.api_key` | 百炼 API Key | - |
| `languages.default_target` | 默认目标语言 | `en` |
| `audio.sample_rate` | 采样率 | `16000` |
| `model.vad_silence_duration_ms` | VAD静音断句阈值 | `400` |
| `ui.always_on_top` | 窗口置顶 | `false` |

## 📝 License

MIT
