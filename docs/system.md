# JChat 系统文档

> 定位：Windows 桌面 AI 搭子（Live2D 形象 + 长期记忆 + 本地工具）。个人本地工具，无沙箱。
> 术语遵循 `CONTEXT.md`：称"搭子/伙伴"，禁用"桌宠"。

## 1. 整体架构

```
┌─ ui/ ──────────────────────────────┐
│ companion_window.py  伴侣窗（QWebEngineView 透明窗口 + Live2D）      │
│ chat_window.py       大窗（对话详情：气泡历史 + 工具卡 + 输入）      │
│ settings_dialog.py   设置面板（LLM/搭子/记忆/工具）                  │
│ widgets.py / theme.py 气泡、记忆 chips、工具卡、马卡龙样式            │
└─────────────┬──────────────────────┘
              │ 事件（tap/drag/menu）↑ ↓ 指令（表情/气泡/摇尾）
┌─ app.py（整合层 App(QObject)）──────┐
│ ui_task 信号桥（worker线程 → UI线程唯一安全通道）                     │
│ on_send → LLMQueue(单worker,优先级:对话0/主动1/整理2) → _run_worker_turn │
│ 滚动抽取 _maybe_rolling_extract / 摘要带 _maybe_summarize            │
└──────┬──────────────┬───────────────┘
       │              │
┌─ agent/ ──┐   ┌─ memory/ ────────────────┐
│ loop.py    │   │ memory.py    AgentMemory(短期/长期/摘要带)  │
│ tools.py   │   │ extractor.py 会话抽取+生活摘要(第一人称)     │
│ prompts.py │   │ storage.py   SQLiteStore(chats/memories/docs/entities/relations) │
│ extractor  │   │ retriever.py 混合检索(实体链接+图谱+RRF)     │
└─────┬─────┘   │ graph.py/ontology.py 三元组知识图谱           │
      │         │ vector.py    TF-IDF(可插拔 SentenceTransformer)│
┌─ llm/client.py ─┐└──────────────────────────┘
│ OpenAI 兼容(DeepSeek) │
└──────────────┘
```

- **线程模型**：主线程只做 UI；LLM/工具/抽取/摘要全部走 `LLMQueue` 单 worker（避免并发写库与 UI 卡顿）；worker → UI 一律 `ui_task.emit(闭包)`。
- **配置**：`config.json`（公开）+ `config.private.json`（git 忽略，api_key 只放这里）；`_sanitize` 校验并回填默认值。

## 2. 记忆系统（融合 JChat 检索精度 × Alife 在场感）

### 2.1 设计来源
- 参考 Alife（github.com/BDFFZI/Alife）的核心理念：**不依赖 AI 自主决定记什么，机械自动化保证记忆必然发生**；但**不照搬**其"唯一永久会话+多级压缩内联"（我们 prompt 每轮重组、无缓存前提，内联会贵很多）。
- 保留 JChat 自有优势：三元组知识图谱、冲突检测、importance 分层、记忆卡按需注入省 token。

### 2.2 管线（每轮 AI 回复后自动运转）
```
AI 回复
 ├─ ① 滚动抽取：新增 ≥4 轮 → LLM 抽 facts(第一人称,importance≥3) + 三元组 → memories/relations
 │    （相似度 ≥0.85 判重只 touch；会话结束 30s 兜底再抽一次）
 └─ ② 摘要带：已滑出滚动窗口(20轮)的消息攒 ≥6 轮 → 压成 1 条第一人称带日期的生活轨迹
      （scope=summary；>4 条时最老两条合并成"[更早期]"粗轨迹——两级封顶；与上一条 overlap≥0.6 防重）

下一轮 system prompt =
  persona
  + 【近期轨迹】常驻摘要带（在场感/时间感——Alife 精华的轻量版）
  + 【记忆】recall Top-5（带 [N天前] 时间标签）+【知识】≤6 三元组（预算 800 token）
  + 提示线索：用户消息含"还记得/上次/那天…" → 注入"先用 recall 回忆"
```

### 2.3 记忆通路
| 通路 | 写入 | 读出 |
|---|---|---|
| 记忆卡（事实） | 滚动抽取 / `remember` 工具 / 设置面板手动 | 每轮自动注入 Top-5 |
| 摘要带（轨迹） | 滚动摘要（scope=summary） | 每轮常驻注入，不参与检索 |
| 知识图谱 | 抽取三元组（ implements/based_on/outperforms/used_in/proposes） | 实体链接+图谱搜索→三元组行 |
| 主动回忆 | — | `recall` 工具（AI 自主查询，带时间标签） |
| 演化 | `consolidate()`（short→long 提升/降级）、decay 衰减、冲突检测 | 原文永久存 chats 表（可溯源） |

### 2.4 存储结构（jchat.sqlite）
- `chats`：全部原文（session_id/role/content/created_at）——先存后理，永不丢
- `memories`：memory_id/scope(short/long/summary)/content/entities/importance/score
- `docs`+`entities`+`relations`：图谱（doc_id 回指来源）

## 3. 交互模式

- **伴侣窗**（Live2D，vvm 模型，参数数组直写）：
  - 表情预设 10 种（idle/happy/thinking/shy/surprised/angry/sad/tongue/sleepy/talk）
  - 常驻动画：眨眼 300ms、口型说话 140ms 随机、视线跟随+3s 回中、摇尾 550ms/步
  - 点击分区（优先级）：**呆毛**（胶囊 (232,309)-(277,308) r18，惊讶反应）> **尾巴**（弱点文案）> 头 > 身；连点 combo
  - 拖拽移动；右键菜单（对话/设置/退出）
