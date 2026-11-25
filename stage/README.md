# KHQS stage v3 — lobby, opening, acts 1–3, finale

The show's screen. Painted plates (GPT edits of the original concept images) with text, scores, badges, lights,
audience, the ghost host and player motion drawn on top by code. A mock engine replays the scenarios in
`interface/scenarios` over the `khqs.stage/1` protocol, so the stage runs on its own with no server.

**This folder is frozen.** A real engine attaches through the connector contract (see `docs/HANDOFF.md` §5 in the
handoff package and `interface/KHQS_STAGE_INTERFACE.md`); it does not edit these files.

| Act | Mock scenario | What it shows |
| --- | --- | --- |
| 1 OX | `duo-act1-ox-betrayal` | 2 players + empty-seat board, players rising behind the O/X ledges, unanimity stamp, betrayal-chance roulette spotlight, correct-card highlight |
| 2 Buzzer | `trio-act2-buzzer-music` | 3 lecterns, **scores on the lectern name plates**, top frames = question number / buzzer state, BUZZ!, answer speech bubbles, buzzing during a music question |
| 3 Final | `trio-act3-final-allin` | category, secret bet lock, 4 choices on a drop-in board, deadline timer, bets revealed one by one (ALL IN), correct highlight, winner |

Paths below that point outside this folder (`review/…`, `kiro-assets/…`, `ASSET_ORDER_*.md`) are the art and review
workspace on the author's PC. They are not part of the package; they are named so the build tools make sense.

## Running

Open `index.html` in Chrome or Edge. No server is needed for the mock replay (web fonts need internet).
Sound starts on the first click. Sound **files** (`assets/sound/`) need http: under `file://` the fetch is blocked and
the synthetic fallbacks play instead. Serve the folder (any static server) to hear the real files.

Script order in `index.html` matters: `assets/manifest.js`, `scenarios.js`, `sound-files.js`, `sound.js`,
`mock-engine.js`, `qr.js`, `assets/opening-art.js`, `stage.js`. A connector is injected right after `mock-engine.js`.

**HUD:** act buttons (keys 1/2/3), `Opening` (key 0), Space pause, R restart, S sound, L protocol log, scene chips to jump.

**Hash options**

| Hash | Effect |
| --- | --- |
| `#act=N` | play act N's mock scenario; when it ends, chain into the next act through its transition |
| `#act=3&step=25&clean` | stop just before step 25; `clean` hides the control panel (screenshots) |
| `#opening` (alias `#showtime`) | lobby → blackout → 3-2-1 → sheet → host reveal → iris → lit stage |
| `#opening&clean` | auto-registers two players and starts; `&cast=A,B` sets names, `&stay` stays in the lobby, `&qr=URL` previews a QR |
| `#demo` | unattended full run: lobby (Mina, Junho, Ray join) → opening → act 1 → bats → act 2 → pumpkins → act 3 → finale. Sets `window.KHQS_showDone` at the end |
| `&badge=halloween\|plain` | verdict badge style (also HUD button / `B` key; saved in the browser) |
| `&verdict=2x` / `&stuck` | review a big verdict badge on seat 2 / stuck on the lectern |
| `#act=1&trans=act&clean` | review the bat transition (`act=2` → pumpkins; `act=3&trans=newshow` → finale → bats → lobby with a fake reset) |
| `#act=3&finale=1\|2\|3\|tie` | review the finale from the curtain; `&still` jumps to the finished picture |

`#demo` is a highlight reel: each act is a separate scenario, so questions are skipped between acts and scores do not
carry over. Its act 1 is a trio version (`demoTrioAct1`; Ray picks X twice and is wrong).

Recording: `uv run --with websocket-client --with imageio-ffmpeg python review/tools/record_demo.py stage-v3 demo review/demo/khqs_full_demo.mp4`
makes a real-time 30 fps MP4 with headless Chrome. **It has no sound** (WebAudio is not captured). For sound, open
`#demo` in a browser and screen-record.

