# JChat

一个具备长期记忆与工作能力的 Windows 桌面"搭子"（companion）——Live2D 形象、会记住你的生活轨迹、能帮你干活的赛博伙伴。

> 特性
> - **Live2D 搭子**：透明置顶窗口，10 种表情、视线跟随、摇尾、点击分区反馈（呆毛/头/身/尾巴各有专属反应）、拖拽、主动搭话
> - **长期记忆**（融合"检索精度 × 在场感"）：
>   - 常驻【近期轨迹】带——每段滑出短期窗口的生活被压成第一人称带日期的摘要，始终在场
>   - 检索式记忆卡——滚动抽取的关于你的事实（带时间标签）按相关度注入每轮对话
>   - 知识图谱——对话中的实体关系沉淀为三元组，支持实体链接与图谱检索
>   - 主动回忆——`recall` 工具让搭子自己翻记忆；"还记得…"自动触发回忆提示
> - **Agent 能力**：标准 tool-calling 循环，7 工具（本地 Python / 文件读写 / 网页抓取 / 记忆读写）
> - **省钱设计**：记忆卡预算 800 token、优先级队列、单 worker 串行整理

## 运行

```bash
uv sync                 # 安装依赖（需 Python 3.12+，uv 管理）
uv run python -m JChat  # 启动
```

首次启动生成 `config.json`（默认配置）；API key 写入 `config.private.json`（git 忽略），默认指向 OpenAI 兼容端点（DeepSeek）。

> ⚠️ 免责：本工具在本地运行、**无沙箱**，`run_python` 可访问本地文件与网络，请自行评估风险。

## 隐私

- 所有对话、记忆、知识图谱**仅保存在本地** `jchat.sqlite`，不上传任何服务器
- 唯一外发数据是你与所选 LLM 端点之间的对话内容（由你自己配置端点与 key）

## Live2D 模型说明

仓库内置的 `assets/live2d/models/vvm` 是游戏《明日方舟》角色**维什戴尔（Wiš'adel）的同人二创模型**：

- 版权归原作《明日方舟》（鹰角网络）及同人模型原作者所有
- 仅供个人学习与娱乐使用，**禁止商用**
- 如需移除，删除 `assets/live2d/models/vvm` 目录并替换 `assets/live2d/web/index.html` 中的模型路径即可使用任意 Cubism 4/5 模型
- 渲染依赖 [pixi-live2d-display](https://github.com/guansss/pixi-live2d-display)（MIT）与 Live2D Cubism Core（Live2D Inc. 专有许可，见其官方条款）

## 开发

```bash
uv run --with pytest pytest        # 测试
uv run --with ruff ruff check src  # lint
```

- 架构与记忆系统设计见 [`docs/system.md`](docs/system.md)
- 域词汇表见 [`CONTEXT.md`](CONTEXT.md)
- Python 3.12（uv 管理）；PySide6 锁定 6.8.3（6.11 存在已知 DLL 兼容问题）

## License

[GPL-3.0](LICENSE) © 2026 JChat 作者。使用本仓库即表示你同意 Live2D Cubism Core 与内置同人模型的各自许可条款。
