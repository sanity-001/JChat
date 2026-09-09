"""按键说话录音：sounddevice（PortAudio）采集 16k mono int16。

toggle 语义：按快捷键开始，再按结束（组合键的按下/释放跟踪不可靠，用开关式）。
"""

from __future__ import annotations

import threading

import numpy as np

try:
    import sounddevice as sd
except Exception:  # noqa: BLE001 - voice extra 未安装
    sd = None


class Recorder:
    def __init__(self, sample_rate: int = 16000) -> None:
        self._rate = sample_rate
        self._stream = None
        self._chunks: list[np.ndarray] = []
        self._lock = threading.Lock()

    def recording(self) -> bool:
        return self._stream is not None

    def start(self) -> bool:
        if sd is None or self.recording():
            return False

        def _cb(indata, frames, _time, _status):
            with self._lock:
                self._chunks.append(indata.copy())

        self._chunks = []
        self._stream = sd.InputStream(
            samplerate=self._rate, channels=1, dtype="int16", callback=_cb
        )
        self._stream.start()
        return True

    def stop(self) -> list[int]:
        """停止并返回 int16 采样数组；未在录音返回空。"""
        if self._stream is None:
            return []
        self._stream.stop()
        self._stream.close()
        self._stream = None
        with self._lock:
            chunks = self._chunks
            self._chunks = []
        if not chunks:
            return []
        return np.concatenate(chunks).ravel().tolist()
