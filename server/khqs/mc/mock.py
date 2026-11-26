"""The free mock MC: no voice, same playback-cursor contract as the live MC.

Each McSay is "played" after a simulated duration, then `engine.mc_played(token)`. An interrupt cancels
pending lines. Progress lines go to the stage as captions through the engine's secret filter.
"""
from __future__ import annotations

import asyncio

from ..engine.effects import McInterrupt, McListen, McMic, McSay, McStopListen

MIN_MS, MAX_MS, PER_CHAR_MS = 900, 6000, 60


def _names(names):
    names = list(names)
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def _grant_line(f: dict) -> str:
    opener = {"solo": "Nobody to ask, so granted! ", "agreed": "The others agree! ", "silence": "Silence means yes! "}[f["how"]]
    return opener + (f"It's by {f['text']}!" if f["kind"] == "composer" else f"{f['text']}")


def line_for(cue: str, f: dict) -> str:
    c = f.get("choices")
    table = {
        "greeting": lambda: f"Welcome, {_names(f['names'])}, to the Kiro Horror Quiz Show!",
        "act_intro": lambda: f"Welcome to {f['title']}.",
        "read_ox": lambda: f"Question {f['number']}. {f['text']} True or false?",
        "read_buzzer": lambda: f"Question {f['number']}. Listen carefully, and buzz in whenever you know it!",
        "intro_music": lambda: "Let's have a listen.",
        "longer_listen": lambda: "Buzzers open again. Here comes a longer listen!",
        "hint_ask": lambda: f"Ooh, {f['name']} wants a hint! Do the others agree?",
        "hint_grant": lambda: _grant_line(f),
        "hint_refused": lambda: "Denied! You're on your own.",
        "hint_none": lambda: "No hints left!" if f["why"] == "none_left" else "One hint per player!",
        "suspense": lambda: "And the answer is...",
        "ask_reason": lambda: f"{f['name']}, why did you pick {f['choice']}?",
        "offer_switch": lambda: f"{f['name']}, would you like to switch from {f['choice']}?",
        "react_betrayal": lambda: (f"A switch! Bold move, {f['name']}." if f["changed"] else f"{f['name']} stays put. Brave!"),
        "react_answer": lambda: f"The answer is {f['answer']}.",
        "react_judge": lambda: (f"Correct, {f['name']}!" if f["correct"] else f"Oh, not quite, {f['name']}."),
        "ask_again": lambda: f"Sorry {f['name']}, say that once more?",
        "phone_fallback": lambda: f"{f['name']}, please type your answer on your phone.",
        "final_intro": lambda: "It's time for the final bet! Think carefully.",
        "read_final": lambda: f"{f['text']} A, {c[0]}. B, {c[1]}. C, {c[2]}. D, {c[3]}.",
        "react_winner": lambda: ("A tie! Congratulations, " if f["tie"] else "Congratulations, ") + _names(f["winners"]) + "!",
        "farewell": lambda: "Thanks for playing! Come back to the haunted stage soon.",
    }
    return table[cue]()


class MockMc:
    def __init__(self, host, speed: float = 1.0) -> None:
        self.host = host
        self.speed = max(0.05, speed)
        self._pending: dict[str, asyncio.TimerHandle] = {}
        self._utterance = 0
        self.log: list[tuple[str, str]] = []  # (cue, line), for tests

    def engine_flags(self) -> dict:
        return {"mc_enabled": True, "voice_input": False, "status_from_playback": False}

    def duration_ms(self, cue: str, facts: dict, line: str) -> float:
        basis = facts.get("text") if cue in ("read_buzzer", "read_ox", "read_final") and facts.get("text") else line
        return min(MAX_MS, max(MIN_MS, PER_CHAR_MS * len(basis))) / self.speed

    def handle(self, e) -> None:
        if isinstance(e, McSay):
            line = line_for(e.cue, e.facts)
            self.log.append((e.cue, line))
            self._utterance += 1
            self.host.engine.mc_caption(self._utterance, line, True)
            loop = asyncio.get_running_loop()
            self._pending[e.token] = loop.call_later(self.duration_ms(e.cue, e.facts, line) / 1000, self._played, e.token)
        elif isinstance(e, McInterrupt):
            self.cancel_all()
        # McListen / McStopListen / McMic need no action: the mock cannot hear and has no mic

    def _played(self, token: str) -> None:
        self._pending.pop(token, None)
        self.host.run(self.host.engine.mc_played, token)

    def cancel_all(self) -> None:
        for h in self._pending.values():
            h.cancel()
        self._pending.clear()
