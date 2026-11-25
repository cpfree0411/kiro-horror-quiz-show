"""A GameHost whose engine has tiny windows, so real-clock tests finish quickly."""
import random

from khqs.engine.config import EngineConfig
from khqs.engine.core import Engine
from khqs.server.host import GameHost


class FastHost(GameHost):
    def _new_engine(self):
        cfg = EngineConfig(ox_answer_ms=150, betrayal_input_ms=100, prompt_failsafe_ms=400, reading_failsafe_ms=500,
                           buzzer_answer_ms=150, buzzer_open_ms=150, music_open_ms=150, media_interrupt_wait_ms=100,
                           media_watchdog_extra_ms=100, final_bet_ms=150, final_answer_ms=150, gate_grace_ms=20,
                           gate_timeouts={k: 40 for k in EngineConfig().gate_timeouts})
        return Engine(self.bank, self.clock, random.Random(3), cfg, mc_enabled=True, voice_input=False)
