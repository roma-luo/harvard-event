"""Layer 3: keyword matching, used only to sub-divide what layers 1 and 2 left.

Every rule the plan lists is enforced here:

* word boundaries, never substrings (``AI`` must not fire on ``Chair``)
* acronyms are case-sensitive, ordinary terms are not
* a synonym group is one rule with one weight — matching three of its terms
  still scores once
* hyphen and spacing variants collapse before matching
* the match window is title + series + speaker + the first 300 description
  characters, not the whole body
* an all-caps title falls back to case-insensitive matching, so the
  case-sensitive acronym rules cannot mis-fire on it
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable

from .text import clean, is_all_caps, normalize_for_match

DESCRIPTION_WINDOW = 300


def _boundary(pattern: str) -> str:
    """Wrap in \\b only where the edge character can actually take one."""
    left = r"\b" if pattern[:1].isalnum() else ""
    right = r"\b" if pattern[-1:].isalnum() else ""
    return f"{left}{pattern}{right}"


def _term_pattern(term: str) -> str:
    """A term matches across any run of spaces or hyphens between its words."""
    words = [re.escape(w) for w in normalize_for_match(term).split() if w]
    if not words:
        return ""
    return _boundary(r"[\s\-]+".join(words))


@dataclass
class KeywordGroup:
    name: str
    weight: float
    terms: list[str] = field(default_factory=list)
    acronyms: list[str] = field(default_factory=list)
    _terms_re: re.Pattern[str] | None = None
    _acronyms_re: re.Pattern[str] | None = None
    _acronyms_ci_re: re.Pattern[str] | None = None

    def compile(self) -> "KeywordGroup":
        term_parts = [p for p in (_term_pattern(t) for t in self.terms) if p]
        acr_parts = [p for p in (_term_pattern(a) for a in self.acronyms) if p]
        self._terms_re = re.compile("|".join(term_parts), re.IGNORECASE) if term_parts else None
        # Acronyms are matched case-sensitively by default...
        self._acronyms_re = re.compile("|".join(acr_parts)) if acr_parts else None
        # ...with a case-insensitive twin for all-caps titles.
        self._acronyms_ci_re = (
            re.compile("|".join(acr_parts), re.IGNORECASE) if acr_parts else None
        )
        return self

    def match(self, haystack: str, *, fold_acronym_case: bool) -> list[str]:
        hits: list[str] = []
        if self._terms_re:
            hits += [m.group(0) for m in self._terms_re.finditer(haystack)]
        acr_re = self._acronyms_ci_re if fold_acronym_case else self._acronyms_re
        if acr_re:
            hits += [m.group(0) for m in acr_re.finditer(haystack)]
        return hits


@dataclass
class KeywordHit:
    group: str
    weight: float
    matched: list[str]


class KeywordEngine:
    def __init__(self, spec: dict[str, Any]):
        self.groups = [
            KeywordGroup(
                name=g["name"],
                weight=float(g.get("weight", 0)),
                terms=list(g.get("terms") or []),
                acronyms=list(g.get("acronyms") or []),
            ).compile()
            for g in (spec.get("groups") or [])
        ]
        self.negative = [
            KeywordGroup(
                name=g["name"],
                weight=float(g.get("weight", 0)),
                terms=list(g.get("terms") or []),
                acronyms=list(g.get("acronyms") or []),
            ).compile()
            for g in (spec.get("negative") or [])
        ]

    @staticmethod
    def build_haystack(
        title: str,
        series: str | None,
        speaker: str | None,
        description: str,
    ) -> tuple[str, bool]:
        """The match window, plus whether acronym case must be folded."""
        parts = [title, series or "", speaker or "", clean(description)[:DESCRIPTION_WINDOW]]
        raw = " . ".join(p for p in parts if p)
        # Only the title decides the all-caps question; a shouty description
        # should not disable acronym precision for a normally-cased title.
        return normalize_for_match(raw), is_all_caps(title)

    def evaluate(
        self,
        title: str,
        series: str | None,
        speaker: str | None,
        description: str,
    ) -> tuple[float, list[KeywordHit]]:
        haystack, fold = self.build_haystack(title, series, speaker, description)
        total = 0.0
        hits: list[KeywordHit] = []
        for group in [*self.groups, *self.negative]:
            matched = group.match(haystack, fold_acronym_case=fold)
            if not matched:
                continue
            # One group scores once, however many of its synonyms appear.
            total += group.weight
            hits.append(
                KeywordHit(
                    group=group.name,
                    weight=group.weight,
                    matched=sorted(set(matched))[:6],
                )
            )
        return total, hits

    def topic_names(self, hits: Iterable[KeywordHit]) -> list[str]:
        return sorted({h.group for h in hits if h.weight > 0})
