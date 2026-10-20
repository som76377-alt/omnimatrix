"""Generate useful, bounded visual-search variants from natural-language briefs.

This is a deterministic fallback, not a language model. It removes production
instructions, separates distinct actions, and adds a few safe subject/action
variants so providers do not receive only the whole video brief.
"""
from __future__ import annotations

import re
from typing import Any

MAX_QUERY_VARIANTS = 6

_COMMAND_RE = re.compile(
    r"^\s*(?:please\s+)?(?:create|make|generate|produce|build|find|search(?:\s+for)?)\s+",
    re.IGNORECASE,
)
_MEDIA_WRAPPER_RE = re.compile(
    r"^\s*(?:a|an|the)?\s*(?:(?:short|vertical|horizontal|cinematic|realistic|documentary|premium|beautiful|animated|motion-graphics)\s+)*(?:video|film|clip|reel|shorts|animation|image|picture|photo|scene|shot)\s+(?:(?:of|about|showing|explaining|where|in\s+which)\s+)?",
    re.IGNORECASE,
)
_STOP_WORDS = {
    "a", "an", "the", "of", "for", "in", "on", "with", "by", "to", "from",
    "and", "or", "but", "as", "at", "into", "onto", "over", "under",
    "how", "why", "what", "when", "where", "which", "who", "please",
    "this", "that", "these", "those", "it", "its", "his", "her", "their",
    "my", "our", "your", "me", "then", "while", "about", "show", "showing",
    "explaining", "explain", "create", "make", "generate", "produce", "build",
    "video", "film", "clip", "reel", "shorts", "animation", "image", "picture",
    "photo", "scene", "shot", "seconds", "second", "secs", "sec",
}
_PEOPLE = ("person", "people", "man", "woman", "boy", "girl", "child", "children",
           "worker", "chef", "student", "teacher", "doctor", "scientist", "character")
_ACTIONS = ("wave", "waves", "waving", "greet", "greets", "greeting",
            "say", "says", "saying", "said", "speak", "speaks", "speaking",
            "walk", "walks", "walking", "run", "runs", "running",
            "hold", "holds", "holding", "turn", "turns", "turning",
            "pour", "pours", "pouring", "open", "opens", "opening")


def _clean_phrase(value: str) -> str:
    text = re.sub(r"[^\w' -]", " ", value, flags=re.UNICODE)
    tokens = [token.strip("'-") for token in re.findall(r"[\w'-]+", text, flags=re.UNICODE)]
    tokens = [token for token in tokens if token and token.casefold() not in _STOP_WORDS]
    return re.sub(r"\s+", " ", " ".join(tokens)).strip()


def build_search_query_variants(query: Any, *, limit: int = MAX_QUERY_VARIANTS) -> list[str]:
    """Return a ranked, de-duplicated set of image-search phrases for a video brief.

    It deliberately never invents an unrelated subject. Variants use words from
    the brief, plus a small set of generic person/greeting aliases for human
    action prompts. The original cleaned concept always appears first.
    """
    if not isinstance(query, str):
        return []
    raw = re.sub(r"\s+", " ", query).strip()
    if not raw:
        return []
    try:
        max_items = max(1, min(int(limit), MAX_QUERY_VARIANTS))
    except (TypeError, ValueError):
        max_items = MAX_QUERY_VARIANTS

    working = _COMMAND_RE.sub("", raw, count=1)
    working = _MEDIA_WRAPPER_RE.sub("", working, count=1)
    # Remove common production directives without discarding scene nouns/actions.
    working = re.sub(
        r"\b(?:in\s+)?\d{1,3}\s*(?:seconds?|secs?|s)\b|\b(?:9:16|16:9|1:1)\b",
        " ", working, flags=re.IGNORECASE,
    )
    working = re.sub(
        r"\b(?:in\s+)?(?:a\s+)?(?:cinematic|premium|beautiful|high[- ]quality|photorealistic|realistic|vertical|horizontal)\s+style\b",
        " ", working, flags=re.IGNORECASE,
    )
    working = re.sub(r"\s+", " ", working).strip(" .,:;!?-")
    full = _clean_phrase(working) or _clean_phrase(raw) or raw[:180]
    if not full:
        return [raw[:180]]

    candidates: list[str] = [full]
    clauses = re.split(
        r"\s*(?:,|;|\bthen\b|\bwhile\b|\bafter\b|\bbefore\b|\band\b|\bfollowed by\b)\s*",
        working, flags=re.IGNORECASE,
    )
    useful_clauses = [_clean_phrase(part) for part in clauses]
    useful_clauses = [part for part in useful_clauses if len(part.split()) >= 2]

    words = full.split()
    subject = next((word for word in words if word.casefold() in _PEOPLE), "")
    action = next((word for word in words if word.casefold() in _ACTIONS), "")
    for part in useful_clauses:
        if subject and not any(token.casefold() in _PEOPLE for token in part.split()):
            if part.split()[0].casefold() in _ACTIONS:
                part = subject + " " + part
        candidates.append(part)

    # Put semantic human-action variants before generic n-grams. Otherwise a
    # short six-query budget can be consumed by low-value adjacent word pairs.
    if subject and action:
        candidates.append(f"{subject} {action}")
    if subject and any(token.casefold() in {"wave", "waves", "waving"} for token in words):
        candidates.extend(["person waving", f"{subject} waving", "hand waving greeting"])
    if subject and any(token.casefold() in {"hi", "hello", "greeting", "greetings"} for token in words):
        candidates.extend([f"{subject} greeting", "person saying hello", "person greeting"])

    # Adjacent keyword pairs help surface the main object/process when a brief is
    # too long for asset metadata, without degenerating to one-word searches.
    for index in range(len(words) - 1):
        left, right = words[index:index + 2]
        if len(left) > 1 and len(right) > 1:
            candidates.append(left + " " + right)

    if len(words) >= 4:
        candidates.append(" ".join(words[:3]))
        candidates.append(" ".join(words[-3:]))

    output: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        value = re.sub(r"\s+", " ", candidate).strip(" -").lower()
        folded = value.casefold()
        if len(value) < 3 or len(value) > 100 or len(value.split()) < 2 or folded in seen:
            continue
        seen.add(folded)
        output.append(value)
        if len(output) >= max_items:
            break
    return output or [raw[:100]]
