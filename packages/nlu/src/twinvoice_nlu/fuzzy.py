"""Post-correction of a spoken machine reference against the twin registry (FR-VN-04).

Speech gives "cnc three"; the registry holds `cnc-03` / "CNC Mill 03". Both sides are reduced to the
same spoken shape — separators to spaces, leading zeros dropped — before rapidfuzz scores them, so
the match is on what a person would say rather than on the punctuation an engineer typed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from rapidfuzz import fuzz, process

from twinvoice_nlu.slots import parse_asset

THRESHOLD = 85.0  # architecture §M9.1
AMBIGUOUS_MARGIN = 5.0  # two candidates this close are a "did you mean" question, not a match

_SEPARATORS = re.compile(r"[-_/.]+")
_ZERO_PADDED = re.compile(r"\b0+(\d)")


@dataclass(frozen=True)
class AssetRef:
    id: str
    code: str
    name: str

    def spoken_forms(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(f for f in (spoken(self.code), spoken(self.name)) if f))


@dataclass(frozen=True)
class Candidate:
    ref: AssetRef
    score: float


def spoken(text: str) -> str:
    """Reduce a code or name to the way it is said: "cnc-03" and "CNC Mill 03" both give "cnc 3"."""
    return parse_asset(_ZERO_PADDED.sub(r"\1", _SEPARATORS.sub(" ", text))) or ""


def rank(query: str, refs: list[AssetRef], limit: int = 2) -> list[Candidate]:
    """Best matches for a spoken reference, highest score first."""
    spoken_query = parse_asset(query)
    if not spoken_query or not refs:
        return []
    forms = [(form, ref) for ref in refs for form in ref.spoken_forms()]
    scored = process.extract(
        spoken_query,
        [form for form, _ in forms],
        scorer=fuzz.token_set_ratio,
        limit=len(forms),
    )
    best: dict[str, Candidate] = {}
    for form, score, index in scored:
        ref = forms[index][1]
        if ref.id not in best or score > best[ref.id].score:
            best[ref.id] = Candidate(ref=ref, score=float(score))
        del form
    return sorted(best.values(), key=lambda c: c.score, reverse=True)[:limit]


def resolve(query: str, refs: list[AssetRef], threshold: float = THRESHOLD) -> tuple[AssetRef | None, list[Candidate]]:
    """Return (match, alternatives).

    A match is returned only when it clears the threshold *and* is clearly ahead of the runner-up;
    otherwise the caller asks "did you mean …?" with the alternatives (FR-VN-06).
    """
    candidates = rank(query, refs)
    if not candidates or candidates[0].score < threshold:
        return None, candidates
    if len(candidates) > 1 and candidates[0].score - candidates[1].score < AMBIGUOUS_MARGIN:
        return None, candidates
    return candidates[0].ref, candidates[1:]
