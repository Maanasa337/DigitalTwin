"""Intent catalogue (FR-NL-01).

`intents.yaml` is the single source for three things that must never drift apart: the phrasings the
rule matcher compiles, the JSON Schema the LLM is given as a tool definition, and the risk tier the
confirmation protocol enforces. A slot added in one place is therefore added in all three.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

INTENTS_PATH = Path(__file__).with_name("intents.yaml")

LANGS = ("en", "hi", "hinglish")

# Slot type -> JSON Schema type the LLM sees. Everything the router cannot type strictly is a string
# the parser re-reads, so a hallucinated shape fails parsing rather than reaching a tool.
JSON_TYPES = {
    "asset": "string",
    "alarm": "string",
    "text": "string",
    "datetime": "string",
    "period": "string",
    "kpi": "string",
    "severity": "string",
    "view": "string",
    "report_type": "string",
    "verdict": "string",
    "enum": "string",
    "number": "number",
}


@dataclass(frozen=True)
class Slot:
    name: str
    type: str
    required: bool = False
    context: str | None = None
    values: tuple[str, ...] = ()


@dataclass(frozen=True)
class Intent:
    name: str
    tier: str
    summary: str
    slots: tuple[Slot, ...]
    templates: dict[str, tuple[str, ...]]
    samples: dict[str, tuple[str, ...]] = field(default_factory=dict)

    def slot(self, name: str) -> Slot | None:
        return next((s for s in self.slots if s.name == name), None)

    def json_schema(self) -> dict[str, Any]:
        """The tool definition handed to the LLM router."""
        properties: dict[str, Any] = {}
        for slot in self.slots:
            prop: dict[str, Any] = {"type": JSON_TYPES.get(slot.type, "string")}
            if slot.values:
                prop["enum"] = list(slot.values)
            properties[slot.name] = prop
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.summary,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": [s.name for s in self.slots if s.required],
                },
            },
        }


@dataclass(frozen=True)
class Catalogue:
    intents: tuple[Intent, ...]
    control: dict[str, dict[str, tuple[str, ...]]]

    def get(self, name: str) -> Intent | None:
        return next((i for i in self.intents if i.name == name), None)

    def tier(self, name: str) -> str | None:
        intent = self.get(name)
        return intent.tier if intent else None

    def templates_of(self, intent: Intent) -> list[tuple[str, tuple[str, ...]]]:
        return list(intent.templates.items())

    def tools(self) -> list[dict[str, Any]]:
        return [intent.json_schema() for intent in self.intents]

    def control_phrases(self, kind: str) -> frozenset[str]:
        """Every language's phrases for a control word, flattened — an operator may code-switch."""
        return frozenset(p for phrases in self.control.get(kind, {}).values() for p in phrases)


@lru_cache
def load_catalogue(path: Path | None = None) -> Catalogue:
    raw = yaml.safe_load((path or INTENTS_PATH).read_text(encoding="utf-8"))
    intents = tuple(
        Intent(
            name=entry["name"],
            tier=entry["tier"],
            summary=entry["summary"],
            slots=tuple(
                Slot(
                    name=s["name"],
                    type=s["type"],
                    required=bool(s.get("required", False)),
                    context=s.get("context"),
                    values=tuple(s.get("values", ())),
                )
                for s in entry.get("slots") or ()
            ),
            templates={lang: tuple(t) for lang, t in (entry.get("templates") or {}).items()},
            samples={k: tuple(v) for k, v in (entry.get("samples") or {}).items()},
        )
        for entry in raw["intents"]
    )
    control = {
        kind: {lang: tuple(phrases) for lang, phrases in langs.items()}
        for kind, langs in (raw.get("control") or {}).items()
    }
    return Catalogue(intents=intents, control=control)
