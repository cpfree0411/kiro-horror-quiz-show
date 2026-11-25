/* Sound file registry: cue name → file (OPENING_SOUND_FILES), BGM name → track (KHQS_BGM). Load before sound.js.
 * Shared by the stage (index.html) and the sound lab (tools/sound_lab.html). Pages in other folders set the path prefix with window.KHQS_SOUND_BASE.
 * Value format (gain, rate, peak, loopStart, loopEnd, up, arrays): see the sound.js header and the FILE_DEFS notes. A cue with no entry plays its synthetic sound.
 */
(() => {
  const S = (window.KHQS_SOUND_BASE || '') + 'assets/sound/';

  // SFX. The sign-crank 'creak' is Pixabay 'Metallic creak' stretched (tools/make_creak.py, version a of a/b/c)
  // Show SFX (2026-11-16): picked by the user on Pixabay (KHQS_sound_v1/user-picked SFX → tools/build_sfx.py).
  // Files are level-matched (active RMS −16 dBFS); gain here is the mix balance
  window.OPENING_SOUND_FILES = {
    creak: S + 'creak_a.ogg',
    roll: { src: S + 'sfx_roll.ogg', gain: .6, loopStart: 1.959887, loopEnd: 2.959887, up: 'rollUp', cut: .03 },   // default drumroll (length unknown: 1 s flat loop after the intro). cut: stop fast so it does not overlap the following crash (the cymbal from the same recording)
    rollUp: { src: S + 'sfx_roll_up.ogg', gain: .6, peak: 4.20, cut: .03 },   // the whole same drumroll: when the length is known, start late so the moment just before the last hit (4.20 s; cymbal at 4.21 s) lands at the end
    // Cymbal (2026-11-25): the final cymbal of the same drumroll recording (88344), cut from 4.20 s to the end as is. Level unchanged (same gain as the drumroll = same loudness).
    //   Before, there was no file, so a synthetic crash played and the drumroll stopped 0.1 s before the real cymbal (user: the act 3 drumroll sounded synthetic)
    crash: { src: S + 'sfx_crash.ogg', gain: .45 },   // user: a little quieter → .6 to .45 (about −2.5 dB)
    rollComedy: { src: S + 'sfx_roll_comedy.ogg', gain: .7 },            // act 1 OX reveal
    rollTada: { src: S + 'sfx_roll_tada.ogg', gain: .9 },                // winner announcement: 'ta-da' 2.0 s after the drumroll
    correct: { src: S + 'sfx_correct.ogg', gain: .8 },                   // ding-dang-dong correct (freesound_community ding 47489): act 1 OX when someone is right
    dingdong: { src: S + 'sfx_correct_dingdong.ogg', gain: .8 },         // ding-dong correct (freesound_community ding-dong 81717): act 2 buzzer correct
    buzz: { src: S + 'sfx_buzzer.ogg', gain: .7 },                       // buzzer sound (freesound_community buzzer2 6109): pressing the buzzer in act 2 (instead of the synthetic 'bzzzt')
    clockTick: { src: S + 'sfx_clock_tick.ogg', gain: .35, loopStart: 0.279002, loopEnd: 26.075079 },   // clock ticking (freesound_community tickingbuzzer 75859): loops during thinking time (act 1 OX, act 3 answer). tools/make_loop.py
    timeUp: { src: S + 'sfx_time_up.ogg', gain: .6 },                   // the buzzer at the end of the same file: when thinking time runs out
    finaleMusic: { src: S + 'sfx_finale_orchestra.ogg', gain: .8 },      // grand closing orchestra (mrwashingt0n 531057): finale podiums → results, once when first place rises (user request 2026-11-17)
    fanfare: { src: S + 'sfx_tada.ogg', gain: .9 },                      // ta-da~ (all-in correct, results when alone)
    // Act transition jingles (2026-11-17, cut from Gemini tracks, tools/build_sfx.py). Started with the transition, the final bang lands as the new stage is revealed
    actStart: { src: S + 'sfx_act_start.ogg', gain: .8 },                // act 1 start (no transition): bang at 1.6 s
    transBats: { src: S + 'sfx_trans_bats.ogg', gain: .8 },              // act 1→2 bat swarm: bang at about 2.8 s (after the bats fully cover at 2.05 s, while clearing)
    transPumpkin: { src: S + 'sfx_trans_pumpkin.ogg', gain: .8 },        // act 2→3 pumpkin pile: bang at about 3.0 s (when the pile starts to collapse)
    finalBetIntro: { src: S + 'sfx_final_bet_intro.ogg', gain: .8 },     // act 3 betting intro, 7.2 s: tiptoe → boom boom boom! then the betting BGM
    leadChange: [{ src: S + 'sfx_lead_a.ogg', gain: .8 }, { src: S + 'sfx_lead_b.ogg', gain: .8 }, { src: S + 'sfx_lead_c.ogg', gain: .8 }],   // comeback hit (random)
    jingle: { src: S + 'sfx_jingle_intro.ogg', gain: .9 },               // quiz-show intro jingle (curtain up): alex_besss 'The Clowns in Circus' 356787, start to 4 s (replaced 2026-11-16; the first brass sting is sfx_jingle_brass.ogg)
    sad: [{ src: S + 'sfx_wahwah_a.ogg', gain: .7 }, { src: S + 'sfx_wahwah_b.ogg', gain: .7, rate: 1.5 }],   // wah-wah: one of the two per hit. The brass at 1.5× (pitch goes up too, sillier)
    boo: { src: S + 'sfx_crowd_boo.ogg', gain: .5 },                     // crowd boo (slightly distorted in the original)
    aww: { src: S + 'sfx_crowd_aww.ogg', gain: .7 },                     // crowd disappointment
    gasp: { src: S + 'sfx_crowd_gasp.ogg', gain: .7 },                   // crowd gasp
    applause: { src: S + 'sfx_applause.ogg', gain: .6 },
    // Crowd murmur (2026-11-25, user's pick: freesound_community 'crowd noise large theater' 70982): end of act 3 → just before the winner drumroll. Looped and swelled
    crowdMurmur: { src: S + 'sfx_crowd_murmur.ogg', gain: .22, loopStart: 0, loopEnd: 59.797846 },   // user: too loud → .3 to .22 (about −2.7 dB)                 // cheer and applause (curtain up, winner)
  };

  // BGM. Lobby: 'Midnight_Sideshow' made with Gemini (provided by the user), 3.98 s intro, then loops loopStart–loopEnd.
  //   The last 80 ms of the file are pre-mixed with the sound just before loopStart, so the seam is invisible (tools/make_loop.py)
  //   Track tried (2026-11-16 evening; the user went back to Midnight): Pixabay sutton 627238 from 17 s
  //   = { src: S + 'bgm_lobby_sutton.ogg', gain: .13, loopStart: 0, loopEnd: 102.23449 }
  // Opening (2026-11-16 night, user request): from the end of the projector countdown (title) to the start of the quiz (game.snapshot). The sutton 627238 file cut from 17 s, as tried in the lobby; in-show, so clean
  // Act 3 betting (2026-11-17, user request): the 'act 3 betting music' pick 251858 from KHQS_sound_v1
  // Betrayal chance: Pixabay bentomusic 439124 (a loop track; the whole file is one lap). In-show, so clean (stereo, no radio channel)
  window.KHQS_BGM = {
    lobby: { src: S + 'bgm_lobby.ogg', gain: .08, loopStart: 3.981995, loopEnd: 40.462585 },
    opening: { src: S + 'bgm_lobby_sutton.ogg', gain: .3, loopStart: 0, loopEnd: 102.23449, clean: true },
    betrayal: { src: S + 'bgm_betrayal.ogg', gain: .4, loopStart: 0, loopEnd: 25.626122, clean: true },
    betting: { src: S + 'bgm_betting.ogg', gain: .4, loopStart: 0, loopEnd: 29.105986, clean: true },   // act 3 betting (final.betting → final.bets_locked): sergequadrado 'Funky and Jazzy Gang' 251858, only the leading mp3 silence trimmed, whole file looped
    // Winner (2026-11-25): from first place's podium rising to the end of the results screen. alex_besss 'The Tent Circus' 371589, 5.7 s intro then a 48 s loop (tools/make_loop.py 5.735 53.731).
    // First added as BGM from the end of act 3 to the winner drumroll; the user moved it to the winner music in place of the grand orchestra (finaleMusic)
    winner: { src: S + 'bgm_finale_wait.ogg', gain: .33, loopStart: 5.735011, loopEnd: 53.733129, clean: true },  };
})();
