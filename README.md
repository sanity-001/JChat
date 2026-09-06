# JChat

一个具备长期记忆与工作能力的 Windows 桌面"搭子"（companion）。

- **UI**：PySide6（Qt6）——搭子主窗口（透明置顶 + **Live2D** 模型渲染 + 悬停输入/气泡 + 点击/连击/视线/拖拽交互）+ 聊天大窗（对话详情）
- **记忆**：合并自 MemoKG 的长期记忆层（三层记忆 + 知识图谱 + 混合检索 + RRF）
- **Agent**：标准 tool-calling 循环（上限 5 次迭代），6 个工具（run_python / read_file / write_file / list_files / web_fetch / remember）
- **LLM**：OpenAI 兼容（默认 DeepSeek V4 Flash Vision Exp，任意兼容端点可换）

## 运行

```bash
uv sync                 # 安装依赖（需 Python 3.10+）
uv run python -m JChat  # 启动
```

首次启动会生成 `config.json`（默认配置）；API key 请写入 `config.private.json`（git 忽略）。

> 免责：本工具在本地运行、无沙箱，`run_python` 可访问本地文件与网络。仅供个人学习使用。

## 设计

完整决策集见 [`wayfinder/map.md`](wayfinder/map.md)（wayfinder 路线图，9 张票据全部关闭）。
域词汇表见 [`CONTEXT.md`](CONTEXT.md)。
