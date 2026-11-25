/* Kiro Horror Quiz Show — opening demo sound layer.
 *
 * Audio hooks: real audio is registered in sound-files.js (the registry), loaded before this file,
 *   window.OPENING_SOUND_FILES = { fanfare: 'sfx/fanfare.mp3', sad: [{ src, rate: 1.5 }, ...] };
 * mapping cue name → file (value format: see FILE_DEFS below). A registered cue plays its file;
 * an unregistered cue falls back to the WebAudio synthetic sound (placeholder) below.
 * Loops (waltz, murmur, film) also loop a file if one is registered under the same name.
 * (file:// pages block fetch, so file audio works only from a local server.)
 *
 * Not allowed: actual Rocky Horror songs/melodies, a Halloween pipe-organ toccata.
 *
 * Scene tone (scene) and BGM (2026-11-16):
 *   Sound.scene('lobby' | 'show') — in the lobby only the BGM goes through an old-radio channel. SFX are clean and unprocessed in every scene
 *     (user decision 2026-11-16: SFX were first muffled to 2.4 kHz in the lobby too, then that was removed).
 *   Sound.bgm('lobby' | null, { fade }) — switch to one BGM track (crossfades). It goes through a BGM channel separate from SFX;
 *     in the lobby it adds lo-fi treatment (narrow band, slight record wow, crackle).
 *   Audio files: register like window.KHQS_BGM = { lobby: { src: 'assets/sound/bgm_lobby.mp3', gain: .7 } }
 *     (loopStart, loopEnd in seconds set the loop region). If nothing is registered or not yet loaded, the synthetic stand-in below plays.
 *     A track with clean: true skips the radio channel and plays in plain stereo (in-show BGM, e.g. the betrayal chance).
 *   Audio cannot start before the first click, so bgm() remembers the track and starts it on unlock().
 */
