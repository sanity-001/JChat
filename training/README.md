# JChat 本地模型训练

> 目标：把「伙伴」跑在本地小模型上（Qwen3-1.7B 主力 / 0.6B 练手），并亲手走完
> **推理 → LoRA → 全量 SFT → DPO → 蒸馏 → 量化 → 多端部署** 的关键环节。
> 决策依据见 `wayfinder/`（地图与票据）与 `research/local-stack.md`、`research/training-data-alignment.md`。

## 里程碑

| # | 内容 | 验收 |
|---|---|---|
| M1 | llama-server 跑 Qwen3-1.7B Q5_K_M，接入 JChat | JChat 正常聊天 + 记忆注入 + ≥1 工具调用成功 |
| M2 | LLaMA-Factory QLoRA 人设微调 1.7B → 接入 JChat | 10 条固定 prompt 盲评，比 base 平均 +≥0.5；无「助手腔」 |
| M3 | 手写全量 SFT（0.6B，transformers+peft） | loss 正常下降 + 能出话 + 接入 JChat |
| M4 | DPO（LoRA-DPO，200~400 对） | chosen 概率 > rejected（或人工偏好 ≥70%） |
| M5 | 蒸馏（DeepSeek 造 1k~2k 条 → 训 0.6B） | 0.6B 蒸馏版 > 未蒸馏 0.6B |
| M6 | 量化导出 GGUF（Q5_K_M + Q4_K_M）+ 手机验证 | 手机完成 3 轮对话 |

## 目录约定

```
training/          本目录：脚本 + 配置 + 数据配方（入库）
data/              训练数据 JSONL + dataset_info.json（不入库）
models/            基座权重 / GGUF（不入库）
outputs/           LoRA 适配器 / 合并模型 / 导出（不入库）
research/notes-*.md  学习笔记（不入库）
```

## 推理（M1）

```powershell
# llama-server（llama.cpp Windows CUDA 构建）
llama-server.exe -m models/Qwen3-1.7B-Q5_K_M.gguf `
  -c 8192 -ngl 99 -np 2 --jinja -fa auto `
  -ctk q8_0 -ctv q8_0 --port 8080
```

JChat 侧：`config.json` → `llm.base_url = "http://127.0.0.1:8080/v1"`、`llm.api_key = "local"`、`llm.model = "qwen3-1.7b"`。

## 微调（M2 / M4）

LLaMA-Factory 放在**项目内**（`JChat/LLaMA-Factory/`，已 gitignore），用**独立环境**（训练栈会拉 torch，不污染 JChat 的 venv）：

```bash
cd D:\MyCode\JChat
git clone --depth 1 https://github.com/hiyouga/LLaMA-Factory.git
cd LLaMA-Factory
uv sync                       # 读其 pyproject 建独立 .venv 并装依赖（含 CUDA 版 torch，~3GB）
uv run llamafactory-cli version
```

训练/导出（在 `LLaMA-Factory/` 目录内执行；配置路径相对项目根）：

```bash
uv run llamafactory-cli train ..\training\llamafactory_sft_lora_1.7b.yaml
uv run llamafactory-cli train ..\training\llamafactory_dpo_1.7b.yaml
uv run llamafactory-cli export ..\training\llamafactory_sft_lora_1.7b.yaml   # 合并适配器
```

> 基座权重走本地路径：把 yaml 里的 `model_name_or_path` 改为 `..\models\Qwen3-1.7B`（避免训练时联网下载）。

## 数据配方（见票据 004）

- 人设对话 800~1500 条：30~50 条手写「对味」种子 + **改写 70% / 纯生成 30%**（ShareGPT 格式）
- 工具调用 300~600 条：单轮单调用 + **25% 拒答/无关负样本**（用 JChat 的 12 工具 schema）
- 通用指令混入 10~15%（防退化）
- DPO 200~400 对：chosen=角色口吻 / rejected=助手腔（AI 标注）
- 蒸馏 1k~2k 条：DeepSeek 一次性生成，仅用于 0.6B 学生
- **避开 CC BY-NC 数据集**（BELLE/Alpaca 系）；以自合成 + COIG-CQIA（确认许可子集）为主

## 量化（M6）

```powershell
llama-quantize --imatrix models/qwen3-1.7b-imatrix.gguf `
  models/qwen3-1.7b-f16.gguf models/Qwen3-1.7B-Q4_K_M.gguf Q4_K_M
```

PC 用 Q5_K_M，手机用 Q4_K_M（体积优先）。
