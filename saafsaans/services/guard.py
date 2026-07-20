"""Prompt-injection guard.

Pure and side-effect free: ``check`` classifies a user string and the caller
decides what to log. The guard runs *before* any LLM call, so a blocked prompt
never reaches the model.

Defence approach:
  1. Length check first (cheap; an oversized prompt is suspicious regardless).
  2. Normalize the text once (NFKC unicode fold, lowercase, collapse
     whitespace) so trivial spacing / homoglyph / casing tricks cannot slip a
     keyword past the patterns.
  3. Match an ordered regex table. Verb sets and filler-tolerant spacing catch
     realistic phrasing variants ("ignore instructions", "reveal your prompt",
     "forget your rules"), while word boundaries avoid false positives on
     ordinary words ("contact", "react").
"""
import re
import unicodedata

MAX_LEN = 800

# (label, pattern). Labels are recorded as ``pattern_matched`` in
# security-events. Order matters: the first match wins. Patterns run against
# the NORMALIZED (lowercased, whitespace-collapsed) text.
_FILLER = r"[\w\s'\"-]{0,30}?"  # tolerant, non-greedy filler between verb/target
_PATTERNS = [
    # Instruction-override: verb ... (instructions|rules|guidelines).
    ("ignore_instructions",
     r"\b(?:ignore|disregard|forget|override|skip|bypass)\b" + _FILLER +
     r"\b(?:instructions|rules|guidelines|directives)\b"),
    # Literal "system prompt" (hyphen/underscore/space tolerant).
    ("system_prompt", r"system[\s_-]?prompt"),
    # Exfiltration: reveal/print/show ... (system) prompt|instructions.
    ("print_prompt",
     r"\b(?:print|show|reveal|repeat|output|display|dump|leak|expose|"
     r"tell me|give me|send me|share)\b" + _FILLER +
     r"(?:your\s+|the\s+)?(?:system[\s_-]?)?(?:prompt|instructions)\b"),
    ("you_are_now", r"\byou\s*(?:are|'re)\s+now\b"),
    ("from_now_on", r"\bfrom now on\b" + _FILLER + r"\byou\b"),
    ("pretend", r"\bpretend\s+(?:to be|you|that)\b"),
    ("roleplay", r"\brole[\s-]?play\s+as\b"),
    # "act as X" but NOT the legitimate "act as a doctor"; \b avoids "contact".
    ("act_as", r"\bact as\b(?! a doctor)"),
    ("disregard", r"\bdisregard\b"),
    ("jailbreak", r"\bjailbreak\b"),
    ("api_key", r"api[\s_-]?key"),
    ("password", r"\bpassword\b"),
    ("developer_mode", r"\bdeveloper\s*mode\b"),
]

PATTERNS = [(label, re.compile(pat, re.IGNORECASE)) for label, pat in _PATTERNS]


def _normalize(text: str) -> str:
    """Fold unicode, lowercase, and collapse whitespace for robust matching."""
    t = unicodedata.normalize("NFKC", text)
    # Drop format characters (Cf): zero-width space, zero-width joiner, the
    # bidi overrides. NFKC leaves them in place, so a single invisible
    # codepoint inside a keyword -- "ig<ZWSP>nore your instructions" -- walked
    # past every pattern in the table and reached the model unaudited. They
    # carry no meaning in a question about air quality.
    t = "".join(c for c in t if unicodedata.category(c) != "Cf")
    t = t.lower()
    t = re.sub(r"\s+", " ", t)
    return t


def check(text: str):
    """Return ``(ok, pattern)``.

    ``(True, None)``  -> looks safe, proceed to the LLM.
    ``(False, label)`` -> blocked; caller logs the label and refuses.
    """
    text = text or ""
    if len(text) > MAX_LEN:
        return (False, "oversized_input")
    normalized = _normalize(text)
    for label, pattern in PATTERNS:
        if pattern.search(normalized):
            return (False, label)
    return (True, None)
