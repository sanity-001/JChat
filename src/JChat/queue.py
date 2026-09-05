"""单 worker LLM 队列（票据 009）：同一时间只发一个请求，优先级 用户聊天 > 主动搭话 > 记忆抽取。"""

from __future__ import annotations

import heapq
import threading
from dataclasses import dataclass, field


@dataclass(order=True)
class _Job:
    priority: int
    seq: int = field(compare=False)
    fn: object = field(compare=False)


class LLMQueue:
    """优先级队列：数字越小优先级越高。用户聊天=0，主动搭话=1，抽取=2。"""

    def __init__(self, workers: int = 1):
        self._heap: list[_Job] = []
        self._lock = threading.Lock()
        self._cv = threading.Condition(self._lock)
        self._seq = 0
        self._stopped = False
        for _ in range(workers):
            threading.Thread(target=self._run, daemon=True).start()

    def submit(self, priority: int, fn) -> None:
        with self._cv:
            self._seq += 1
            heapq.heappush(self._heap, _Job(priority, self._seq, fn))
            self._cv.notify()

    def _run(self) -> None:
        while True:
            with self._cv:
                while not self._heap and not self._stopped:
                    self._cv.wait()
                if self._stopped and not self._heap:
                    return
                job = heapq.heappop(self._heap)
            try:
                job.fn()
            except Exception:  # noqa: BLE001
                import logging

                logging.getLogger("JChat.queue").exception("job failed")
