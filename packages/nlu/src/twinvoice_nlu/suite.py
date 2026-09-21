"""The labelled intent suite (FR-NL-06): ≥ 500 utterances, ≥ 10 per intent, en / hi / Hinglish.

Utterances are generated from `intents.yaml` by filling each template with its samples, so the suite
and the grammar can never drift: adding a phrasing adds test cases, and a template that stops
matching its own generated utterance fails the accuracy assertion.

**Deliberate simplification.** FR-VN-09 specifies additive MIMII/DCASE noise at 55/65/75 dB SNR.
That sweep belongs to the STT stage, which lives in the deferred `apps/voice` service. What is
measurable without audio is how the *router* behaves once noise has already damaged a transcript, so
`corrupt` applies the transcription errors those SNR levels produce — dropped function words and
phonetically confusable substitutions — and the suite reports intent accuracy per level. The WER
half of FR-VN-09 arrives with the speech service.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass
from typing import Any

from twinvoice_nlu.schema import Catalogue, Intent, load_catalogue
from twinvoice_nlu.vocab import CLOSED_VOCABS

# Transcription damage per SNR level, as a probability of corrupting any one token.
NOISE_LEVELS = {"75db": 0.05, "65db": 0.12, "55db": 0.25}

# Substitutions a noisy channel actually produces: short, phonetically close, meaning-preserving.
CONFUSIONS = {
    "two": "to", "to": "two", "four": "for", "for": "four", "one": "on", "on": "one",
    "is": "its", "the": "a", "show": "so", "what": "watt", "how": "now", "line": "lane",
    "karo": "karo", "kya": "kia", "hai": "he", "batao": "bata", "ka": "ke",
}  # fmt: skip

# Words an operator swallows under noise without changing what they asked for.
DROPPABLE = frozenset({"the", "a", "an", "is", "are", "me", "do", "please", "what", "of"})


@dataclass(frozen=True)
class Utterance:
    text: str
    intent: str
    lang: str
    noise_variant: bool
    split: str
    slots: dict[str, str]


def _fill(intent: Intent, template: str, index: int) -> tuple[str, dict[str, str]]:
    """Substitute the index-th sample for each slot, and collapse the optional/alternation syntax."""
    text = template
    slots: dict[str, str] = {}
    for slot in intent.slots:
        placeholder = f"{{{slot.name}}}"
        if placeholder not in text:
            continue
        samples = intent.samples.get(slot.name)
        if not samples:
            # A slot with no sample cannot be generated; drop the optional wrapper that holds it.
            text = re.sub(r"\[[^\]]*" + re.escape(placeholder) + r"[^\]]*\]", "", text)
            text = text.replace(placeholder, "").strip()
            continue
        value = samples[index % len(samples)]
        slots[slot.name] = value
        text = text.replace(placeholder, value)
    # An alternation keeps its first branch: `(it|{asset})` resolves to "it", which drops the slot
    # out of the utterance. Labelling it anyway would mark the router wrong for reading what is
    # actually there, so the label is kept only if its value survived into the text.
    text = re.sub(r"\(([^|)]+)\|[^)]*\)", r"\1", text)
    text = re.sub(r"\[([^\]]*)\]", r"\1", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text, {name: value for name, value in slots.items() if value in text}


def corrupt(text: str, level: str, rng: random.Random) -> str:
    """Apply the transcription damage a given SNR level produces."""
    probability = NOISE_LEVELS[level]
    tokens = text.split()
    out: list[str] = []
    for token in tokens:
        if rng.random() >= probability:
            out.append(token)
        elif token in CONFUSIONS:
            out.append(CONFUSIONS[token])
        elif token in DROPPABLE and len(tokens) > 3:
            continue
        else:
            out.append(token)
    return " ".join(out) or text


def generate(catalogue: Catalogue | None = None, *, seed: int = 20260919) -> list[Utterance]:
    """The full labelled suite: one clean utterance per template per sample index, plus noise variants."""
    cat = catalogue or load_catalogue()
    rng = random.Random(seed)
    suite: list[Utterance] = []

    for intent in cat.intents:
        fills = max((len(v) for v in intent.samples.values()), default=1)
        for lang, templates in intent.templates.items():
            for template in templates:
                for index in range(fills):
                    text, slots = _fill(intent, template, index)
                    if not text:
                        continue
                    clean = Utterance(text, intent.name, lang, False, "test", slots)
                    if clean not in suite:
                        suite.append(clean)

    for level in NOISE_LEVELS:
        for utterance in list(suite):
            if utterance.noise_variant:
                continue
            noisy = corrupt(utterance.text, level, rng)
            if noisy != utterance.text:
                suite.append(Utterance(noisy, utterance.intent, utterance.lang, True, level, utterance.slots))
    return suite


# ── Slot scoring ──────────────────────────────────────────────────────
#
# Intent accuracy alone says nothing about whether the right machine was identified. An utterance
# routed to `create_work_order` with the wrong asset is a work order on the wrong machine, so the
# slots the suite already labels are scored here too.

# Slots whose value the router deliberately rewrites (a period becomes a pair of timestamps, a
# datetime becomes an instant). Their surface form is not comparable to the label.
DERIVED_SLOTS = frozenset({"when", "period", "period_start", "period_end", "value"})


def slot_targets(utterance: Utterance, intent: Intent | None = None) -> dict[str, str]:
    """The labelled slots, canonicalised the way the router canonicalises them.

    A closed-vocabulary slot is compared by its code, not its surface form: the router turning
    "weekly maintenance" into `weekly_maintenance` is the behaviour under test, not an error.
    """
    from twinvoice_nlu.slots import parse_asset

    targets = {}
    for name, value in utterance.slots.items():
        if name in DERIVED_SLOTS:
            continue
        slot = intent.slot(name) if intent else None
        vocab = CLOSED_VOCABS.get(slot.type) if slot else None
        if vocab is not None:
            canonical = vocab.get(value.strip().lower())
            if canonical is not None:
                targets[name] = str(canonical).lower()
            continue
        normalised = parse_asset(value) if name in ("asset", "alarm", "scope") else value.strip().lower()
        if normalised:
            targets[name] = normalised
    return targets


def score_slots(utterance: Utterance, predicted: dict[str, Any], intent: Intent | None = None) -> tuple[int, int]:
    """(matched, expected) for one utterance, comparing only the slots the label pins down."""
    targets = slot_targets(utterance, intent)
    if not targets:
        return 0, 0
    matched = sum(1 for name, expected in targets.items() if _same(predicted.get(name), expected))
    return matched, len(targets)


# Articles a sample may carry that the router strips before it hands the value on.
_ARTICLES = ("a ", "an ", "the ")


def _same(actual: Any, expected: str) -> bool:
    """Compare a returned slot to its label, allowing the shapes the router legitimately returns."""
    if actual is None:
        return False
    text = str(actual).strip().lower()
    if text == expected:
        return True
    # A numeric slot comes back parsed: "40" and 40.0 are the same answer.
    try:
        if float(text) == float(expected):
            return True
    except ValueError:
        pass
    return any(expected.startswith(article) and text == expected[len(article) :] for article in _ARTICLES)
