"""M5 数据：蒸馏集（教师模型生成 + 自检验证）。

与 gen_persona_data 的区别（蒸馏的关键）：
1. 教师先思考“怎么答才像维维美”，再给最终回复（只保留回复）——把教师的判断力蒸馏进数据
2. 生成后**教师自检打分**（1-5），只保留 ≥4 分样本（质量过滤 = 蒸馏的核心价值）
3. 多轮对话（2~3 轮），覆盖连续语境

用法：uv run python training/gen_distill_data.py --n 600 --workers 8
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

PERSONA = (
    "维维美：明日方舟维什戴尔的Q版化身，毒舌嘴硬心软的桌面搭子。"
    "短句、口癖（哈？/啧/哼/嘻嘻）、把干活说成“大扫除”，关心用损人的话表达，"
    "被使唤会抱怨但一定做完，绝不煽情、绝不说教。"
)

SCENES = [
    "被使唤干活", "用户情绪低落", "用户炫耀/兴奋", "深夜闲聊", "用户道歉",
    "用户问身份/关系", "用户求安慰", "用户闲聊天气/生活", "用户要下棋/玩游戏",
    "用户夸她", "用户抱怨工作", "用户提到朋友", "用户要她记住某事", "用户开玩笑逗她",
    "用户让她评价自己", "用户道别/晚安", "用户很久没来", "用户问建议",
]

GEN_SYS = """你在为角色「维维美」造高质量蒸馏数据。
角色设定：{persona}

先在心里判断"怎样回应才最像维维美"，再给出数据。只输出 JSON：
{{"user1": "用户第1句（口语、≤25字）", "reply1": "维维美第1句回复（≤40字）",
  "user2": "用户第2句（顺着上文，≤25字）", "reply2": "维维美第2句回复（≤40字）"}}
要求：
- 场景：{scene}
- 维维美的回复要短、有口癖、有性格，禁止助手腔（"作为AI""很高兴""希望对你有帮助"）
- 两句回复都要贴合人设，第2句要有上下文衔接"""

VERIFY_SYS = """你是严格的角色一致性评审。给下面维维美的回复打分（1-5）：
5=性格鲜明口吻准确；4=基本贴合；3=略平；2=偏助手腔；1=完全不像。
只输出 JSON：{{"score": 数字, "why": "一句话"}}"""

# 规则化质检（免 API）：助手腔关键词 / 长度 / 重复
_BAD_TONE = re.compile(
    r"作为(一个)?AI|人工智能助手|很高兴(为你|帮|能)|希望对你有帮助|抱歉|我是一个|请随时告诉我|有什么可以帮"
)


def quality_ok(r1: str, r2: str, seen_users: set[str], u1: str) -> str | None:
    """返回 None 表示通过；否则返回拒绝原因。"""
    if _BAD_TONE.search(r1) or _BAD_TONE.search(r2):
        return "assistant_tone"
    if not (6 <= len(r1) <= 80 and 6 <= len(r2) <= 80):
        return "length"
    if r1 == r2:
        return "dup_reply"
    if u1 in seen_users:
        return "dup_user"
    if len(set(r1) & set(r2)) / max(len(set(r1) | set(r2)), 1) >= 0.9:
        return "similar_replies"
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=600)
    ap.add_argument("--keep-floor", type=int, default=4)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--out", default=str(ROOT / "data" / "persona_distill.jsonl"))
    args = ap.parse_args()

    from JChat.config import load_config
    from JChat.llm.client import LLMClient

    llm = LLMClient(load_config())
    stats = {"gen_fail": 0, "verify_fail": 0, "low_score": 0, "kept": 0}

    def one(i: int) -> dict | None:
        scene = SCENES[i % len(SCENES)]
        try:
            raw = llm.chat(
                [
                    {"role": "system", "content": GEN_SYS.format(persona=PERSONA, scene=scene)},
                    {"role": "user", "content": f"生成一组（场景：{scene}）"},
                ],
                max_tokens=1200,  # 推理模型留足预算
                temperature=0.9,
            )
            m = re.search(r"\{.*\}", raw["choices"][0]["message"]["content"] or "", re.S)
            if not m:
                stats["gen_fail"] += 1
                return None
            d = json.loads(m.group(0))
            u1, r1 = str(d.get("user1", "")).strip(), str(d.get("reply1", "")).strip()
            u2, r2 = str(d.get("user2", "")).strip(), str(d.get("reply2", "")).strip()
            if not all((u1, r1, u2, r2)):
                stats["gen_fail"] += 1
                return None

            reason = quality_ok(r1, r2, seen_users, u1)
            if reason:
                stats[reason] = stats.get(reason, 0) + 1
                return None
            stats["kept"] += 1
            return {
                "system": PERSONA,
                "conversations": [
                    {"from": "human", "value": u1}, {"from": "gpt", "value": r1},
                    {"from": "human", "value": u2}, {"from": "gpt", "value": r2},
                ],
            }
        except Exception as e:  # noqa: BLE001
            stats["gen_fail"] += 1
            print("  失败:", str(e)[:80], file=sys.stderr)
            return None

    seen_users: set[str] = set()
    with ThreadPoolExecutor(args.workers) as ex:
        rows = [r for r in ex.map(one, range(args.n)) if r]

    path = Path(args.out)
    with path.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    info_path = path.parent / "dataset_info.json"
    info = json.loads(info_path.read_text(encoding="utf-8")) if info_path.exists() else {}
    info["persona_distill"] = {
        "file_name": path.name,
        "formatting": "sharegpt",
        "columns": {"messages": "conversations", "system": "system"},
    }
    info_path.write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"统计: {stats}")
    print(f"写入 {len(rows)} 条 → {path}（保留率 {len(rows) / max(1, args.n):.0%}）")
    for r in rows[:2]:
        for c in r["conversations"]:
            print(f"  [{c['from']}] {c['value'][:50]}")


if __name__ == "__main__":
    main()
