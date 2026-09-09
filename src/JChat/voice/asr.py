"""听觉输入（ASR）：sherpa-onnx + SenseVoice（本地 onnx，模型首次自动下载）。"""

from __future__ import annotations

import logging
import os
import tarfile
import urllib.request
from pathlib import Path

logger = logging.getLogger("JChat.voice.asr")

MODEL_URL = (
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/"
    "sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2025-09-09.tar.bz2"
)
SAMPLE_RATE = 16000


def model_dir() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "JChat" / "models"
    base.mkdir(parents=True, exist_ok=True)
    return base


def _ensure_model() -> tuple[Path, Path]:
    """返回 (model.onnx, tokens.txt)；缺失时自动下载解压。"""
    import shutil

    d = model_dir()
    model = d / "model.int8.onnx"
    tokens = d / "tokens.txt"
    if model.exists() and tokens.exists():
        return model, tokens
    archive = d / "sensevoice.tar.bz2"
    logger.info("下载 SenseVoice 模型（~200MB，一次性）…")
    urllib.request.urlretrieve(MODEL_URL, archive)
    with tarfile.open(archive, "r:bz2") as tar:
        for member in tar.getmembers():
            if member.name.endswith(("model.int8.onnx", "tokens.txt")):
                member.name = Path(member.name).name
                tar.extract(member, d)
    archive.unlink(missing_ok=True)
    if not (model.exists() and tokens.exists()):
        raise RuntimeError("模型文件解压失败")
    _ = shutil
    return model, tokens


class SenseVoiceASR:
    """离线转写：int16 PCM (16k mono) → 文本。sherpa-onnx 缺失时 available()=False。"""

    def __init__(self) -> None:
        self._recognizer = None
        self._failed = False

    def available(self) -> bool:
        if self._recognizer is not None:
            return True
        if self._failed:
            return False
        try:
            import sherpa_onnx

            model, tokens = _ensure_model()
            self._recognizer = sherpa_onnx.OfflineRecognizer.from_sense_voice(
                model=str(model), tokens=str(tokens), use_itn=True, num_threads=2
            )
            return True
        except Exception as e:  # noqa: BLE001
            logger.info("ASR 不可用：%s", e)
            self._failed = True
            return False

    def transcribe(self, samples_int16) -> str:
        import numpy as np

        if not self.available():
            return ""
        audio = np.asarray(samples_int16, dtype=np.int16).astype(np.float32) / 32768.0
        stream = self._recognizer.create_stream()
        stream.accept_waveform(SAMPLE_RATE, audio)
        self._recognizer.decode_stream(stream)
        return (stream.result.text or "").strip()