Replay hashes (`act=`, `step=`, `opening`, `showtime`, `clean`, `verdict=`, `demo`, `finale=`, `trans=`) are mock-only.
A connector must leave the mock in place when any of them is present.

## Entry hooks

- `window.KHQS_ENTRY = { join(name), start() }` and `window.KHQS_JOIN_URL` route the lobby to a real engine. Without them the mock engine handles joins.
- Phone ticket: `ticket.html`. Define `window.KHQS_TICKET_JOIN = async name => ({ ok: true } | { error: '…' })` in its `<head>`; without it the ticket talks to a same-origin stage demo tab over BroadcastChannel.
- If a real server shows only the audience and a dark background, check the stage connection first (a second tab holding the `primary` role was the cause once).

## Lobby — the TONIGHT'S CAST wall

One painted wall (`assets/lobby`) with code on top. Positions live in `CAST` in `stage.js`; `tools/build_cast_lobby.py` builds the art from the same values.

- **QR note** (left frame): the real join URL. If phones cannot reach it (file, localhost) a notice is printed instead.
- **Three cast cards:** an empty seat is the `?` silhouette in the background. On `seat.joined`: jolt → flip to blank paper (`assets/lobby_cards`) → name types in letter by letter → portrait stamped on (the monster art multiplied in, like print) → sign bulbs sweep. `seat.left` flips back; a lost `seat.connection` greys the card.
- **Typing a name** into the first empty card's name tag joins without a phone.
- **Bulbs:** the powered-off background (`assets/lobby_dark`) is laid over a single bulb in a circle to turn it off; they flicker irregularly.
- **IT'S SHOWTIME! sign:** rises from behind the shelf once at least one player is in; clicking calls `KHQS_ENTRY.start()`. The lit art (`showtime_on`) sits over the unlit art (`showtime_off`) and is shown/hidden. Wiggles on hover (`cbWiggle`).
- **Pointer:** 0.9 s after the sign lights, an old-style pointing hand and `CLICK!` pop up left of it (`showPointer`); the hand jabs twice every 1.6 s and the word blinks every 0.45 s (`paintPointer`; glow is CSS brightness + orange). It shrinks away on click or when the sign drops; it vanishes at once on blackout. Art: `tools/build_pointer.py` cuts only the hand and word from the delivered plywood picket. Position: `PT` in `stage.js`.
- **Faded look:** `.lobby` has `saturate(.72) sepia(.14) brightness(.88) contrast(.97)` plus an edge vignette (`.cb-dull`, z-index 20, click-through). Change values, not art.
- **Lights up** (`lightsUp`): wall lamps flicker on and the sign bulbs come in on first load.
- **Wall lamps:** breathe slightly and sag now and then (`lampSag`, unlit art at 0–0.5). Five tiny SVG moths circle under the shades and bump the bulbs (`paintMoths`); they go out with the lamp. During the blackout (`wallOut`) the moths are drawn there because the lobby loop stops at START.
- **Blackout:** on start, bulbs go out one by one, then with `assets/lobby_off` (all lights out) one gust puts out both candles and the lantern (staggered by tens of ms; 4th value in `CAST.flames`), the pumpkin 0.4 s later, then black. The room darkens as a whole (`lobby_off` fades in) and pools of light (`lobby_dark`) remain around the lights still burning; a dead candle is covered by `lobby_snuff` (flame erased, brightness kept) inside every pool that reaches it, so no black holes appear. Then the sheet's darkness (snoring).
- Art: four images from `kiro-assets/KHQS_v12/` → `build_cast_lobby.py`. The three backgrounds align within 1 px (the script reports any offset).

## Opening

The sheet section's art (cloth texture, clips, title card) is built by `assets/opening-art.js`; `createOpening` in
`stage.js` does the motion and order. `index.html` must load `assets/opening-art.js` before `stage.js` (it is under
`assets/` so a play server that only serves `assets/` scripts can still send it). The cloth texture is baked once per
page, not filtered every frame.

The whole opening is one `show.opening` gate, closed after the lights come up (MC_READY). `Esc` or SKIP skips it.

