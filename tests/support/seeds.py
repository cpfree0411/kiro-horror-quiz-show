import random

from support.content_fixture import BANK


def seed_for_track(key: str, game_index: int = 0) -> int:
    """A seed whose first RNG draw (the music track) is the wanted track."""
    for seed in range(1000):
        if BANK.select(game_index, random.Random(seed)).track.key == key:
            return seed
    raise AssertionError("no seed found")
