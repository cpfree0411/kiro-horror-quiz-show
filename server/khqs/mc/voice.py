"""Voiced-audio evidence for a listen window (PCM16 mono, 16 kHz). Pure and deterministic.

Audio is held back until it is voiced; only then does the adapter start a Live activity. The same measurements
say when speech ended. Evidence is measured on the PCM actually forwarded, never on the model's claims.
"""
from __future__ import annotations

import array
import math
from dataclasses import dataclass

BYTES_PER_MS = 32  # 16 kHz * 2 bytes


def rms(pcm: bytes) -> float:
    n = len(pcm) // 2
    if n == 0:
        return 0.0
    a = array.array("h")
    a.frombytes(pcm[: n * 2])
    return math.sqrt(sum(x * x for x in a) / n) / 32768.0


@dataclass
class MeterResult:
    forward: bytes = b""
    started: bool = False  # voiced evidence reached on this chunk: send activity_start first
    ended: bool = False  # speech finished (silence after speech, or the length cap)


class VoiceMeter:
    def __init__(self, rms_floor: float = 0.012, min_voiced_ms: int = 160, end_silence_ms: int = 700, max_ms: int = 16000) -> None:
        self.floor, self.min_voiced_ms, self.end_silence_ms, self.max_ms = rms_floor, min_voiced_ms, end_silence_ms, max_ms
        self.held = bytearray()
        self.voiced_ms = 0.0
        self.silent_ms = 0.0
        self.total_ms = 0.0
        self.peak = 0.0
        self.started = False
        self.ended = False

    @property
    def voiced(self) -> bool:
        """True once real voiced audio was seen (the evidence the engine asks for)."""
        return self.voiced_ms >= self.min_voiced_ms

    def feed(self, pcm: bytes) -> MeterResult:
        if self.ended or not pcm:
            return MeterResult()
        ms = len(pcm) / BYTES_PER_MS
        level = rms(pcm)
        self.total_ms += ms
        self.peak = max(self.peak, level)
        if level >= self.floor:
            self.voiced_ms += ms
            self.silent_ms = 0.0
        else:
            self.silent_ms += ms
        res = MeterResult()
        if not self.started:
            self.held += pcm
            if self.voiced:
                self.started, res.started = True, True
                res.forward, self.held = bytes(self.held), bytearray()
            elif len(self.held) > 2 * 1000 * BYTES_PER_MS:  # keep at most ~2 s of lead-in
                del self.held[: len(self.held) - 2 * 1000 * BYTES_PER_MS]
            return res
        res.forward = pcm
        if self.silent_ms >= self.end_silence_ms or self.total_ms >= self.max_ms:
            self.ended = res.ended = True
        return res