## Assets

`python stage-v3/tools/build_assets_v3.py` builds from the labelled `KHQS_v3` / `KHQS_v4` / `KHQS_v5` folders: 3 plates,
12 character stickers, 8 audience heads + 6 seats, 12 ghost poses, the empty-seat board, the BUZZ burst and more
(46 files, about 1.6 MB). Needs Pillow. Text positions on the plates are in `LAYOUT` (1600×900 design coordinates) in
`stage.js`; re-measure them if a plate changes.

Every other build tool **appends to** `manifest.js`, so rerun them after `build_assets_v3.py` (which rewrites it).
All tools hard-code the author's art folders and will not run without that source art; they are kept as a record of
how each asset was made.

| Tool | Makes | Needs |
| --- | --- | --- |
| `build_act1_ledges.py` | rewrites `plate1.webp` with the act 1 voting ledges (`build_assets_v3.py` does the same composite) | Pillow |
| `build_decoys.py` | `decoy_sack`, `decoy_tophat_skull`, `decoy_vampire`, `decoy_bolt` | numpy, opencv |
| `build_listen_bubbles.py` | `listen`, `bubble_s`, `bubble_l` (with `inner` text box and `tip`) | numpy, opencv |
| `build_act3_question.py` | `plate3q`, `qboard3` (with its x, y) | numpy, opencv |
| `build_curtain.py` | `curtain` (left half, mirrored), `sign_winner`, `sign_score` | numpy, opencv |
| `build_bats_pumpkins.py` | `bat_0..2`, `bat_big`, `pk_0..5`, `pk_bit_0..8` | numpy, opencv |
| `build_finale.py` | `plateF`, `frontF`, `fin_pod1..3`, `fin_trophy`, `fin_crown`, `fin_rosette`, `fin_theend`, `fin_bouquet` | numpy, opencv |
| `build_cast_lobby.py` | `lobby`, `lobby_dark`, `lobby_off`, `lobby_snuff`, `lobby_cards`, `showtime_off/on` | numpy, opencv |
| `build_pointer.py` | `pointer_hand`, `pointer_word` | numpy, opencv |
| `build_sfx.py`, `make_loop.py`, `find_loop.py`, `make_creak.py` | sound files (see Sound) | numpy, imageio-ffmpeg |

## Act 1 — ledges and the decoy gag

- When picks are revealed (`ox.choices_revealed`), each player rises behind the ledge in front of the card they chose (up to three per card). Changing one's mind in the betrayal chance moves them across (`betrayal.decided`). On the answer, the right side cheers and the wrong side slumps. The correct card's halo spreads only outside its border. Back edge of the ledges: `LAYOUT[1].ledgeY`.
- The same character on the scoreboard and the ledge would look like two people, so on `ox.submitted` the scoreboard character ducks below the window and a crude plywood cut-out of it pops up in its place (`duck`, `makeSign`): a scarecrow hiding the empty seat. The ledges stay empty until the reveal, so nothing leaks; only players who have not answered still show as characters. The `?` badge is therefore not used in act 1.
- On `score.settled` the players drop from the ledges and pop back up on the scoreboard with their cheer/slump face, then the score rolls. The roulette light, shake and `…` bubble of the betrayal chance aim at the body on the ledge (`bodyAt`).
- Betrayal chance for first-time viewers: `betrayal.offered` slams a big `BETRAYAL CHANCE` stamp mid-stage (`slamStamp`, about 1 s) and flies it to the stamp spot on the board. When the roulette stops, a `STAY X  OR?  BETRAY O` strip appears above the audience (`betrayPick`, the current and opposite answers as text). On `betrayal.decided` the chosen side glows, the other dims, then the strip leaves (`betrayPicked`).
- No countdown is shown here: the engine sends `deadline: null` for the `ox.betrayal` phase and counts the 8 s reason + 8 s decision internally. To show numbers the engine would have to send that deadline in `phase.changed` (or `betrayal.*`). No ticking sound, because the MC is listening to the player.

