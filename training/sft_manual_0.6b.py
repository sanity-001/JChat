"""M3：手写全量 SFT（Qwen3-0.6B）——不用 Trainer，手动实现训练循环。

学习目标（每步都在代码里注释原理）：
1. 数据：ShareGPT → chat template 渲染 → **只对 assistant 回复计算 loss**（label mask）
2. 训练循环：zero_grad → bf16 前向 → backward → 梯度裁剪 → 优化器/调度器 step
3. 显存技巧：8bit AdamW、梯度检查点、梯度累积（小显存跑大 batch 等效）

用法：
    # 冒烟（20 步）
    uv run --directory D:\\Tool\\LLM_Tools\\LLaMA-Factory python training/sft_manual_0.6b.py --max-steps 20
    # 全量
    uv run --directory D:\\Tool\\LLM_Tools\\LLaMA-Factory python training/sft_manual_0.6b.py --epochs 2
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

import torch
from torch.utils.data import DataLoader, Dataset

ROOT = Path(r"D:\MyCode\JChat")
BASE_MODEL = str(ROOT / "models" / "Qwen3-0.6B")
DATA = ROOT / "data" / "persona_v1.jsonl"
OUT = ROOT / "outputs" / "qwen3-0.6b-full-sft"
MAX_LEN = 1024

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


class PersonaDataset(Dataset):
    """把 ShareGPT 多轮对话转成 (input_ids, labels)，labels 只覆盖 assistant 回复。"""

    def __init__(self, path: Path, tokenizer):
        self.tok = tokenizer
        self.items: list[dict] = []
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                row = json.loads(line)
                conv = [c for c in row["conversations"] if c["from"] in ("human", "gpt")]
                # 只保留含 assistant 回复的普通对话（工具样本此处跳过，M2 已覆盖）
                if len(conv) >= 2 and conv[-1]["from"] == "gpt":
                    self.items.append({"system": row.get("system", ""), "conv": conv})

    def __len__(self) -> int:
        return len(self.items)

    def __getitem__(self, idx: int) -> dict:
        item = self.items[idx]
        sys_prompt = item["system"]
        conv = item["conv"]
        input_ids: list[int] = []
        labels: list[int] = []
        # 逐轮构造：提示部分 mask 为 -100，assistant 回复部分才计算 loss
        for i, turn in enumerate(conv):
            if turn["from"] != "gpt":
                continue
            history = conv[:i]  # 该轮之前的所有对话
            messages = ([{"role": "system", "content": sys_prompt}] if sys_prompt else []) + [
                {"role": "user" if c["from"] == "human" else "assistant", "value": c["value"],
                 "content": c["value"]} for c in history
            ]
            for m in messages:
                m.pop("value", None)
            prompt_text = self.tok.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True
            )
            reply_text = turn["value"] + self.tok.eos_token
            p_ids = self.tok(prompt_text, add_special_tokens=False)["input_ids"]
            r_ids = self.tok(reply_text, add_special_tokens=False)["input_ids"]
            input_ids += p_ids + r_ids
            labels += [-100] * len(p_ids) + r_ids  # -100 = 该位置不参与 loss
        input_ids = input_ids[:MAX_LEN]
        labels = labels[:MAX_LEN]
        return {"input_ids": input_ids, "labels": labels}


def collate(batch: list[dict], pad_id: int) -> dict:
    maxlen = max(len(b["input_ids"]) for b in batch)
    input_ids, labels, attn = [], [], []
    for b in batch:
        pad = maxlen - len(b["input_ids"])
        input_ids.append(b["input_ids"] + [pad_id] * pad)
        labels.append(b["labels"] + [-100] * pad)
        attn.append([1] * len(b["input_ids"]) + [0] * pad)
    return {
        "input_ids": torch.tensor(input_ids),
        "labels": torch.tensor(labels),
        "attention_mask": torch.tensor(attn),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--epochs", type=float, default=2.0)
    ap.add_argument("--batch", type=int, default=1)
    ap.add_argument("--accum", type=int, default=8)          # 梯度累积：等效 batch = batch*accum
    ap.add_argument("--lr", type=float, default=1e-5)        # 全量微调用小学习率
    ap.add_argument("--max-steps", type=int, default=0)      # 冒烟用
    ap.add_argument("--save-steps", type=int, default=200)
    args = ap.parse_args()

    from transformers import AutoModelForCausalLM, AutoTokenizer

    print("加载 tokenizer / 模型（bf16 + 梯度检查点）…", flush=True)
    tok = AutoTokenizer.from_pretrained(BASE_MODEL, trust_remote_code=True)
    model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL, torch_dtype=torch.bfloat16, trust_remote_code=True
    ).cuda()
    model.gradient_checkpointing_enable()  # 用时间换显存：不保存中间激活
    model.train()

    ds = PersonaDataset(DATA, tok)
    print(f"样本数: {len(ds)}（首条 token 数: {len(ds[0]['input_ids'])}）", flush=True)
    loader = DataLoader(
        ds,
        batch_size=args.batch,
        shuffle=True,
        collate_fn=lambda b: collate(b, tok.pad_token_id or tok.eos_token_id),
    )

    try:
        import bitsandbytes as bnb

        optim = bnb.optim.AdamW8bit(model.parameters(), lr=args.lr)  # 8bit 优化器省 4x 显存
        print("优化器: AdamW8bit", flush=True)
    except Exception:  # noqa: BLE001
        optim = torch.optim.AdamW(model.parameters(), lr=args.lr)
        print("优化器: AdamW(fp32)", flush=True)

    total_steps = args.max_steps or math.ceil(len(loader) * args.epochs / args.accum)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(optim, T_max=max(1, total_steps))
    step = 0
    t0 = time.time()
    running = 0.0
    for _epoch in range(math.ceil(args.epochs)):
        for i, batch in enumerate(loader):
            batch = {k: v.cuda() for k, v in batch.items()}
            out = model(**batch)                      # 前向（bf16 autocast 由模型 dtype 决定）
            loss = out.loss / args.accum              # 梯度累积：loss 按累积步数缩放
            loss.backward()
            running += loss.item()
            if (i + 1) % args.accum == 0:
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)  # 防梯度爆炸
                optim.step()
                sched.step()
                optim.zero_grad(set_to_none=True)
                step += 1
                if step % 10 == 0:
                    print(
                        f"step {step}/{total_steps} | loss {running / (10 * args.accum):.4f} "
                        f"| lr {sched.get_last_lr()[0]:.2e} | {time.time() - t0:.0f}s",
                        flush=True,
                    )
                    running = 0.0
                if step % args.save_steps == 0:
                    model.save_pretrained(OUT)
                    tok.save_pretrained(OUT)
                    print(f"已保存 → {OUT}", flush=True)
                if args.max_steps and step >= args.max_steps:
                    model.save_pretrained(OUT)
                    tok.save_pretrained(OUT)
                    print(f"冒烟结束，已保存 → {OUT}", flush=True)
                    return
    model.save_pretrained(OUT)
    tok.save_pretrained(OUT)
    print(f"训练完成 → {OUT}（{time.time() - t0:.0f}s）", flush=True)


if __name__ == "__main__":
    main()
