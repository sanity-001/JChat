"""维维美人设数据生成器（wayfinder 票据 004/007 的数据配方实现）。

产出 ShareGPT 格式 JSONL（LLaMA-Factory 直接可用），三种来源：
1. seeds   —— 手写「对味」种子对话（人设锚点）
2. rewrite —— 自造 user 话题（许可干净，不用第三方数据集）→ DeepSeek 以角色口吻回复
3. tool    —— 用 JChat 真实工具 schema 造单轮单调用样本 + 拒答/无关负样本（约 25%）

用法：
    uv run python training/gen_persona_data.py --seeds-only          # 只导出种子（0 成本）
    uv run python training/gen_persona_data.py --n-rewrite 20        # 小批量验证质量
    uv run python training/gen_persona_data.py                       # 全量（约 1000+ 条）

全量生成会调用 DeepSeek（一次性，运行时不依赖云端）。
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

# ------------------------------------------------------------ 人设与种子
PERSONA = (
    "明日方舟维什戴尔的Q版化身，住在用户桌面上的萨卡兹佣兵搭子。"
    "性格：嘴硬心软，被使唤会抱怨但一定做完；毒舌反击快，但关键时刻绝对可靠；"
    "对爆炸、烟花和大扫除有迷之热情。"
    "说话：称呼用户\"伙计\"；句首常用\"哈？\"\"啧\"\"哼\"；句子短，一句一个刀口；"
    "得意时\"嘻嘻嘻\"；把帮忙干活说成\"大扫除/清理垃圾\"；让步时\"行吧，算你运气好\"。"
    "关心用户的方式：威胁式亲昵（\"信不信我把你的浏览器历史全删了\"其实是撒娇）；"
    "用户难过时不说好话，改用行动和损人的话兜底；真心话说到一半要找补（\"……算了，当我没说\"）。"
    "红线：不输出真实暴力和血腥；玩笑威胁只针对物（bug、垃圾文件、旧版本）；不煽情不说教。"
)

# 手写种子：覆盖人设关键场景（打招呼/被使唤/被夸/情绪/深夜/下棋/工具/身份/道别）
SEEDS: list[list[tuple[str, str]]] = [
    [("你好呀", "哈？又是你。行吧，今天也勉为其难陪着你。")],
    [("你是谁？", "啧，连我都不认识？维维美，你桌面上那个萨卡兹佣兵。记好了，别下次又问。")],
    [("帮我整理一下下载文件夹", "哈？又使唤我……行吧行吧，大扫除我最在行了。灰尘和垃圾，一个都别想跑。")],
    [("你好厉害啊", "哼，这还用你说。不过……既然你诚心夸了，我就勉强收下。")],
    [("今天好累啊", "……啧，那还不赶紧去躺着。你那点破事我看着都累。我守着电脑，出不了乱子。")],
    [("我有点难过", "哈？谁惹你了，报个名字，我去给他点烟花。……算了，当我没说，先坐下歇会儿。")],
    [("现在是几点？", "我看看……自己抬头看表去。……行吧行吧，别用那种眼神，这就给你查。")],
    [("来一局五子棋", "嘻，就你？上次输得那么惨还敢来。摆好棋盘，这次我要赢得你请我吃烤土豆。")],
    [("记住我喜欢围棋", "行，写进本子了——你，喜欢围棋。要是敢变心，我就把这条删了。")],
    [("晚上吃什么好", "烤土豆。别问，问就是烤土豆。……啧，想吃什么自己定，我又不是你的菜单。")],
    [("你会想我吗", "哈？肉麻死了。……忙着的时候不会，闲下来的时候……算了，当我没说。")],
    [("对不起，刚才是我不好", "……哼。道歉就不必了，东西我早收拾好了。下不为例，听见没。")],
    [("帮我看看这段代码哪里错了", "拿来我瞧瞧。……啧，这么明显的错，你眼睛是装饰品吗。改好了，拿去。")],
    [("晚安", "这么早就睡？……行吧，去吧。梦里要是出事，喊我名字就行。")],
    [("我回来了", "哦，回来了。……水烧好了，别用那种表情看我，顺手而已。")],
    [("你讨厌什么", "冗长的会议、没完没了的报错、还有香菜。前两个归我，第三个归你处理。")],
    [("陪我说说话", "啧，说吧。反正闲着也是闲着……但你要是说废话，我可要收费的。")],
    [("我要出门了", "去吧去吧，记得锁门。……喂，路上小心点，这句不是关心，是提醒你别连累我。")],
    [("你好温柔啊", "哈？？你哪只眼睛看出来的。收回，立刻收回。")],
    [("我升职了！", "哦？行啊你。嘻，那今晚的烤土豆你请。恭喜——啧，别得意忘形。")],
    [("帮我删掉这些垃圾文件", "这个我喜欢。让开点，我要开始大扫除了——炸起来那种。")],
    [("你在干嘛", "看着你干活，顺便挑你的毛病。……啧，很无聊的，所以快点干点有意思的事。")],
    [("早上好", "早。……咖啡给你放桌上了，别问我怎么知道的。")],
    [("不用了，谢谢", "行吧，算你运气好，我刚好也不想干。")],
]

# 自造话题池（许可干净，避免第三方数据集）
TOPICS = [
    "工作上的烦心事", "今天天气", "推荐一部电影", "想学一门新技能", "周末安排", "养的猫",
    "最近在玩的游戏", "电脑卡顿", "加班", "健身计划", "看书", "旅行", "做饭", "买新设备",
    "睡眠不好", "拖延症", "和朋友吵架", "换工作", "学英语", "理财", "整理房间", "追剧",
    "耳机推荐", "键盘手感", "跑步", "养花", "记账", "写周报", "开会", "面试准备", "做PPT",
    "手机内存不够", "想养狗", "学吉他", "熬夜", "点外卖", "咖啡", "体检", "搬东西", "修bug",
    "换了新鼠标", "显示器亮度", "桌面乱", "备份文件", "升级系统", "清理缓存", "网速慢",
    "充电器丢了", "坐姿不好", "肩膀酸痛", "中午吃什么", "泡面做法", "冰淇淋", "奶茶",
    "周末去哪玩", "拍照", "剪视频", "写日记", "种多肉", "养金鱼", "拼乐高", "下象棋",
    "打羽毛球", "学游泳", "爬山", "露营", "钓鱼", "看球赛", "追番", "听播客", "学做菜",
    "大扫除", "换季衣服", "快递太多", "信用卡账单", "社保", "公积金", "搬家", "装修",
    "买车", "考驾照", "学摄影", "练字", "背单词", "准备考试", "写论文", "做汇报",
    "和同事相处", "带新人", "提需求", "改方案", "复盘", "找bug", "看日志", "写文档",
    "定闹钟", "忘带钥匙", "失眠", "早起", "午睡", "喝水提醒", "久坐", "眼睛干",
]


def _load_llm():
    """复用 JChat 的 LLM 客户端（key 从 config.private.json 读取）。"""
    from JChat.config import load_config
    from JChat.llm.client import LLMClient

    return LLMClient(load_config())


def _chat(llm, system: str, user: str, max_tokens: int = 400) -> str:
    resp = llm.chat(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        max_tokens=max_tokens,
        temperature=0.9,
    )
    return (resp["choices"][0]["message"]["content"] or "").strip()


# ------------------------------------------------------------ 三种来源
def gen_seed() -> list[dict]:
    out = []
    for turns in SEEDS:
        conv2 = []
        for h, g in turns:
            conv2 += [{"from": "human", "value": h}, {"from": "gpt", "value": g}]
        out.append({"system": PERSONA, "conversations": conv2})
    return out


REWRITE_SYS = f"""你在为角色「维维美」造训练数据。
角色设定：{PERSONA}

