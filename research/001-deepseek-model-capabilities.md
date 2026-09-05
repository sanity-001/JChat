# 001: DeepSeek V4 Flash Vision Exp — 模型能力调研

> 调研日期：2026-09-05
> 目的：确认 "DeepSeek V4 Flash Vision Exp" 是否可作为 JChat 桌面搭子 agent 的 LLM 后端（OpenAI 兼容接口 + function calling）。
> 结论先行：**模型真实存在，为 DeepSeek 官方模型，OpenAI 兼容接入，支持 function calling 与视觉输入。可直接采用。**

---

## 1. 模型真实身份

- 模型 ID：`deepseek-v4-flash-vision-exp`
- 归属：**DeepSeek（深度求索）官方模型**，非第三方命名。2026-08-21 发布（见官方 News）。
- 定位：DeepSeek V4 家族首个视觉（多模态）模型，实验性质（`exp` 后缀），基于 V4-Flash 轻量架构，文本能力与 V4-Flash-0731 一致（含 agent、推理、世界知识），多模态 agent 基准接近 Opus-4.8。
- 开源权重：`deepseek-ai/DeepSeek-V4-Flash-Vision-Exp`（Hugging Face，MIT License，305B 参数），可用 vLLM / SGLang 自托管（OpenAI 兼容），但 JChat 走官方 API 即可，无需自托管。
- 本会话运行的 `opencode-go/deepseek-v4-flash-vision-exp` 即该模型经 **OpenCode Go** 订阅服务（$10/月）的代理入口，前缀 `opencode-go/` 是 provider 命名空间，后端就是同一个 DeepSeek 模型。

## 2. OpenAI 兼容接入（可用性）

| 接入方式 | base_url | model 参数 |
|---|---|---|
| DeepSeek 官方 API（推荐） | `https://api.deepseek.com` | `deepseek-v4-flash-vision-exp` |
| DeepSeek Anthropic 兼容 | `https://api.deepseek.com/anthropic` | 同上 |
| OpenCode Go（本会话所用） | `https://opencode.ai/zen/go/v1` | `deepseek-v4-flash-vision-exp` |
| OpenRouter / Fireworks / SiliconFlow / DeepInfra / Novita 等 | 各服务商 base_url | 各服务商 ID |

- 端点：`POST /chat/completions`（标准 OpenAI Chat Completions），也支持 `POST /responses`（Responses API）。
- 认证：`Authorization: Bearer <API Key>`；DeepSeek Key 在 https://platform.deepseek.com/api_keys 申请。
- 官方文档明确："The DeepSeek API uses an API format compatible with OpenAI/Anthropic"，可用 OpenAI SDK 直接调用。

## 3. Function calling / tools 支持：**支持（关键结论）**

