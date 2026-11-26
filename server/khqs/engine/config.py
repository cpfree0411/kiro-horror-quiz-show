"""All engine windows and limits in one place (docs/GAME_RULES.md section 4 and 11)."""
from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType

# Wire `timeoutMs` per gate (stage-animation reference). Keys may carry a ':kind' suffix.
GATE_TIMEOUTS = MappingProxyType({
    "show.opening": 60_000,
    "act.started": 8_000,
    "act.started:3": 10_000,
    "question.presented": 5_000,
    "question.presented:final": 6_000,
    "ox.choices_revealed": 6_000,
    "betrayal.offered": 6_000,
    "betrayal.decided": 6_000,
    "answer.revealed": 5_000,
    "answer.revealed:ox": 6_000,
    "answer.revealed:final": 7_000,
    "score.settled": 5_000,
    "score.settled:ox": 5_000,
    "score.settled:final": 7_000,
    "buzzer.judged": 5_000,
    "av.hint": 5_000,
    "final.category": 6_000,
    "final.choices_revealed": 7_000,
    "final.bet_revealed": 6_000,
    "finale.winner": 12_000,
    "finale.results": 15_000,
})


@dataclass(frozen=True)
class EngineConfig:
    ox_answer_ms: int = 20_000
    betrayal_input_ms: int = 8_000
    prompt_failsafe_ms: int = 15_000  # waited MC lines: suspense, offer_switch, greeting, final_intro
    reading_failsafe_ms: int = 45_000  # buzzer question reading
    buzzer_answer_ms: int = 20_000  # 60_000 with the live voice MC (retries and phone fallback need the room)
    buzzer_open_ms: int = 15_000
    music_open_ms: int = 10_000
    hint_consent_ms: int = 8_000  # the others' yes or no to a requested hint; silence counts as yes
    media_interrupt_wait_ms: int = 800
    media_watchdog_extra_ms: int = 1_000
    media_end_tolerance_sec: float = 1.5
    final_bet_ms: int = 20_000
    final_answer_ms: int = 20_000
    gate_grace_ms: int = 25_000  # safety = timeoutMs + grace
    voice_attempts: int = 2
    text_answer_max: int = 60
    gate_timeouts: dict = field(default_factory=lambda: dict(GATE_TIMEOUTS))

    def gate_timeout(self, gate_type: str, kind: str | None = None) -> int:
        if kind is not None and f"{gate_type}:{kind}" in self.gate_timeouts:
            return self.gate_timeouts[f"{gate_type}:{kind}"]
        return self.gate_timeouts[gate_type]
