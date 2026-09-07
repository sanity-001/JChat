# JChat

一个具备长期记忆与工作能力的 Windows 桌面"搭子"（companion）——Q 版精灵形象、会记住你的生活轨迹、能帮你看屏幕干活陪你下棋的赛博伙伴。

> 特性
> - **Q 版精灵搭子**：透明置顶窗口，10 种表情、待机眨眼、说话口型、点击分区反馈（呆毛/头/身/尾巴各有专属反应）、拖拽跑动、主动搭话、一起玩五子棋
> - **长期记忆**（融合"检索精度 × 在场感"）：
>   - 常驻【近期轨迹】带——每段滑出短期窗口的生活被压成第一人称带日期的摘要，始终在场
>   - 检索式记忆卡——滚动抽取的关于你的事实（带时间标签）按相关度注入每轮对话
>   - 知识图谱——对话中的实体关系沉淀为三元组，支持实体链接与图谱检索
>   - 主动回忆——`recall` 工具让搭子自己翻记忆；"还记得…"自动触发回忆提示
> - **Agent 能力**：标准 tool-calling 循环 + 12 项工具（本地代码执行 / 文件读写 / 联网搜索 / 屏幕视觉感知 / 自主定时报点 / 记忆读写）
> - **省钱设计**：记忆卡预算 800 token、优先级队列、单 worker 串行整理

## 演示

| 形象交互 | 一起玩五子棋 |
|:---:|:---:|
| <img src="screenshots/demo-companion.gif" width="200"> | <img src="screenshots/demo-gomoku.gif" width="440"> |
| 戳呆毛/尾巴/头/身各有专属反应，拖拽会朝对应方向跑动，对话时表情全程联动 | 说“来一局五子棋”即可开局；她边下边用角色口吻点评局势，赢了欢呼、输了委屈 |

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

## 形象素材说明

形象渲染为 **Petdex 精灵图**（`assets/live2d/web/sprite/pets/vivimi`，明日方舟维什戴尔同人二创）：帧动画，资源占用极低。

- 版权归原作《明日方舟》（鹰角网络）及同人素材原作者所有
- 仅供个人学习与娱乐使用，**禁止商用**
- 如需更换形象：替换 `assets/live2d/web/sprite/pets/vivimi` 为任意 Petdex 精灵图（`pet.json` + 8×9 网格 spritesheet），或修改 `config.companion` 的 `avatar_scale` 调整大小

## 开发

```bash
uv run --with pytest pytest        # 测试
uv run --with ruff ruff check src  # lint
```

- 域词汇表见 [`CONTEXT.md`](CONTEXT.md)
- Python 3.12（uv 管理）；PySide6 锁定 6.8.3（6.11 存在已知 DLL 兼容问题）
- 仅支持 Windows（屏幕视觉感知依赖 win32 API）

## License

[GPL-3.0](LICENSE) © 2026 JChat 作者。使用本仓库即表示你同意内置同人素材的各自许可条款。
