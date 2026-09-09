"""语音轮控制器：录音 toggle → ASR → 文字管线 → 发声播放 + 口型联动。

线程约定：所有 Qt 对象（QMediaPlayer）只在 GUI 线程触碰；
worker 侧（ASR/TTS/keyboard 回调）一律经 ui_task.emit 派回。
"""

from __future__ import annotations

import logging
import os
import threading

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer

from JChat.voice.recorder import Recorder

logger = logging.getLogger("JChat.voice")


class VoiceController(QObject):
    mic_requested = Signal()  # 网页麦克风按钮 → toggle（GUI 线程）

    def __init__(self, config: dict, app):
        super().__init__()
        self.config = config
        self.app = app
        self.recorder = Recorder()
        self._asr = None
        self._asr_lock = threading.Lock()
        from JChat.voice.monitor import VoiceMonitor

        self.monitor = VoiceMonitor(self)
        self._player = QMediaPlayer(self)
        self._audio_out = QAudioOutput(self)
        self._player.setAudioOutput(self._audio_out)
        self._player.mediaStatusChanged.connect(self._on_media_status)
        self._audio_out.setVolume(0.9)
        self._playing = False

    def ensure_monitor(self) -> None:
        """唤醒模式开关时同步监听状态（配置变更后需重启或重开设置生效）。"""
        c = self.config["companion"]
        want = bool(c.get("voice_wake_enabled")) and bool(c.get("voice_enabled"))
        if want and not self.monitor.running():
            self.monitor.start()
        elif not want and self.monitor.running():
            self.monitor.stop()

    # ------------------------------------------------------------ 听（toggle）
    def toggle(self) -> None:
        """按键/麦克风按钮：开始录音，再按结束并转写。可在任意线程调用。"""
        if not self.config["companion"].get("voice_enabled"):
            return
        if self.recorder.recording():
            samples = self.recorder.stop()
            self._mic_ui(False)
            if samples:
                self.app.queue.submit(0, lambda: self._transcribe_worker(samples))
            if self.monitor and bool(self.config["companion"].get("voice_wake_enabled")):
                self.monitor.start()  # 录音时暂停的监听恢复
            return
        if self.monitor.running():
            self.monitor.stop()  # 按键录音与常驻监听互斥，避免双份收音
        self.stop_speaking()
        if not self.recorder.start():
            logger.warning("录音启动失败（sounddevice 未安装或无麦克风）")
        else:
            self._mic_ui(True)
            logger.info("录音中…（再按 %s 结束）", self.config["companion"].get("voice_hotkey"))

    def _mic_ui(self, on: bool) -> None:
        """录音状态反映到麦克风按钮（toggle 可能来自键盘线程，转 GUI）。"""
        self.app.ui_task.emit(
            lambda: getattr(self.app.companion, "set_mic_recording", lambda _o: None)(on)
        )

    def _transcribe_worker(self, samples: list[int], from_monitor: bool = False) -> None:
        if self._asr is None:
            from JChat.voice.asr import SenseVoiceASR

            self._asr = SenseVoiceASR()
        with self._asr_lock:
            text = self._asr.transcribe(samples)
        logger.info("识别结果：%r", text)
        if not text:
            return
        if from_monitor:
            c = self.config["companion"]
            wake = str(c.get("voice_wake_word", "")).strip()
            rest = self._strip_wake(text, wake)
            if rest is None:
                return  # 未喊唤醒词
            if rest == "":
                # 只喊了唤醒词：确认"我在听"（不走 LLM）
                logger.info("唤醒确认")
                self.app.ui_task.emit(
                    lambda: getattr(self.app.companion, "show_reply", lambda *_a: None)(
                        "嗯，我在听。", []
                    )
                )
                self.app.queue.submit(1, lambda: self.speak("嗯，我在听。"))
                return
            text = rest
        self.app.ui_task.emit(lambda: self.app.on_send(text, via="voice"))

    @staticmethod
    def _strip_wake(text: str, wake: str) -> str | None:
        """唤醒词匹配（含同音字容错："维维美/唯唯美/微微美"）。

        返回去掉唤醒词后的内容；未命中返回 None；只喊了唤醒词返回空串。
        """
        if not wake:
            return text
        if wake in text:
            return text.replace(wake, "", 1).strip()
        # 拼音同音：逐前缀切分比较（ASR 常把唤醒词写成同音/近音字）
        try:
            import difflib

            from pypinyin import lazy_pinyin

            wp = "".join(lazy_pinyin(wake))
            max_cut = min(len(text), len(wake) + 3)
            fuzzy_best = None
            for cut in range(1, max_cut + 1):
                head = "".join(lazy_pinyin(text[:cut]))
                if head == wp:  # 同音精确：优先
                    return text[cut:].strip()
                if fuzzy_best is None and difflib.SequenceMatcher(None, wp, head).ratio() >= 0.8:
                    fuzzy_best = cut  # 记录最长（最后一个）近音切分
            if fuzzy_best is not None:
                return text[fuzzy_best:].strip()
        except ImportError:
            pass
        # 无 pypinyin：字符重叠兜底
        head = text[: len(wake)]
        if head and len(set(head) & set(wake)) / max(len(set(head) | set(wake)), 1) >= 0.6:
            return text[len(wake):].strip()
        return None

    # ------------------------------------------------------------ 说（TTS）
    def speak(self, text: str) -> None:
        """worker 线程调用：合成并派回 GUI 播放。GPT-SoVITS 失败回落 EdgeTTS。"""
        if not self.config["companion"].get("voice_enabled"):
            return
        from JChat.voice.tts import speak_edge, speak_gptsovits, tts_text

        spoken = tts_text(text)
        if not spoken:
            return
        c = self.config["companion"]
        path = None
        engine = ""
        if c.get("voice_ref_audio") and os.path.exists(c["voice_ref_audio"]):
            try:
                path = speak_gptsovits(
                    spoken,
                    base_url=c.get("gptsovits_url", "http://127.0.0.1:9880"),
                    ref_audio=c["voice_ref_audio"],
                    ref_text=c.get("voice_ref_text", ""),
                )
                engine = "gptsovits"
            except Exception as e:  # noqa: BLE001
                logger.info("GPT-SoVITS 不可用，回落 EdgeTTS：%s", e)
        if path is None:
            try:
                path = speak_edge(spoken, voice=c.get("tts_fallback_voice", "zh-CN-XiaoyiNeural"))
                engine = "edge"
            except Exception as e:  # noqa: BLE001
                logger.warning("TTS 全部失败：%s", e)
                return
        logger.info("发声（%s）：%s", engine, spoken[:30])
        self.app.ui_task.emit(lambda: self._play(path))

    # ------------------------------------------------------------ 播放（GUI 线程）
    def is_playing(self) -> bool:
        return self._playing

    def stop_speaking(self) -> None:
        """打断（barge-in）：停止当前播放。任意线程可调。"""
        self.app.ui_task.emit(self._stop_player)

    def _stop_player(self) -> None:
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._player.stop()
            self._playing = False
            companion = self.app.companion
            if companion:
                companion.set_talking(False)

    def _play(self, path: str) -> None:
        companion = self.app.companion
        if companion:
            companion.set_talking(True)
        self._playing = True
        self._player.setSource(QUrl.fromLocalFile(path))
        self._player.play()

    def _on_media_status(self, status) -> None:
        from PySide6.QtMultimedia import QMediaPlayer

        if status in (
            QMediaPlayer.MediaStatus.EndOfMedia,
            QMediaPlayer.MediaStatus.InvalidMedia,
        ):
            self._playing = False
            companion = self.app.companion
            if companion:
                companion.set_talking(False)