## Rule cards at act start

Acts 1 and 2 hang a three-line rule card on the empty board until the first question (`RULES`, `ruleCard`):
`HOW TO PLAY` / `PICK O OR X ON YOUR PHONE` · `EVERY RIGHT ANSWER +10` (act 1), `BUZZ IN & SAY IT!` ·
`RIGHT +20 · WRONG? SIT THAT ONE OUT` (act 2). These match the engine's scoring (act 1 +10, act 2 +20, no penalty,
a wrong act 2 answer locks that player's buzzer for that question). The card nudges once on `act.started`
(`rulesNudge`) and the first `showQuestion` clears it (`rulesOut`, 0.26 s; instant when fast). Act 2's side frames show
`4 QUESTIONS` and `GET READY…` before the first question.

The mock act 2 scenario stalls about 10 s before its first question: the stage sends `stage.media_ready` as soon as it
gets `act.started`, but the mock engine only starts waiting for it one step later and so waits for the timeout. In a
real engine run the first act 2 question came 3.85 s after `act.started`.

## Act 2 — LISTEN art and speech bubbles

While a question is hidden (music/listening questions) the board shows painted LISTEN art (gramophone, notes,
`LISTEN!`, a listening ghost); it leaves when the question text is revealed. Speech bubbles are torn-paper art
(`sayBubble`): the tail tip points at the speaker; up to four characters use the round one, longer text the long one.
Used for act 2 answers (`buzzer.answer_heard`) and the act 1 betrayal chance (`betrayal.listening`, a small `…`).

## Act 3 — the last question board

The act 3 plate's centre strip only fits one category line (652×115), so on `question.presented` a big question board
drops in on chains (`dropBoard`) and covers the FINAL BET sign and the strip. Question text up to 46 px, choices up to
32 px. Greeting, category and betting use the plain plate. The board is a red tin frame with gold trim and no bulbs
(the scoreboard bulb marquee stays). Text boxes inside it are in `buildAct3` in board-art coordinates; the A–D disc
position is `.choice3 b` in `stage.css`.

## Transitions

Full-screen covers that change the scene behind them are registered by name in `TRANSITIONS` in `stage.js`:
`curtain` (before the finale), `bat-swarm`, `pumpkin-pile`.

- Register: `layer => ({ cover(), uncover(), dispose(), …extras })`. `cover` must resolve when the screen is fully covered.
- Use: `runTransition(name, during, fast)`. After covering, `during(t)` changes the scene, then it uncovers. One at a time; `fast` (skip) just calls `during(null)`. A snapshot clears it via `clearTransition`, unless `t.span = true`.
- Layers: the curtain draws in `curL` (above the stage, below lights and front-row audience). Factories registered with `Object.assign(fn, { top: true })` (bats, pumpkins) draw in `topL`, above everything including the lobby. Clicks are blocked while drawing.
- Placement: act 1 → 2 bats, act 2 → 3 pumpkins (`ACT_TRANSITION`, when `act.started` changes the act number). Finale `NEW SHOW` → lobby uses bats (`newShow`): it resets the engine while covered and clears when the new lobby snapshot lands; if the reset fails it returns to the finale and re-enables the button.
- **Bats:** a diagonal night sweep. Four distant bats pass, then a swarm leads a dark band of night across left to right; the big bat is just the small leader (width 300). A few bats circle while covered; a second swarm drags the night's tail off to the right. Cover about 2.05 s, uncover about 1.45 s.
- **Pumpkins:** three drop one by one, then a rush, stacking in five rows; they squash, bounce and roll a little, the ones below flinch, rind bits and seeds fly. A dark backing fills behind them. Uncovering: they shudder and collapse downward. Cover about 2.5 s, uncover about 1.35 s.
- Synthetic sounds `squeak`, `flutter`, `bonk` are in `sound.js`.
- **Timing margin:** the engine waits 8 s on the `act.started` gate. Act 2 uses about 3.5 s bats + 1.6 s; act 3 about 3.9 s pumpkins + 2.6 s cheer = about 6.5 s, leaving about 1.5 s. Check this margin before making transitions longer.
- **Preview act chaining** (mock only): when an act's scenario ends, `crossAct(next)` loads the next scenario 2.5 s later behind that act's transition (1→2 bats, 2→3 pumpkins, act 3 ends in the finale). HUD act buttons take the same path (going back uses bats). The transition has `span` on and `restart(…, keepTrans)` keeps it and `keep` tweens, so the new scenario's first snapshot changes the stage behind the cover. Act buttons are ignored mid-transition. Not used with `trans=`, `finale=`, `verdict=`. The mock calls `engine.onEnd(scenario, run)` at the end of a scenario. The real engine path (`act.started`) is unchanged.