- **悬停气泡**：鼠标悬停输入区弹出（伙伴下方），单条最新回复限高 140px 内部滚动，"查看全文↗"跳大窗；离开 1.5s 收起（200ms 轮询光标）
- **大窗**：完整历史 + 工具卡 + 输入（Enter 发送/Shift+Enter 换行）；与悬停共享同一会话；关闭不清会话
- **主动搭话**：proactive_min/max 分钟随机 + 免打扰时段；AI 发起（优先级 1）
- **生命周期**：`setQuitOnLastWindowClosed(False)`，仅右键"退出"结束
- **AI 状态联动**：回复后 happy/sad + 口型 5s；工具调用时 surprised/thinking

## 4. Agent 能力

- 标准 tool-calling 循环（`max_iterations` 上限，支持取消）
- 7 工具：`run_python`（无沙箱本地执行）、`read_file`、`write_file`、`list_files`、`web_fetch`、`remember`（写记忆）、`recall`（主动检索记忆+图谱）
- 大窗工具卡实时显示每个工具的运行状态与输出预览

## 5. 模块化程度评估：JChat vs Alife

**结论：JChat 是"分层单体"，模块化但不插件化；Alife 是"全插件框架"。**

| 维度 | Alife | JChat 现状 |
|---|---|---|
| 功能承载 | 一切功能皆插件（C# DLL，含热编译/热重载） | 固定模块，import 直接引用 |
| 插件生态 | 插件市场 + 开发 MCP，AI 可自我改造 | 无 |
| 模块边界 | 框架定义 Module 抽象 + 事件总线 | 隐式约定（tools.py 注册表、memory 分包）已是清晰接缝 |
| 交互模式 | 交互也是插件（DeskPet/Speech/Auditory…可插拔） | 交互内置于 app.py+ui/，不可替换 |

诚实的定位差异：
1. **Alife 的插件化服务于它的产品目标**（开放生态、AI 自我进化、多开社交）。JChat 是单用户个人工具，没有第三方开发者，全插件化的收益（热插拔、市场）几乎为零，成本（抽象层、事件总线、加载器）很高——**不建议照搬**。
2. JChat 现有的"天然接缝"已经足够支撑未来演进：
   - 工具层：`tools.py` 的 schema+execute 已是注册表式，加工具=加两个条目
   - 记忆管线：抽取/摘要/consolidate 都是独立函数，可独立替换实现
   - 检索：`VectorIndex` 是 Protocol，TF-IDF/SentenceTransformer 可切换
3. 若未来想要"轻量插件化"，性价比最高的演进顺序：
   - ① 工具插件化（JSON/函数注册，最简单，收益最直接）
   - ② 交互模式拆为"输入源"接口（悬停/大窗/QQ/语音都实现同一 send 接口）
   - ③ 记忆管线阶段化（每阶段一个可替换的 processor）
   - ④ 全插件框架 + AI 自我改造（仅在真需要时再做）

> **2026-09-07 更新**：JChat 目标变更为开源产品，§5 的结论在开源语境下修订为"先接缝化、后插件 API"，详见 §6 开源路线图。

## 6. 开源路线图（2026-09-07 定案）

**目标**：JChat 后续开源为产品。已决策：

| 决策 | 结论 |
|---|---|
| 开源范围 | 代码 + **保留 vvm 模型**（明日方舟维什戴尔同人二创；README 需附同人声明：版权归原作者/禁止商用/可自行替换模型） |
| 插件化目标 | **先接缝化，后插件 API**：现在按"未来可插件化"设计接口但不写加载器；等真实第三方需求再上插件 API；AI 自我改造（MCP 化）缓行 |
| 时间点 | 立即做 LICENSE + README 骨架；正式开源等记忆系统实跑稳定后 |
| 许可证 | **GPL-3.0**（防闭源魔改；同时要求使用者遵守 Cubism Core 与同人模型各自条款） |

**接缝化三步**（对应 §5 演进顺序 ①②③，现在开始按此约束新代码）：
1. 工具注册表：新工具只改 `tools.py`（schema + execute 条目），不碰 loop/app
2. 输入源接口：悬停/大窗已共享 `send_requested` 信号——未来接入源（QQ/语音）实现同一接口即可
3. 记忆管线阶段化：抽取/摘要/consolidate 已是独立函数；下一步把它们统一成 processor 接口

**正式开源前清单**：
- [x] LICENSE（GPL-3.0）
- [x] README 骨架（含同人声明/隐私声明/免责）
- [ ] 隐私审计：确认无遥测、无硬编码 key/路径（`config.private.json` 已隔离 ✓）
- [ ] git 历史清理确认：`tap_coords.log`/`jchat.sqlite`/`config.private.json` 持续 gitignore ✓
- [ ] 记忆系统实跑 ≥1 周验证（滚动抽取/摘要带/consolidate 无劣化）
- [ ] 中英双语 README、CONTRIBUTING、版本 tag、发布说明

---
*生成于 2026-09-07；对应提交：滚动抽取(4轮)/摘要带(6轮,两级封顶)/recall 工具/Enter 发送之后的版本。*