const Sound = (() => {
  'use strict';
  const FILES = window.OPENING_SOUND_FILES || {};
  // SFX file value: a path string, or { src, gain, rate, peak, loopStart, loopEnd, up }, or an array of them (an array picks one per hit)
  //   peak: the second where the sound is loudest. If cue/loop gets opts.dur, start that much later so the peak lands dur seconds later
  //   up: the cue name to play instead when the length is known, as in loop(name, true, { dur }) (drumroll: a version that ends on the peak instead of the loop)
  const FILE_DEFS = {};
  for (const [name, v] of Object.entries(FILES)) FILE_DEFS[name] = [].concat(v).map(d => typeof d === 'string' ? { src: d } : d);
  const BGM_FILES = Object.assign({}, window.KHQS_BGM || {});
  let ctx = null, out = null, noiseBuf = null, enabled = false;
  const buffers = {}, loops = {}, bgmBufs = {}, bgmFail = {};
  // Scene tone: lp = low-pass on everything, wet = reverb. SFX are not processed, so both scenes keep them open (values kept).
  // BGM old radio: bgmHp/bgmLp band, honk = small-speaker nasal peak (dB), drive = distortion ratio, wow = wobble (s),
  // crackle = noise (hiss, crackle, tube hum), bgmGain = volume, fading = depth of signal fading in and out, box = wooden cabinet resonance (dB), squash = broadcast compression (0–1)
  // (2026-11-16 first values: bgmLp 3000, bgmHp 340, honk 7, drive .4, crackle .5, fading .14, no box/squash, stereo)
  const SCENES = {
    lobby: { lp: 20000, gain: 1, wet: .22, bgmLp: 2300, bgmHp: 520, honk: 10, box: 5, drive: .5, wow: .0007, crackle: 1.1, bgmGain: .08, fading: .22, squash: 1 },
    show: { lp: 20000, gain: 1, wet: .22, bgmLp: 20000, bgmHp: 25, honk: 0, box: 0, drive: 0, wow: 0, crackle: 0, bgmGain: 1, fading: 0, squash: 0 },
  };
  let meterNode = null;
  let scene = 'show', sceneLp = null, toneGain = null, wet = null, bgmNodes = null, bgmWant = null, bgmNow = null;

  function unlock() {
    if (!ctx) {
      const AC = window.AudioContext || window.webkitAudioContext;
      if (!AC) return;
      ctx = new AC();
      const comp = ctx.createDynamicsCompressor();
      comp.connect(ctx.destination);
      meterNode = ctx.createAnalyser(); meterNode.fftSize = 2048; comp.connect(meterNode);   // measurement for review (meter)
      out = ctx.createGain();
      out.gain.value = .8;
      // scene tone: out → sceneLp (low-pass) → toneGain → compressor. Reverb branches off after that
      const S = SCENES[scene];
      sceneLp = B('lowpass', S.lp, .5); toneGain = G(S.gain);
      wire(out, sceneLp, toneGain, comp);
      const verb = ctx.createConvolver(); // reverb of a small box theatre
      verb.buffer = impulse(1.8);
      wet = G(S.wet);
      toneGain.connect(verb); verb.connect(wet); wet.connect(comp);
      noiseBuf = makeNoise();
      bgmNodes = bgmChain();
      for (const [name, defs] of Object.entries(FILE_DEFS)) defs.forEach(def => {
        fetch(def.src).then(r => r.arrayBuffer()).then(b => ctx.decodeAudioData(b))
          .then(buf => { (buffers[name] = buffers[name] || []).push({ def, buf }); }).catch(() => {});
      });
      for (const [name, f] of Object.entries(BGM_FILES)) {
        fetch(f.src).then(r => r.arrayBuffer()).then(b => ctx.decodeAudioData(b))
          .then(buf => {
            bgmBufs[name] = buf;
            if (bgmNow && bgmNow.name === name && bgmNow.synth) { bgmNow.stop(1.2); bgmNow = null; }   // if the stand-in was playing, switch to the real track
            if (bgmWant === name && !bgmNow) bgm(name);
          })
          .catch(() => { bgmFail[name] = true; if (bgmWant === name && !bgmNow) bgm(name); });   // if it cannot load, use the synthetic stand-in
      }
    }
    if (ctx.state === 'suspended') ctx.resume();
    enabled = true;
    if (bgmWant && !bgmNow) bgm(bgmWant);
  }

  function setEnabled(on) {
    if (on) { unlock(); return; }
    enabled = false;
    for (const name of Object.keys(loops)) loop(name, false);
    if (bgmNow) { bgmNow.stop(.3); bgmNow = null; }       // turning on again resumes bgmWant
    ambSync();
  }

  function makeNoise() {
    const len = ctx.sampleRate * 2, b = ctx.createBuffer(1, len, ctx.sampleRate), d = b.getChannelData(0);
    for (let i = 0; i < len; i++) d[i] = Math.random() * 2 - 1;
    return b;
  }
  function impulse(sec) {
    const len = Math.floor(ctx.sampleRate * sec), b = ctx.createBuffer(2, len, ctx.sampleRate);
    for (let c = 0; c < 2; c++) {
      const d = b.getChannelData(c);
      for (let i = 0; i < len; i++) d[i] = (Math.random() * 2 - 1) * Math.pow(1 - i / len, 3.4);
    }
    return b;
  }

  /* ---------- node helpers ---------- */
  const now = () => ctx.currentTime;
  const cents = c => Math.pow(2, c / 1200);
  function N() { const s = ctx.createBufferSource(); s.buffer = noiseBuf; s.loop = true; return s; }
  function O(type, f) { const o = ctx.createOscillator(); o.type = type; o.frequency.value = f; return o; }
  function G(v = 0) { const g = ctx.createGain(); g.gain.value = v; return g; }
  function B(type, f, q = 1) { const b = ctx.createBiquadFilter(); b.type = type; b.frequency.value = f; b.Q.value = q; return b; }
  function wire(...n) { for (let i = 0; i < n.length - 1; i++) n[i].connect(n[i + 1]); return n[0]; }
  function hit(g, t, a, peak, rel) {
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(peak, t + a);
    g.gain.exponentialRampToValueAtTime(0.0001, t + a + rel);
  }
  function run(src, t, dur) {
    if (src instanceof AudioBufferSourceNode) src.start(t, Math.random() * 1.5); else src.start(t);
    src.stop(t + dur);
  }
  function noiseHit(type, f, q, t, a, peak, rel, dest = out) {
    const s = N(), b = B(type, f, q), g = G();
    wire(s, b, g, dest); hit(g, t, a, peak, rel); run(s, t, a + rel + .05);
    return b;
  }
  function tone(type, f, t, a, peak, rel, dest = out) {
    const o = O(type, f), g = G();
    wire(o, g, dest); hit(g, t, a, peak, rel); run(o, t, a + rel + .05);
    return o;
  }

  // one slightly out-of-tune small brass note
  function brass(f, t, dur, vel = .12, dest = out) {
    const g = G(), lp = B('lowpass', 500, 2);
    wire(lp, g, dest);
    lp.frequency.setValueAtTime(400, t);
    lp.frequency.exponentialRampToValueAtTime(2600, t + .06);
    lp.frequency.exponentialRampToValueAtTime(1400, t + dur);
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(vel, t + .03);
    g.gain.setValueAtTime(vel * .8, t + dur);
    g.gain.exponentialRampToValueAtTime(0.0001, t + dur + .12);
    const off = cents((Math.random() - .5) * 28);
    for (const d of [1, cents(9)]) {
      const o = O('sawtooth', f * off * d), lfo = O('sine', 5.5), lg = G(f * .006);
      wire(lfo, lg); lg.connect(o.frequency);
      o.connect(lp); run(o, t, dur + .15); run(lfo, t, dur + .15);
    }
  }
  function snare(t, vel = .25, dest = out) {
    noiseHit('bandpass', 2400, .6, t, .002, vel, .13, dest);
    tone('triangle', 190, t, .002, vel * .6, .07, dest);
  }
  function bell(f, t, vel = .14, dest = out) { // handbell
    [1, 2.0, 3.01, 4.2].forEach((m, i) => tone('sine', f * m, t, .003, vel / (i + 1.2), 1.8 / (i * .5 + 1), dest));
  }
  function xylo(f, t, vel = .2) {
    tone('sine', f, t, .002, vel, .32);
    tone('sine', f * 3.9, t, .002, vel * .25, .08);
    noiseHit('bandpass', f * 2, 2, t, .001, vel * .3, .02);
  }

  /* ---------- one-shot cues (synthetic placeholders) ---------- */
  const SYN = {
    pop() { // skewer 'pop'
      const t = now(), o = O('sine', 380), g = G();
      o.frequency.exponentialRampToValueAtTime(1200, t + .06);
      wire(o, g, out); hit(g, t, .003, .35, .09); run(o, t, .15);
    },
    flap() { // paddle 'flap'
      const t = now();
      noiseHit('bandpass', 1300, .8, t, .01, .2, .06);
      noiseHit('bandpass', 900, .8, t + .07, .01, .14, .07);
    },
    slide({ up = true, dur = .45, vel = .12 } = {}) { // slide whistle
      const t = now(), o = O('sine', up ? 500 : 1500), g = G(), lfo = O('sine', 7), lg = G(14);
      o.frequency.exponentialRampToValueAtTime(up ? 1500 : 380, t + dur);
      wire(lfo, lg); lg.connect(o.frequency);
      wire(o, g, out);
      g.gain.setValueAtTime(0.0001, t); g.gain.exponentialRampToValueAtTime(vel, t + .04);
      g.gain.setValueAtTime(vel, t + dur - .05); g.gain.exponentialRampToValueAtTime(0.0001, t + dur + .05);
      run(o, t, dur + .1); run(lfo, t, dur + .1);
    },
    marker() { // marker 'squeak'
      const t = now(), b = noiseHit('bandpass', 3800, 6, t, .02, .16, .22);
      b.frequency.linearRampToValueAtTime(5200, t + .24);
    },
    mumble() { // sleep-talk 'mumble…'
      const t = now(), o = O('sawtooth', 95), lp = B('lowpass', 500, 3), g = G();
      o.frequency.linearRampToValueAtTime(70, t + .7);
      lp.frequency.linearRampToValueAtTime(260, t + .7);
      wire(o, lp, g, out); hit(g, t, .12, .14, .65); run(o, t, .9);
    },
    scratch() { // the record needle lifts
      const t = now(), b = noiseHit('bandpass', 1600, 3, t, .005, .3, .25);
      b.frequency.exponentialRampToValueAtTime(300, t + .28);
    },
    stomp({ vel = .6 } = {}) { // stomp on a cardboard floor
      const t = now(), o = O('sine', 120), g = G();
      o.frequency.exponentialRampToValueAtTime(40, t + .16);
      wire(o, g, out); hit(g, t, .003, vel, .2); run(o, t, .3);
      noiseHit('lowpass', 420, .8, t, .002, vel * .5, .08);
    },
    clap() {
      const t = now();
      for (let i = 0; i < 3; i++) noiseHit('bandpass', 1200 + Math.random() * 600, 1, t + i * .008, .001, .12, .05);
    },
    saw({ dur = 6 } = {}) { // musical saw rising with the gauge
      const t = now(), o = O('sine', 190), g = G(), lfo = O('sine', 5), lg = G(6);
      o.frequency.setValueAtTime(190, t);
      o.frequency.exponentialRampToValueAtTime(780, t + dur);
      lg.gain.linearRampToValueAtTime(16, t + dur);
      wire(lfo, lg); lg.connect(o.frequency);
      wire(o, g, out);
      g.gain.setValueAtTime(0.0001, t); g.gain.exponentialRampToValueAtTime(.05, t + .5);
      g.gain.linearRampToValueAtTime(.12, t + dur); g.gain.setValueAtTime(0.0001, t + dur + .01);
      run(o, t, dur + .05); run(lfo, t, dur + .05);
    },
    fuse() { // pop — the electric hum dies away. Then complete silence.
      const t = now();
      noiseHit('lowpass', 900, .7, t, .002, .8, .35);
      tone('sine', 70, t, .002, .5, .3);
      const o = O('sawtooth', 100), lp = B('lowpass', 600), g = G();
      o.frequency.exponentialRampToValueAtTime(30, t + .55);
      wire(o, lp, g, out); hit(g, t, .005, .16, .5); run(o, t, .6);
    },
    snore() { // one snore in the dark
      const t = now(), s = N(), lp = B('lowpass', 300, 4), g = G(), o = O('sawtooth', 55), og = G();
      lp.frequency.setValueAtTime(220, t); lp.frequency.linearRampToValueAtTime(520, t + .9);
      wire(s, lp, g, out); wire(o, og, lp);
      og.gain.value = .5;
      g.gain.setValueAtTime(0.0001, t); g.gain.exponentialRampToValueAtTime(.35, t + .7); g.gain.exponentialRampToValueAtTime(0.0001, t + 1.25);
      run(s, t, 1.3); run(o, t, 1.3);
    },
    motor() { // the projector motor clunks into motion
      const t = now();
      noiseHit('lowpass', 600, 1, t, .002, .5, .12);
      noiseHit('lowpass', 500, 1, t + .14, .002, .35, .1);
      const o = O('square', 30), lp = B('lowpass', 300), g = G();
      o.frequency.exponentialRampToValueAtTime(48, t + .8);
      wire(o, lp, g, out); hit(g, t, .05, .1, .8); run(o, t, .9);
    },
    beep() { tone('sine', 1000, now(), .004, .16, .14); },
    roll({ dur = 1.6 } = {}) {
      const t = now(), n = Math.floor(dur * 28);
      for (let i = 0; i < n; i++) snare(t + i / 28 + (Math.random() - .5) * .005, .04 + .22 * Math.pow(i / n, 1.4));
    },
    crash() {
      const t = now();
      noiseHit('highpass', 3200, .7, t, .004, .34, 2.2);
      noiseHit('bandpass', 6400, .5, t, .004, .18, 1.1);
    },
    // original fanfare in the style of an old TV quiz-show jingle (trumpet, trombone, snare, cymbal)
    fanfare() {
      const t = now();
      const tp = [[0, 392, .1], [.12, 392, .1], [.24, 523.3, .2], [.48, 659.3, .1], [.6, 784, .3], [.96, 659.3, .1], [1.08, 784, .18], [1.3, 1046.5, 1.1]];
      tp.forEach(([d, f, len]) => { brass(f, t + d, len, .1); snare(t + d, .12); });
      [[0, 130.8, .45], [.48, 98, .42], [1.3, 130.8, 1.1]].forEach(([d, f, len]) => brass(f, t + d, len, .12));
      [[0, 196, .45], [.48, 146.8, .42], [1.3, 164.8, 1.1]].forEach(([d, f, len]) => brass(f, t + d, len, .07));
      for (let i = 0; i < 9; i++) snare(t + .96 + i * .036, .06 + i * .02);
      setTimeout(() => SYN.crash(), 1300);
    },
    stab() { // one hit of the main theme
      const t = now();
      [261.6, 329.6, 392, 523.3].forEach(f => brass(f, t, .35, .07));
      [130.8, 65.4].forEach(f => brass(f, t, .35, .1));
      snare(t, .3);
      noiseHit('highpass', 3200, .7, t, .004, .25, 1.2);
    },
    // Comeback hit (2026-11-25, user: the jingle and crowd reaction both felt off, so use a synthetic one). The stage calls cue 'twist' → routed to the chosen version
    //   First version (twistFull): slide-whistle V → brass ♭VI→I 'ba-bam!' → xylophone. User: not great, simpler → three simple versions (A/B/C)
    twist() { SYN.twistC(); },   // user's pick (2026-11-25): C, xylophone 'tee-dee-dee-ding↗'
    twistA() { // one whistle 'wheee↗' (0.35 s)
      const t = now(), o = O('sine', 450), vib = O('sine', 12), vg = G(20), g = G();
      o.frequency.exponentialRampToValueAtTime(1800, t + .3);
      wire(vib, vg); vg.connect(o.frequency); wire(o, g, out);
      g.gain.setValueAtTime(0.0001, t); g.gain.exponentialRampToValueAtTime(.26, t + .03);
      g.gain.setValueAtTime(.26, t + .27); g.gain.exponentialRampToValueAtTime(0.0001, t + .36);
      run(o, t, .4); run(vib, t, .4);
    },
    twistB() { // two brass 'ba-bam!' hits (♭VI→I, 0.5 s)
      const t = now(), b = t + .16;
      [207.7, 261.6, 311.1].forEach(f => brass(f, t, .1, .07)); brass(103.8, t, .1, .09); snare(t, .15);
      [261.6, 329.6, 392].forEach(f => brass(f, b, .3, .075)); brass(130.8, b, .3, .1); snare(b, .22);
    },
    twistC() { // xylophone 'tee-dee-dee-ding↗', four notes (C E G C, 0.45 s)
      const t = now();
      [523.3, 659.3, 784, 1046.5].forEach((f, i) => xylo(f, t + i * .07, .2 + i * .02));
    },
    twistFull() {
      const t = now();
      const o = O('sine', 1100), vib = O('sine', 11), vg = G(18), g = G();
      o.frequency.setValueAtTime(1100, t);
      o.frequency.exponentialRampToValueAtTime(400, t + .14);
      o.frequency.exponentialRampToValueAtTime(1700, t + .32);
      wire(vib, vg); vg.connect(o.frequency); wire(o, g, out);
      g.gain.setValueAtTime(0.0001, t); g.gain.exponentialRampToValueAtTime(.075, t + .03);
      g.gain.setValueAtTime(.075, t + .28); g.gain.exponentialRampToValueAtTime(0.0001, t + .36);
      run(o, t, .4); run(vib, t, .4);
      const a = t + .36, b = t + .54;
      [207.7, 261.6, 311.1, 415.3].forEach(f => brass(f, a, .11, .06)); brass(103.8, a, .11, .09); snare(a, .18);
      [261.6, 329.6, 392, 523.3, 659.3].forEach(f => brass(f, b, .42, .065)); [130.8, 65.4].forEach(f => brass(f, b, .42, .1)); snare(b, .28);
      xylo(1568, b + .1, .12); xylo(2093, b + .18, .1);
    },
    cheer({ vel = 1 } = {}) { // monster audience cheer — a shout with kazoo in it
      const t = now();
      noiseHit('bandpass', 850, .5, t, .3, .16 * vel, 1.6);
      for (let i = 0; i < 9; i++) {
        const ti = t + Math.random() * .6, f = 220 + Math.random() * 420;
        const o = O('sawtooth', f), b = B('bandpass', 1100, 4), g = G();
        o.frequency.linearRampToValueAtTime(f * (1.25 + Math.random() * .5), ti + .3);
        wire(o, b, g, out); hit(g, ti, .04, .05 * vel, .4); run(o, ti, .5);
      }
    },
    murmurs() { noiseHit('bandpass', 500, .7, now(), .2, .05, .9); },
    tick() { noiseHit('bandpass', 4200, 2, now(), .001, .12, .025); },
    fabric() { // fabric rustle
      const t = now(), b = noiseHit('bandpass', 2200, .8, t, .08, .1, .3);
      b.frequency.linearRampToValueAtTime(1200, t + .35);
    },
    yawn() { // a long yawn, muffled as if through cloth
      const t = now(), o = O('sawtooth', 150), f1 = B('bandpass', 500, 5), lp = B('lowpass', 900), g = G();
      o.frequency.setValueAtTime(150, t); o.frequency.linearRampToValueAtTime(210, t + .5); o.frequency.exponentialRampToValueAtTime(80, t + 1.6);
      f1.frequency.setValueAtTime(400, t); f1.frequency.linearRampToValueAtTime(900, t + .6); f1.frequency.linearRampToValueAtTime(350, t + 1.6);
      wire(o, f1, lp, g, out);
      g.gain.setValueAtTime(0.0001, t); g.gain.exponentialRampToValueAtTime(.3, t + .35); g.gain.setValueAtTime(.3, t + 1.1); g.gain.exponentialRampToValueAtTime(0.0001, t + 1.7);
      run(o, t, 1.8);
      noiseHit('bandpass', 700, 1, t, .4, .05, 1.2);
    },
    xylo({ f = 523.3 } = {}) { xylo(f, now()); },
    whoosh({ vel = 1 } = {}) {
      const t = now(), b = noiseHit('bandpass', 300, .9, t, .25, .24 * vel, .5);
      b.frequency.setValueAtTime(260, t); b.frequency.exponentialRampToValueAtTime(2400, t + .6);
    },
    squeak({ f = 2600, vel = .07 } = {}) { // bat 'squeak squeak': two short toy-like chirps
      const t = now();
      for (const d of [0, .07]) {
        const o = O('sine', f * 1.3), g = G();
        o.frequency.setValueAtTime(f * 1.3, t + d); o.frequency.exponentialRampToValueAtTime(f * .7, t + d + .06);
        wire(o, g, out); hit(g, t + d, .004, vel, .05); run(o, t + d, .08);
      }
    },
    flutter({ vel = .5 } = {}) { // bat wing flutter
      const t = now();
      for (let i = 0; i < 3; i++) noiseHit('bandpass', 700 + Math.random() * 500, 1.2, t + i * .035, .004, .07 * vel, .03);
    },
    bonk({ f = 160, vel = .4 } = {}) { // a hollow pumpkin bumps 'thonk'
      const t = now(), o = O('sine', f * 1.4), g = G();
      o.frequency.exponentialRampToValueAtTime(f * .7, t + .12);
      wire(o, g, out); hit(g, t, .002, vel, .16); run(o, t, .22);
      tone('triangle', f * 2.7, t, .001, vel * .25, .05);
      noiseHit('lowpass', 900, .8, t, .001, vel * .35, .05);
    },
    creak({ f = 520, vel = .45 } = {}) { // sign crank 'creak': metal catching and slipping on metal (stick-slip). A high 'cree' + a low rough 'eek'
      const t = now(), sr = ctx.sampleRate, len = Math.ceil(sr * .26), buf = ctx.createBuffer(1, len, sr), d = buf.getChannelData(0);
      for (const [at, dur, f0, f1, jit] of [[0, .11, f * 1.15, f * 1.45, .25], [.14, .09, f * .8, f * .6, .5]]) {
        let ph = 0; const n0 = Math.floor(at * sr), n = Math.floor(dur * sr);
        for (let i = 0; i < n; i++) {
          const k = i / n, env = Math.sin(Math.PI * Math.min(1, k * 1.25)) ** .6;
          ph += (f0 + (f1 - f0) * k) * (1 + (Math.random() - .5) * jit) / sr;
          if (ph >= 1) { ph -= 1; for (let j = 0; j < 20 && n0 + i + j < len; j++) d[n0 + i + j] += env * Math.exp(-j / 3) * (j % 2 ? -1 : 1); }
        }
      }
      const src = ctx.createBufferSource(), mix = G(vel); src.buffer = buf; mix.connect(out);
      [[1850, 14, 1], [2950, 18, .8], [4400, 20, .5], [950, 4, .5]].forEach(([fq, q, a]) => { const b = B('bandpass', fq * f / 520, q), gg = G(a); wire(src, b, gg, mix); });
      src.start(t);
    },
    knock({ f = 900, vel = .16 } = {}) { // the pointer taps the sign: a small wooden knock
      const t = now(), o = O('sine', f * 1.25), g = G();
      o.frequency.exponentialRampToValueAtTime(f, t + .02);
      wire(o, g, out); hit(g, t, .001, vel, .05); run(o, t, .08);
      noiseHit('bandpass', f * 1.8, 4, t, .001, vel * .5, .015);
    },
    whistleUp({ vel = .07 } = {}) { // 'whee-oop' as the pointer pops out: a toy slide whistle
      const t = now(), o = O('sine', 520), vib = O('sine', 14), vg = G(25), g = G();
      o.frequency.exponentialRampToValueAtTime(1500, t + .2);
      wire(vib, vg); vg.connect(o.frequency);
      wire(o, g, out); g.gain.setValueAtTime(0.0001, t); g.gain.exponentialRampToValueAtTime(vel, t + .03);
      g.gain.setValueAtTime(vel, t + .17); g.gain.exponentialRampToValueAtTime(0.0001, t + .26);
      run(o, t, .3); run(vib, t, .3);
    },
    tak() { // stick 'tak' — wood block
      const t = now();
      tone('sine', 880, t, .001, .35, .07);
      tone('sine', 1320, t, .001, .12, .04);
      noiseHit('bandpass', 2500, 3, t, .001, .2, .02);
    },
    clip() { noiseHit('bandpass', 3000, 2, now(), .001, .25, .03); SYN.tak(); },
    handbell({ f = 587.3 } = {}) { bell(f, now()); },
    sad() { // wrong-answer trombone 'wah wah wah waaah'
      const t = now();
      [[0, 233.1, .32], [.36, 220, .32], [.72, 207.7, .32], [1.08, 196, 1.1]].forEach(([d, f, len]) => brass(f, t + d, len, .12));
    },
    boo() { // monster audience boo
      const t = now();
      noiseHit('bandpass', 420, .8, t, .25, .14, 1.4);
      for (let i = 0; i < 6; i++) {
        const ti = t + Math.random() * .3, f = 120 + Math.random() * 70, o = O('sawtooth', f), b = B('bandpass', 500, 3), g = G();
        o.frequency.linearRampToValueAtTime(f * .7, ti + 1.1);
        wire(o, b, g, out); hit(g, ti, .15, .05, 1.0); run(o, ti, 1.3);
      }
    },
    ding() { bell(1046.5, now(), .18); bell(1568, now() + .08, .12); },
    buzz() { // game-show buzzer 'bzzzt'
      const t = now();
      [110, 116.5, 220].forEach(f => {
        const o = O('square', f), lp = B('lowpass', 1400), g = G();
        wire(o, lp, g, out); hit(g, t, .01, f > 200 ? .06 : .12, .5); run(o, t, .6);
      });
    },
    stamp() { // rubber stamp 'thunk'
      const t = now();
      noiseHit('lowpass', 500, .9, t, .002, .45, .12);
      tone('sine', 90, t, .002, .4, .15);
    },
    // placeholder for the ghost host's voice — in the real show the Gemini Live voice replaces it
    voice({ dur = 2.4 } = {}) {
      const t = now(), syl = Math.max(3, Math.round(dur * 4.4));
      const s = N(), b = B('bandpass', 1100, 5), g = G(0);
      const o = O('sawtooth', 92), lp = B('lowpass', 520), og = G(0);
      wire(s, b, g, out); wire(o, lp, og, out);
      for (let i = 0; i < syl; i++) {
        const ti = t + i * (dur / syl), len = (dur / syl) * (.55 + Math.random() * .3);
        b.frequency.setValueAtTime([650, 1050, 1700, 2300][Math.floor(Math.random() * 4)], ti);
        g.gain.setValueAtTime(0.0001, ti); g.gain.exponentialRampToValueAtTime(.09, ti + .04); g.gain.exponentialRampToValueAtTime(0.0001, ti + len);
        og.gain.setValueAtTime(0.0001, ti); og.gain.exponentialRampToValueAtTime(.08, ti + .05); og.gain.exponentialRampToValueAtTime(0.0001, ti + len);
        o.frequency.setValueAtTime(82 + Math.random() * 30, ti);
      }
      run(s, t, dur + .1); run(o, t, dur + .1);
    },
  };

  /* ---------- Scene tone and BGM ---------- */
  // BGM channel (old radio): track → bus (summed to mono) → high-pass ×2 → broadcast compression → speaker nasal peak + wooden cabinet resonance (two peaking)
  //   → low-pass ×2 → (clean path + tube-like distorted path) → wow (wobbling delay) → signal fading (two slow wobbles) → out.
  //   Radio noise (hiss + crackle + tube hum) is added before the band filters so it goes through the same speaker
  function bgmChain() {
    const S = SCENES[scene], bus = G(1);
    bus.channelCount = 1; bus.channelCountMode = 'explicit'; bus.channelInterpretation = 'speakers';   // a radio with one speaker
    const hp = B('highpass', S.bgmHp, .7), hp2 = B('highpass', S.bgmHp, .7), lp = B('lowpass', S.bgmLp, .7), lp2 = B('lowpass', S.bgmLp, .7);
    const sq = ctx.createDynamicsCompressor(); sq.knee.value = 6; sq.attack.value = .005; sq.release.value = .15;
    const sqSet = (v, t, k) => { [[sq.threshold, -6 - 26 * v], [sq.ratio, 1 + 7 * v]].forEach(([prm, val]) => (t == null ? (prm.value = val) : prm.setTargetAtTime(val, t, k))); };
    sqSet(S.squash);
    const sqMake = G(1 + 1.6 * S.squash);                                   // make up the level lost to compression
    const honk = B('peaking', 1150, 1.4); honk.gain.value = S.honk;
    const box = B('peaking', 2100, 1.6); box.gain.value = S.box;
    const clean = G(1 - S.drive), dirty = G(S.drive), pre = G(14), post = G(1 / 9), shaper = ctx.createWaveShaper();
    const curve = new Float32Array(1024); for (let i = 0; i < 1024; i++) { const x = i / 511.5 - 1; curve[i] = Math.tanh(2.5 * x + .25 * x * x) / Math.tanh(2.5); }   // asymmetric, so even harmonics appear (tube flavour)
    shaper.curve = curve; shaper.oversample = '2x';
    const wow = ctx.createDelay(.05); wow.delayTime.value = .012;
    const lfo = O('sine', .55), depth = G(S.wow); wire(lfo, depth); depth.connect(wow.delayTime); lfo.start();
    const fade = G(S.bgmGain), fl = O('sine', .06), fl2 = O('sine', .17), fd = G(S.fading * S.bgmGain), fd2 = G(S.fading * S.bgmGain * .4);
    wire(fl, fd); fd.connect(fade.gain); wire(fl2, fd2); fd2.connect(fade.gain); fl.start(); fl2.start();
    wire(bus, hp, hp2, sq, sqMake, honk, box, lp, lp2);
    lp2.connect(clean); wire(lp2, pre, shaper, post, dirty);
    clean.connect(wow); dirty.connect(wow);
    wire(wow, fade, out);
    // radio noise: a 4 s looping buffer of hiss (band noise) + sparse clicks, plus the low hum of a tube power supply (120 Hz harmonics)
    const len = ctx.sampleRate * 4, cb = ctx.createBuffer(1, len, ctx.sampleRate), d = cb.getChannelData(0);
    for (let i = 0; i < len; i++) d[i] = (Math.random() * 2 - 1) * .05;
    for (let i = 0; i < 70; i++) {
      const at = Math.floor(Math.random() * (len - 40)), a = Math.random() * .8;
      for (let k = 0; k < 30; k++) d[at + k] += (Math.random() * 2 - 1) * a * Math.exp(-k / 6);
    }
    const cr = ctx.createBufferSource(); cr.buffer = cb; cr.loop = true;
    const crBp = B('bandpass', 2000, .6), crG = G(0);
    wire(cr, crBp, crG, hp); cr.start();
    const hum = O('sawtooth', 120), humLp = B('lowpass', 900, .7), humG = G(.012);
    wire(hum, humLp, humG, crG); hum.start();
    return { bus, hp, hp2, lp, lp2, honk, box, sqSet, sqMake, clean, dirty, depth, fade, fd, fd2, crG };
  }
  function setScene(name, sec = .8) {
    if (!SCENES[name]) return;
    scene = name;
    if (!ctx) return;                                  // start in this scene when audio comes on
    const S = SCENES[name], t = now(), k = Math.max(.01, sec / 4), N_ = bgmNodes;
    sceneLp.frequency.setTargetAtTime(S.lp, t, k); toneGain.gain.setTargetAtTime(S.gain, t, k); wet.gain.setTargetAtTime(S.wet, t, k);
    [N_.lp, N_.lp2].forEach(f => f.frequency.setTargetAtTime(S.bgmLp, t, k)); [N_.hp, N_.hp2].forEach(f => f.frequency.setTargetAtTime(S.bgmHp, t, k));
    N_.honk.gain.setTargetAtTime(S.honk, t, k); N_.box.gain.setTargetAtTime(S.box, t, k);
    N_.sqSet(S.squash, t, k); N_.sqMake.gain.setTargetAtTime(1 + 1.6 * S.squash, t, k); N_.clean.gain.setTargetAtTime(1 - S.drive, t, k); N_.dirty.gain.setTargetAtTime(S.drive, t, k);
    N_.depth.gain.setTargetAtTime(S.wow, t, k); N_.fade.gain.setTargetAtTime(S.bgmGain, t, k); N_.fd.gain.setTargetAtTime(S.fading * S.bgmGain, t, k); N_.fd2.gain.setTargetAtTime(S.fading * S.bgmGain * .4, t, k);
    N_.crG.gain.setTargetAtTime(bgmNow ? S.crackle * .05 : 0, t, k);
  }
  // play one track into the bus. A file if there is one, otherwise the synthetic stand-in
  function startTrack(name) {
    const f = BGM_FILES[name], buf = bgmBufs[name];
    const g = G(0); g.connect(buf && f.clean ? out : bgmNodes.bus);   // clean: plain stereo without the radio channel (in-show BGM)
    let stopSrc;
    if (buf) {
      const s = ctx.createBufferSource(); s.buffer = buf; s.loop = true;
      if (f.loopStart != null) s.loopStart = f.loopStart;
      if (f.loopEnd != null) s.loopEnd = f.loopEnd;
      const vg = G(f.gain == null ? .7 : f.gain); wire(s, vg, g); s.start();
      stopSrc = t => { try { s.stop(t); } catch (e) { /* already stopped */ } };
    } else if (BGM_SYN[name]) {
      const parts = BGM_SYN[name](g);
      stopSrc = t => { parts.stop(); (parts.srcs || []).forEach(x => { try { x.stop(t); } catch (e) { /* already stopped */ } }); };
    } else { g.disconnect(); return null; }
    return {
      name, g, synth: !buf,
      stop(fade = 1.2) {
        const t = now();
        g.gain.cancelScheduledValues(t); g.gain.setValueAtTime(g.gain.value, t); g.gain.linearRampToValueAtTime(0, t + fade);
        setTimeout(() => stopSrc(now()), fade * 1000 + 60);       // the synthetic stand-in must cancel its schedule, so stop it after the fade
      },
    };
  }
  function bgm(name, { fade = 1.5 } = {}) {
    bgmWant = name || null;
    if (!ctx || !enabled || ctx.state !== 'running') return;   // unlock() plays bgmWant
    ambSync(Math.min(fade, 1));
    if (bgmNow && bgmNow.name === name) return;
    if (bgmNow) { bgmNow.stop(fade); bgmNow = null; }
    if (name && BGM_FILES[name] && !bgmBufs[name] && !bgmFail[name]) name = null;   // if the file is still loading, wait (it plays on arrival)
    if (name) {
      bgmNow = startTrack(name);
      if (bgmNow) { const t = now(); bgmNow.g.gain.setValueAtTime(0, t); bgmNow.g.gain.linearRampToValueAtTime(1, t + Math.min(fade, 2)); }
    }
    bgmNodes.crG.gain.setTargetAtTime(bgmNow ? SCENES[scene].crackle * .05 : 0, now(), Math.max(.05, fade / 3));
  }

  // Lobby stand-in: relaxed theatre waiting music. Same world as the opening record waltz — toy-piano melody + reed-organ chords, 3/4, about 83 BPM.
  // The old-radio sound comes from the BGM channel (bgmChain), not the track. When the real track (KHQS_BGM.lobby) arrives, it switches to that
  const LN = { G2: 98, A2: 110, F2: 87.3, C3: 130.8, D3: 146.8, E3: 164.8, F3: 174.6, G3: 196, A3: 220, B3: 246.9, C4: 261.6, D4: 293.7,
    A4: 440, B4: 493.9, C5: 523.3, D5: 587.3, E5: 659.3, F5: 698.5, G5: 784, A5: 880 };
  const CH = { C: [LN.C3, [LN.E3, LN.G3, LN.C4]], Am: [LN.A2, [LN.E3, LN.A3, LN.C4]], F: [LN.F2, [LN.F3, LN.A3, LN.C4]],
    G7: [LN.G2, [LN.F3, LN.B3, LN.D4]], Dm: [LN.D3, [LN.F3, LN.A3, LN.D4]], CG: [LN.G2, [LN.E3, LN.G3, LN.C4]] };
  const LOBBY = [   // [chord, melody [beat, note, length (beats)]]
    ['C', [[0, 'E5', 2], [2, 'D5', 1]]], ['Am', [[0, 'C5', 2], [2, 'A4', 1]]], ['F', [[0, 'A4', 1], [1, 'C5', 1], [2, 'F5', 1]]], ['G7', [[0, 'E5', 2], [2, 'D5', 1]]],
    ['C', [[0, 'E5', 1], [1, 'G5', 1], [2, 'E5', 1]]], ['Am', [[0, 'C5', 2], [2, 'E5', 1]]], ['Dm', [[0, 'D5', 1], [1, 'F5', 1], [2, 'A5', 1]]], ['G7', [[0, 'G5', 3]]],
    ['F', [[0, 'A5', 2], [2, 'G5', 1]]], ['C', [[0, 'E5', 2], [2, 'C5', 1]]], ['Dm', [[0, 'D5', 1], [1, 'E5', 1], [2, 'F5', 1]]], ['Am', [[0, 'E5', 2], [2, 'C5', 1]]],
    ['F', [[0, 'A4', 1], [1, 'C5', 1], [2, 'F5', 1]]], ['CG', [[0, 'E5', 2], [2, 'C5', 1]]], ['G7', [[0, 'D5', 1], [1, 'B4', 1], [2, 'D5', 1]]], ['C', [[0, 'C5', 3]]],
  ];
  function radioLobby(g) {
    const beat = .72, vol = G(.28);
    vol.connect(g);
    const organ = (f, t, len, v) => {       // reed organ: two slightly detuned saw waves, slow attack, bellows tremble
      const lp = B('lowpass', 1500, .7), gg = G(), vib = O('sine', 5.2), vg = G(f * .004);
      wire(lp, gg, vol); wire(vib, vg);
      for (const d of [1, cents(7)]) { const o = O('sawtooth', f * d); vg.connect(o.frequency); o.connect(lp); run(o, t, len + .3); }
      gg.gain.setValueAtTime(0.0001, t); gg.gain.exponentialRampToValueAtTime(v, t + .09);
      gg.gain.setValueAtTime(v, t + len); gg.gain.exponentialRampToValueAtTime(0.0001, t + len + .25);
      run(vib, t, len + .3);
    };
    const toy = (f, t, v) => {              // toy piano: clear fundamental + metallic overtones (inharmonic), a short click
      tone('sine', f, t, .002, v, 1.3, vol);
      tone('sine', f * 2.76, t, .001, v * .35, .22, vol);
      tone('sine', f * 5.4, t, .001, v * .12, .06, vol);
    };
    let next = now() + .15, i = 0;
    const timer = setInterval(() => {
      while (next < now() + .4) {
        const [ch, mel] = LOBBY[Math.floor(i / 3) % LOBBY.length], b = i % 3, t = next, [bass, notes] = CH[ch];
        if (b === 0) { organ(bass, t, beat * 2.6, .05); notes.forEach(f => organ(f, t + .02, beat * 2.8, .022)); }
        else notes.forEach(f => organ(f * 2, t, beat * .45, .008));                   // light 'cha cha' on beats 2 and 3
        mel.filter(m => m[0] === b).forEach(([, n, len]) => toy(LN[n] * 2, t + (Math.random() - .5) * .02, len > 1 ? .07 : .06));
        next += beat * (1 + (Math.random() - .5) * .03) + (b === 2 ? .04 : 0); i++;  // a small breath at the end of the bar
      }
    }, 50);
    return { srcs: [], stop: () => clearInterval(timer) };
  }
  const BGM_SYN = { lobby: radioLobby };

  // Room sound that runs with the BGM (not through the radio channel). It is tied to the name (lobby), so it stays when the track changes
  // Lobby: an old fluorescent tube somewhere hums 'zzing' now and then (every 6–15 s) — a soft swelling-and-fading buzz like a phone vibrating on a desk.
  // A 75 Hz hum filtered to its nasal band (0.29–1 kHz) with a 9 Hz tremble. Sometimes one more short buzz (2026-11-16: flickers and ticks were too loud and removed)
  function fluoroFlicker() {
    const g = G(1); g.connect(out);
    const o = O('sawtooth', 75), o2 = O('square', 150.3), o2g = G(.4), hp = B('highpass', 290, .7), lp = B('lowpass', 1000, .7), nose = B('peaking', 560, 2);
    nose.gain.value = 6;                                        // 2026-11-16: lowered three times, 120 Hz (0.9 kHz nasal) → 100 → 89 → 75 Hz
    const env = G(0), trem = O('sine', 9), tg = G(0);              // the tremble depth follows env too
    wire(o2, o2g, hp); o.connect(hp); wire(hp, nose, lp, env, g);
    wire(trem, tg); tg.connect(env.gain);
    [o, o2, trem].forEach(x => x.start());
    const buzz = (t, dur, lv) => {
      [[env.gain, lv], [tg.gain, lv * .25]].forEach(([prm, v]) => {
        prm.setValueAtTime(0, t); prm.linearRampToValueAtTime(v, t + .12);
        prm.setValueAtTime(v, t + dur - .18); prm.linearRampToValueAtTime(0, t + dur);
      });
    };
    let next = now() + 1.5 + Math.random() * 1.5;               // so it is heard right after entering the lobby
    const timer = setInterval(() => {
      if (next > now() + .3) return;
      const dur = .6 + Math.random() * .5, lv = .016 + Math.random() * .007;   // 2026-11-16: .008–.013 was buried under the BGM
      buzz(next, dur, lv);
      let end = next + dur;
      if (Math.random() < .35) { buzz(end + .25, .4, lv * .8); end += .65; }   // 'zzing… zing'
      next = end + 5 + Math.random() * 7;
    }, 60);
    return {
      stop(fade = .3) {
        clearInterval(timer); const t = now();
        g.gain.setValueAtTime(g.gain.value, t); g.gain.linearRampToValueAtTime(0, t + fade);
        setTimeout(() => { try { [o, o2, trem].forEach(x => x.stop()); } catch (e) { /* already stopped */ } g.disconnect(); }, fade * 1000 + 80);
      },
    };
  }
  const BGM_AMB = { lobby: fluoroFlicker };
  let ambNow = null;
  function ambSync(fade = .3) {
    const want = bgmWant && BGM_AMB[bgmWant] && enabled && ctx && ctx.state === 'running' ? bgmWant : null;
    if (ambNow && ambNow.name !== want) { ambNow.stop(fade); ambNow = null; }
    if (want && !ambNow) ambNow = Object.assign(BGM_AMB[want](), { name: want });
  }

  /* ---------- loops ---------- */
  function loopNode(build) {
    const g = G(0); g.connect(out);
    const parts = build(g), t = now();
    g.gain.setValueAtTime(0, t); g.gain.linearRampToValueAtTime(1, t + .5);
    const srcs = parts.srcs || parts;
    srcs.forEach(s => (s instanceof AudioBufferSourceNode ? s.start(t, Math.random()) : s.start(t)));
    return {
      stop() {
        const n = now();
        if (parts.stop) parts.stop();
        g.gain.cancelScheduledValues(n); g.gain.setValueAtTime(g.gain.value, n); g.gain.linearRampToValueAtTime(0, n + .3);
        srcs.forEach(s => { try { s.stop(n + .35); } catch (e) { /* already stopped */ } });
      },
    };
  }

  // An old record's 3/4 waltz — toy piano, reed organ, brush snare, crackle. A snore on beat 1 every two bars.
  const A = { A2: 110, D3: 146.8, E2: 82.4, F2: 87.3, C4: 261.6, D4: 293.7, E4: 329.6, F4: 349.2, Gs4: 415.3, A4: 440, B4: 493.9, C5: 523.3, D5: 587.3, E5: 659.3, F5: 698.5 };
  const WALTZ = [
    { bass: A.A2, ch: [A.C4, A.E4, A.A4], mel: [[0, A.E5, .5], [1, A.D5, .3], [2, A.C5, .3]] },
    { bass: A.D3, ch: [A.D4, A.F4, A.A4], mel: [[0, A.F5, .9], [2, A.E5, .3]] },
    { bass: A.E2 * 2, ch: [A.D4, A.Gs4, A.B4], mel: [[0, A.D5, .5], [1, A.B4, .3], [2, A.Gs4, .3]] },
    { bass: A.A2, ch: [A.C4, A.E4, A.A4], mel: [[0, A.A4, 1.4]] },
    { bass: A.F2 * 2, ch: [A.C4, A.F4, A.A4], mel: [[0, A.C5, .5], [1, A.A4, .3], [2, A.F4, .3]] },
    { bass: A.D3, ch: [A.D4, A.F4, A.A4], mel: [[0, A.D5, .5], [1, A.F5, .3], [2, A.E5, .3]] },
    { bass: A.E2 * 2, ch: [A.D4, A.Gs4, A.B4], mel: [[0, A.B4, .5], [1, A.D5, .3], [2, A.E5, .3]] },
    { bass: A.A2, ch: [A.C4, A.E4, A.A4], mel: [[0, A.A4, 1.4]] },
  ];
  function waltz(g) {
    const beat = .66, lp = B('lowpass', 2600, .5), vol = G(.55);
    wire(lp, vol, g); // the narrow band of an old record
    const crackle = N(), cb = B('highpass', 3000), cg = G(0);
    wire(crackle, cb, cg, g);
    let next = now() + .1, i = 0;
    const timer = setInterval(() => {
      while (next < now() + .3) {
        const bar = WALTZ[Math.floor(i / 3) % WALTZ.length], b = i % 3, t = next;
        if (b === 0) {
          tone('triangle', bar.bass, t, .01, .12, .5, lp);
          if (Math.floor(i / 3) % 2 === 0) { // snore on beat 1
            const s = N(), sl = B('lowpass', 320, 3), sg = G();
            wire(s, sl, sg, g); hit(sg, t, .25, .06, .5); run(s, t, .8);
          }
        } else {
          bar.ch.forEach(f => tone('sawtooth', f, t, .02, .018, .3, lp));
          noiseHit('bandpass', 5000, .4, t, .03, .035, .12, lp);
        }
        bar.mel.filter(m => m[0] === b).forEach(([, f, len]) => {
          tone('sine', f * 2, t, .002, .05, len, lp);
          tone('triangle', f * 8.1, t, .001, .01, .08, lp);
        });
        for (let k = 0; k < 3; k++) { // crackle
          const tk = t + Math.random() * beat;
          cg.gain.setValueAtTime(.08 * Math.random(), tk); cg.gain.setValueAtTime(0, tk + .004);
        }
        next += beat * (1 + (Math.random() - .5) * .02); i++;
      }
    }, 40);
    return { srcs: [crackle], stop: () => clearInterval(timer) };
  }
  // suspense before the answer reveal: an open-ended snare drumroll
  function rollLoop(g) {
    let next = now() + .05, n = 0;
    const timer = setInterval(() => {
      while (next < now() + .2) {
        const swell = Math.min(1, n / 60);
        snare(next, .05 + .14 * swell, g);
        next += 1 / 26; n++;
      }
    }, 30);
    return { srcs: [], stop: () => clearInterval(timer) };
  }
  // synthetic fallbacks for file-only cues (used only if the file failed to load)
  Object.assign(SYN, {
    rollUp: o => SYN.roll(o), rollComedy: () => SYN.roll({ dur: .9 }),
    rollTada: () => { SYN.roll({ dur: 1.9 }); setTimeout(() => SYN.fanfare(), 2000); },
    jingle: () => SYN.fanfare(), actStart: () => SYN.stab(), transBats: () => setTimeout(() => SYN.stab(), 2800), transPumpkin: () => setTimeout(() => SYN.fanfare(), 3000), leadChange: () => SYN.stab(), correct: () => SYN.ding(), dingdong: () => SYN.ding(), finaleMusic: () => SYN.fanfare(), applause: () => SYN.cheer(), gasp: () => SYN.murmurs(), aww: () => SYN.boo(),
  });

  const LOOPS = {
    waltz,
    roll: rollLoop,
    murmur: g => { // meaningless monster mumbling
      const s = N(), b = B('bandpass', 420, 1.2), lg = G(.03), lfo = O('sine', .9), dg = G(.016);
      const o = O('sawtooth', 70), ob = B('bandpass', 380, 4), og = G(.012), olfo = O('sine', 2.3), odg = G(.012);
      wire(s, b, lg, g); wire(lfo, dg); dg.connect(lg.gain);
      wire(o, ob, og, g); wire(olfo, odg); odg.connect(og.gain);
      return [s, lfo, o, olfo];
    },
    film: g => { // film rattling 'tatatata'
      const s = N(), b = B('bandpass', 2600, 2), lg = G(.03), lfo = O('square', 18), dg = G(.03);
      const hum = O('sine', 50), hg = G(.015);
      wire(s, b, lg, g); wire(lfo, dg); dg.connect(lg.gain); wire(hum, hg, g);
      return [s, lfo, hum];
    },
  };

  // Play a file once: opts.rate = playback speed (pitch too), opts.gain = volume — multiplied with the registered value (def). SFX go to out unprocessed
  function playFile(name, opts = {}, looped = false) {
    const list = buffers[name], { def, buf } = list[Math.floor(Math.random() * list.length)];
    const s = ctx.createBufferSource(), g = G((opts.gain == null ? 1 : opts.gain) * (def.gain == null ? 1 : def.gain));
    s.buffer = buf; s.playbackRate.value = (opts.rate || 1) * (def.rate || 1);
    if (looped) { s.loop = true; if (def.loopStart != null) s.loopStart = def.loopStart; if (def.loopEnd != null) s.loopEnd = def.loopEnd; }
    if (opts.swell) {                                     // opts.swell = [start factor, seconds]: start at that factor and rise to full volume over that time
      const full = g.gain.value, t = now();
      g.gain.setValueAtTime(full * opts.swell[0], t); g.gain.linearRampToValueAtTime(full, t + opts.swell[1]);
    }
    const off = opts.dur != null && def.peak != null ? Math.max(0, def.peak - opts.dur) : 0;
    wire(s, g, out); s.start(now(), off);
    // stop(f): f = decay time constant (s). Default .1 is almost instant; .35 fades over about 1 s
    return { cut: def.cut, stop(f = .1) { g.gain.setTargetAtTime(0, now(), f); try { s.stop(now() + f * 5); } catch (e) { /* already stopped */ } } };
  }

  // Loop on/off. opts.dur (s) means the end time is known — if the file has an up version, play that so its peak lands then
  function loop(name, on, opts = {}) {
    on = on && enabled && !!ctx;
    if (on && !loops[name]) {
      const up = buffers[name] && buffers[name][0].def.up;
      if (opts.dur != null && up && buffers[up]) loops[name] = playFile(up, opts);
      else if (buffers[name]) loops[name] = playFile(name, opts, true);
      else if (LOOPS[name]) loops[name] = loopNode(LOOPS[name]);
    } else if (!on && loops[name]) { loops[name].stop(loops[name].cut); delete loops[name]; }   // if the registered value has cut, stop with that time constant
  }

  function cue(name, opts = {}) {
    if (!enabled || !ctx || ctx.state !== 'running') return null;
    if (buffers[name]) return playFile(name, opts);   // a file returns { stop() } (to cut a long jingle midway)
    if (SYN[name]) SYN[name](opts);
    return null;
  }

  // Review: current scene and track, output level (rms) and the energy ratio above 3 kHz (hi). Used for recorded reviews where the sound cannot be heard
  function meter() {
    const st = { scene, bgm: bgmNow && bgmNow.name, synth: !!(bgmNow && bgmNow.synth), running: !!ctx && ctx.state === 'running' };
    if (!meterNode) return st;
    const td = new Float32Array(meterNode.fftSize); meterNode.getFloatTimeDomainData(td);
    const fd = new Float32Array(meterNode.frequencyBinCount); meterNode.getFloatFrequencyData(fd);
    let e = 0, hi = 0; const cut = Math.floor(3000 / (ctx.sampleRate / 2) * fd.length);
    fd.forEach((db, i) => { const p = Math.pow(10, db / 10); e += p; if (i >= cut) hi += p; });
    st.rms = +Math.sqrt(td.reduce((a, v) => a + v * v, 0) / td.length).toFixed(4); st.hi = +(hi / (e || 1)).toFixed(4);
    return st;
  }
  return { unlock, setEnabled, isEnabled: () => enabled, cue, loop, scene: setScene, bgm, meter };
})();
