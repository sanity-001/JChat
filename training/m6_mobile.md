# M6：手机端验证（Android）

目标：用手机跑微调后的模型，完成 3 轮对话（截图留证）。

模型：`models/jchat-1.7b-Q4_K_M.gguf`（1.06GB，Q5_K_M 是 PC 用；手机用 Q4 省内存）

## 路线 A（推荐，5 分钟，零命令行）

1. **装 App**：Google Play / F-Droid 搜 **PocketPal AI**（开源，直接支持 GGUF）
   - 备选：**ChatterUI**（Android，同样支持 GGUF）
2. **传模型到手机**：USB 连接 → 拷贝 `jchat-1.7b-Q4_K_M.gguf` 到手机 `Download/` 目录
3. **导入模型**：App 内 → Models → Add local model → 选该 gguf
4. **设系统提示词**（关键，人设靠它）：
   ```
   你是维维美，明日方舟维什戴尔的Q版化身，毒舌嘴硬心软的桌面搭子。
   称呼用户"伙计"，说话短，常带"哈？""啧""哼""嘻嘻"，把干活说成"大扫除"。
   禁说"作为AI""很高兴帮你"。不要说教，不要煽情。
   ```
5. **跑 3 轮对话**（验证人设 + 常识 + 连贯）：
   - 第 1 轮：`你好呀`
   - 第 2 轮：`今天好累啊`
   - 第 3 轮：`那你说说我该干嘛`
6. **截图**保存到 `research/m6_mobile_*.png`

## 路线 B（命令行，Termux）

1. Termux 安装（F-Droid 版）
2. 从 llama.cpp releases 下载对应 build 的 `android-arm64` 包（如 b11147 的 "Android arm64 (CPU)"）
3. `pkg install -y && termux-setup-storage`，把二进制与 gguf 推到手机
4. 运行：
   ```bash
   ./llama-cli -m jchat-1.7b-Q4_K_M.gguf -p "<系统提示词>\n用户：你好呀\n维维美：" -n 80
   ```

## 验收标准（票据 005 / M6）

- [ ] 手机完成 3 轮对话
- [ ] 回复是人设口吻（短句 + 口癖，无助手腔）
- [ ] 截图留证

## 已知约束

- 1.7B Q4_K_M 约 1.06GB，中端手机 4-8GB RAM 可跑（PocketPal 会按可用内存配置上下文）
- 若内存吃紧：App 内把 context 降到 2048；或改用更小模型（0.6B 蒸馏版导出 GGUF 亦可，本仓库已训出 LoRA 但未导出）
