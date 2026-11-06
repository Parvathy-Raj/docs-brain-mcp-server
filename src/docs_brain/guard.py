"""Prompt-injection guard for retrieved text.

Docs are untrusted input: anyone who can get a PR merged into a library's docs (or poison a
mirror) can plant text aimed at the AI reading them. Everything this server returns goes through
`scan()` first. Suspicious lines are replaced with a marker and the result is flagged, so the
client can see that something was removed. Nothing is dropped silently.

This is a heuristic filter (regex + a few structural checks), not a guarantee. It catches the
common, low-effort attacks and makes the risk visible. See README "Limitations".
"""

from __future__ import annotations

import base64
import binascii
import re
from dataclasses import dataclass, field

MARKER = "[removed: possible prompt injection]"

_I = re.IGNORECASE
PATTERNS: list[tuple[str, re.Pattern]] = [
    (
        "ignore-instructions",
        re.compile(
            r"\b(ignore|disregard|forget|override|bypass)\b[^.\n]{0,40}"
            r"\b(previous|prior|above|earlier|preceding|all|any|your)\b[^.\n]{0,30}"
            r"\b(instructions?|prompts?|rules|directions|guidelines|context)\b",
            _I,
        ),
    ),
    (
        "role-override",
        re.compile(
            r"\byou are now\b|\bfrom now on,? you\b|\bnew instructions?\s*:|"
            r"\bpretend (to be|you are)\b|\bdeveloper mode\b|\bjailbreak",
            _I,
        ),
    ),
    (
        "system-prompt-probe",
        re.compile(
            r"\b(reveal|print|show|output|leak|repeat)\b[^.\n]{0,30}"
            r"\b(system prompt|hidden instructions|your instructions|initial prompt)\b",
            _I,
        ),
    ),
    (
        "fake-chat-turn",
        re.compile(
            r"<\s*/?\s*(system|assistant|im_start|im_end)\s*>|^\s*(system|assistant)\s*:", _I | re.M
        ),
    ),
    (
        "exfiltration",
        re.compile(
            r"\b(send|post|upload|exfiltrate|forward|email)\b[^.\n]{0,40}"
            r"\b(conversation|chat history|system prompt|api keys?|environment variables|"
            r"user'?s? (data|files|secrets|credentials))\b",
            _I,
        ),
    ),
    (
        "addressed-to-ai",
        re.compile(
            r"\b(ai|llm|language model|assistant|claude|chatgpt|copilot)\b[^.\n]{0,20}"
            r"\b(must|should|need to|are required to)\b[^.\n]{0,40}"
            r"\b(call|run|execute|delete|tell the user|say|respond|reply)\b",
            _I,
        ),
    ),
]

# Zero-width spaces, word joiners, BOMs and bidi overrides are suspicious anywhere. The
# zero-width joiner/non-joiner (U+200C/D) is legitimate inside emoji, so it only counts when it
# sits between letters, where it splits words to slip past filters.
ZERO_WIDTH = re.compile(
    "[\u200b\u200e\u200f\u202a-\u202e\u2060-\u2064\ufeff]|(?<=\\w)[\u200c\u200d](?=\\w)"
)
HTML_COMMENT = re.compile(r"<!--(.*?)-->", re.S)
BASE64_BLOB = re.compile(r"[A-Za-z0-9+/]{40,}={0,2}")


@dataclass
class GuardResult:
    text: str
    flagged: bool = False
    reasons: list[str] = field(default_factory=list)


def _matches(text: str) -> list[str]:
    return [name for name, pat in PATTERNS if pat.search(text)]


def _decoded_blobs(text: str) -> list[str]:
    """Decode base64-looking runs, so instructions hidden in encoding are caught too."""
    out = []
    for blob in BASE64_BLOB.findall(text):
        try:
            decoded = base64.b64decode(blob + "=" * (-len(blob) % 4), validate=True)
            out.append(decoded.decode("utf-8"))
        except (binascii.Error, UnicodeDecodeError, ValueError):
            continue  # binary data (images etc.) is not text, so not an instruction
    return out


def scan(text: str) -> GuardResult:
    reasons: set[str] = set()

    # Invisible characters: always removed, flagged because docs have no reason to contain them.
    if ZERO_WIDTH.search(text):
        reasons.add("zero-width-characters")
        text = ZERO_WIDTH.sub("", text)

    # HTML comments are invisible to a human reading the rendered page, so they are always
    # stripped. They are flagged only when the hidden text looks like an instruction.
    def _comment(m: re.Match) -> str:
        if _matches(m.group(1)):
            reasons.add("hidden-html-comment")
            return MARKER
        return ""

    text = HTML_COMMENT.sub(_comment, text)

    lines = text.split("\n")
    for i, line in enumerate(lines):
        hits = _matches(line)
        hidden = [f"base64:{name}" for blob in _decoded_blobs(line) for name in _matches(blob)]
        if hits or hidden:
            reasons.update(hits + hidden)
            lines[i] = MARKER
    text = "\n".join(lines)

    return GuardResult(text=text, flagged=bool(reasons), reasons=sorted(reasons))