## Finale

The winner is announced when the curtain opens, not on the act 3 stage.

1. `finale.winner`: lights dim, the curtain closes, the stage changes to the finale behind it, then the `AND THE WINNER IS…` sign (`YOUR FINAL SCORE…` when solo) hangs with thumps behind the curtain. Then a `WINNER` sign (stab), lower podiums rise (pop), and just before first place the one drumroll (`rollTada`) plays; first place rises on its 'ta-da', the crown settles (`finaleReveal`). The MC's announcement comes after this gate closes, so the picture finishes first.
2. 1.2 s after the podiums, the stage starts its own ending: trophy and bouquet, then `THE END` drops 1.8 s later (about 2 s and 4.7 s after first place rises) (`finaleEnding`).
3. `NEW SHOW` and `KHQS_showDone` wait for the engine's end (`game.ended` / `finale.results`) (`finaleDone`), so a new show never opens while the MC is still talking. `drawFinale` (results drawn directly, missed or skipped announcement) and the `finale=N` review count as already ended.

- With three players the announcement takes about 10 s; the engine's `finale.winner` gate is 12 s, a margin of about 2 s. If it gets longer the engine moves on first (order is still kept by waiting on `finaleBusy`), so check engine timing too.
- Results: `WINNER`, `IT'S A TIE!`, or `SHOW COMPLETE!` (solo). Two players: two podiums, first on the left. Solo: one centre podium, no crown. Tie: two gold podiums, two crowns. Players use the existing stickers.
- **Winner dance:** after the crown lands, the winner(s) dance on the podium every frame (`finaleDance`): character + crown as one group pivoting at the feet, bouncing at 1.7 beats/s, tilting ±3.5°, the crown lagging slightly, easing in over 0.6 s. The art's bottom is hidden 9 px behind the podium, so the dance crouches 8 px and bounces only 6 px (no cut edge shows).
- **3rd-place podium:** the original art was short with a flat plaque; `tall_pod3` stretches the body under the number disc by 9% (wood grain and plaque stretched; the riveted side borders repeat a rivet-free band). Still the lowest of the three.

## Ghost host

Normally a faceless body (`ghost_body`) with eyes and mouth drawn by code (blinks, gaze, talking). Reactions swap to
11 expression pictures: call `ghostPose(name, holdMs)` from an event handler (0 = hold until the next pose). The
ghost glows, so it sits on a layer above the blackout (`ghostL`); the lectern and mic cut from the plate (`front1..3`)
are laid over it so it stands behind the lectern. The ghost art has the stage grade baked in (warm light, gold rim,
curtain bounce, lectern shadow, texture, ink outline). If a plate changes, re-measure the polygons in `save_front`.

## Sound

`sound.js` is the engine (WebAudio synth + file playback); `sound-files.js` is the registry (cue → file, BGM → track),
shared by the stage and `tools/sound_lab.html`. Sources and licences: [CREDITS.md](CREDITS.md).

**Rules that hold everywhere**

