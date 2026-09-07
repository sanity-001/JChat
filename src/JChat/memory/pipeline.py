"""记忆管线阶段化（开源接缝③，docs/system.md §6）。

滚动整理阶段的统一骨架：以"消息数水位线"跟踪已整理进度，每轮回复后检查
新增消息是否达到阈值，达标则把"上次水位线 → 阶段边界"的块提交到后台队列。

现有阶段：
- extract（滚动抽取）：边界=最新消息，产出记忆卡+三元组，随后 consolidate
- summary（摘要带）：边界=滚动窗口前沿（只压已滑出的消息），产出生活轨迹

未来新阶段（如按周汇总、图谱沉淀）= 一个 RollingStage 实例 + run 函数。
"""

from __future__ import annotations

from collections.abc import Callable


class RollingStage:
    """以水位线驱动的后台记忆整理阶段。

    min_turns_key 读自 config["memory"]（设置变更即时生效）；
    bound(app, transcript) 返回本阶段当前的覆盖边界（消息条数索引）；
    run(block) 由宿主以绑定方法/闭包提供，在 LLMQueue worker 线程中执行（priority=2）。
    """

    def __init__(
        self,
        name: str,
        min_turns_key: str,
        bound: Callable[[object, list[dict]], int],
        run: Callable[[list[dict]], None],
    ):
        self.name = name
        self.min_turns_key = min_turns_key
        self._bound = bound
        self._run = run
        self.watermark = 0

    def maybe_submit(self, app, transcript: list[dict]) -> None:
        end = min(self._bound(app, transcript), len(transcript))
        if end <= self.watermark:
            return
        block = transcript[self.watermark:end]
        if len(block) // 2 < app.config["memory"][self.min_turns_key]:
            return
        app.queue.submit(2, lambda: self._run(list(block)))
        self.watermark = end
