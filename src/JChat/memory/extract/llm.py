"""LLMExtractor: schema-constrained extraction via any OpenAI-compatible API.

Works as-is with DeepSeek, Qwen (DashScope), GLM (Zhipu), OpenAI, etc.
Configuration is environment-driven:

    MEMOKG_API_KEY   (falls back to OPENAI_API_KEY)
    MEMOKG_BASE_URL  (e.g. https://api.deepseek.com/v1)
    MEMOKG_MODEL     (default: deepseek-chat)
"""

from __future__ import annotations

import json
import os
import re

from JChat.memory.documents import Document
from JChat.memory.extract.base import ExtractedEntity, ExtractedRelation, Extraction
from JChat.memory.ontology import Ontology

_SYSTEM_TEMPLATE = """You extract a knowledge graph from documents.
Strictly use ONLY the schema below. Return JSON only, no prose.

SCHEMA:
{schema}

RULES:
- "entities": list of {{"name": ..., "label": ...}} with label from SCHEMA entity_types.
- "relations": list of {{"head": <entity name>, "rel_type": <name>, "tail": <entity name>}}
  - rel_type from SCHEMA relation_types
  - head/tail MUST exactly match an emitted entity name
- Only extract what the document actually states.
"""

_USER_TEMPLATE = """Document:

{text}

Return the JSON knowledge graph now."""

_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


class LLMExtractor:
    def __init__(
        self,
        ontology: Ontology,
        model: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        chunk_size: int = 6000,
    ):
        self.ontology = ontology
        self.model = model or os.getenv("MEMOKG_MODEL", "deepseek-chat")
        self.base_url = base_url or os.getenv("MEMOKG_BASE_URL") or "https://api.deepseek.com/v1"
        self.api_key = api_key or os.getenv("MEMOKG_API_KEY") or os.getenv("OPENAI_API_KEY")
        self.chunk_size = chunk_size
        if not self.api_key:
            raise ValueError(
                "LLMExtractor needs an API key: set MEMOKG_API_KEY (or OPENAI_API_KEY), "
                "or use the RuleExtractor when no key is available."
            )

    def _client(self):
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover - optional dep
            raise RuntimeError("pip install memo-kg[api] to use the LLM extractor") from exc
        return OpenAI(base_url=self.base_url, api_key=self.api_key)

    def extract(self, document: Document) -> Extraction:
        text = document.text
        result = Extraction.empty()
        if not text.strip():
            return result
        client = self._client()
        for chunk in _chunks(text, self.chunk_size):
            payload = self._call_once(client, chunk)
            result.merge(payload)
        return result

    def _call_once(self, client, chunk: str) -> Extraction:
        schema = json.dumps(self.ontology.as_schema_json(), ensure_ascii=False, indent=2)
        resp = client.chat.completions.create(
            model=self.model,
            temperature=0.0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": _SYSTEM_TEMPLATE.format(schema=schema)},
                {"role": "user", "content": _USER_TEMPLATE.format(text=chunk)},
            ],
        )
        raw = resp.choices[0].message.content or "{}"
        data = _parse_json(raw)
        return self._validate(data)

    def _validate(self, data: dict) -> Extraction:
        entities: list[ExtractedEntity] = []
        names: set[str] = set()
        for item in data.get("entities", []):
            label = str(item.get("label", ""))
            name = str(item.get("name", "")).strip()
            if name and label in self.ontology.entity_types:
                entities.append(ExtractedEntity(label=label, name=name))
                names.add(name)
        known_names = names | {e.name for e in entities}
        relations: list[ExtractedRelation] = []
        for item in data.get("relations", []):
            rel = str(item.get("rel_type", ""))
            head = str(item.get("head", "")).strip()
            tail = str(item.get("tail", "")).strip()
            if rel in self.ontology.relation_types and head in known_names and tail in known_names:
                relations.append(ExtractedRelation(head=head, rel_type=rel, tail=tail))
        return Extraction(entities=entities, relations=relations)


def _parse_json(raw: str) -> dict:
    cleaned = _FENCE.sub("", raw).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        raise


def _chunks(text: str, size: int) -> list[str]:
    text = text.strip()
    if len(text) <= size:
        return [text]
    chunks, start = [], 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            cut = max(
                text.rfind("\n\n", start, end),
                text.rfind("\u3002", start, end),
                start + size // 2,
            )
            end = cut if cut > start else end
        chunks.append(text[start:end])
        start = end
    return chunks