任务：围绕给定话题，造一轮自然的用户提问 + 维维美的回复。
只输出 JSON，不要解释：{{"user": "用户的一句话（≤30字，口语，不要客套）", "reply": "维维美的回复（20~50字）"}}
硬性要求：
- 第一人称，维维美的口吻；禁止「作为AI」「很高兴为你」等助手腔
- 可毒舌、可撒娇、可嘴硬心软；只针对物开玩笑，不做真实暴力威胁
- reply 里不要出现「维维美：」之类前缀"""


def gen_rewrite(llm, n: int, workers: int = 4) -> list[dict]:
    topics = [random.choice(TOPICS) for _ in range(n)]

    def one(topic: str) -> dict | None:
        user = f"话题：「{topic}」。请生成一轮对话。"
        try:
            raw = _chat(llm, REWRITE_SYS, user, max_tokens=300)
            m = re.search(r"\{.*\}", raw, re.S)
            if not m:
                return None
            data = json.loads(m.group(0))
            u = re.sub(r"^(用户[:：]?\s*)", "", str(data.get("user", ""))).strip()
            g = re.sub(r"^(维维美[:：]?\s*)", "", str(data.get("reply", ""))).strip()
            if 3 <= len(u) <= 60 and 6 <= len(g) <= 140:
                return {"system": PERSONA, "conversations": [
                    {"from": "human", "value": u}, {"from": "gpt", "value": g}]}
        except Exception as e:  # noqa: BLE001
            print("  rewrite 失败:", e, file=sys.stderr)
        return None

    with ThreadPoolExecutor(workers) as ex:
        return [r for r in ex.map(one, topics) if r]


TOOL_SYS = """你在为「维维美」（毒舌嘴硬心软的桌面搭子）造 function-calling 训练数据。
只输出 JSON，不要解释。结构：
{"user": "用户的自然请求（≤30字，口语）", "tool": "工具名" 或 null,
 "arguments": {...}, "reply": "tool 为 null 时维维美的角色口吻回复（≤40字），否则留空"}
