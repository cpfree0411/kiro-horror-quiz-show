"""DEVELOPMENT content so the server can run before P4. P4 replaces this with the real English bank.

The three music tracks are the real files in media/, referenced by opaque asset ids. Credits follow
docs/HANDOFF.md section 9 and media/CREDITS.md.
"""
from __future__ import annotations

from pathlib import Path

from .model import (BuzzerQuestion, ContentBank, Credit, FinalQuestion, MusicTrack, OxQuestion, QuestionSet,
                    validate_bank)

MEDIA_FILES = {  # opaque asset id -> file in media/ (the id says nothing about the piece)
    "a-3f9c1d2e7b40": "danse_macabre.mp3",
    "a-8a1d00c2f917": "mountain_king.mp3",
    "a-c47e5b09d3a2": "bwv565.mp3",
}
CLIPS = ((0.0, 7.0), (0.0, 16.0), (0.0, 30.0))


def _track(media_dir: Path, key, asset, title, aliases, expl, clues, credit):
    size = (media_dir / MEDIA_FILES[asset]).stat().st_size
    return MusicTrack(key=key, asset_id=asset, bytes=size, duration_sec=30.0, answer=title, aliases=tuple(aliases),
                      explanation=expl, clips=CLIPS, clues=tuple(clues), credit=credit)


def build_dev_bank(media_dir: Path) -> ContentBank:
    tracks = (
        _track(media_dir, "dm", "a-3f9c1d2e7b40", "Danse Macabre", ["Danse Macabre", "죽음의 무도", "Dance Macabre"],
               "Saint-Saëns, Danse Macabre", ["A solo fiddle plays tricks with an out-of-tune string.", "A clock strikes twelve at the start."],
               Credit("Danse macabre, Op. 40", "Public domain (US): PD-US-record-expired", author="Camille Saint-Saëns",
                      performer="Philadelphia Orchestra, cond. Leopold Stokowski (1925)",
                      source="https://commons.wikimedia.org/wiki/File:PhiladelphiaSymphonyOrchestra-DanseMacabre.ogg")),
        _track(media_dir, "hk", "a-8a1d00c2f917", "In the Hall of the Mountain King",
               ["Hall of the Mountain King", "산왕의 궁전", "마왕의 궁전"], "Grieg, In the Hall of the Mountain King",
               ["It starts quietly and keeps speeding up.", "The tune creeps along on low strings."],
               Credit("In the Hall of the Mountain King (Peer Gynt Suite No. 1, Op. 46)", "Public domain (Musopen)",
                      author="Edvard Grieg", performer="Czech National Symphony Orchestra (for Musopen)",
                      source="https://commons.wikimedia.org/wiki/File:Musopen_-_In_the_Hall_Of_The_Mountain_King.ogg")),
        _track(media_dir, "tf", "a-c47e5b09d3a2", "Toccata and Fugue in D minor",
               ["Toccata and Fugue", "토카타와 푸가", "토카타 푸가"], "Bach, Toccata and Fugue in D minor",
               ["It is played on a very big keyboard instrument.", "Three quick notes open it."],
               Credit("Toccata and Fugue in D minor, BWV 565", "CC BY-SA 3.0",
                      author="Johann Sebastian Bach", performer='Wikipedia user "Cor anglais 16" (Flentrop organ, Oberlin Conservatory)',
                      source="https://commons.wikimedia.org/wiki/File:BWV-565-intro.ogg")),
    )
    set_a = QuestionSet(
        id="dev-a",
        ox=(OxQuestion("q-ox-01", "Monster Biology", "An octopus has three hearts.", "O", "Octopuses really do have three hearts."),
            OxQuestion("q-ox-02", "Spooky Facts", "Vampire bats really live on the blood of other animals.", "O",
                       "Vampire bats are mammals that live on blood alone."),
            OxQuestion("q-ox-03", "Creepy Crawlies", "A spider is an insect.", "X", "Spiders have eight legs, so they are arachnids.")),
        buzzers=(BuzzerQuestion("q-bz-01", "Midnight Superstitions", "At midnight, what should you never look into before bed?",
                                "Mirror", ("The mirror", "거울"), "The midnight mirror"),
                 BuzzerQuestion("q-bz-02", "Autumn Harvest", "Which glowing fruit gets a carved smile on Halloween?",
                                "Pumpkin", ("Jack-o'-lantern", "호박"), "Pumpkins become jack-o'-lanterns."),
                 BuzzerQuestion("q-bz-03", "Witch's Kitchen", "What do witches ride through the night sky?",
                                "Broomstick", ("Broom", "빗자루"), "A broom is the classic witch's ride.")),
        final=FinalQuestion("q-final-01", "Cursed Legends", "In Mary Shelley's novel, whose name is 'Frankenstein'?",
                            ("The monster", "The scientist who made it", "The village it was born in", "The detective chasing it"),
                            "B", "Frankenstein is the surname of Victor Frankenstein, the scientist who made the monster."),
        music_position=2)
    set_b = QuestionSet(
        id="dev-b",
        ox=(OxQuestion("q-ox-11", "Bat Facts", "Bats are blind.", "X", "Bats can see, and many see quite well."),
            OxQuestion("q-ox-12", "Candle Lore", "A candle flame burns wax vapor.", "O", "The wick draws melted wax up, and the vapor burns."),
            OxQuestion("q-ox-13", "Ghost Stories", "A lab has confirmed that ghosts exist.", "X", "No lab has ever confirmed one.")),
        buzzers=(BuzzerQuestion("q-bz-11", "Haunted Rooms", "What creaky thing connects the floors of a haunted house?",
                                "Staircase", ("Stairs", "계단"), "Haunted houses always have creaky stairs."),
                 BuzzerQuestion("q-bz-12", "Night Sounds", "Which animal howls at the full moon in stories?",
                                "Wolf", ("Werewolf", "늑대"), "The wolf howls at the moon."),
                 BuzzerQuestion("q-bz-13", "Sweet Treats", "What sweet do children collect when trick-or-treating?",
                                "Candy", ("Sweets", "사탕"), "Candy fills the trick-or-treat bags.")),
        final=FinalQuestion("q-final-11", "Spooky Science", "Which planet is nicknamed the Red Planet?",
                            ("Venus", "Mars", "Jupiter", "Mercury"), "B", "Mars looks red because of iron oxide dust."),
        music_position=3)
    bank = ContentBank(sets=(set_a, set_b), tracks=tracks)
    problems = validate_bank(bank)
    if problems:
        raise ValueError("dev bank invalid: " + "; ".join(problems))
    return bank
