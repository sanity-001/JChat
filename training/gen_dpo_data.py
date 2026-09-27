"""M4 数据：DPO 偏好对生成（chosen=角色口吻 / rejected=典型失败模式）。

rejected 刻意覆盖微调版实测出的三种真实短板：
1. 助手腔（“作为AI助手，我很乐意帮你”）
2. 逻辑跑偏（答非所问、语义不通）
3. 口头禅滥用（“行吧，算你运气好”堆砌）

用法：
    uv run python training/gen_dpo_data.py --n 300
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

PERSONA = (
    "维维美：明日方舟维什戴尔的Q版化身，毒舌嘴硬心软的桌面搭子。"
    "短句、口癖（哈？/啧/哼/行吧算你运气好）、把干活说成“大扫除”，关心用损人的话表达。"
)

FAIL_MODES = {
    "assistant": "写成标准 AI 助手腔（“作为AI助手”“很高兴帮你”“希望对你有帮助”之类），礼貌但没有人味",
    "incoherent": "逻辑跑偏：答非所问、前后矛盾或语义不通顺（但仍像中文句子）",
    "catchphrase": "疯狂堆砌口头禅（“哈？”“啧”“行吧，算你运气好”重复多次），内容空洞",
}

SYS = """你在为角色「维维美」造 DPO 偏好数据。
角色设定：{persona}

给定一轮用户提问和一个「好的回答」，请再造一个「差回答」。
只输出 JSON：{{"rejected": "差回答内容"}}
差回答要求：{mode_desc}
- 长度与好回答接近（±20 字），不要出现任何解释或前缀"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=300)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--out", default=str(ROOT / "data" / "persona_dpo.jsonl"))
    args = ap.parse_args()

    from JChat.config import load_config
    from JChat.llm.client import LLMClient

    llm = LLMClient(load_config())
    rows = [json.loads(line) for line in (ROOT / "data" / "persona_v1.jsonl").open(encoding="utf-8")]
    pairs_src = []
    for r in rows:
        conv = [c for c in r["conversations"] if c["from"] in ("human", "gpt")]
        if len(conv) == 2 and len(pairs_src) < args.n:
            pairs_src.append((conv[0]["value"], conv[1]["value"]))
    random.shuffle(pairs_src)
    print(f"候选对: {len(pairs_src)}")

    drops = {"no_json": 0, "len": 0, "same": 0}

    def one(item: tuple[str, str]) -> dict | None:
        user, chosen = item
        mode = random.choice(list(FAIL_MODES))
        try:
            resp = llm.chat(
                [
                    {"role": "system", "content": SYS.format(persona=PERSONA, mode_desc=FAIL_MODES[mode])},
                    {"role": "user", "content": f"用户提问：{user}\n好的回答：{chosen}"},
                ],
                max_tokens=1000,  # 推理型模型：思考会吃掉预算，留足空间
                temperature=1.0,
            )
            raw = resp["choices"][0]["message"]["content"] or ""
            m = re.search(r"\{.*\}", raw, re.S)
            if not m:
                drops["no_json"] += 1
                return None
            rejected = str(json.loads(m.group(0)).get("rejected", "")).strip()
            if not (4 <= len(rejected) <= 200):
                drops["len"] += 1
                return None
            if rejected == chosen:
                drops["same"] += 1
                return None
            return {
                "conversations": [{"from": "human", "value": user}],
                "chosen": {"from": "gpt", "value": chosen},
                "rejected": {"from": "gpt", "value": rejected},
                "system": "你是维维美。",
            }
        except Exception as e:  # noqa: BLE001
            print("  失败:", e, file=sys.stderr)
            return None

    with ThreadPoolExecutor(args.workers) as ex:
        out = [r for r in ex.map(one, pairs_src) if r]
    print("丢弃统计:", drops)

    path = Path(args.out)
    with path.open("w", encoding="utf-8") as fh:
        for r in out:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    info = path.parent / "dataset_info_dpo.json"
    info.write_text(json.dumps({
        "persona_dpo": {
            "file_name": path.name,
            "formatting": "sharegpt",
            "ranking": True,
            "columns": {"messages": "conversations", "chosen": "chosen", "rejected": "rejected"},
        }
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"写入 {len(out)} 对 → {path}")
    for r in out[:3]:
        print(f"  用户: {r['conversations'][0]['value'][:26]}")
        print(f"    chosen : {r['chosen']['value'][:50]}")
        print(f"    rejected: {r['rejected']['value'][:50]}")


if __name__ == "__main__":
    main()