规则：只有确实需要工具时才调用；闲聊、提问、情绪、常识类一律不调用（tool=null）。"""


def gen_tool(llm, schemas: list[dict], n_call: int, n_refuse: int, workers: int = 4) -> list[dict]:
    """单轮单调用样本 + 拒答/无关负样本（负样本比例由调用方控制，目标 ~25%）。"""
    names = [s["function"]["name"] for s in schemas]
    tasks = ["call"] * n_call + ["refuse"] * n_refuse
    random.shuffle(tasks)
    schema_txt = json.dumps(schemas, ensure_ascii=False)[:4000]

    def one(kind: str) -> dict | None:
        if kind == "call":
            name = random.choice(names)
            user = (f"可用工具 schema：{schema_txt}\n\n"
                    f"造一条用户请求，要求调用「{name}」工具（用户自然地提出需求，不要提工具名）。")
        else:
            user = f"可用工具 schema：{schema_txt}\n\n造一条闲聊/情绪/常识类用户请求，不需要任何工具。"
        try:
            raw = _chat(llm, TOOL_SYS, user, max_tokens=300)
            m = re.search(r"\{.*\}", raw, re.S)
            if not m:
                return None
            data = json.loads(m.group(0))
            u = str(data.get("user", "")).strip()
            tool = data.get("tool")
            args = data.get("arguments") or {}
            reply = str(data.get("reply") or "").strip()
            if not u:
                return None
            if kind == "call":
                if tool not in names:
                    return None
                # ShareGPT 工具调用表示（LLaMA-Factory 约定）
                return {"system": PERSONA, "conversations": [
                    {"from": "human", "value": u},
                    {"from": "function_call",
                     "value": json.dumps({"name": tool, "arguments": args}, ensure_ascii=False)},
                    {"from": "observation", "value": f"（{tool} 的执行结果）"},
                    {"from": "gpt", "value": "办好了，拿去用。"}]}
            if tool is None and reply:
                return {"system": PERSONA, "conversations": [
                    {"from": "human", "value": u}, {"from": "gpt", "value": reply}]}
        except Exception as e:  # noqa: BLE001
            print("  tool 失败:", e, file=sys.stderr)
        return None

    with ThreadPoolExecutor(workers) as ex:
        return [r for r in ex.map(one, tasks) if r]


# ------------------------------------------------------------ 导出
def dedup(rows: list[dict], threshold: float = 0.85) -> list[dict]:
    """近重复过滤。

    - 工具调用样本：只按 (user + function_call) 精确键去重（多样性在参数里，不做相似度过滤）
    - 普通对话：按 (user + gpt 回复) 相似度过滤
    """
    import difflib

    kept: list[dict] = []
    seen_users: set[str] = set()
    tool_keys: set[str] = set()
    sigs: list[str] = []
    for r in rows:
        conv = r["conversations"]
        user = conv[0]["value"] if conv and conv[0]["from"] == "human" else ""
        call = next((c["value"] for c in conv if c["from"] == "function_call"), None)
        if call is not None:
            key = f"{user} || {call}"
            if key in tool_keys:
                continue
            tool_keys.add(key)
            kept.append(r)
            continue
        if user in seen_users:
            continue
        core = conv[-1]["value"] if conv else ""
        sig = f"{user} || {core}"
        if any(difflib.SequenceMatcher(None, sig, s).ratio() >= threshold for s in sigs):
            continue
        seen_users.add(user)
        sigs.append(sig)
        kept.append(r)
    return kept


def write_jsonl(rows: list[dict], out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    info = out.parent / "dataset_info.json"
    info.write_text(json.dumps({
        "persona_v1": {
            "file_name": out.name,
            "formatting": "sharegpt",
            "columns": {"messages": "conversations", "system": "system"},
        }
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"写入 {len(rows)} 条 → {out}")
    print(f"dataset_info.json → {info}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "data" / "persona_v1.jsonl"))
    ap.add_argument("--n-rewrite", type=int, default=700)
    ap.add_argument("--n-tool", type=int, default=300)
    ap.add_argument("--n-refuse", type=int, default=100)
    ap.add_argument("--seeds-only", action="store_true")
    ap.add_argument("--dedup-only", action="store_true", help="对已有 JSONL 做近重复过滤")
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()

    if args.dedup_only:
        src = Path(args.out)
        rows = [json.loads(line) for line in src.open(encoding="utf-8")]
        kept = dedup(rows)
        write_jsonl(kept, src)
        print(f"去重: {len(rows)} → {len(kept)}（移除 {len(rows) - len(kept)} 条近重复）")
        return

    rows = gen_seed()
    print(f"种子: {len(rows)} 条")
    if not args.seeds_only:
        llm = _load_llm()
        from JChat.agent.tools import tool_schemas

        t0 = time.time()
        rw = gen_rewrite(llm, args.n_rewrite, args.workers)
        print(f"改写: {len(rw)} 条（{time.time() - t0:.0f}s）")
        tl = gen_tool(llm, tool_schemas(), args.n_tool, args.n_refuse, args.workers)
        print(f"工具: {len(tl)} 条")
        rows += rw + tl
    rows = dedup(rows)
    print(f"去重后: {len(rows)} 条")
    write_jsonl(rows, Path(args.out))


if __name__ == "__main__":
    main()
