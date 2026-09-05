# Local-Markdown Tracker 约定

本项目未配置外部 issue tracker，按 wayfinder 流程使用本地 Markdown 追踪器。

## 结构

```
wayfinder/
├── README.md            # 本文件（追踪器约定）
├── map.md               # 地图（label: wayfinder:map）—— 唯一权威制品
└── tickets/
    ├── NNN-slug.md      # 开放票据
    └── closed/          # 已关闭票据（决议后移入，或保留原地标注 status: closed）
```

## 票据格式

```markdown
---
id: 1
title: 票据标题
type: research | prototype | grilling | task
status: open | closed | out-of-scope
blocked_by: []        # 阻塞方 id 列表（数字）
---

## Question

<该票据要决议的问题，控制在一次 100K token 会话内>
```

## Wayfinding 操作（本仓库的表达方式）

- **创建地图**：写 `wayfinder/map.md`，frontmatter 含 `label: wayfinder:map`
- **创建票据**：`wayfinder/tickets/NNN-slug.md`，作为地图的子项（文件级关联：地图 Decisions 区引用其路径）
- **接线**：票据创建后，用 `blocked_by` 前置字段互相引用（第二次遍历）
- **Claim**：frontmatter 加 `assignee: <dev>`，在开始工作前完成
- **阻塞**：`blocked_by` 中所有票据 status 为 closed 才解锁
- **Frontier**：status=open 且无未关闭阻塞方的票据（即当前可取的）
- **决议记录**：在票据 body 末尾追加 `## Resolution` 段落，将 status 改为 `closed`，并在 `map.md` 的 Decisions so far 追加一行（标题 + 链接 + 一句话要点）
- **范围外**：status 改为 `out-of-scope`，在 map.md 的 Out of scope 区留一行
- **研究类票据**：由子代理调用 research 技能解决，成果落在 `research/NNN-<name>.md`，票据 Resolution 中链接该文件
