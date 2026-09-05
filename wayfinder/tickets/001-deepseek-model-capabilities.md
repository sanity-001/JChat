---
id: 1
title: DeepSeek V4 Flash Vision Exp 能力与接入验证
type: research
status: closed
blocked_by: []
resolved: 2026-09-05
---

## Question

DeepSeek V4 Flash Vision Exp（用户指定的模型）作为本 agent 的 LLM 后端是否可行？需要确认的事实：

1. 模型是否可通过 OpenAI 兼容接口（chat/completions）访问？base_url 是什么（官方 DeepSeek 还是第三方/代理端点）？
2. 是否支持 **function calling / tools 参数**？（Q8 的 tool-calling 循环依赖此能力；若不支持，需回退方案）
3. 是否支持视觉输入（vision）？上下文窗口多大？
4. 推荐的接入方式（SDK/端点/鉴权）与价格量级

无法从用户处获取的事实由研究子代理查证；若模型在公开渠道查不到，记录"需向用户索取端点信息"作为结论。

## Resolution

研究完成（2026-09-05，详见 `research/001-deepseek-model-capabilities.md`）：

- 模型真实存在：`deepseek-v4-flash-vision-exp` 是 DeepSeek 官方 2026-08-21 发布的 V4 家族首个实验性多模态模型
- OpenAI 兼容端点：`https://api.deepseek.com`，model 传 `deepseek-v4-flash-vision-exp`，标准 chat/completions + Bearer key
- **支持 function calling**（官方 Tool Calls 指南含 tools→tool_calls→role:tool 完整循环），agent 的 tool-calling 循环可行
- 视觉：支持 JPEG/PNG/GIF/WebP（仅 user 消息），上下文 1M / 输出 384k
- 两种接入：A) 官方 `api.deepseek.com`（需官方 key）；B) 复用 OpenCode Go 订阅（`https://opencode.ai/zen/go/v1`）——最终端点选择作为小决策并入票据 007（配置 schema）

结论：Q8 的 tool-calling 循环假设成立，无需回退方案。
