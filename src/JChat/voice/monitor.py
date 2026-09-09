"""常驻语音监听（唤醒词 + 实时打断）。

- 能量 VAD：RMS 阈值（无需额外模型；近场麦克风够用）
- 发声中（TTS 播放）：检测到持续说话 ≥320ms → 停止播放（实时打断）
- 空闲中：说话→静音 800ms 判定一句话结束 → ASR 转写 → 唤醒词门控 → 进对话
- 与按键说话互斥：录音时暂停监听，结束后恢复
"""

from __future__ import annotations

import logging
import threading

import numpy as np

try:
    import sounddevice as sd
except Exception:  # noqa: BLE001
    sd = None

logger = logging.getLogger("JChat.voice.monitor")

# 帧参数：100ms 一帧（16k → 1600 采样）
FRAME_MS = 100
SPEECH_FRAMES_BARGE = 3   # 发声中：连续 300ms 有声 → 打断
SIL_FRAMES_END = 8        # 空闲中：连续 800ms 无声 → 一句话结束
MIN_SPEECH_FRAMES = 4     # 少于 400ms 的"说话"当作噪声丢弃


class VoiceMonitor:
    def __init__(self, controller) -> None:
        self.c = controller
        self.stream = None
        self._lock = threading.Lock()
        self._reset()

    def _reset(self) -> None:
        self._in_speech = False
        self._speech_run = 0
        self._sil_run = 0
        self._buf: list[np.ndarray] = []

    def running(self) -> bool:
        return self.stream is not None

    def start(self) -> bool:
        if sd is None or self.running():
            return False

        def _cb(indata, frames, _time, _status):
            try:
                self._feed(indata)
            except Exception as e:  # noqa: BLE001
                logger.warning("监听回调异常：%s", e)

        self._reset()
        self.stream = sd.InputStream(
            samplerate=16000, channels=1, dtype="int16",
            blocksize=160, callback=_cb,
        )
        self.stream.start()
        logger.info("常驻监听已开启（唤醒词：%r）", self.config().get("voice_wake_word"))
        return True

    def stop(self) -> None:
        if self.stream is None:
            return
        self.stream.stop()
        self.stream.close()
        self.stream = None
        self._reset()

    def config(self) -> dict:
        return self.c.config["companion"]

    # ------------------------------------------------------------ 状态机
    def _feed(self, indata) -> None:
        rms = float(np.sqrt(np.mean(indata.astype(np.float32) ** 2))) / 32768.0
        threshold = float(self.config().get("voice_rms_threshold", 0.01))
        voiced = rms > threshold

        if self.c.is_playing():
            # barge-in：播放中持续有声 → 停止播放（本次发声期间不再转写）
            if voiced:
                self._speech_run += 1
                if self._speech_run >= SPEECH_FRAMES_BARGE:
                    self._speech_run = 0
                    self._barge_hit = True
                    self.app_stop_speaking()
            else:
                self._speech_run = 0
            return

        if voiced:
            self._sil_run = 0
            if not self._in_speech:
                self._in_speech = True
                self._buf = []
            self._buf.append(indata.copy())
        elif self._in_speech:
            self._sil_run += 1
            self._buf.append(indata.copy())  # 保留句尾余音
            if self._sil_run >= SIL_FRAMES_END:
                self._in_speech = False
                audio = self._buf
                self._buf = []
                self._reset()
                if len(audio) >= MIN_SPEECH_FRAMES:
                    samples = np.concatenate(audio).ravel().tolist()
                    self.app_queue_transcribe(samples)

    def app_stop_speaking(self) -> None:
        self.c.app.ui_task.emit(self.c._stop_player)

    def app_queue_transcribe(self, samples: list[int]) -> None:
        self.c.app.queue.submit(0, lambda: self.c._transcribe_worker(samples, from_monitor=True))
