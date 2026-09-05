---
id: 7
title: 配置文件 schema
type: grilling
status: closed
blocked_by: [2, 3, 5]
assignee: opencode
resolved: 2026-09-05
---

## Question

统一配置（Q15 已定：`config.json` + `config.private.json` 覆盖）的最终 schema：

1. 完整字段清单：LLM（base_url/model/api_key/代理）、搭子（昵称/persona/图标/移动/随机搭话开关）、记忆（衰减率/窗口/预算/抽取阈值）、工具（工作目录/超时）、UI（主题/字号）
2. 分层：哪些字段可被 private 覆盖、哪些必须 private（api_key）
3. 校验与缺省值策略（首启生成默认配置？）
4. 与 MemoKG 原环境变量（MEMOKG_*）的映射关系：读 config.json 还是兼容环境变量？

## Resolution

诘问一轮定案（2026-09-05）：

1. **LLM 接入**：配置化，默认 `base_url=https://api.deepseek.com`、`model=deepseek-v4-flash-vision-exp`，任意 OpenAI 兼容端点可换（OpenCode Go 端点亦可）
2. **分层**：`config.json`（公开）+ `config.private.json`（git 忽略）深度合并；api_key 仅允许在 private，出现在公开文件则告警
3. **字段清单**（用户确认"如上"，默认值已含）：`llm`（base_url/model/api_key/proxy/timeout/max_retry/temperature/top_p/max_tokens）、`agent`（max_iterations=5）、`companion`（nickname/icon/persona/random_walk/random_chat/width/height/shortcut_chat）、`memory`（decay_rate=0.01/working_window=10/recall_k=5/triples_limit=6/card_budget_tokens=800/card_memory_ratio=0.6/window_turns=20/window_budget_tokens=3000/window_dedup_threshold=0.6/memory_dedup_threshold=0.85/extraction_min_turns=8/importance_threshold=3）、`tools`（working_dir/run_timeout/output_limit_bytes/web_fetch_timeout/web_fetch_max_bytes）、`ui`（theme/font_size）
4. **校验**：首启生成带中文注释的默认 `config.json`；缺字段/非法值回退默认并日志警告
5. **环境变量**：config.json 优先 → 未配置字段回退环境变量（MEMOKG_* 兼容）→ 默认值