- SFX are crisp in every scene: trimmed and level-matched only (leading silence cut, active RMS −16 dBFS, peak ≤ 0.89, last 15 ms faded; `tools/build_sfx.py`). No filters, no reverb. Mix balance is the `gain` in the registry.
- `Sound.scene('lobby'|'show', s)` changes only the BGM radio channel. The output front end (`out → sceneLp → toneGain → comp`) is open in both scenes (lp 20 kHz, level 1, reverb 0.22).
- Never name a BGM `waltz`: a connector wraps `Sound.loop('waltz')` to play the real music-question asset.
- In-show BGM plays `clean` (stereo, no radio). Restart, act skip and a new game snapshot (`game.snapshot`) stop it.

**Registry format** (`FILE_DEFS` in `sound.js`): a path string, `{ src, gain, rate, peak, loopStart, loopEnd, up, cut }`,
or an array of those (one picked per hit). With `peak`, giving `opts.dur` starts the file late so the peak lands `dur`
seconds later. `Sound.loop(name, true, { dur })` plays the `up` version instead of the loop when it exists.
`playFile` takes `opts.rate`, `opts.gain`, `opts.swell: [startFactor, seconds]`; its handle's `stop(f)` takes a
fade time constant (default .1). `Sound.cue` returns `{ stop() }` for file sounds. Files registered in `KHQS_BGM` are
fetched on `unlock`; a synthetic stand-in of the same name is replaced as soon as the file arrives.

**Lobby BGM and the radio channel**

- Track: `Midnight_Sideshow` (Gemini-made cheap carnival waltz, 3/4, about 92 BPM) → `assets/sound/bgm_lobby.ogg`, 3.98 s intro once, then loops 3.98–40.46 s (gain 0.08). OGG, because MP3 encoder padding shifts loop points. Made with `tools/find_loop.py` (tempo + matching pair) → `tools/make_loop.py <src> <out.ogg> <start> <end> [head]` (keeps the intro, pre-mixes the last 80 ms with the sound before loopStart, peak 0.89).
- If the file is registered, the stage waits for it instead of starting the synthetic stand-in; if it fails, the synthetic `radioLobby` waltz plays (16 bars, toy piano + reed organ).
- `Sound.bgm(name|null, { fade })` routes lobby BGM through: mono bus → high-pass ×2 → broadcast compressor → peaking 1.15 kHz (speaker nasal) → peaking 2.1 kHz (wooden box) → low-pass ×2 → clean + valve-distorted (asymmetric tanh) mix → wow delay → radio fading (0.06 Hz and 0.17 Hz) → out. Radio noise (hiss + crackle + 120 Hz hum) enters before the high-pass. Lobby values: 520 Hz–2.3 kHz, nasal +10 dB, box +5 dB, distortion 0.5, compression 1, noise 1.1, fading 0.22. All off in `show`. The radio channel is fixed by the owner: a new lobby track only swaps the clean source.
- The lobby BGM fades over 1.6 s when START is pressed.
- Room sound: fluorescent hum `fluoroFlicker` (`BGM_AMB.lobby`, follows the lobby BGM, not through the radio): 0.6–1.1 s swells like a phone buzzing on a desk, 35% chance of a short second buzz, 75 Hz saw + 150 Hz square band-passed 0.29–1 kHz with +6 dB at 0.56 kHz, 9 Hz tremolo, level 0.016–0.023; first 1.5–3 s after entering the lobby, then every 5–12 s.
- Sign crank `creak` = `OPENING_SOUND_FILES.creak` (`creak_a.ogg`, stretched 'Metallic creak' via `tools/make_creak.py`), on the first and third of four winds (third at rate 1.08); synthetic stick-slip creak if missing. Pointer: `whistleUp` + `pop` when it appears, `knock` on the first three jabs only.

**Where each show sound plays**

