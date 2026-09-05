---
label: wayfinder:map
title: JChat 长期记忆桌面搭子 — 路线图
---

# JChat 长期记忆桌面搭子 — 路线图

## Destination

一个可运行的 Windows 本地桌面"搭子"应用（包名 **JChat**，UI 基于 PySide6）：继承 Pet-GPT 的桌宠式交互与聊天界面，内置**合并进代码的 MemoKG** 长期记忆层（三层记忆 + 知识图谱 + 混合检索），具备 6 个工具的工作能力，LLM 主动搭话，persona 人格配置。到达终点 = 所有决策票据关闭，留下一套可直接实施的设计决策集。

## Notes

- **域**：Python 3.11 + uv；PySide6（Qt6）；OpenAI 兼容 LLM（DeepSeek V4 Flash Vision Exp）；MemoKG 以源码合并方式进入项目（非 pip 依赖）
- **术语**：称"搭子/伙伴"，禁用"桌宠"；包名 `src/JChat/`；"记忆卡"指每轮注入的蒸馏记忆；"知识库"指文档图谱
- **技能**：grilling、domain-modeling、prototype、research
- **流程**：每次会话只解决一个票据（research 类除外，可并行）
- **建图时已定**（诘问 3 轮结论，写入本区作为常设偏好）：
  - 可运行桌面程序；项目建在当前 `D:\MyCode\JChat`，Pet-GPT 为基线拷贝
  - 标准 tool-calling 循环（上限 ~5 次迭代），后台线程
  - 记忆写入 = agent 主动 `remember` + 会话后自动抽取（会话 ≥8 轮才抽，异步）
  - 每轮 prompt = persona + 滚动窗口（最近 20 轮，≤3000 token）+ 记忆卡（≤800 token）
  - 主动对话 = LLM 生成 + 记忆感知；首版非流式（打字机效果）；统一 `config.json` + 私有覆盖
  - 首版工具：run_python / read_file / write_file / list_files / web_fetch / remember；无沙箱
  - 排除 gradio Web 端；聊天历史持久化到 SQLite（chats 表）

## Decisions so far

> **状态：地图已完成**（2026-09-05）——全部 9 张决策票据关闭，无剩余开放票据。下方索引即为完整决策集，可据此进入实施。

<!-- 索引：每个已关闭票据一行：标题（链接）— 一句话要点。决议只在票据里，地图只做索引 -->

- [DeepSeek V4 Flash Vision Exp 能力与接入验证](tickets/001-deepseek-model-capabilities.md) — 模型真实存在且支持 function calling/视觉/1M 上下文；官方端点 api.deepseek.com，tool-calling 循环可行（端点选择并入票据 007）
- [主动对话策略](tickets/004-proactive-chat-policy.md) — 随机 10~30 分钟搭话（可调）；聊天窗打开/输入聚焦/锁屏/夜间抑制；独立轻量 LLM 调用（persona+记忆卡，128 token）；搭话不进窗口不抽取，用户回复时才进入循环；失败安静放弃
- [记忆与知识库的领域模型](tickets/002-memory-knowledge-domain-model.md) — 记忆=关于用户的衰减事实，知识库=关于世界的不衰减知识（来源：文档+对话）；分离存储，记忆卡=记忆条目+相关三元组（6:4 用户优先）；记忆条目软关联实体
- [记忆卡组装规则](tickets/003-memory-card-composition.md) — 每轮记忆卡 = recall k=5 条目 + ≤6 三元组；窗口重叠>60% 去重；超预算按分数裁剪（同分先丢三元组）；`【记忆】/【知识】` 分段标注；仅用户输入时刷新；persona 定表达、记忆卡定事实
- [自动抽取规则](tickets/005-auto-extraction-policy.md) — 会话关闭时异步抽取（≥8 轮）：一次调用出 facts+triples；相似度≥0.85 判重只 touch；importance≥3 才入库；无 key 时对话抽取停用；设置面板提供记忆列表（查看/删除/手动添加）
- [配置文件 schema](tickets/007-config-schema.md) — `config.json`+`config.private.json` 深度合并，api_key 仅 private；字段清单含 llm/agent/companion/memory/tools/ui（默认值见票据）；首启生成默认配置；config 优先→环境变量兜底→默认值
- [聊天 UI 视觉方案](tickets/006-chat-ui-visual-prototype.md) — 选定"搭子互动式"（原型 3 变体）：伙伴大卡片+并排聊天窗、渐变贴纸气泡、便签风工具卡、记忆 chips、暗色渐变主题；原型存 `prototypes/ui-visual/`
- [工具执行边界](tickets/008-tool-execution-boundaries.md) — run_python 固定工作目录+60s 超时+16KB 截断（网络/包自由）；文件工具全盘自由（write 记日志）；web_fetch 15s/1MB/仅 http(s) 返纯文本；remember 默认 importance 3 不限阈值；回灌格式 `[工具名] 输出/[Error]`，元信息只进 UI；工具注册表扩展
- [停止、取消与并发策略](tickets/009-stop-cancel-concurrency.md) — 停止=放弃整个循环（HTTP 连接关闭+Event 标志，Popen terminate）；搭话触发前抑制、生成中用户消息优先；工具卡片状态流转；单 worker 队列（聊天>搭话>抽取）

## Not yet specified

- 知识图谱可视化（图谱浏览视图）——首版明确不做（见票据 005 决议：仅记忆列表入口入首版），后续版本再议
- 对话历史回看 UI（chats 表存了历史，如何浏览）
- 搭子形象素材体系（gif 换肤、多形象）
- 多模型/多后端切换的 UI 形态

## Out of scope

- 沙箱隔离、gradio Web 端、移动端、语音（TTS/STT）、图片生成、Live2D、多用户/多设备同步、插件市场、自动更新（诘问 Q22 确认全排除）
