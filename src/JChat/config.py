"""统一配置系统（票据 007）。

config.json（公开） + config.private.json（git 忽略，深度合并覆盖）。
读取优先级：config.json/private 已配置字段 > 环境变量（MEMOKG_* / OPENAI_API_KEY 兜底）> 默认值。
首启在项目根生成 config.json 与 config.example.json（带中文注释）。
"""

from __future__ import annotations

import copy
import json
import logging
import os
from pathlib import Path

logger = logging.getLogger("JChat.config")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = PROJECT_ROOT / "config.json"
PRIVATE_PATH = PROJECT_ROOT / "config.private.json"
EXAMPLE_PATH = PROJECT_ROOT / "config.example.json"

DEFAULT_CONFIG: dict = {
    "llm": {
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-v4-flash-vision-exp",
        "api_key": "",
        "proxy": "",
        "timeout": 100,
        "max_retry": 3,
        "temperature": 0.5,
        "top_p": 1.0,
        "max_tokens": 2048,
    },
    "agent": {"max_iterations": 5},
    "companion": {
        "nickname": "小J",
        "icon": "",
        "persona": "一个活泼幽默、善解人意的桌面搭子，说话简洁自然，偶尔开个玩笑。",
        "avatar_backend": "sprite",
        "avatar_scale": 0.82,
        "random_walk": False,
        "random_chat": False,
        "width": 300,
        "height": 300,
        "shortcut_chat": "Ctrl+Alt+2",
        "proactive_min": 10,
        "proactive_max": 30,
        "quiet_hours_start": 23,
        "quiet_hours_end": 8,
        "reply_ttl_seconds": 30,
        "recall_hints": ["还记得", "上次", "之前", "那天", "我们聊过", "以前", "上次说"],
    },
    "memory": {
        "decay_rate": 0.01,
        "working_window": 10,
        "recall_k": 5,
        "triples_limit": 6,
        "card_budget_tokens": 800,
        "card_memory_ratio": 0.6,
        "window_turns": 20,
        "window_budget_tokens": 3000,
        "window_dedup_threshold": 0.6,
        "memory_dedup_threshold": 0.85,
        "extraction_min_turns": 4,
        "summary_min_turns": 6,
        "summary_max_count": 4,
        "importance_threshold": 3,
    },
    "tools": {
        "working_dir": str(Path.home()),
        "run_timeout": 60,
        "output_limit_bytes": 16384,
        "web_fetch_timeout": 15,
        "web_fetch_max_bytes": 1048576,
    },
    "ui": {"font_size": 14},
}

EXAMPLE_COMMENTS = {
    "llm": "LLM 后端（OpenAI 兼容）。api_key 请填到 config.private.json，勿提交。",
    "companion": "搭子设置。persona 决定说话风格；icon 为 gif 路径；proactive_* 为主动搭话间隔"
    "（分钟）；quiet_hours 为免打扰时段。",
    "memory": "记忆与知识库参数（衰减、记忆卡、窗口、抽取阈值）。",
    "tools": "工具执行边界（工作目录、超时、输出截断）。",
    "ui": "界面字号。",
}


def _deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for key, val in override.items():
        if isinstance(val, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], val)
        else:
            out[key] = val
    return out


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        logger.warning("配置文件 %s 解析失败，忽略", path)
        return {}


def _env_fallback(cfg: dict) -> dict:
    cfg = copy.deepcopy(cfg)
    llm = cfg["llm"]
    if not llm.get("api_key"):
        llm["api_key"] = os.getenv("MEMOKG_API_KEY") or os.getenv("OPENAI_API_KEY", "")
    if not llm.get("base_url"):
        llm["base_url"] = os.getenv("MEMOKG_BASE_URL") or DEFAULT_CONFIG["llm"]["base_url"]
    if not llm.get("model"):
        llm["model"] = os.getenv("MEMOKG_MODEL") or DEFAULT_CONFIG["llm"]["model"]
    return cfg


def _sanitize(cfg: dict) -> dict:
    """类型校验：字段类型不符则回退默认值并告警（票据 007：非法值回退默认）。"""

    NUM = (int, float)

    def check(section: str, key: str, expected: type | tuple):
        got = cfg[section].get(key)
        if got is not None and not isinstance(got, expected):
            logger.warning("config.%s.%s 类型错误（%s），回退默认值", section, key, type(got).__name__)
            cfg[section][key] = copy.deepcopy(DEFAULT_CONFIG[section][key])

    for sec in DEFAULT_CONFIG:
        cfg.setdefault(sec, copy.deepcopy(DEFAULT_CONFIG[sec]))
    for sec, keys in {
        "llm": (str, str, str, str, int, int, NUM, NUM, int),
        "agent": (int,),
        "memory": (NUM, int, int, int, int, NUM, int, int, NUM, NUM, int, int, int, NUM),
    }.items():
        for key, expected in zip(DEFAULT_CONFIG[sec], keys, strict=True):
            check(sec, key, expected)
    for key in ("nickname", "icon", "persona", "shortcut_chat", "avatar_backend"):
        check("companion", key, str)
    check("companion", "avatar_scale", (int, float))
    for key in ("random_walk", "random_chat"):
        check("companion", key, bool)
    for key in ("width", "height", "proactive_min", "proactive_max", "quiet_hours_start",
                "quiet_hours_end", "reply_ttl_seconds"):
        check("companion", key, int)
    for key, expected in {
        "working_dir": str,
        "run_timeout": int,
        "output_limit_bytes": int,
        "web_fetch_timeout": int,
        "web_fetch_max_bytes": int,
    }.items():
        check("tools", key, expected)
    for key, expected in {"font_size": int}.items():
        check("ui", key, expected)
    return cfg


def load_config() -> dict:
    """加载配置：private 覆盖公开配置，环境变量兜底，类型校验。"""
    cfg = _deep_merge(DEFAULT_CONFIG, _read_json(CONFIG_PATH))
    cfg = _deep_merge(cfg, _read_json(PRIVATE_PATH))
    cfg = _env_fallback(cfg)
    cfg = _sanitize(cfg)
    if _read_json(CONFIG_PATH).get("llm", {}).get("api_key"):
        logger.warning("检测到 api_key 出现在公开 config.json，建议移入 config.private.json")
    return cfg


def ensure_default_configs() -> None:
    """首启生成 config.json（默认值）与 config.example.json（带注释）。"""
    if not CONFIG_PATH.exists():
        CONFIG_PATH.write_text(json.dumps(DEFAULT_CONFIG, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("已生成默认配置 %s", CONFIG_PATH)
    if not EXAMPLE_PATH.exists():
        commented = copy.deepcopy(DEFAULT_CONFIG)
        for sec, note in EXAMPLE_COMMENTS.items():
            commented[sec] = {"_comment": note, **commented[sec]}
        EXAMPLE_PATH.write_text(json.dumps(commented, ensure_ascii=False, indent=2), encoding="utf-8")
