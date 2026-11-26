"""Effects the engine emits. Outside code (server, harness) consumes them; the engine does no I/O."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class StageBroadcast:
    """A stream message for every connected stage socket (primary and viewers)."""
    msg: dict


@dataclass(frozen=True)
class StageDirect:
    """A message for one stage socket: snapshot, pong, error."""
    conn: str
    msg: dict


@dataclass(frozen=True)
class PhoneChanged:
    """These seats' private views changed; push `phone_view(seat)`."""
    seats: tuple[int, ...]


@dataclass(frozen=True)
class McSay:
    """Tell the MC to say something. `facts` is a whitelisted public dict per cue."""
    token: str
    cue: str
    facts: dict = field(default_factory=dict)


@dataclass(frozen=True)
class McListen:
    listen_id: str
    seat: int
    purpose: str  # answer | reason | decision | consent
    attempt: int
    deadline: int


@dataclass(frozen=True)
class McStopListen:
    listen_id: str


@dataclass(frozen=True)
class McInterrupt:
    """Flush browser playback and interrupt the Live session now."""
    reason: str


@dataclass(frozen=True)
class McMic:
    """Open or close mic forwarding. Closed during the music clip."""
    open: bool
    reason: str


Effect = (StageBroadcast | StageDirect | PhoneChanged | McSay | McListen | McStopListen | McInterrupt | McMic)

# Which keys each cue may carry. Nothing secret is on this list before its reveal.
CUE_FACTS: dict[str, frozenset[str]] = {
    "greeting": frozenset({"names", "mode"}),
    "act_intro": frozenset({"act", "title", "names"}),
    "read_ox": frozenset({"number", "category", "text"}),
    "read_buzzer": frozenset({"number", "category", "text", "resume"}),
    "intro_music": frozenset({"number", "category"}),
    "longer_listen": frozenset({"level", "max_level"}),
    "hint_ask": frozenset({"name"}),
    "hint_grant": frozenset({"name", "how", "kind", "text", "number"}),
    "hint_refused": frozenset({"name"}),
    "hint_none": frozenset({"name", "why"}),
    "suspense": frozenset({"kind"}),
    "ask_reason": frozenset({"name", "choice"}),
    "offer_switch": frozenset({"name", "choice"}),
    "react_betrayal": frozenset({"name", "changed", "from", "to", "reason"}),
    "react_answer": frozenset({"kind", "answer", "explanation", "results"}),
    "react_judge": frozenset({"name", "correct"}),
    "ask_again": frozenset({"name", "attempt"}),
    "phone_fallback": frozenset({"name"}),
    "final_intro": frozenset({"scores"}),
    "read_final": frozenset({"number", "category", "text", "choices"}),
    "react_winner": frozenset({"winners", "tie", "standings"}),
    "farewell": frozenset({"mode", "standings"}),
}
