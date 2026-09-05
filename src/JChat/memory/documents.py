"""Document ingestion: normalize files into plain text."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from pathlib import Path

_TAG_RE = re.compile(r"<[^>]+>")
_PDF_RE = re.compile(r"[ \t]+")


@dataclass(frozen=True)
class Document:
    """A unit of knowledge ingested into the graph."""

    name: str
    text: str

    def fingerprints(self) -> str:
        return self.text


def load_documents(paths: list[str | Path]) -> list[Document]:
    docs: list[Document] = []
    for raw in paths:
        path = Path(raw)
        text = _read_one(path)
        if text.strip():
            docs.append(Document(name=path.name, text=text))
    return docs


def _read_one(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError as exc:  # pragma: no cover - optional dep
            raise RuntimeError(
                "PDF support requires the optional dependency: pip install memo-kg[pdf]"
            ) from exc
        pages = "".join(page.extract_text() or "" for page in PdfReader(str(path)).pages)
        return _PDF_RE.sub(" ", pages)
    if suffix in {".html", ".htm"}:
        return _TAG_RE.sub(" ", html.unescape(path.read_text(encoding="utf-8", errors="ignore")))
    return path.read_text(encoding="utf-8", errors="ignore")