- DeepSeek 官方 [Tool Calls 指南](https://api-docs.deepseek.com/guides/tool_calls) 提供标准 OpenAI `tools` 参数用法：`tools=[{"type":"function","function":{...}}]`，模型返回 `message.tool_calls`，客户端执行后以 `role:"tool"` + `tool_call_id` 回填，循环调用。
- 非 thinking 与 thinking 模式均支持 tool use（V3.2 起 thinking 模式支持）。
- 可选 `strict` 模式（Beta）：`base_url="https://api.deepseek.com/beta"` + function 内 `strict:true`，服务端校验 JSON Schema。
- Vision Exp 同样支持：官方发布说明称其文本能力与 V4-Flash 一致（含 agents）；DeepSeek Harness 0.1.1 开箱支持该模型；Responses API 指南中提及 `function_call_output` 项可携带 `input_image`（tool 输出图片），均证明工具调用链路在该模型上可用。
- 注意（对 JChat 设计的影响）：**图片仅允许出现在 `user` 消息中**；`system` / `assistant` 消息中带图片会返回 400。若 harness 只走 Chat Completions，截图类输入须放在用户轮次。

## 4. 视觉输入 / 上下文窗口 / 模型 ID 写法

- 视觉输入：支持 JPEG、PNG、GIF、WebP（按文件内容检测，不看扩展名）。三种传入方式（Chat Completions 中 `content` 用 block 数组）：
  1. Base64 `data:` URL 内联（计 48 MiB 请求体上限）
  2. 外部 http(s) URL（≤8192 字符，≤32 MiB，60 秒内下载完成）
  3. Files API `file_id`（`file-api-...` 格式；单图 ≤64 MiB，可复用）
- 细节：`image_url` 可带 `detail` 字段（`low`/`high`/`original`/`auto`）；图片自动缩放至约 800×800，**每图 token 上限 384**，按 V4-Flash 价格计费；每请求最多 600 图；单边最大 8192px（≥15 图时降到 4096px）。
- 上下文窗口：**1,000,000 tokens（1M）**；最大输出 384,000 tokens（来源：OpenCode catalog 与第三方对照；DeepSeek 官方 pricing 页列三款 V4 API 模型均为 1M 上下文）。建议实现时仍以服务端返回/文档为准做兜底。
- 推荐模型 ID 写法：直连 DeepSeek 用 `deepseek-v4-flash-vision-exp`（不要用 `deepseek-chat`/`deepseek-reasoner` 等旧别名；图片只能发给该模型，其它模型返回 400 "This model does not support image"）。
- 可选增强：`thinking: {"type":"enabled"}` + `reasoning_effort`（low/medium/high/xhigh/max）开启思考模式；注意 Vision Exp 的 effort 映射官方未单独说明，默认行为可能不同于 Flash/Pro。

## 5. 定价（OpenCode Go 目录价，供预算参考）

- 输入 $0.22 / 输出 $0.66 / cache read $0.007 / cache write $0（每百万 token）。
- 官方按 V4-Flash 定价，未单独公布 Vision Exp 单价；图片按 384 token/图上限计费。

## 6. JChat 接入建议

### 方案 A（推荐）：直连 DeepSeek 官方 API
- `base_url = https://api.deepseek.com`，`model = deepseek-v4-flash-vision-exp`，API key 在 platform.deepseek.com 申请。
- 优点：官方一手、无中间商、文档齐全；缺点：国内/国际网络需自行保证可达性。

### 方案 B：复用 OpenCode Go（即本会话所用后端）
- `base_url = https://opencode.ai/zen/go/v1`，`model = deepseek-v4-flash-vision-exp`，用 OpenCode Go 的 API key（opencode.ai 订阅，$10/月，国际用户稳定访问）。
- 缺点：依赖 opencode 平台、可能有速率限制；优点：与现有工具链一致，无需新申请 key（若用户已有 Go 订阅）。

### 若在 opencode 侧配置自定义 provider（供参考，非 JChat 必需）
opencode.json 标准自定义 OpenAI 兼容 provider 写法（来自 opencode 官方文档 Custom provider 一节）：

```json
{
  "$schema": "https://opencode.ai/config.json",
  "provider": {
    "myprovider": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "My AI Provider Display Name",
      "options": {
        "baseURL": "https://api.deepseek.com"
      },
      "models": {
        "deepseek-v4-flash-vision-exp": {
          "name": "DeepSeek V4 Flash Vision Exp",
          "limit": { "context": 1000000, "output": 384000 }
        }
      }
    }
  }
}
```

（opencode-go 内置 provider 的等效目录项：`api: openai-completions`, `baseUrl: https://opencode.ai/zen/go/v1`, `contextWindow: 1000000`, `maxTokens: 384000`。）

### JChat 集成要点
1. 工具循环：标准 OpenAI `tools` → `tool_calls` → `role:"tool"` 回填即可，无需特殊处理。
2. 视觉：搭子截图/图片一律放 `user` 消息的 content block 数组；按需 `detail:"low"` 省 token。
3. 长期记忆（≤800 token 记忆卡）与滚动窗口（20 轮）直接放 system/user 文本，无兼容问题；1M 上下文非常充裕。
4. 建议在配置层 pin 模型 ID（`deepseek-v4-flash-vision-exp`），因 `exp` 实验模型行为可能变化，便于日后切换。

## 7. 需向用户确认的事项

- 用户是否已有 DeepSeek 官方 API key，或倾向复用 OpenCode Go 订阅（决定方案 A/B）。
- 是否接受 `exp` 实验模型的稳定性风险（无 SLA、可能变更），或需要另备文本模型（`deepseek-v4-flash`）作为降级后端。
- 是否需要视觉输入（若 JChat 当前路线图不含截图/图片，可用文本版 `deepseek-v4-flash`，同 API 无缝切换）。

## 8. 信息来源（均为 2026-09-05 可访问的官方/一手源）

| 事实 | 来源 |
|---|---|
| 模型存在、实验性质、多模态发布 | https://api-docs.deepseek.com/news/news260821 |
| OpenAI 兼容 base_url / 模型列表 | https://api-docs.deepseek.com/ |
| 视觉输入三种方式、限制、384 token/图 | https://api-docs.deepseek.com/guides/vision |
| Tool Calls / strict 模式 | https://api-docs.deepseek.com/guides/tool_calls |
| 上下文 1M / 输出 384k、OpenCode Go 目录 | https://pi.dev/models/opencode-go/deepseek-v4-flash-vision-exp ；https://opencode.ai/docs/go/ |
| opencode 自定义 OpenAI 兼容 provider 配置 | https://opencode.ai/docs/providers/ |
| 开源权重（MIT，305B） | https://huggingface.co/deepseek-ai/DeepSeek-V4-Flash-Vision-Exp |
| OpenRouter 多服务商托管 | https://openrouter.ai/deepseek/deepseek-v4-flash-vision-exp |

注：第三方站点（chat-deep.ai、deepseek.ai、developersdigest.tech 等）仅作交叉印证，结论均以 DeepSeek 官方文档为准。
