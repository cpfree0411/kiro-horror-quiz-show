# Stage credits

Sources of everything the stage ships. Music-question assets (`media/`) have their own `CREDITS.md`.

## Art

All plates and sprites in `assets/` were made for this project: the project's concept images edited and extended
with ChatGPT image generation under the owner's direction, then cut, aligned and graded by the scripts in `tools/`.
Code-drawn parts (verdict badges, text, lights, moths, the ghost's face, the opening sheet) are in `stage.js`,
`stage.css` and `assets/opening-art.js`.

Fonts are loaded from Google Fonts (SIL Open Font License): Alfa Slab One, Black Han Sans, Fredoka, Do Hyeon,
Special Elite (stage); Black Han Sans, Fredoka, Special Elite, Stardos Stencil (phone ticket).

## Sound

Processing is trimming, looping and level only (no filters or reverb), unless a note says otherwise. Synthetic sounds
(stab, cheer, ding, twist, squeak, flutter, bonk, fluorescent hum, the lobby fallback waltz and others) are generated
in `sound.js` and have no external source.

### Generated with Google Gemini (by the project owner)

| File | Source track | Use |
| --- | --- | --- |
| `bgm_lobby.ogg` | Midnight_Sideshow | lobby BGM (through the radio channel) |
| `sfx_trans_bats.ogg` | The Puppet's Midnight Trick, 53.0–57.7 s | act 1 → 2 transition |
| `sfx_act_start.ogg` | The Puppet's Midnight Trick, 21.5–24.0 s | sound lab only |
| `sfx_trans_pumpkin.ogg` | Pumpkin Tumble, 53.0–57.7 s | act 2 → 3 transition |
| `sfx_final_bet_intro.ogg` | Tiptoeing Past the Curtain, 0–3.85 s + 60.1–63.5 s | sound lab only |
| `sfx_lead_a/b/c.ogg` | The Trick Question, three short cuts | sound lab only |

### From Pixabay (Pixabay Content License)

Author names and ids as shown on Pixabay. Many `freesound_community` items are Freesound uploads mirrored on Pixabay.

| File | Pixabay item (author – title – id) | Use |
| --- | --- | --- |
| `sfx_jingle_intro.ogg` | alex_besss – The Clowns in Circus – 356787 (first 4 s) | curtain-up jingle |
| `bgm_finale_wait.ogg` | alex_besss – The Tent Circus – 371589 | winner BGM |
| `bgm_lobby_sutton.ogg` | sutton – Cinematic Background Horror – 627238 (from 16.9 s) | opening BGM |
| `bgm_betrayal.ogg` | bentomusic – Comical Style Music of Silliness and Goofing Around (loop) – 439124 | betrayal-chance BGM |
| `bgm_betting.ogg` | sergequadrado – Funky and Jazzy Gang (loop) – 251858 | act 3 betting BGM |
| `sfx_finale_orchestra.ogg` | mrwashingt0n – Orchestral Radio – 531057 | sound lab only |
| `sfx_roll.ogg`, `sfx_roll_up.ogg`, `sfx_crash.ogg` | freesound_community – 065391_drumroll.wav – 88344 (crash = its final cymbal) | drumrolls, cymbal |
| `sfx_roll_alt.ogg` | 47660826 – Drum Roll Sound Effect – 278576 | sound lab only |
| `sfx_roll_comedy.ogg` | universfield – Comedy Drum Roll – 242242 | act 1 OX reveal |
| `sfx_roll_tada.ogg` | freesound_community – Tadaa – 47995 | winner announcement |
| `sfx_tada.ogg` | freesound_community – Tada Fanfare A – 6313 | fanfare |
| `sfx_correct.ogg` | freesound_community – Ding – 47489 | act 1 / act 3 correct |
| `sfx_correct_dingdong.ogg` | freesound_community – Ding-Dong – 81717 | act 2 correct |
| `sfx_buzzer.ogg` | freesound_community – Buzzer2 – 6109 | act 2 buzz |
| `sfx_clock_tick.ogg`, `sfx_time_up.ogg` | freesound_community – Tickingbuzzer – 75859 | thinking time, time-up buzzer |
| `sfx_wahwah_a.ogg` | freesound_community – Wah Wah Sad Trombone – 6347 | wrong answer |
| `sfx_wahwah_b.ogg` | floraphonic – Brass Fail 8 B – 207131 (played at 1.5× speed) | wrong answer |
| `sfx_crowd_gasp.ogg` | universfield – Crowd Shocked Reaction – 352766 | change of mind, all-in |
| `sfx_crowd_aww.ogg` | universfield – Crowd Disappointment Reaction – 352718 | act 2 wrong |
| `sfx_crowd_boo.ogg` | dragon-studio – Crowd Booing – 494319 | all wrong |
| `sfx_applause.ogg` | driken5482 – Applause Cheer – 236786 | curtain up, correct, winner |
| `sfx_crowd_murmur.ogg` | freesound_community – Crowd Noise Large Theater – 70982 | end of act 3 → winner |
| `sfx_jingle_brass.ogg` | cartoon_music – Game Show Brass Intro Sting – 504456 | sound lab only |
| `creak_a/b/c.ogg` | freesound_community – Metallic Creak – 43679 (stretched/pitched by `tools/make_creak.py`) | lobby sign crank (`creak_a`) |

The Pixabay Content License allows use in a project without attribution; it does not allow redistributing the sound
files on their own. Shipping them inside the app is the intended use. This list is kept for transparency.