| Moment | Sound |
| --- | --- |
| Opening title → iris | BGM `opening` (sutton track from 17 s, gain 0.3), in over 2 s at the title, out over 1.5 s as the iris closes; silent by the black frame |
| Curtain up (lobby → show) | `jingle` (The Clowns in Circus, first 4 s) + `applause` 0.2 s later |
| Act 1 start | synthetic `stab`, `cheer` 0.3 s later |
| Act 1 → 2 / 2 → 3 | `transBats` / `transPumpkin` jingles (bang lands as the new stage is revealed); `cheer` stays, no `stab` or `fanfare` |
| Thinking time (act 1 `ox.answering`, act 3 `final.answering`) | `clockTick` loop; on leaving the phase after its deadline (+0.4 s) the `timeUp` buzzer; no buzzer if everyone answered early |
| Act 1 OX reveal | `rollComedy` (has its own ending, no crash) |
| Act 1 answer, someone right | `crash`, then `correct` (ding-dang-dong) + `applause` 0.25 s later, faded out after 2.6 s (`correctCheer()`); wah-wah `sad` 0.5 s later only if the player offered the betrayal chance (`A1.btrSeat`) was wrong |
| Act 1 all wrong | `crash`, then `sad` + `boo` |
| Betrayal chance | BGM `betrayal` (gain 0.4) from the roulette stop to `betrayal.decided` (0.5 s fade); `gasp` on a change of mind |
| Act 2 buzz | `buzz` (buzzer press) |
| Act 2 judgement | right: `dingdong` + `applause` (`correctCheer()`); wrong: `sad` + `aww`; the later `answer.revealed` is silent if someone was right, `sad` + `boo` if nobody was |
| Act 2 hint | synthetic `ding` |
| Drumrolls | `roll` (unknown length: intro then 1.96–2.96 s loop); known lengths (reveal 0.9 s, act 3 1.1 s) use `rollUp` started late so 4.20 s lands at the end |
| Cymbal | `crash` (the same recording's cymbal, gain 0.45): act 3 bets locked, choices revealed, non-all-in bet reveals. Not on act 3 `answer.revealed` (drumroll → answer sound directly) |
| Act 3 betting | BGM `betting` from `final.betting` to `final.bets_locked` (0.6 s fade) |
| Act 3 all-in bet reveal | `fanfare` + `gasp` (with the audience `shock` pose) about 0.5 s later |
| Act 3 answer | someone right: `correct` + `applause`, `sad` 0.5 s later if mixed; all wrong: `sad` + `boo` |
| Lead change | synthetic `twist` (xylophone C-E-G-C run) + clapping pose |
| End of act 3 → winner drumroll | `crowdMurmur` loop from `score.settled` (swell 0.4× → full over 8 s), cut dead just before `rollTada` (also on direct draw, restart, act skip) |
| Winner | `rollTada` (ta-da at 2.0 s, first place rises) + `applause`; solo: `fanfare`, no drumroll. Then BGM `winner` (The Tent Circus, gain 0.33, in over 0.2 s) through trophy, THE END and NEW SHOW; stops on a new game snapshot or restart |

Kept for the sound lab only (not played by the show): `actStart`, `finalBetIntro`, `leadChange` files, `finaleMusic`
(orchestra), `sfx_jingle_brass.ogg`, `sfx_roll_alt.ogg`, `creak_b/c`.

**Checking:** `Sound.meter()` returns `{ scene, bgm, synth, running, rms, hi }` (`hi` = energy share above 3 kHz). In
headless checks open `#opening` and call `Sound.unlock()`. Lobby BGM: rms ≈ 0.005–0.02. To audition sounds, serve the
folder and open `tools/sound_lab.html` (`?bgm=0` mutes the lobby BGM to hear only the room sound).

## Real engine

The stage reaches a real engine only through the connector: a script injected after `mock-engine.js` that replaces
`window.MockEngine` with the same shape (`constructor({ deliver, log })`, `receive`, `load`, `start`, `stop`, `labels`,
`send`, `sleep`) backed by a WebSocket. Opening the file directly, or any replay hash above, keeps the mock.
`finale.results` (spec 1.1) makes `drawFinale` draw the podium finale. `mc.caption` is not drawn yet.

In the 2026-11 prototype the home server's game server injected `/play/link.js` this way. That prototype is reference
only; the Kiro-built engine writes its own connector against `interface/KHQS_STAGE_INTERFACE.md`.
