"""设置面板（含记忆列表：查看/删除/手动添加，票据 005）。"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from JChat.memory.memory import AgentMemory


class SettingsDialog(QDialog):
    def __init__(self, config: dict, memory: AgentMemory, parent=None):
        super().__init__(parent)
        self.config = config
        self.memory = memory
        self.setWindowTitle("设置")
        self.setMinimumSize(560, 560)
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        c = self.config["companion"]

        grid = QGridLayout()
        grid.addWidget(QLabel("昵称"), 0, 0)
        self.nickname = QLineEdit(c["nickname"])
        grid.addWidget(self.nickname, 0, 1)
        grid.addWidget(QLabel("人格"), 1, 0)
        self.persona = QLineEdit(c["persona"])
        grid.addWidget(self.persona, 1, 1)
        grid.addWidget(QLabel("API Key"), 2, 0)
        self.api_key = QLineEdit(self.config["llm"].get("api_key", ""))
        self.api_key.setEchoMode(QLineEdit.Password)
        grid.addWidget(self.api_key, 2, 1)
        root.addLayout(grid)

        self.walk_chk = QCheckBox("随机走动")
        self.walk_chk.setChecked(c["random_walk"])
        self.proactive_chk = QCheckBox("主动搭话")
        self.proactive_chk.setChecked(c["random_chat"])
        root.addWidget(self.walk_chk)
        root.addWidget(self.proactive_chk)

        # ---- 语音
        root.addWidget(QLabel("语音（开启后用快捷键/麦克风按钮说话，回复会读出来）"))
        self.voice_chk = QCheckBox("启用语音")
        self.voice_chk.setChecked(c.get("voice_enabled", False))
        root.addWidget(self.voice_chk)
        vgrid = QGridLayout()
        vgrid.addWidget(QLabel("说话快捷键"), 0, 0)
        self.voice_hotkey = QLineEdit(c.get("voice_hotkey", "ctrl+alt+1"))
        vgrid.addWidget(self.voice_hotkey, 0, 1)
        vgrid.addWidget(QLabel("参考音频"), 1, 0)
        self.voice_ref = QLineEdit(c.get("voice_ref_audio", ""))
        self.voice_ref.setPlaceholderText("GPT-SoVITS 参考音频 wav/mp3 路径")
        vgrid.addWidget(self.voice_ref, 1, 1)
        vgrid.addWidget(QLabel("参考音频内容"), 2, 0)
        self.voice_ref_text = QLineEdit(c.get("voice_ref_text", ""))
        self.voice_ref_text.setPlaceholderText("参考音频里说的那句话（一字不差）")
        vgrid.addWidget(self.voice_ref_text, 2, 1)
        vgrid.addWidget(QLabel("GPT-SoVITS 地址"), 3, 0)
        self.gptsovits_url = QLineEdit(c.get("gptsovits_url", "http://127.0.0.1:9880"))
        vgrid.addWidget(self.gptsovits_url, 3, 1)
        vgrid.addWidget(QLabel("兜底音色"), 4, 0)
        self.tts_fallback = QLineEdit(c.get("tts_fallback_voice", "zh-CN-XiaoyiNeural"))
        vgrid.addWidget(self.tts_fallback, 4, 1)
        self.wake_chk = QCheckBox("免提模式（常驻监听，说话需先喊唤醒词）")
        self.wake_chk.setChecked(c.get("voice_wake_enabled", False))
        root.addWidget(self.wake_chk)
        vgrid.addWidget(QLabel("唤醒词"), 5, 0)
        self.wake_word = QLineEdit(c.get("voice_wake_word", "维维美"))
        vgrid.addWidget(self.wake_word, 5, 1)
        vgrid.addWidget(QLabel("收音灵敏度"), 6, 0)
        self.rms_threshold = QLineEdit(str(c.get("voice_rms_threshold", 0.01)))
        self.rms_threshold.setPlaceholderText("RMS 阈值 0.01（太灵改大，听不见改小）")
        vgrid.addWidget(self.rms_threshold, 6, 1)
        root.addLayout(vgrid)

        # ---- 记忆管理
        root.addWidget(QLabel("记忆管理（长期记忆：关于你的事实）"))
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["内容", "分数", "层级"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(0, 300)
        self._reload_memories()
        root.addWidget(self.table)

        add_row = QHBoxLayout()
        self.new_mem = QLineEdit()
        self.new_mem.setPlaceholderText("添加一条记忆…（如：用户偏好向量数据库）")
        self.mem_importance = QSpinBox()
        self.mem_importance.setRange(1, 10)
        self.mem_importance.setValue(5)
        add_row.addWidget(self.new_mem, stretch=1)
        add_row.addWidget(self.mem_importance)
        add_btn = QPushButton("添加")
        add_btn.setObjectName("Ghost")
        add_btn.clicked.connect(self._add_memory)
        add_row.addWidget(add_btn)
        del_btn = QPushButton("删除选中")
        del_btn.setObjectName("Danger")
        del_btn.clicked.connect(self._delete_memory)
        add_row.addWidget(del_btn)
        root.addLayout(add_row)

        save_btn = QPushButton("保存")
        save_btn.setObjectName("Send")
        save_btn.clicked.connect(self._save)
        root.addWidget(save_btn)

    def _reload_memories(self) -> None:
        rows = self.memory.state()
        self.table.setRowCount(len(rows))
        for i, m in enumerate(rows):
            self.table.setItem(i, 0, QTableWidgetItem(m["content"]))
            self.table.setItem(i, 1, QTableWidgetItem(f"{m['score']:.2f}"))
            self.table.setItem(i, 2, QTableWidgetItem(m["scope"]))

    def _add_memory(self) -> None:
        text = self.new_mem.text().strip()
        if text:
            self.memory.remember(text, importance=float(self.mem_importance.value()))
            self.new_mem.clear()
            self._reload_memories()

    def _delete_memory(self) -> None:
        selected = self.table.selectionModel().selectedRows()
        ids = [self.memory.state()[i.row()]["memory_id"] for i in selected]
        self.memory.store.delete_memories(ids)
        self._reload_memories()

    def _save(self) -> None:
        c = self.config["companion"]
        c["nickname"] = self.nickname.text()
        c["persona"] = self.persona.text()
        c["random_walk"] = self.walk_chk.isChecked()
        c["random_chat"] = self.proactive_chk.isChecked()
        c["voice_enabled"] = self.voice_chk.isChecked()
        c["voice_hotkey"] = self.voice_hotkey.text().strip()
        c["voice_ref_audio"] = self.voice_ref.text().strip()
        c["voice_ref_text"] = self.voice_ref_text.text().strip()
        c["gptsovits_url"] = self.gptsovits_url.text().strip()
        c["tts_fallback_voice"] = self.tts_fallback.text().strip()
        c["voice_wake_enabled"] = self.wake_chk.isChecked()
        c["voice_wake_word"] = self.wake_word.text().strip()
        try:
            c["voice_rms_threshold"] = float(self.rms_threshold.text().strip() or 0.01)
        except ValueError:
            c["voice_rms_threshold"] = 0.01
        self.config["llm"]["api_key"] = self.api_key.text()
        self.accept()
