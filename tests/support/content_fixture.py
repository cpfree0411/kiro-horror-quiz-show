"""Small fixture bank for engine tests. Not the shipped English bank (that is P4).

Answers and explanations never appear in question texts or choices, so the secrecy scanner can
look for them as plain strings. The first set mirrors the scenario files where the data matters.
"""
from khqs.content.model import (BuzzerQuestion, ContentBank, Credit, FinalQuestion, MusicTrack, OxQuestion,
                                QuestionSet)


def _track(key, asset, title, aliases, expl, clues, credit_title):
    return MusicTrack(
        key=key, asset_id=asset, bytes=412000, duration_sec=30.0, answer=title, aliases=tuple(aliases),
        explanation=expl, clips=((12.0, 20.0), (0.0, 16.0), (0.0, 30.0)), clues=tuple(clues),
        credit=Credit(title=credit_title, author="Test Composer", performer="Test Orchestra",
                      license="Public domain (fixture)", source="https://example.invalid/fixture"))


TRACKS = (
    _track("dm", "a-3f9c1d2e7b40", "Danse Macabre", ["Danse Macabre", "죽음의 무도", "Dance Macabre"],
           "Saint-Saëns, Danse Macabre", ["It is played by a full orchestra with a solo fiddle.", "A clock strikes twelve at the start."],
           "Danse macabre"),
    _track("hk", "a-8a1d00c2f917", "In the Hall of the Mountain King", ["Hall of the Mountain King", "산왕의 궁전"],
           "Grieg, In the Hall of the Mountain King", ["It starts quietly and keeps speeding up.", "The tune creeps along low strings."],
           "In the Hall of the Mountain King"),
    _track("tf", "a-c47e5b09d3a2", "Toccata and Fugue in D minor", ["Toccata and Fugue", "토카타와 푸가", "토카타 푸가"],
           "Bach, Toccata and Fugue in D minor", ["It is played on a very big keyboard instrument.", "Three quick notes open it."],
           "Toccata and Fugue in D minor"),
)

SET_A = QuestionSet(
    id="set-a",
    ox=(
        OxQuestion("q-ox-01", "Monster Biology", "An octopus has three hearts.", "O", "Octopuses really do have three hearts."),
        OxQuestion("q-ox-02", "Spooky Facts", "Vampire bats really live on the blood of other animals.", "O",
                   "Vampire bats are mammals that live on blood alone."),
        OxQuestion("q-ox-03", "Creepy Crawlies", "A spider is an insect.", "X", "Spiders have eight legs, so they are arachnids."),
    ),
    buzzers=(
        BuzzerQuestion("q-bz-01", "Midnight Superstitions", "At midnight, what should you never look into before bed?",
                       "Mirror", ("The mirror", "거울"), "The midnight mirror"),
        BuzzerQuestion("q-bz-02", "Autumn Harvest", "Which glowing fruit gets a carved smile on Halloween?",
                       "Pumpkin", ("Jack-o'-lantern", "호박"), "Pumpkins become jack-o'-lanterns."),
        BuzzerQuestion("q-bz-03", "Witch's Kitchen", "What do witches ride through the night sky?",
                       "Broomstick", ("Broom", "빗자루"), "A broom is the classic witch's ride."),
    ),
    final=FinalQuestion("q-final-01", "Cursed Legends", "In Mary Shelley's novel, whose name is 'Frankenstein'?",
                        ("The monster", "The scientist who made it", "The village it was born in", "The detective chasing it"),
                        "B", "Frankenstein is the surname of Victor Frankenstein, the scientist who made the monster."),
    music_position=2,
)

SET_B = QuestionSet(
    id="set-b",
    ox=(
        OxQuestion("q-ox-11", "Bat Facts", "Bats are blind.", "X", "Bats can see, and many see quite well."),
        OxQuestion("q-ox-12", "Candle Lore", "A candle burns with a flame of wax vapor.", "O", "The wick draws melted wax up, and the vapor burns."),
        OxQuestion("q-ox-13", "Ghost Stories", "Ghosts have been photographed by science labs.", "X", "No lab has ever confirmed one."),
    ),
    buzzers=(
        BuzzerQuestion("q-bz-11", "Haunted Rooms", "What creaky thing connects the floors of a haunted house?",
                       "Staircase", ("Stairs", "계단"), "Haunted houses always have creaky stairs."),
        BuzzerQuestion("q-bz-12", "Night Sounds", "Which animal howls at the full moon in stories?",
                       "Wolf", ("Werewolf", "늑대"), "The wolf howls at the moon."),
        BuzzerQuestion("q-bz-13", "Sweet Treats", "What sweet do children collect when trick-or-treating?",
                       "Candy", ("Sweets", "사탕"), "Candy fills the trick-or-treat bags."),
    ),
    final=FinalQuestion("q-final-11", "Spooky Science", "Which planet is nicknamed the Red Planet?",
                        ("Venus", "Mars", "Jupiter", "Mercury"), "B", "Mars looks red because of iron oxide dust."),
    music_position=3,
)

BANK = ContentBank(sets=(SET_A, SET_B), tracks=TRACKS)
