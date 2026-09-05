---
id: 8
title: 工具执行边界
type: grilling
status: closed
blocked_by: [1]
assignee: opencode
resolved: 2026-09-05
---

## Question

6 个工具（run_python / read_file / write_file / list_files / web_fetch / remember）的执行边界细节（Q13 已定：无沙箱、个人本地工具）：

1. **run_python**：工作目录（项目目录？用户指定？）、超时（秒）、输出截断（KB）、是否允许访问网络/文件系统（无沙箱但要不要限制包）
2. **文件工具**：读写路径是否限定在某个根目录（如 ~/JChat 工作区）？还是全盘自由？
3. **web_fetch**：请求超时、响应大小上限、是否只允许 http/https
4. **remember**：与记忆卡的关系（主动写的条目 importance 默认值）
5. 工具结果回灌格式（截断规则、错误信息格式）——影响 agent 决策质量

依赖票据 1 确认模型支持 function calling 后决议。

## Resolution

诘问一轮定案（2026-09-05）：

1. **run_python**：工作目录固定 `config.tools.working_dir`（默认 `~`），网络/第三方包完全自由（无沙箱，与 Q13 一致）；超时 60s（kill 并报 `[Error] Timeout after 60s`），输出/stderr 合并截断 16KB
2. **文件工具**：全盘自由读写/列表，write 操作记日志；无路径限制
3. **web_fetch**：超时 15s、上限 1MB、仅 http/https（拒绝 file:// 等本地协议）；返回剥标签的纯文本
4. **remember**：importance 可选默认 3；主动写入不受抽取阈值 ≥3 限制（高置信信号）
5. **回灌格式**：成功 `[工具名] <输出>`（超限截断标记）；失败 `[工具名] [Error] <类型: 消息>`；耗时/路径等元信息只进 UI 卡片不混入回灌文本；完整输出 agent 可用 read_file 补读
6. **扩展方式**：工具注册表模式（name + JSON schema + 执行函数），新增工具只注册即可，无额外接口预留——地图 fog"工具扩展接口预留"由此澄清并移除
