# Contributing to JChat

感谢你对 JChat 的兴趣！这是一个个人色彩很强的项目，贡献前请先了解它的边界。

## 开发环境

```bash
git clone https://github.com/sanity-001/JChat.git
cd JChat
uv sync --extra voice --extra semantic --extra dev
uv run --with pytest pytest        # 测试
uv run --with ruff ruff check src  # lint（行宽 110）
uv run python -m JChat             # 启动
```

- Python 3.12 + [uv](https://docs.astral.sh/uv/)；仅支持 Windows（屏幕视觉感知依赖 win32 API）
- PySide6 锁定 6.8.3（6.11 存在已知 DLL 兼容问题，勿升级）

## 项目约定

- **术语**：叫"搭子/伙伴"，禁用"桌宠"；词汇表见 `CONTEXT.md`
- **配置**：公开配置进 `config.json`，机密只进 `config.private.json`（git 忽略）；新增配置键必须同步 `config.py` 的 `DEFAULT_CONFIG` 与 `_sanitize` 类型表
- **线程纪律**：主线程只做 UI；一切 LLM/工具/音频合成走 `LLMQueue` 单 worker；worker/键盘钩子/音频回调回到 UI 一律 `ui_task.emit(闭包)`
- **接缝**：加工具 = `tools.py` 一个 `@tool` 函数；加输入源 = 实现 `send_requested` 信号 + `attach_input`；加游戏 = 实现 Board + `GAMES` 注册；加 TTS provider = 同接口函数。不要在主流程里写 if-else 扩展点

## 提交流程

1. Fork → 分支（`feat/xxx`）
2. 改动必须通过 `ruff check` 与 `pytest`
3. 提交信息用中文简述改动（一行）
4. PR 描述清楚：动机 / 改动点 / 验证方式

## 不接受的方向

- 引入 torch 系大依赖（桌面产品体积红线，见 `docs/adr/`）
- 云端遥测 / 数据外发（隐私是核心卖点，记忆全在本地 sqlite）
- 修改内置同人素材或移除其授权声明

## 语音相关

- STT：sherpa-onnx + SenseVoice（模型首次运行自动下载至 `%LOCALAPPDATA%\JChat\models`）
- TTS：GPT-SoVITS `api_v2`（用户自备参考音频并启动其 api 服务）/ EdgeTTS 兜底
- 涉及 onnxruntime 时注意 Windows DLL 版本冲突（见 `src/JChat/voice/asr.py` 的预加载注释）

## License

提交即表示你同意贡献内容以 [GPL-3.0](LICENSE) 授权。
