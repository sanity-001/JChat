# JChat 项目规则

## Git 提交（强制）

- **每次修改或功能添加后，必须提交到 git**（提交信息用中文简述改动）
- git 不在 PATH 中，路径为：`D:\Tool\git\Git\cmd\git.exe`
- 提交前检查 `git status` / `git diff`，不要提交机密：`config.private.json`、api_key、`*.sqlite`
- 不要主动 push / 创建分支，除非用户明确要求

## 项目结构

- `src/JChat/` — 主包：`app.py`（入口整合）、`agent/`（循环/工具/抽取/prompt）、`memory/`（合并的 MemoKG）、`ui/`（PySide6）、`llm/`（OpenAI 兼容客户端）
- `wayfinder/` — 路线图与决策票据（local-markdown tracker，**不入库**）
- `prototypes/` — 原型（丢弃件，勿移入生产代码）
- `tests/`、`research/` — 测试与前期调研（**不入库**）
- 域词汇表见 `CONTEXT.md`（术语用"搭子/伙伴"，禁用"桌宠"）

## 常用命令

```powershell
uv run python -m JChat        # 启动
uv run --with pytest pytest   # 测试
uv run --with ruff ruff check src tests   # lint
```

## 约定

- Python 3.12（uv 管理）；PySide6 锁定 6.8.3（6.11 在此机器 DLL 不兼容，勿升级）
- 配置：`config.json`（公开）+ `config.private.json`（git 忽略，api_key 只放这里）
- 无沙箱：`run_python` 可访问本地文件与网络（个人本地工具，免责）
