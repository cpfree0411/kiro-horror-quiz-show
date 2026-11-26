"""Per-question round state. Private fields are marked; the snapshot builder reads only public ones."""
from __future__ import annotations

from dataclasses import dataclass, field

BETRAYAL_REASONS = {
    "knew": "I KNEW IT",
    "hunch": "JUST A HUNCH",
    "crowd": "FOLLOWED THE CROWD",
    "dunno": "NO IDEA",
}


@dataclass
class BetrayalState:
    seat: int
    selection: str  # lowest | tied_random
    tied: list[int]
    from_: str
    to: str | None = None
    status: str = "offered"  # offered | listening | decided
    step: str | None = None  # reason | decision (private: which input is open)
    reason: str | None = None  # private
    reason_source: str | None = None  # private: phone | voice
    decision: bool | None = None  # private: True = switch
    listen_id: str | None = None  # private


@dataclass
class OxRound:
    picks: dict[int, str] = field(default_factory=dict)  # private until ox.choices_revealed
    revealed: list[dict] | None = None
    betrayal: BetrayalState | None = None


@dataclass
class Consent:
    """The short window in which the other players say whether the requester may have a hint (private)."""
    seat: int  # the requester
    voters: tuple[int, ...]
    deadline: int
    listen_id: str | None = None
    votes: dict[int, bool] = field(default_factory=dict)  # phone votes by seat: True = agree
    voice_yes: int = 0  # spoken agreements (the room mic cannot tell who spoke)
    voice_no: int = 0

    @property
    def refused(self) -> bool:
        return self.voice_no > 0 or not all(self.votes.values())

    @property
    def explicit_yes(self) -> int:
        return sum(self.votes.values()) + self.voice_yes

    @property
    def complete(self) -> bool:
        """Everyone said yes, or somebody said no: nothing more to wait for."""
        return self.refused or self.explicit_yes >= len(self.voters)


@dataclass
class BuzzRound:
    armed: bool = False  # buzzer accepts presses right now
    holder: int | None = None
    locked: list[int] = field(default_factory=list)
    attempts: list[tuple[int, bool]] = field(default_factory=list)
    media_playing: bool = False
    level: int = 0
    winner: int | None = None
    # reading (private)
    reading_token: str | None = None
    # answering (private)
    answer_deadline: int | None = None
    listen_id: str | None = None
    listen_attempt: int = 0
    failures: int = 0
    text_box: bool = False
    answer: tuple[str, str] | None = None  # (text, source)
    # music (private)
    clip: tuple[int, float, float] | None = None  # (level, start, end) while a clip is playing or being interrupted
    interrupt_pending: bool = False
    interrupted_at: int = 0
    media_end: tuple[str, float] | None = None
    # spoken hints on request (private, music question only)
    hint_asked: set[int] = field(default_factory=set)  # seats that asked once already
    hints_given: int = 0  # 0..3: clue 1, clue 2, the composer
    hint_request: bool = False  # the holder asked for a hint; the flow picks it up
    hint_notice: bool = False  # "no hints" was already said in this answer turn
    consent: Consent | None = None
    composer_out: bool = False  # the composer was handed to the MC: no longer secret


@dataclass
class FinalRound:
    category: str | None = None  # public once final.category was sent
    bets: dict[int, int] = field(default_factory=dict)  # private until each bet_revealed
    choices: dict[int, str] = field(default_factory=dict)  # private until final.choices_revealed
    bet_placed: set[int] = field(default_factory=set)
    answer_placed: set[int] = field(default_factory=set)
    revealed_choices: list[dict] | None = None
    revealed_bets: list[dict] | None = None
