"""Deterministic first stage of the hybrid router (FR-NL-02).

**Deliberate simplification.** The architecture names spaCy's `Matcher` here. spaCy ships no Hindi
pipeline, so a `Matcher` would cover one of the three languages this grammar has to serve while
adding a 40 MB dependency and a model download to the image. The templates in `intents.yaml` are
compiled to anchored regexes instead: one table covers en, hi and Hinglish, every match is
traceable to the template that produced it, and the stage stays dependency-free.

Two passes, in order:
  exact    the utterance is entirely accounted for by one template          -> confidence 0.95
  relaxed  the template matches inside filler ("hey twin, ... please")      -> confidence 0.80
Anything below that is the LLM's problem (`llm_router`).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from twinvoice_nlu.schema import Catalogue, Intent, load_catalogue
from twinvoice_nlu.vocab import (
    CLOSED_VOCABS,
    FILLER,
    FILLER_PATTERN,
    NUMBER_WORDS,
    slot_pattern,
    token_alternatives,
)

EXACT_CONFIDENCE = 0.95
RELAXED_CONFIDENCE = 0.80

# Straight, curly and backtick apostrophes: a transcript may carry any of the three.
_APOSTROPHES = dict.fromkeys((0x27, 0x2019, 0x60), None)
_NON_WORD = re.compile(r"[^\w%\s]+", re.UNICODE)
_SPACES = re.compile(r"\s+")


def normalise(text: str) -> str:
    """Lowercase, drop apostrophes, punctuation to space, collapse whitespace.

    Apostrophes are deleted rather than spaced so "how's" becomes the single token "hows", which is
    how the templates spell it; every other separator becomes a space.
    """
    folded = unicodedata.normalize("NFKC", text).lower().translate(_APOSTROPHES)
    return _SPACES.sub(" ", _NON_WORD.sub(" ", folded)).strip()


# ── Template compilation ──────────────────────────────────────────────


@dataclass(frozen=True)
class CompiledTemplate:
    intent: str
    lang: str
    source: str
    pattern: re.Pattern[str]
    relaxed: re.Pattern[str]
    slots: tuple[str, ...]
    open_slots: int


def _literal(token: str) -> tuple[str, bool]:
    """A literal token, widened to the confusions noise produces.

    A function word is compiled as *any* function word, optionally: a noisy channel turns "the" into
    "a" as readily as it drops it, and neither substitution changes what was asked for.
    """
    if token in FILLER:
        return FILLER_PATTERN, True
    alternatives = token_alternatives(token)
    fragment = re.escape(token) if len(alternatives) == 1 else "(?:" + "|".join(map(re.escape, alternatives)) + ")"
    return fragment, False


def _parse(template: str, intent: Intent) -> list[tuple[str, bool]]:
    """Template text -> [(regex fragment, optional)], one entry per literal token, slot or group."""
    parts: list[tuple[str, bool]] = []
    literal: list[str] = []
    i = 0

    def flush() -> None:
        parts.extend(_literal(token) for token in literal)
        literal.clear()

    tokens = template.split(" ")
    while i < len(tokens):
        token = tokens[i]
        if token.startswith("{") and token.endswith("}"):
            flush()
            name = token[1:-1]
            slot = intent.slot(name)
            parts.append((f"(?P<{name}>{slot_pattern(slot.type if slot else 'text')})", False))
            i += 1
        elif token.startswith("("):
            flush()
            # An alternative may span tokens: "(kya hai|bataao)".
            body, i = _group(tokens, i, ")")
            options = "|".join(_join(_parse(option.strip(), intent)) for option in body.split("|"))
            parts.append((f"(?:{options})", False))
        elif token.startswith("["):
            flush()
            body, i = _group(tokens, i, "]")
            parts.append((_join(_parse(body, intent)), True))
        else:
            literal.append(token)
            i += 1
    flush()
    return _keep_an_anchor(parts)


def _keep_an_anchor(parts: list[tuple[str, bool]]) -> list[tuple[str, bool]]:
    """A template whose every part is optional would match any utterance, so keep one required.

    "is {asset} ok" is all filler but for the slot; dropping the filler there is safe because the
    slot still anchors it. A template with no required part at all keeps its first literal.
    """
    if not parts or any(not optional for _, optional in parts):
        return parts
    fragment, _ = parts[0]
    return [(fragment, False), *parts[1:]]


def _group(tokens: list[str], start: int, closer: str) -> tuple[str, int]:
    """Consume tokens from an opening bracket to its closer; return the inner text and the next index."""
    collected = [tokens[start]]
    index = start
    while not collected[-1].endswith(closer):
        index += 1
        collected.append(tokens[index])
    return " ".join(collected)[1:-1], index + 1


def _join(parts: list[tuple[str, bool]]) -> str:
    """Join fragments with whitespace, folding the separator into each optional group.

    The separator belongs to whichever side is present: a leading optional carries the space after
    it, every later part carries the space before it. Getting this wrong makes a template that
    starts with an optional word require a leading space and match nothing.
    """
    out = ""
    anchored = False  # something required has been emitted, so a separator must precede the next part
    for fragment, optional in parts:
        if optional:
            out += rf"(?:\s+{fragment})?" if anchored else rf"(?:{fragment}\s+)?"
        else:
            out += rf"\s+{fragment}" if anchored else fragment
            anchored = True
    return out


def compile_template(intent: Intent, lang: str, template: str) -> CompiledTemplate:
    body = _join(_parse(template, intent))
    names = tuple(re.findall(r"\(\?P<(\w+)>", body))
    return CompiledTemplate(
        intent=intent.name,
        lang=lang,
        source=template,
        pattern=re.compile(body),
        # Named groups must stay unique, so the relaxed form reuses the same body with filler around it.
        relaxed=re.compile(rf"(?:.*?\s)?{body}(?:\s.*?)?"),
        slots=names,
        open_slots=sum(1 for n in names if (intent.slot(n).type if intent.slot(n) else "text") not in CLOSED_VOCABS),
    )


def compile_all(catalogue: Catalogue) -> tuple[CompiledTemplate, ...]:
    return tuple(
        compile_template(intent, lang, template)
        for intent in catalogue.intents
        for lang, templates in catalogue.templates_of(intent)
        for template in templates
    )


@lru_cache
def _default_compiled() -> tuple[CompiledTemplate, ...]:
    return compile_all(load_catalogue())


def compiled(catalogue: Catalogue | None = None) -> tuple[CompiledTemplate, ...]:
    """Compiling 234 templates costs ~10 ms, so the default catalogue is compiled once per process.

    A caller that supplies its own catalogue (tests, a future per-plant grammar) gets a fresh
    compile: `Catalogue` holds dicts and cannot be a cache key.
    """
    if catalogue is None or catalogue is load_catalogue():
        return _default_compiled()
    return compile_all(catalogue)


# ── Matching ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class RuleMatch:
    intent: str
    lang: str
    slots: dict[str, str]
    confidence: float
    template: str
    open_slots: int = 0
    split_reference: bool = False


def _captured_chars(slots: dict[str, str]) -> int:
    return sum(len(v) for v in slots.values())


REFERENCE_SLOTS = ("asset", "alarm", "scope")


def _splits_a_reference(found: re.Match[str], utterance: str) -> bool:
    """True when a reference capture stops immediately before the number word that completes it.

    A literal widened for noise tolerance will match a number: the "for" in `on {asset} for {task}`
    happily consumes the "four" of "press four", which leaves the asset a bare "press". That reading
    captures fewer characters than the right one, so it would otherwise win the ranking below.
    """
    for name in REFERENCE_SLOTS:
        try:
            end = found.end(name)
        except (IndexError, re.error):
            continue
        if end < 0:
            continue
        tail = utterance[end:].split()
        if tail and tail[0] in NUMBER_WORDS:
            return True
    return False


def _best(candidates: list[RuleMatch]) -> RuleMatch | None:
    """Prefer the template that explained the most of the utterance with literals, not with slots.

    A reading that tore a machine reference in half is rejected first, however little it captured:
    naming the wrong machine is worse than leaving more of the sentence unexplained. Ties then go to
    the template with fewer wildcard slots: "show energy" is the energy *page*, matched by
    `show {view}` against a closed vocabulary, not an asset called "energy" matched by `show me {asset}`.
    """
    key = lambda m: (m.split_reference, _captured_chars(m.slots), m.open_slots, len(m.slots))  # noqa: E731
    return min(candidates, key=key) if candidates else None


def match(text: str, catalogue: Catalogue | None = None) -> RuleMatch | None:
    utterance = normalise(text)
    if not utterance:
        return None
    templates = compiled(catalogue)

    for attr, confidence in (("pattern", EXACT_CONFIDENCE), ("relaxed", RELAXED_CONFIDENCE)):
        candidates: list[RuleMatch] = []
        for template in templates:
            found = getattr(template, attr).fullmatch(utterance)
            if found is None:
                continue
            slots = {k: v.strip() for k, v in found.groupdict().items() if v and v.strip()}
            candidates.append(
                RuleMatch(
                    intent=template.intent,
                    lang=template.lang,
                    slots=slots,
                    confidence=confidence,
                    template=template.source,
                    open_slots=template.open_slots,
                    split_reference=_splits_a_reference(found, utterance),
                )
            )
        best = _best(candidates)
        if best is not None:
            return best
    return None


def control_word(text: str, catalogue: Catalogue | None = None) -> str | None:
    """Return 'confirm' | 'cancel' | 'repeat' | 'slower' when the utterance is exactly that word.

    Exact only: "confirm the order for later" must not execute a pending read-back (FR-VN-07).
    """
    cat = catalogue or load_catalogue()
    utterance = normalise(text)
    for kind in ("confirm", "cancel", "repeat", "slower"):
        if utterance in {normalise(p) for p in cat.control_phrases(kind)}:
            return kind
    return None


def describe(catalogue: Catalogue | None = None) -> list[dict[str, Any]]:
    """The help/cheat-sheet payload: one row per intent with an example phrasing per language."""
    cat = catalogue or load_catalogue()
    return [
        {
            "intent": intent.name,
            "tier": intent.tier,
            "summary": intent.summary,
            "examples": {
                lang: _example(intent, templates[0]) for lang, templates in intent.templates.items() if templates
            },
        }
        for intent in cat.intents
    ]


def _example(intent: Intent, template: str) -> str:
    """Fill a template's slots with their first sample so the cheat sheet shows a sayable sentence."""
    text = template
    for slot in intent.slots:
        samples = intent.samples.get(slot.name)
        if samples:
            text = text.replace(f"{{{slot.name}}}", samples[0])
    return re.sub(r"[\[\]]", "", re.sub(r"\(([^|)]+)\|[^)]*\)", r"\1", text)).strip()
