/* Kiro Horror Quiz Show — main stage v3 (acts 1, 2, 3)
 *
 * The background is one plate: the original concept image edited with GPT. On top of it the code
 * draws text, scores, badges, lights, audience, ghost and player motion. Coordinates are in the 1600×900 plate space.
 * Protocol (khqs.stage/1) handling is the same as v1/v2: snapshot → state, event → handler, gate → beat_done.
 */
(() => {
  'use strict';
  const A = window.KHQS_ASSETS;
  const stage = document.getElementById('stage');

  /* ===================== utils ===================== */
  const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
  const lerp = (a, b, k) => a + (b - a) * k;
  const easeIO = k => (k < .5 ? 4 * k * k * k : 1 - Math.pow(-2 * k + 2, 3) / 2);
  const easeOut = k => 1 - Math.pow(1 - k, 3);
  const backOut = k => { const c = 2.0; return 1 + (c + 1) * Math.pow(k - 1, 3) + c * Math.pow(k - 1, 2); };
  const q12 = x => Math.floor(x * 12) / 12;
  const cx = r => (r[0] + r[2]) / 2, cy = r => (r[1] + r[3]) / 2;

  function el(tag, cls, parent, style) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (style) Object.assign(e.style, style);
    if (parent) parent.appendChild(e);
    return e;
  }
  function place(e, r) { Object.assign(e.style, { left: r[0] + 'px', top: r[1] + 'px', width: (r[2] - r[0]) + 'px', height: (r[3] - r[1]) + 'px' }); return e; }
  function img(key, parent, w) {
    const i = el('img', '', parent); i.src = A[key].src; i.alt = ''; i.draggable = false;
    if (w) { i.style.width = w + 'px'; i.style.height = (w * A[key].h / A[key].w) + 'px'; }
    return i;
  }
  // Text inside rect r. Also used for signs tilted by rot (degrees)
  function text(parent, r, str, cls, size, extra) {
    const t = place(el('div', 't ' + (cls || ''), parent), r);
    t.textContent = str;
    t.style.fontSize = size + 'px';
    if (extra) Object.assign(t.style, extra);
    return t;
  }
  // Shrink the font size until it fits the width
  // If the web font loads late, sizes measured with the fallback font are off → measure again after fonts load
  const fitted = [];
  document.fonts && document.fonts.ready.then(() => fitted.forEach(f => measure(f.t, f.max, f.min, f.wOnly)));
  // wOnly: check width only (for one-line text whose font ascent/descent exceeds the line height)
  function fit(t, max, min = 12, wOnly = false) { fitted.push({ t, max, min, wOnly }); measure(t, max, min, wOnly); }
  function measure(t, max, min, wOnly) {
    if (!t.isConnected) return;
    // With centred text the overflow on both sides is not counted in scrollWidth, so pin it top-left only while measuring
    const j = t.style.justifyContent, a = t.style.alignItems;
    t.style.justifyContent = 'flex-start'; t.style.alignItems = 'flex-start';
    let s = max;
    t.style.fontSize = s + 'px';
    while (s > min && (t.scrollWidth > t.clientWidth + 1 || (!wOnly && t.scrollHeight > t.clientHeight + 1))) { s -= 1; t.style.fontSize = s + 'px'; }
    t.style.justifyContent = j; t.style.alignItems = a;
  }

  /* ===================== Clock and animation ===================== */
  let clock = 0, paused = false, speed = 1;
  const tweens = new Set();
  // keep: do not stop even when the whole scene changes (snapshot). Used for transitions that span that moment (NEW SHOW → lobby)
  function anim(ms, fn, { fast = false, ease = easeIO, keep = false } = {}) {
    if (fast || ms <= 0) { fn(1); return Promise.resolve(); }
    return new Promise(res => tweens.add({ t0: clock, ms, fn, ease, res, keep }));
  }
  const wait = (ms, fast) => anim(ms, () => {}, { fast });

  /* ===================== Per-act layout (plate coordinates) ===================== */
  const LAYOUT = {
    1: {
      signs: { onair: [92, 62, 285, 148, 4], applause: [1336, 66, 1524, 140, -4] },
      title: [600, 212, 1030, 290],
      board: [380, 300, 1240, 465],
      cards: { O: [415, 465, 775, 665], X: [840, 465, 1200, 665] },
      cardLabels: { O: [500, 648, 685, 700], X: [925, 648, 1115, 700] },
      ledgeY: 652, // back edge of the voting ledge: players rise from behind this line
      arrows: [[1402, 396, 1524, 438, -4, 'QUIZ'], [1395, 456, 1528, 504, 3, 'MONSTERS'], [1410, 526, 1524, 570, -3, 'GOOD TIME!']],
      slots: [
        // Portraits sit at the inner bottom of the frame (above the bulb row). The middle slot is short to clear the title sign crown (about x 770–840, y 165+)
        // Same portrait size in all three slots (98×100, based on the middle slot)
        // Mina's slot: lowered so the hands grip the marquee below, tilted slightly left
        { frame: [350, 65, 625, 220], portrait: [380, 94, 478, 194], tilt: -6, name: [490, 78, 602, 124], score: [490, 132, 602, 192] },
        { frame: [670, 65, 960, 220], portrait: [696, 80, 794, 180], name: [800, 80, 904, 118], score: [818, 126, 946, 192] },
        { frame: [1000, 65, 1265, 220], portrait: [1032, 80, 1130, 180], name: [1142, 80, 1236, 126], score: [1142, 132, 1242, 192] },
      ],
      ghost: { cx: 172, bottom: 640, w: 140 },
      foot: [180, 302, 355, 453, 542, 632, 735, 838, 938, 1035, 1145, 1250, 1335, 1483], footY: 738,
    },
    2: {
      signs: { onair: [84, 62, 286, 150, 6], applause: [1332, 66, 1528, 150, -5] },
      qframe: [335, 160, 527, 250], sframe: [1073, 160, 1263, 250],
      title: [578, 55, 1030, 172], sub: [668, 198, 938, 243],
      board: [440, 290, 1186, 476], tag: [1030, 296, 1180, 344, 8],
      pods: [{ cx: 537, top: 612, plate: [480, 639, 596, 680] }, { cx: 797, top: 612, plate: [739, 639, 855, 680] }, { cx: 1063, top: 612, plate: [1005, 639, 1123, 680] }],
      ghost: { cx: 116, bottom: 556, w: 122 },
      foot: [133, 243, 352, 480, 602, 731, 851, 976, 1100, 1220, 1337, 1460], footY: 735,
    },
    3: {
      signs: { onair: [92, 62, 285, 152, 5], applause: [1336, 66, 1524, 145, -4] },
      title: [470, 72, 1135, 235],
      header: [440, 290, 1165, 342], inner: [474, 350, 1126, 465],
      boards: [
        { frame: [425, 492, 665, 688], portrait: [438, 502, 522, 590], name: [526, 507, 652, 536], score: [526, 541, 652, 586], bet: [442, 598, 650, 672] },
        { frame: [685, 492, 925, 688], portrait: [698, 502, 782, 590], name: [786, 507, 912, 536], score: [786, 541, 912, 586], bet: [702, 598, 912, 672] },
        { frame: [942, 492, 1188, 688], portrait: [956, 502, 1040, 590], name: [1044, 507, 1172, 536], score: [1044, 541, 1175, 586], bet: [958, 598, 1175, 672] },
      ],
      redbar: [640, 688, 962, 734],
      timer: { top: [1324, 364, 1478, 462], clock: [1332, 474, 1474, 536], foot: [1324, 548, 1478, 636] },
      ghost: { cx: 186, bottom: 612, w: 140 },
      foot: [175, 355, 470, 625, 722, 880, 970, 1133, 1237, 1330], footY: 738,
    },
  };
  const FANS = ['sack', 'tophat_skull', 'vampire', 'bolt'];
  // If the fixed English signs (ON AIR, APPLAUSE, act titles, FINAL QUESTION, …) are baked into the plate, hide the code text. Light and flicker stay
  const BAKED = true;
  const fanKey = t => (FANS.includes(t) ? t : 'vampire');

  /* ===================== Layers ===================== */
  const plate = el('img', '', stage); Object.assign(plate.style, { left: 0, top: 0, width: '1600px', height: '900px' });
  // Preload all three plates so the previous one never lingers when the act changes
  const platePreload = [1, 2, 3].map(n => { const i = new Image(); i.src = A[`plate${n}`].src; return i; });
  // Act 3 last question: the plate with the question board on it. Shown only after the board has fully dropped
  const plateQ = el('img', '', stage); Object.assign(plateQ.style, { left: 0, top: 0, width: '1600px', height: '900px', opacity: 0 });
  plateQ.src = A.plate3q.src; plateQ.alt = '';
  // Finale: the stage with the boards cleared and the curtain closed. The podium goes on finL
  const plateF = el('img', '', stage); Object.assign(plateF.style, { left: 0, top: 0, width: '1600px', height: '900px', opacity: 0 });
  plateF.src = A.plateF.src; plateF.alt = '';
  const ov = el('div', 'layer', stage);           // overlay rebuilt per act (text, badges, players)
  const finL = el('div', 'layer', stage);         // finale podium (above the act overlay, below the blackout)
  const darkness = el('div', '', stage); darkness.id = 'darkness';
  const ghostL = el('div', 'layer', stage);       // The ghost glows by itself, so it sits above the blackout. Its face must be visible in tense moments
  const sheetL = el('div', 'layer', stage);       // the opening's sheet. Kept separate so rebuilding an act does not remove it
  const curL = el('div', 'layer', stage);         // scene transition (curtain): covers the whole stage. Lights and the front-row audience are in front of it
  const lights = el('div', 'layer', stage);       // glow (screen)
  const audL = el('div', 'layer', stage);         // front-row audience (out of focus)
  const fx = el('div', 'layer', stage);           // confetti, BUZZ, speech bubbles
  const topL = el('div', 'layer', stage, { zIndex: 60, pointerEvents: 'none' }); // bat and pumpkin transitions: cover the whole screen, audience and lobby included
  // Preload transition art so it never pops in late mid-flight
  const transPreload = ['bat_0', 'bat_1', 'bat_2', 'bat_big', ...[0, 1, 2, 3, 4, 5].map(n => `pk_${n}`), ...[0, 1, 2, 3, 4, 5, 6, 7, 8].map(n => `pk_bit_${n}`)]
    .filter(k => A[k]).map(k => { const i = new Image(); i.src = A[k].src; return i; });

  // Audience: heads behind, seat backs in front
  const HEAD_X = [92, 288, 486, 690, 905, 1110, 1312, 1510];
  const heads = HEAD_X.map((x, i) => {
    const k = `aud_${i}`, h = 196, w = h * A[k].w / A[k].h;
    const b = el('div', 'abs', audL, { left: (x - w / 2) + 'px', top: (902 - h) + 'px', width: w + 'px', height: h + 'px', transformOrigin: '50% 100%' });
    img(k, b, w);
    const bang = el('div', 't han', b, { left: '50%', top: '-34px', fontSize: '38px', color: '#e8323f', opacity: 0, textShadow: '0 2px 0 #2a0505' });
    bang.textContent = i % 2 ? '!' : '!!';
    return { b, i, bang };
  });
  [140, 405, 670, 935, 1200, 1465].forEach((x, i) => {
    const w = 290, h = w * A[`seat_${i}`].h / A[`seat_${i}`].w;
    const b = el('div', 'abs', audL, { left: (x - w / 2) + 'px', top: (842) + 'px', width: w + 'px', height: h + 'px' });
    img(`seat_${i}`, b, w);
  });

  // No film grain — keep the plate's own texture

  /* ===================== State ===================== */
  let act = 1, LY = LAYOUT[1];
  const seats = [0, 1, 2].map(i => ({ i, player: null, view: null }));
  const ghostLit = { ghost: .72, front: 0, soft: false, aud: 1 }; // opening: brightness while the ghost glows by itself, audience factor while the fuse is blown
  const light = { dark: 0, fx: 800, fy: 400, rx: 400, ry: 300, flash: 0, aud: 0, chase: 0 };
  const target = { dark: 0, fx: 800, fy: 400, rx: 400, ry: 300 };
  let applauseUntil = 0, focusUntil = 0, shockUntil = 0;
  const state = { phase: null, deadline: null, question: null, choices: null };
  let A1 = null, A2 = null, A3 = null; // per-act overlay handles
  let ghost = null, signs = null, foot = [];

  function setDark(d, focus, fast) {
    target.dark = d;
    if (focus) Object.assign(target, { fx: focus[0], fy: focus[1], rx: focus[2], ry: focus[3] });
    if (fast) Object.assign(light, target);
  }
  const applause = s => { applauseUntil = clock + s * 1000; focusUntil = Math.max(focusUntil, clock + s * 900); };
  let betBgm = false;   // act 3 betting BGM is playing
  // The betting BGM starts at once. The intro jingle that used to precede it (finalBetIntro) was removed: the user found its timing and sound awkward (2026-11-25)
  function startBetMusic() { betBgm = true; Sound.bgm('betting', { fade: .8 }); }
  function stopBetMusic(fade = .6) { betBgm = false; Sound.bgm(null, { fade }); }
  const THINK_PHASES = new Set(['ox.answering', 'final.answering']);
  let thinkTick = false; // while the thinking-time tick runs: that step's deadline (ms, 0 if none); otherwise false
  const shock = s => { shockUntil = clock + s * 1000; focusUntil = Math.max(focusUntil, clock + s * 900); };

  /* ===================== Building the act overlay ===================== */
  function buildAct(n) {
    act = n; LY = LAYOUT[n];
    plate.src = A[`plate${n}`].src;
    plateQ.style.opacity = 0;
    audL.style.top = n === 3 ? '40px' : '0'; // act 3's red status strip sits lower, so the audience moves down a little
    ov.innerHTML = ''; ghostL.innerHTML = ''; lights.innerHTML = ''; fx.innerHTML = '';
    A1 = A2 = A3 = null;
    // sign
    const mkSign = (r, str, color, bg) => {
      const t = text(ov, r, str, 'sign', 34, { color, transform: `rotate(${r[4]}deg)`, background: bg || 'transparent', borderRadius: '4px' });
      fit(t, 40);
      if (BAKED) t.style.visibility = 'hidden'; // the text is in the art; only the flickering light is code
      return t;
    };
    signs = {
      onair: mkSign(LY.signs.onair, 'ON AIR', '#fff3e0', n === 2 && !BAKED ? 'rgba(196, 24, 36, .92)' : null),
      applause: mkSign(LY.signs.applause, 'APPLAUSE', '#3a1d08', n === 2 && !BAKED ? 'rgba(255, 196, 70, .92)' : null),
    };
    signs.onair.style.textShadow = '0 0 10px rgba(255, 120, 120, .8)';
    const sg = r => el('div', 'abs glow', lights, { left: (r[0] - 70) + 'px', top: (r[1] - 50) + 'px', width: (r[2] - r[0] + 140) + 'px', height: (r[3] - r[1] + 100) + 'px' });
    signs.onairGlow = sg(LY.signs.onair); signs.onairGlow.style.background = 'radial-gradient(ellipse, rgba(255,70,70,.45), rgba(255,60,60,0) 70%)';
    signs.applauseGlow = sg(LY.signs.applause); signs.applauseGlow.style.background = 'radial-gradient(ellipse, rgba(255,214,110,.75), rgba(255,190,80,0) 70%)';
    // footlight flicker
    foot = LY.foot.map(x => el('div', 'abs glow', lights, { left: (x - 46) + 'px', top: (LY.footY - 50) + 'px', width: '92px', height: '80px', background: 'radial-gradient(ellipse, rgba(255,214,140,.55), rgba(255,180,90,0) 70%)' }));
    // ghost (only the upper body shows behind the lectern)
    ghost = buildGhost(LY.ghost);
    if (n === 1) A1 = buildAct1();
    if (n === 2) A2 = buildAct2();
    if (n === 3) A3 = buildAct3();
    seats.forEach(s => { s.view = buildSeat(s.i, s.player); });
  }

  // purple effect mark next to the ghost's expression (viewBox 0 0 70 70)
  const MARK = (d, extra = '') => `<path d="${d}" fill="#b78bff" stroke="#2c1150" stroke-width="2.5" stroke-linejoin="round" ${extra}/>`;
  const TICKS = MARK('M10 40 L4 26 L12 23 L17 38 Z') + MARK('M26 32 L24 10 L34 10 L35 32 Z') + MARK('M42 37 L54 20 L61 26 L48 41 Z');
  const GHOST_MARKS = {
    happy: TICKS,
    present: TICKS,
    surprised: MARK('M20 38 L14 8 L28 6 L29 37 Z') + MARK('M42 40 L46 14 L58 18 L49 42 Z') + '<circle cx="24" cy="50" r="6" fill="#b78bff" stroke="#2c1150" stroke-width="2.5"/><circle cx="43" cy="53" r="5" fill="#b78bff" stroke="#2c1150" stroke-width="2.5"/>',
    worried: MARK('M22 10 C32 24 36 30 32 38 C28 45 15 44 13 35 C12 28 18 20 22 10 Z') + MARK('M48 26 C55 36 57 40 54 45 C51 50 42 49 41 43 C40 38 44 33 48 26 Z'),
    wink: MARK('M32 6 C34 22 38 28 56 32 C38 36 34 42 32 58 C30 42 26 36 8 32 C26 28 30 22 32 6 Z'),
    sad: MARK('M16 12 L24 12 L24 42 L16 42 Z') + MARK('M32 18 L40 18 L40 52 L32 52 Z') + MARK('M48 12 L56 12 L56 38 L48 38 Z'),
    angry: MARK('M26 8 L33 26 L14 26 L8 18 Z') + MARK('M38 8 L58 16 L54 27 L34 26 Z') + MARK('M12 36 L32 34 L26 56 L16 52 Z') + MARK('M36 34 L56 36 L52 52 L42 56 Z'),
    tease: TICKS,
    sleep: '<text x="14" y="52" font-family="Alfa Slab One" font-size="34" fill="#b78bff" stroke="#2c1150" stroke-width="1.5">Z</text><text x="42" y="28" font-family="Alfa Slab One" font-size="24" fill="#b78bff" stroke="#2c1150" stroke-width="1.2">z</text>',
    think: '<text x="20" y="52" font-family="Alfa Slab One" font-size="46" fill="#b78bff" stroke="#2c1150" stroke-width="2">?</text>',
  };
  const GHOST_POSES = ['happy', 'surprised', 'worried', 'wink', 'sad', 'angry', 'sleep', 'present', 'peek', 'think', 'tease'];
  const GHOST_SLEEP_AFTER = 15000;

  // Normally a faceless body + code face (blink, gaze, mouth); when reacting, swap to an expression image.
  // The box origin is the bottom centre, so the body does not jump when the expression changes, and the squash-and-bounce is anchored at the bottom.
  function buildGhost(g) {
    const body = A.ghost_body, U = g.w / body.w, h = body.h * U;
    const glow = el('div', 'abs glow', ghostL, { left: (g.cx - g.w * .8) + 'px', top: (g.bottom - h * 1.26) + 'px', width: (g.w * 1.6) + 'px', height: (h * 1.6) + 'px', background: 'radial-gradient(circle, rgba(150,90,255,.26), rgba(150,90,255,.12) 50%, rgba(150,90,255,0) 70%)' });
    const box = el('div', 'abs', ghostL, { left: g.cx + 'px', top: g.bottom + 'px', width: 0, height: 0, transformOrigin: '0 0' });
    const sprite = key => {
      const a = A[key], lift = key === 'ghost_sleep' ? h * .16 : 0; // the flat melted pose is raised so the face is not hidden by the lectern
      const b = el('div', 'abs', box, { left: (-a.ax * U) + 'px', top: (-a.h * U - lift) + 'px', width: (a.w * U) + 'px', height: (a.h * U) + 'px', visibility: 'hidden' });
      img(key, b, a.w * U);
      return b;
    };
    const calm = sprite('ghost_body');
    calm.style.visibility = 'visible';
    const poses = {};
    GHOST_POSES.forEach(k => { poses[k] = sprite(`ghost_${k}`); });
    const NS = 'http://www.w3.org/2000/svg';
    const svg = document.createElementNS(NS, 'svg');
    svg.setAttribute('viewBox', `0 0 ${body.w} ${body.h}`);
    Object.assign(svg.style, { position: 'absolute', left: 0, top: 0, width: '100%', height: '100%', overflow: 'visible' });
    calm.appendChild(svg);
    const mk = (tag, a, parent = svg) => { const e = document.createElementNS(NS, tag); for (const k in a) e.setAttribute(k, a[k]); parent.appendChild(e); return e; };
    // Oval eyes, slightly tilted and offset right like the Kiro mascot. Slightly different sizes, tiny highlight dots. The mouth appears only while speaking
    const eyes = [[120, 106, 16, 24], [204, 99, 18.5, 27.5]].map(([x, y, rx, ry]) => {
      const tilt = mk('g', { transform: `rotate(7 ${x} ${y})` });
      return { x, y, rx, ry, ball: mk('ellipse', { cx: x, cy: y, rx, ry, fill: '#120b18' }, tilt), hi: mk('circle', { cx: x, cy: y, r: rx * .2, fill: '#fff' }, tilt) };
    });
    const mouth = mk('ellipse', { cx: 164, cy: 146, rx: 10, ry: 0, fill: '#1c0f24' });
    const marks = el('div', 'abs', box, { left: (g.w * .22) + 'px', top: (-h * 1.24) + 'px', width: '62px', height: '62px', transformOrigin: '30% 90%' });
    // Put the lectern and mic back in front of the ghost. This layer is above the blackout, so match its brightness to the blackout
    const f = A[`front${act}`], front = el('div', 'abs', ghostL, { left: f.x + 'px', top: f.y + 'px', width: f.w + 'px', height: f.h + 'px' });
    img(`front${act}`, front, f.w);
    return { box, glow, front, calm, poses, marks, eyes, mouth, status: 'idle', focus: null, voiceT: 0, pose: null, until: 0, shown: null, popT: -1e9 };
  }

  // Ghost expression. Held for ms, then back to normal. ms 0 = hold until the next expression
  function ghostPose(name, ms = 1800) {
    if (!ghost) return;
    ghost.pose = name;
    ghost.until = ms ? clock + ms : Infinity;
  }

  function buildAct1() {
    const L = LY;
    const title = BAKED ? null : text(ov, L.title, 'ACT 1 · O / X', 'slab ink', 40);
    const qno = text(ov, [L.board[0], L.board[1] + 14, L.board[2], L.board[1] + 50], '', 'slab', 30, { color: 'var(--red)' });
    // the question line starts below the stamp (top left)
    const q = text(ov, [L.board[0] + 60, L.board[1] + 64, L.board[2] - 60, L.board[3] - 8], '', 'wrap ink', 46);
    const timer = el('div', 'timerchip', ov, { left: (L.board[2] - 92) + 'px', top: (L.board[1] + 16) + 'px' });
    const stamp = el('div', 'stamp', ov, { left: (L.board[0] + 36) + 'px', top: (L.board[1] + 14) + 'px', transform: 'rotate(-7deg)' });
    if (!BAKED) {
      text(ov, L.cardLabels.O, 'O', 'slab', 34, { color: '#fff3e0' });
      text(ov, L.cardLabels.X, 'X', 'slab', 34, { color: '#fff3e0' });
      L.arrows.forEach(([x1, y1, x2, y2, rot, s]) => fit(text(ov, [x1, y1, x2, y2], s, 'slab ink', 22, { transform: `rotate(${rot}deg)` }), 22));
    }
    // Highlight the correct card: halo behind it; wrong cards dim
    const cards = {};
    for (const k of ['O', 'X']) {
      const r = L.cards[k];
      const halo = el('div', 'abs glow', lights, { left: (r[0] - 90) + 'px', top: (r[1] - 80) + 'px', width: (r[2] - r[0] + 180) + 'px', height: (r[3] - r[1] + 160) + 'px', background: 'radial-gradient(ellipse, rgba(255,220,140,0) 46%, rgba(255,214,130,.6) 58%, rgba(255,200,100,0) 72%)', opacity: 0 });
      const shade = place(el('div', 'abs', ov, { background: 'rgba(10,4,6,.6)', borderRadius: '10px', opacity: 0 }), [r[0] + 10, r[1] + 8, r[2] - 10, r[3] - 8]);
      const ring = place(el('div', 'abs', ov, { borderRadius: '12px', border: '5px solid #f2c26a', boxShadow: '0 0 26px 8px rgba(255,200,90,.75), inset 0 0 22px rgba(255,220,140,.6)', opacity: 0 }), [r[0] + 4, r[1] + 2, r[2] - 4, r[3] - 2]);
      cards[k] = { halo, shade, ring, win: 0, lose: 0 };
    }
    // Voting ledge: a window spanning both cards. Its bottom edge is the ledge's back edge, so players are clipped as if rising from behind the ledge
    const booth = { x0: L.cards.O[0] - 30, h: 240 };
    booth.n = el('div', 'abs', ov, { left: booth.x0 + 'px', top: (L.ledgeY - booth.h) + 'px', width: (L.cards.X[2] + 30 - booth.x0) + 'px', height: booth.h + 'px', overflow: 'hidden' });
    const rules = ruleCard([L.board[0] + 40, L.board[1] + 12, L.board[2] - 40, L.board[3] - 12], 1);
    return { title, qno, q, timer, stamp, cards, booth, voters: {}, rules };
  }

  // Act-start rule card: before the first question, hang this act's rules on the empty board (same content as the MC's rule intro). Removed when the first question appears
  const RULES = {
    1: ['HOW TO PLAY', 'PICK <b class="o">O</b> OR <b class="x">X</b> ON YOUR PHONE', 'EVERY RIGHT ANSWER <b>+10</b>'],
    2: ['HOW TO PLAY', 'BUZZ IN &amp; SAY IT!', 'RIGHT <b>+20</b> · WRONG? SIT THAT ONE OUT'],
  };
  function ruleCard(r, n) {
    const c = place(el('div', 'rules', ov), r);
    RULES[n].forEach((h, k) => { el('div', ['rh', 'rm', 'rs'][k], c).innerHTML = h; });
    fit(c.children[1], n === 1 ? 46 : 42, 24, true); fit(c.children[2], 22, 14, true);
    return c;
  }
  // Give the card one little shake when the act opens so it catches the eye
  function rulesNudge(fast) {
    const c = (A1 || A2 || {}).rules;
    if (!c || fast || c.style.opacity === '0') return;
    anim(520, k => { c.style.transform = `scale(${lerp(.9, 1, backOut(k)).toFixed(3)}) rotate(${(Math.sin(k * 14) * 1.6 * (1 - k)).toFixed(2)}deg)`; }, { ease: k => k });
  }
  function rulesOut(fast) {
    const c = (A1 || A2 || {}).rules;
    if (!c || c.style.opacity === '0') return;
    return anim(260, k => { c.style.opacity = k >= 1 ? '0' : 1 - k; c.style.transform = `scale(${lerp(1, .94, k).toFixed(3)})`; }, { fast });
  }

  function buildAct2() {
    const L = LY;
    if (!BAKED) {
    text(ov, [L.title[0], L.title[1] + 6, L.title[2], L.title[1] + 62], 'KIRO', 'slab ink', 48);
    const t2 = text(ov, [L.title[0] + 20, L.title[1] + 60, L.title[2] - 20, L.title[3] - 6], 'HORROR QUIZ SHOW', 'slab', 40, { color: 'var(--red)' });
    fit(t2, 40);
    text(ov, L.sub, 'ACT 2 · BUZZER', 'slab ink', 26);
    }
    const qn = text(ov, [L.qframe[0], L.qframe[1] + 6, L.qframe[2], L.qframe[1] + 58], '', 'score', 40);
    const qs = text(ov, [L.qframe[0], L.qframe[1] + 56, L.qframe[2], L.qframe[3] - 4], '', '', 20, { color: '#d9c39a' });
    const st = text(ov, [L.sframe[0] + 8, L.sframe[1] + 8, L.sframe[2] - 8, L.sframe[3] - 8], '', 'slab wrap', 24, { color: 'var(--amber)' });
    const tag = text(ov, [L.tag[0], L.tag[1], L.tag[2], L.tag[3]], 'BUZZER', 'slab', 22, { color: '#fff1d6', transform: `rotate(${L.tag[4]}deg)` });
    const cat = text(ov, [L.board[0], L.board[1] + 16, L.board[2], L.board[1] + 50], '', 'han', 24, { color: 'var(--red)' });
    const q = text(ov, [L.board[0] + 60, L.board[1] + 52, L.board[2] - 60, L.board[3] - 46], '', 'wrap ink', 46);
    // The answer appears as the ghost host's speech bubble: a bulb-framed card whose tail points down at the ghost
    const ans = el('div', 'ghostsay', ov, { left: '24px', bottom: (900 - 386) + 'px', width: '300px' }); // width that does not cover the top Q frame (x 335+)
    const ansHead = el('div', 'head', ans); ansHead.textContent = 'THE ANSWER IS…';
    const ansMain = el('div', 'main', ans);
    const ansSub = el('div', 'sub', ans);
    const stamp = el('div', 'stamp', ov, { left: (L.board[0] + 30) + 'px', top: (L.board[1] + 12) + 'px', transform: 'rotate(-7deg)' });
    const music = el('div', 'music', ov, { left: (L.board[0] + 130) + 'px', top: (L.board[3] - 52) + 'px', width: (L.board[2] - L.board[0] - 260) + 'px', height: '40px' });
    const notes = [0, 1, 2].map(() => { const n = el('span', 'note', music); n.textContent = '♪'; return n; });
    const bar = el('div', 'bar', music, { flex: 1 }); const fill = el('i', '', bar);
    // Art hung on the board while the question is hidden (KHQS_v11): gramophone, notes, LISTEN!, listening ghost
    const lw = 500, lh = lw * A.listen.h / A.listen.w;
    const listen = el('div', 'abs listen', ov, { left: (cx(L.board) - lw / 2) + 'px', top: (L.board[1] + 104 - lh / 2) + 'px', width: lw + 'px', height: lh + 'px', opacity: 0 });
    img('listen', listen, lw);
    // Keep the side frames filled before the first question too: question count and a ready line (replaced when the question appears)
    qn.textContent = QTOTAL[2]; qs.textContent = 'QUESTIONS'; st.textContent = 'GET READY…'; fit(st, 24);
    const rules = ruleCard([L.board[0] + 20, L.board[1] + 14, L.board[2] - 80, L.board[1] + 122], 2); // moved a little left because the top right has the BUZZER tag; below y 412 the players' heads cover it
    return { qn, qs, st, tag, cat, q, ans, ansMain, ansSub, stamp, music, notes, fill, listen, media: null, rules };
  }

  function buildAct3() {
    const L = LY;
    if (!BAKED) text(ov, [L.title[0] + 60, L.title[1] + 12, L.title[2] - 60, L.title[1] + 112], 'FINAL BET', 'slab', 84, { color: '#3a2a20', letterSpacing: '4px' });
    if (!BAKED) text(ov, [L.title[0] + 60, L.title[1] + 112, L.title[2] - 60, L.title[3] - 14], '★  FINAL BETTING ROUND  ★', 'slab', 28, { color: 'var(--red)' });
    const header = BAKED ? null : text(ov, L.header, '♛  FINAL QUESTION  ♛', 'slab', 24, { color: 'var(--red)' });
    // inner board (115 px tall): category line → question line → choices 2×2
    const cat = text(ov, [L.inner[0], L.inner[1] + 2, L.inner[2], L.inner[1] + 24], '', 'han', 18, { color: '#7a4a2a' });
    const big = text(ov, [L.inner[0] + 120, L.inner[1] + 28, L.inner[2] - 120, L.inner[3] - 8], '', 'han ink', 44);
    // Last question board: drops from above when the question appears and covers the sign and the middle paper board (art: tools/build_act3_question.py)
    // Coordinates below are slots inside the board art (KHQS_v17, red tin frame without bulbs): header strip, question area, four choice cells (red disc at the left end)
    const QB = A.qboard3;
    const qb = el('div', 'abs qb3', ov, { left: QB.x + 'px', top: QB.y + 'px', width: QB.w + 'px', height: QB.h + 'px', visibility: 'hidden' });
    img('qboard3', qb, QB.w);
    const qhead = text(qb, [130, 106, 770, 150], '', 'qb3-head', 25);
    const q = text(qb, [70, 166, 830, 286], '', 'han ink wrap', 46, { lineHeight: 1.2 });
    const choices = [0, 1, 2, 3].map(k => {
      const x = 52 + (k % 2) * 407, y = 304 + Math.floor(k / 2) * 75;
      const c = place(el('div', 'choice3', qb, { opacity: 0 }), [x, y, x + 387, y + 63]);
      c.innerHTML = '<b></b><span></span>';
      return c;
    });
    const red = text(ov, L.redbar, '', 'slab', 22, { color: '#fff1d6' });
    const tTop = text(ov, L.timer.top, '⌛\nBETS CLOSE IN', 'slab ink wrap', 18, { whiteSpace: 'pre-line' });
    const tClock = text(ov, L.timer.clock, '--:--', 'score', 34);
    const tFoot = text(ov, L.timer.foot, '', 'slab ink wrap', 17, { whiteSpace: 'pre-line' });
    return { header, cat, big, qb, qhead, q, choices, red, tTop, tClock, tFoot };
  }

  /* ===================== Seats (shaped differently per act) ===================== */
  function portraitBox(r, fan, tilt = 0) {
    // The character hangs its hands over the bottom edge of the scoreboard window (anything outside the window is clipped)
    const box = place(el('div', 'abs', ov, { overflow: 'hidden', transformOrigin: '50% 100%', transform: tilt ? `rotate(${tilt}deg)` : '' }), r);
    const inner = el('div', 'abs', box, { left: 0, top: 0, width: '100%', height: '100%', transformOrigin: '50% 100%' });
    const poses = {};
    for (const p of ['idle', 'cheer', 'sad']) {
      const k = `fan_${fan}_${p}`, w = (r[2] - r[0]) * (p === 'cheer' ? 1.08 : .98), h = w * A[k].h / A[k].w;
      const i = img(k, inner, w);
      Object.assign(i.style, { left: ((r[2] - r[0]) - w) / 2 + 'px', top: ((r[3] - r[1]) - h + 4) + 'px', display: p === 'idle' ? '' : 'none' });
      poses[p] = i;
    }
    return { box, inner, poses };
  }
  /* Act 1 decoy: when a player answers, the scoreboard character ducks below the window (its body has gone to the ledge below),
   * and a crude plywood cut-out of the character pops up in its place (KHQS_v16, tools/build_decoys.py).
   * It has the sticker's width and baseline, so the hands rest on the window's bottom edge at the same height. Plywood is stiff, so it only tilts */
  function makeSign(box, fk, r) {
    const W = r[2] - r[0], H = r[3] - r[1], k = `decoy_${fk}`, w = W * .98, h = w * A[k].h / A[k].w;
    const s = el('div', 'abs', box, { left: 0, top: 0, width: W + 'px', height: H + 'px', transformOrigin: '50% 100%', translate: `0 ${H + 40}px` });
    Object.assign(img(k, s, w).style, { left: ((W - w) / 2) + 'px', top: (H - h + 6) + 'px' });
    return s;
  }
  // down: the character goes below the window and the sign comes up. Calling it the other way reverts. Overlapping calls: only the last one moves
  function duck(v, down, fast) {
    if (!v || !v.sign || !!v.ducked === down) return Promise.resolve();
    v.ducked = down;
    const tok = v.duckTok = {}, H = v.box.offsetHeight + 14, mine = f => k => { if (v.duckTok === tok) f(k); };
    const inner = y => { v.inner.style.translate = `0 ${y.toFixed(1)}px`; }, sign = y => { v.sign.style.translate = `0 ${y.toFixed(1)}px`; };
    const [first, then] = down ? [inner, sign] : [sign, inner];
    return anim(down ? 200 : 180, mine(k => first(k * k * H)), { fast, ease: k => k })
      .then(() => { if (!fast && v.duckTok === tok) Sound.cue('pop'); return anim(down ? 420 : 380, mine(k => then((1 - backOut(k)) * H)), { fast, ease: k => k }); });
  }
  function vacantOver(r) {
    const w = r[2] - r[0], h = w * A.vacant.h / A.vacant.w;
    const b = el('div', 'abs', ov, { left: r[0] + 'px', top: (cy(r) - h / 2) + 'px', width: w + 'px', height: h + 'px', transform: 'rotate(-2deg)' });
    img('vacant', b, w);
    const eyes = el('div', 'abs', b, { left: '43%', top: '52%', width: '14%', height: '8%', borderRadius: '6px' });
    return { b, eyes };
  }

  function buildSeat(i, p) {
    if (act === 1) {
      const S = LY.slots[i];
      if (!p) { const v = vacantOver([S.frame[0] + 10, S.frame[1] + 8, S.frame[2] - 10, S.frame[3] - 6]); return { vacant: v, focus: [cx(S.frame), cy(S.frame)] }; }
      const pb = portraitBox(S.portrait, fanKey(p.fanType), S.tilt);
      pb.sign = makeSign(pb.box, fanKey(p.fanType), S.portrait);
      const name = text(ov, S.name, p.name, 'ink', 30); fit(name, 30);
      const score = text(ov, S.score, String(p.score), 'score', 44);
      // The answer badge sits at the scoreboard's top right corner (the bottom overlaps the title sign)
      const badge = el('div', 'badge', ov, { left: (S.frame[2] - 44) + 'px', top: (S.frame[1] - 22) + 'px', width: '54px', height: '54px', fontSize: '30px' });
      const delta = el('div', 'delta', ov, { left: (cx(S.score) - 30) + 'px', top: (S.score[3] - 10) + 'px' });
      return { ...pb, name, score, badge, delta, value: p.score, focus: [cx(S.frame), cy(S.frame) + 40], pose: 'idle', hop: -9, shake: -9 };
    }
    if (act === 2) {
      const P = LY.pods[i];
      if (!p) { const v = vacantOver([P.cx - 118, P.top - 26, P.cx + 118, P.top + 110]); return { vacant: v, focus: [P.cx, P.top] }; }
      const w = 176, bottom = P.top + 14;
      const box = el('div', 'abs', ov, { left: (P.cx - w / 2) + 'px', top: (bottom - 230) + 'px', width: w + 'px', height: '230px' });
      const inner = el('div', 'abs', box, { left: 0, top: 0, width: '100%', height: '100%', transformOrigin: '50% 100%' });
      const poses = {};
      for (const pz of ['idle', 'cheer', 'sad']) {
        const k = `fan_${fanKey(p.fanType)}_${pz}`, pw = w * (pz === 'cheer' ? 1.12 : 1), ph = pw * A[k].h / A[k].w;
        const im = img(k, inner, pw);
        Object.assign(im.style, { left: (w - pw) / 2 + 'px', top: (230 - ph) + 'px', display: pz === 'idle' ? '' : 'none' });
        poses[pz] = im;
      }
      const dome = el('div', 'dome', ov, { left: (P.cx - 34) + 'px', top: (P.top - 16) + 'px', width: '68px', height: '26px' });
      const domeGlow = el('div', 'abs glow', lights, { left: (P.cx - 70) + 'px', top: (P.top - 60) + 'px', width: '140px', height: '100px', background: 'radial-gradient(ellipse, rgba(255,90,90,.85), rgba(255,60,60,0) 70%)', opacity: 0 });
      const name = text(ov, [P.plate[0] + 6, P.plate[1], P.plate[0] + 60, P.plate[3]], p.name, 'ink', 24); fit(name, 24);
      const score = text(ov, [P.plate[0] + 58, P.plate[1], P.plate[2] - 4, P.plate[3]], String(p.score), 'slab', 26, { color: 'var(--red)' });
      const delta = el('div', 'delta', ov, { left: (P.cx - 20) + 'px', top: (P.plate[1] - 30) + 'px' });
      return { box, inner, poses, dome, domeGlow, name, score, delta, verdict: null, cx: P.cx, top: P.top, value: p.score, focus: [P.cx, P.top - 60], pose: 'idle', hop: -9, shake: -9, locked: false, armed: false };
    }
    const B = LY.boards[i];
    if (!p) { const v = vacantOver([B.frame[0] + 8, B.frame[1] + 14, B.frame[2] - 8, B.frame[3] - 14]); return { vacant: v, focus: [cx(B.frame), cy(B.frame)] }; }
    const pb = portraitBox(B.portrait, fanKey(p.fanType));
    const name = text(ov, B.name, p.name, 'ink', 26); fit(name, 26);
    const score = text(ov, B.score, String(p.score), 'score', 36);
    const bet = text(ov, B.bet, 'THINKING…', 'slab wrap', 20, { color: '#8a6a4a', flexDirection: 'column' });
    const badge = el('div', 'badge ch', ov, { left: (B.frame[2] - 50) + 'px', top: (B.bet[1] - 4) + 'px', width: '44px', height: '44px', fontSize: '22px' });
    const delta = el('div', 'delta', ov, { left: (cx(B.score) - 30) + 'px', top: (B.score[1] - 40) + 'px' });
    const crown = text(ov, [B.portrait[0] - 10, B.portrait[1] - 44, B.portrait[2] + 10, B.portrait[1] + 18], '♛', '', 64, { opacity: 0, color: 'var(--gold)', textShadow: '0 3px 0 #5a3410, 0 0 16px rgba(255,200,90,.9)' });
    return { ...pb, name, score, bet, badge, delta, crown, value: p.score, focus: [cx(B.frame), cy(B.frame)], pose: 'idle', hop: -9, shake: -9 };
  }
  const viewOf = i => seats[i] && seats[i].player ? seats[i].view : null;
  const occupied = () => seats.filter(s => s.player);

  function setPose(v, pose) { if (!v || !v.poses) return; v.pose = pose; for (const k in v.poses) v.poses[k].style.display = k === pose ? '' : 'none'; }
  /* ===================== Act 1 voting ledges =====================
   * When picks are revealed, each player rises from behind the ledge in front of the card they chose. A player who changes their mind in the betrayal chance crosses to the other ledge.
   * The ledge art is in the plate (KHQS_v10, tools/build_act1_ledges.py). Players are clipped at the ledge's back edge (LY.ledgeY) so their hands seem to rest on it.
   * Player art is the same stickers as the act 2 podiums (idle, cheer, sad). */
  const VOTER_W = 104;
  function voterSlots(card, n) {                        // up to three per card, filled from the outer edge
    const r = LY.cards[card], a = r[0] + 62, b = r[2] - 62;
    return n <= 1 ? [card === 'O' ? a : b] : n === 2 ? [a, b] : [a, (r[0] + r[2]) / 2, b];
  }
  function layoutVoters(fast, skip) {
    const moves = [];
    for (const card of ['O', 'X']) {
      const list = Object.values(A1.voters).filter(v => v.card === card).sort((p, q) => p.seat - q.seat), xs = voterSlots(card, list.length);
      list.forEach((v, i) => {
        const from = v.x == null || v === skip ? xs[i] : v.x;
        v.x = xs[i];
        if (from === xs[i]) v.box.style.left = (xs[i] - A1.booth.x0) + 'px';
        else moves.push(anim(280, k => { v.box.style.left = (lerp(from, xs[i], k) - A1.booth.x0) + 'px'; }, { fast }));
      });
    }
    return Promise.all(moves);
  }
  function voterUpDown(v, up, fast, ms = 340) {
    return anim(ms, k => { v.box.style.translate = `0 ${((up ? 1 - backOut(k) : k * k) * (v.h + 12)).toFixed(1)}px`; }, { fast, ease: k => k });
  }
  function addVoter(seat, card) {
    const p = seats[seat] && seats[seat].player;
    if (!p || !A1) return null;
    const fk = fanKey(p.fanType), box = el('div', 'abs', A1.booth.n, { top: A1.booth.h + 'px', width: 0, height: 0 }), poses = {};
    let h = 0;
    for (const pose of ['idle', 'cheer', 'sad']) {
      const a = A[`fan_${fk}_${pose}`], ph = VOTER_W * a.h / a.w, i = img(`fan_${fk}_${pose}`, box, VOTER_W);
      Object.assign(i.style, { left: (-VOTER_W / 2) + 'px', top: (-ph + 7) + 'px', display: pose === 'idle' ? '' : 'none' });
      poses[pose] = i; h = Math.max(h, ph);
    }
    const v = A1.voters[seat] = { seat, card, box, poses, h, x: null };
    box.style.translate = `0 ${h + 12}px`;
    return v;
  }
  function voterPose(seat, pose, hop) {
    const v = A1 && A1.voters[seat]; if (!v) return;
    for (const k in v.poses) v.poses[k].style.display = k === pose ? '' : 'none';
    if (hop) anim(420, k => { v.box.style.translate = `0 ${(-20 * Math.sin(Math.PI * k)).toFixed(1)}px`; }, { ease: k => k });
  }
  async function showVoters(choices, fast) {
    const fresh = choices.filter(c => (c.choice === 'O' || c.choice === 'X') && !A1.voters[c.seat]).map(c => addVoter(c.seat, c.choice)).filter(Boolean);
    layoutVoters(true);
    await Promise.all(fresh.map((v, i) => wait(i * 120, fast).then(() => { if (!fast) Sound.cue('pop'); return voterUpDown(v, true, fast); })));
  }
  async function moveVoter(seat, to, fast) {
    const v = A1.voters[seat];
    if (!v) return showVoters([{ seat, choice: to }], fast);
    if (v.card === to) return;
    await voterUpDown(v, false, fast, 240);
    v.card = to;
    await layoutVoters(fast, v);
    await voterUpDown(v, true, fast, 380);
  }
  // Where that player's body is now (where to aim the light): the ledge if standing there, otherwise the scoreboard
  function bodyAt(seat) {
    const vt = A1 && A1.voters[seat];
    return vt && vt.x != null ? [vt.x, LY.ledgeY - vt.h * .45] : seats[seat].view.focus;   // vt.x is in stage coordinates
  }
  function clearVoters(fast) {
    if (!A1) return;
    const old = Object.values(A1.voters); A1.voters = {};
    if (fast) return old.forEach(v => v.box.remove());   // while skipping, the motion may be dropped, so remove at once
    old.forEach(v => voterUpDown(v, false, false, 220).then(() => v.box.remove()));
  }

  /* Speech bubble (KHQS_v11). Placed so the tail tip touches (tx, ty). The tail is at bottom left; if there is no room on the right, it flips.
   * Short lines use the round one, long lines the long one. To remove, find .bubble in fx as now */
  function sayBubble(tx, ty, str, fast, { w, size = 40 } = {}) {
    const long = [...str].length > 4, a = A[long ? 'bubble_l' : 'bubble_s'], W = w || (long ? 360 : 200), H = W * a.h / a.w;
    const flip = tx - a.tip[0] * W + W > 1590;
    const fxr = v => (flip ? 1 - v : v);
    const b = el('div', 'bubble', fx, { left: (tx - fxr(a.tip[0]) * W) + 'px', top: (ty - a.tip[1] * H) + 'px', width: W + 'px', height: H + 'px', transformOrigin: `${(fxr(a.tip[0]) * 100).toFixed(0)}% ${(a.tip[1] * 100).toFixed(0)}%` });
    const i = img(long ? 'bubble_l' : 'bubble_s', b, W);
    if (flip) i.style.transform = 'scaleX(-1)';
    const x0 = Math.min(fxr(a.inner[0]), fxr(a.inner[2])) * W, x1 = Math.max(fxr(a.inner[0]), fxr(a.inner[2])) * W;
    fit(text(b, [x0, a.inner[1] * H, x1, a.inner[3] * H], str, 'han ink', size), size, 16);
    b.dataset.rot = flip ? 3 : -3;
    pop(b, fast);
    return b;
  }
  function badge(v, kind, label, fast) {
    if (!v || !v.badge) return Promise.resolve();
    const b = v.badge;
    return anim(420, k => {
      const sx = Math.abs(Math.cos(Math.PI * k));
      if (k >= .5) { b.className = 'badge ' + kind; b.textContent = label; }
      b.style.opacity = 1;
      b.style.transform = `scaleX(${Math.max(.04, sx).toFixed(3)})`;
    }, { fast }).then(() => { b.style.transform = ''; });
  }
  function pop(e, fast, ms = 380) { return anim(ms, k => { e.style.opacity = clamp(k * 3); e.style.transform = (e.dataset.rot ? `rotate(${e.dataset.rot}deg) ` : '') + `scale(${lerp(.4, 1, backOut(k)).toFixed(3)})`; }, { fast, ease: k => k }); }
  function stampIt(st, str, fast) {
    st.textContent = str;
    if (!fast) Sound.cue('stamp');
    return anim(260, k => { st.style.opacity = k; st.style.transform = `rotate(-7deg) scale(${lerp(1.8, 1, k).toFixed(3)})`; }, { fast, ease: easeOut });
  }
  // Betrayal chance: stamp big in the middle of the stage, show it briefly, then fly it to the stamp spot in the board's corner (the next animation starts while it flies)
  async function slamStamp(st, str, fast) {
    st.textContent = str;
    if (fast) { st.style.opacity = 1; st.style.transform = 'rotate(-7deg)'; return; }
    st.style.opacity = 0;
    const b = el('div', 'stamp big btr', fx); b.textContent = str;
    const W = b.offsetWidth, H = b.offsetHeight, cx = 808, cy = 400;
    Object.assign(b.style, { left: (cx - W / 2) + 'px', top: (cy - H / 2) + 'px' });
    setDark(.45, [cx, cy, 560, 260]);
    Sound.cue('stamp'); Sound.cue('stab'); shock(.9);
    await anim(280, k => { b.style.opacity = clamp(k * 3); b.style.transform = `rotate(-7deg) scale(${lerp(2.4, 1, k).toFixed(3)})`; }, { ease: easeOut });
    await wait(750);
    const tx = st.offsetLeft + st.offsetWidth / 2 - cx, ty = st.offsetTop + st.offsetHeight / 2 - cy, s = st.offsetWidth / W;
    Sound.cue('whoosh');
    anim(420, k => { b.style.transform = `translate(${(tx * k).toFixed(1)}px, ${(ty * k).toFixed(1)}px) rotate(-7deg) scale(${lerp(1, s, k).toFixed(3)})`; })
      .then(() => { b.remove(); st.style.opacity = 1; st.style.transform = 'rotate(-7deg)'; });
  }
  // Show the target's two paths at the bottom of the stage: STAY (current answer) OR? BETRAY (opposite answer). When the decision arrives, the chosen side lights up.
  // The engine sends no deadline for this step (phase deadline null), so 'OR?' blinks instead of a numeric countdown
  function betrayPick(cur, fast) {
    const other = cur === 'O' ? 'X' : 'O';
    const box = el('div', 'btr btr-pick', fx);
    const tag = (cls, word, ch) => { const t = el('div', 'btr-tag ' + cls, box); el('span', '', t).textContent = word; el('span', 'ch ' + ch.toLowerCase(), t).textContent = ch; return t; };
    const stay = tag('stay', 'STAY', cur);
    el('div', 'btr-or', box).textContent = 'OR?';
    const flip = tag('flip', 'BETRAY', other);
    Object.assign(box.style, { left: (808 - box.offsetWidth / 2) + 'px', top: '712px' });
    if (!fast) Sound.cue('flap');
    pop(box, fast);
    return { box, stay, flip };
  }
  function betrayPicked(bp, changed, fast) {
    if (!bp) return;
    const win = changed ? bp.flip : bp.stay, lose = changed ? bp.stay : bp.flip;
    bp.box.querySelector('.btr-or').style.visibility = 'hidden';
    lose.style.opacity = .3; win.classList.add('on');
    anim(300, k => { win.style.transform = `rotate(-3deg) scale(${lerp(1.5, 1.08, k).toFixed(3)})`; }, { fast, ease: easeOut });
    wait(1600, fast).then(() => anim(350, k => { bp.box.style.opacity = 1 - k; }, { fast })).then(() => bp.box.remove());
  }
  function rollScore(v, to, delta, fast) {
    if (!v || !v.score) return Promise.resolve();
    const from = v.value; v.value = to;
    if (delta) {
      v.delta.textContent = (delta > 0 ? '+' : '') + delta;
      v.delta.style.color = delta > 0 ? 'var(--amber)' : '#ff8a8a';
      anim(1200, k => { v.delta.style.opacity = k < .2 ? k * 5 : 1 - (k - .2) / .8; v.delta.style.transform = `translateY(${(-30 * k).toFixed(1)}px)`; }, { fast, ease: k => k });
      if (!fast) Sound.cue('xylo', { f: delta > 0 ? 1046.5 : 330 });
    }
    return anim(900, k => { v.score.textContent = Math.round(lerp(from, to, k)); }, { fast });
  }

  /* ===================== Confetti ===================== */
  const confetti = [];
  function burst(x, y, n, spread = 600) {
    for (let i = 0; i < n; i++) {
      const c = el('div', 'abs', fx, { width: '10px', height: '16px', background: ['#f2c26a', '#c81e2c', '#fff1d6', '#e88a2a'][i % 4], borderRadius: '2px' });
      confetti.push({ c, x: x + (Math.random() - .5) * 60, y, vx: (Math.random() - .5) * spread, vy: -300 - Math.random() * 500, r: Math.random() * 360, vr: (Math.random() - .5) * 720, life: 3 + Math.random() * 2 });
    }
  }

  /* ===================== Protocol ===================== */
  const logEl = document.querySelector('#log ol');
  function logLine(kind, msg, fast) {
    const li = document.createElement('li');
    if (kind === 'label') { li.className = 'label'; li.textContent = '▸ ' + msg; }
    else if (kind === 'timeout') { li.className = 'timeout'; li.textContent = '⏱ ' + msg; }
    else if (kind === 'out') { li.className = (msg.gate ? 'gate' : '') + (fast ? ' fast' : ''); li.textContent = `→ #${msg.sseq} ${msg.type}${msg.gate ? ` [${msg.gate.id}]` : ''}`; }
    else { li.className = 'in'; li.textContent = `← ${msg.type}${msg.data && msg.data.gate ? ' ' + msg.data.gate : ''}${msg.data && msg.data.reason ? ' ' + msg.data.reason : ''}${msg.data && msg.data.skipped ? ' (skipped)' : ''}`; }
    logEl.appendChild(li);
    while (logEl.children.length > 400) logEl.firstChild.remove();
    logEl.parentElement.scrollTop = logEl.parentElement.scrollHeight;
  }
  const engine = new MockEngine({ deliver: (m, o) => onMessage(m, o), log: logLine });
  const send = (type, data) => engine.receive({ proto: 'khqs.stage/1', type, data });
  let lastSseq = null, lastEventAt = 0;

  function onMessage(msg, { fast = false } = {}) {
    if (msg.type !== 'snapshot' && lastSseq != null && msg.sseq !== lastSseq + 1) { send('stage.need_snapshot', { lastSseq, receivedSseq: msg.sseq }); return; }
    lastSseq = msg.sseq;
    lastEventAt = clock;
    if (ghost && ghost.pose === 'sleep') ghost.pose = null;
    const h = HANDLERS[msg.type];
    const done = h ? h(msg.data, fast, msg) : null;
    if (msg.gate) Promise.resolve(done).then(() => send('stage.beat_done', fast ? { gate: msg.gate.id, sseq: msg.sseq, skipped: true } : { gate: msg.gate.id, sseq: msg.sseq }));
  }

  /* ===================== Music question (placeholder: synthetic waltz) ===================== */
  function stopMedia(reason) {
    if (!A2 || !A2.media) return;
    const m = A2.media; A2.media = null;
    clearTimeout(m.timer);
    Sound.loop('waltz', false);
    send('stage.media_ended', { assetId: m.assetId, level: m.level, reason, positionSec: +(m.start + (clock - m.t0) / 1000).toFixed(2) });
  }

  /* ===================== Handlers ===================== */
  const QTOTAL = { 1: 3, 2: 4, 3: 1 };
  function resetRound(fast) {
    for (const s of occupied()) {
      const v = s.view; setPose(v, 'idle'); duck(v, false, fast);
      if (v.badge) { v.badge.style.opacity = 0; v.badge.className = act === 3 ? 'badge ch' : 'badge'; }
      clearVerdict(v);
      if (act === 2) { v.locked = false; v.armed = false; }
    }
    if (A1) { for (const k of ['O', 'X']) Object.assign(A1.cards[k], { win: 0, lose: 0 }); A1.stamp.style.opacity = 0; A1.betray = null; A1.btrSeat = null; clearVoters(fast); }
    if (A2) { A2.ans.style.opacity = 0; A2.stamp.style.opacity = 0; A2.music.style.opacity = 0; }
    fx.querySelectorAll('.bubble, .buzzimg, .btr').forEach(e => e.remove());
  }
  function showQuestion(q, fast) {
    state.question = q;
    const out = rulesOut(fast);                       // if a rule card is hanging, take it down first (at once if fast)
    if (out && !fast) return out.then(() => showQuestion(q, fast));
    if (act === 1) {
      A1.qno.textContent = `Q${q.number}`;
      A1.q.textContent = q.text || '';
      fit(A1.q, 50);
      return anim(500, k => { A1.q.style.opacity = k; A1.q.style.transform = `scale(${lerp(.85, 1, backOut(k)).toFixed(3)})`; }, { fast, ease: k => k });
    }
    if (act === 2) {
      A2.qn.textContent = `Q${q.number}`;
      A2.qs.textContent = `ACT 2 · ${q.indexInAct} / ${QTOTAL[2]}`;
      A2.cat.textContent = q.category ? `— ${q.category} —` : '';
      A2.tag.textContent = q.kind === 'av' ? '♪ MUSIC' : 'BUZZER';
      A2.q.textContent = q.textHidden ? '' : q.text;
      A2.listen.style.opacity = 0;
      if (q.textHidden) return anim(520, k => { A2.listen.style.opacity = clamp(k * 2); A2.listen.style.scale = lerp(.8, 1, backOut(k)).toFixed(3); }, { fast, ease: k => k });
      fit(A2.q, 46);
      A2.music.style.opacity = q.media && q.media.mediaType === 'audio' ? 1 : 0;
      A2.fill.style.width = '0%';
      return anim(500, k => { A2.q.style.opacity = k; }, { fast });
    }
    // act 3: question + four choices
    A3.cat.textContent = ''; A3.big.textContent = '';   // the category moves to the question board header
    A3.qhead.textContent = 'FINAL QUESTION';
    if (q.category) el('i', '', A3.qhead).textContent = `· ${q.category}`;
    fit(A3.qhead, 25, 14);
    A3.q.textContent = q.text || '';
    fit(A3.q, 46, 22);
    (q.choices || []).forEach((c, k) => {
      const box = A3.choices[k]; box.className = 'choice3';
      box.firstChild.textContent = 'ABCD'[k]; box.lastChild.textContent = c;
      fit(box.lastChild, 32, 15);
    });
    return dropBoard(fast);
  }
  // The act 3 question board drops on chains: falls, bounces once, and when it settles the choices light up one by one.
  // While it settles, swap the plate for the one with the board painted in, so the sign behind does not poke out around the board
  async function dropBoard(fast) {
    const b = A3.qb, UP = -(A.qboard3.h + 40);
    if (!fast) b.style.transform = `translateY(${UP}px)`;   // so it does not flash in place on the first frame
    b.style.visibility = 'visible';
    A3.choices.forEach(c => { c.style.opacity = 0; });
    if (!fast) Sound.cue('slide');
    let hit = false;
    await anim(900, k => {
      const fall = clamp(k / .52), rest = clamp((k - .52) / .48);
      const y = k < .52 ? UP * (1 - fall * fall) : -20 * Math.sin(rest * Math.PI) * (1 - rest);
      const sway = 1.6 * Math.sin(k * 11) * (1 - k);
      b.style.transform = k >= 1 ? '' : `translateY(${y.toFixed(1)}px) rotate(${sway.toFixed(2)}deg)`;
      plateQ.style.opacity = clamp((k - .8) / .2);
      if (!hit && k >= .52) { hit = true; if (!fast) { Sound.cue('tak'); light.flash = .35; } }
    }, { fast, ease: k => k });
    await anim(520, k => { A3.choices.forEach((c, j) => { c.style.opacity = clamp(k * 4 - j * .7); c.style.transform = `scale(${lerp(.9, 1, clamp(k * 4 - j * .7)).toFixed(3)})`; }); }, { fast, ease: k => k });
  }
  const STATUS2 = {
    'buzzer.presenting': 'GET READY…', 'buzzer.reading': 'LISTEN · BUZZ OK', 'buzzer.open': 'BUZZERS OPEN!', 'buzzer.media': '♪ PLAYING · BUZZ OK',
    'buzzer.answering': 'ANSWERING', 'buzzer.judging': 'JUDGING…', 'buzzer.hint': 'HINT!', 'buzzer.revealing_answer': 'THE ANSWER', 'buzzer.settling': 'SCORES',
  };
  const RED3 = {
    'final.intro': 'FINAL BET', 'final.category': 'THE CATEGORY', 'final.betting': 'PLACE YOUR BETS…', 'final.question': 'FINAL QUESTION',
    'final.answering': 'LOCK IN YOUR ANSWER…', 'final.revealing_choices': 'ANSWERS REVEALED', 'final.revealing_bets': 'BETS REVEALED!', 'final.suspense': 'AND THE ANSWER IS…',
    'final.revealing_answer': 'THE ANSWER', 'final.settling': 'SCORES', 'finale.curtain': 'THANK YOU!',
  };

  const TIMER3 = {
    'final.intro': ['GET READY', '', '--:--'], 'final.category': ['GET READY', '', '--:--'],
    'final.betting': ['BETS CLOSE IN', 'CHOOSE\nWISELY!', '--:--'],
    'final.question': ['BETS LOCKED', 'READ\nCAREFULLY!', '--:--'],
    'final.answering': ['ANSWERS CLOSE IN', 'PICK\nYOUR ANSWER!', '--:--'],
    over: ["TIME'S UP!", 'NO MORE\nCHANGES!', '00:00'],
  };

  const HANDLERS = {
    snapshot(d) {
      if (opening) { opening.dispose(); opening = null; }
      // Like the bats of NEW SHOW, a transition (span) running to cover this moment is left to finish
      const spanning = transNow && transNow.span;
      clearFinale(); if (!spanning) clearTransition(); finaleBusy = Promise.resolve();
      for (const tw of [...tweens]) if (!tw.keep) tweens.delete(tw);
      Sound.loop('roll', false); Sound.loop('waltz', false); Sound.loop('clockTick', false); Sound.loop('crowdMurmur', false); thinkTick = false; stopBetMusic(.3);   // so no in-show BGM (betrayal chance, betting) lingers. Transition jingles keep playing into the post-transition snapshot (act chaining in preview)
      d.seats.forEach(s => { seats[s.seat].player = s.status === 'occupied' ? s.player : null; });
      buildAct(Math.max(1, Math.min(3, d.game.act || 1)));
      state.phase = d.game.phase; state.deadline = d.game.deadline;
      resetRound(true);
      if (d.question) showQuestion(d.question, true);
      const r = d.round;
      if (r && r.kind === 'ox') {
        r.submitted.forEach(i => duck(viewOf(i), true, true));
        if (r.revealedChoices && r.revealedChoices.length) { r.revealedChoices.forEach(c => { const v = viewOf(c.seat); if (v && v.badge) v.badge.style.opacity = 0; }); showVoters(r.revealedChoices, true); }
      }
      if (r && r.kind === 'final') {
        r.betPlaced.forEach(i => betLocked(viewOf(i), true));
        (r.revealedChoices || []).forEach(c => badge(viewOf(c.seat), 'ch', c.choice || '-', true));
        (r.revealedBets || []).forEach(b => betShow(viewOf(b.seat), b, true));
      }
      if (d.revealedAnswer) markAnswer(d.revealedAnswer, null, true);
      d.seats.forEach(s => { if (s.player && !s.player.connected) { const v = viewOf(s.seat); if (v) v.disconnected = true; } });
      setDark(0, null, true);
      HANDLERS['phase.changed']({ phase: d.game.phase, deadline: d.game.deadline });
      if (d.game.phase === 'lobby') { opening = createOpening(); opening.lobby(); }
      if (d.game.phase === 'ended' || d.game.phase === 'finale.curtain') drawFinale(standingsFromSeats(d), true);
      if (d.openGate) send('stage.beat_done', { gate: d.openGate.id, sseq: Number(d.openGate.id.slice(2)), skipped: true });
      if (snapWait) { const f = snapWait; snapWait = null; f(); }
    },
    'seat.joined'(d) { seats[d.seat].player = d.player; seats[d.seat].view = null; buildAct(act); Sound.cue('pop'); if (opening) opening.seatChanged(d.seat); },
    'seat.left'(d) { seats[d.seat].player = null; buildAct(act); if (opening) opening.seatChanged(d.seat); },
    'show.opening'(d, fast) { if (!opening) opening = createOpening(); return opening.run(fast); },
    'seat.connection'(d) { const v = viewOf(d.seat); if (v) v.disconnected = !d.connected; if (seats[d.seat].player) seats[d.seat].player.connected = d.connected; if (opening) opening.connChanged(d.seat); },
    'phase.changed'(d) {
      state.phase = d.phase; state.deadline = d.deadline;
      document.getElementById('phase').textContent = d.phase;
      // Thinking-time tick (user request 2026-11-17): while picking in act 1 OX and while writing in act 3. If the deadline has passed when it ends: buzzer (timeUp)
      if (THINK_PHASES.has(d.phase)) { if (!thinkTick) Sound.loop('clockTick', true); thinkTick = d.deadline || 0; }
      else if (thinkTick !== false) { if (thinkTick && Date.now() >= thinkTick - 400) Sound.cue('timeUp'); thinkTick = false; Sound.loop('clockTick', false); }
      // Act 3 betting BGM (user request 2026-11-17): start when betting begins, stop when bets lock (final.bets_locked) or another step begins
      if (d.phase === 'final.betting') { if (!betBgm) startBetMusic(); }
      else if (betBgm) stopBetMusic();
      if (A2 && STATUS2[d.phase]) { A2.st.textContent = STATUS2[d.phase]; fit(A2.st, 24); }
      if (A3 && RED3[d.phase]) { A3.red.textContent = RED3[d.phase]; fit(A3.red, 22); }
      if (A3) {
        // Clock board: per step [top line, bottom line, number shown when the clock stops]. Keeps "BETS CLOSE IN" from lingering after time is up
        const t = TIMER3[d.phase] || (/^final\.|^finale\.|^ended$/.test(d.phase) ? TIMER3.over : null);
        if (t) { A3.tTop.textContent = '⌛\n' + t[0]; A3.tFoot.textContent = t[1]; A3.idleClock = t[2]; }
      }
    },
    'mc.status'(d) { if (ghost) ghost.status = d.status; },

    async 'act.started'(d, fast) {
      if (d.assets && d.assets.length) send('stage.media_ready', { assetIds: d.assets.map(a => a.assetId) });
      // On an act change, cover with a transition and change the stage behind it (the engine waits 8 s: transition ~3–4 s + the cheer below)
      // The transition jingle (2026-11-17) starts with the transition so its final bang lands as the new stage is revealed.
      // Act 1 has no transition, so one synthetic stab (user 2026-11-25: an actStart jingle right after the opening intro jingle felt awkward). The actStart file stays for the sound lab
      if (d.act !== act) await actTransition(ACT_TRANSITION[d.act], async () => { buildAct(d.act); }, fast);
      if (d.act === 1 && !fast) Sound.cue('stab');
      if (!fast) { setTimeout(() => Sound.cue('cheer'), 300); applause(2); light.flash = 1; }
      rulesNudge(fast);
      if (d.act === 3 && !fast) burst(800, 160, 60, 900);
      ghostPose('present', 2600);
      await wait(d.act === 3 ? 2600 : 1600, fast);
    },
    async 'question.presented'(d, fast) {
      resetRound(fast);
      ghostPose('present', 1500);
      if (!fast) Sound.cue('flap');
      await showQuestion(d.question, fast);
    },
    async 'question.text_revealed'(d, fast) {
      await anim(220, k => { A2.listen.style.opacity = 1 - k; }, { fast });
      A2.q.textContent = d.text; fit(A2.q, 46);
      if (!fast) Sound.cue('flap');
      await anim(400, k => { A2.q.style.opacity = k; }, { fast });
    },

    /* ---- Act 1 ---- */
    'ox.submitted'(d, fast) { duck(viewOf(d.seat), true, fast); },   // the character ducks and the picket pops up (instead of a '?' badge)
    async 'ox.choices_revealed'(d, fast) {
      ghostPose('worried', 900);
      if (!fast) { Sound.cue('rollComedy'); await wait(900); }   // act 1 OX reveal: short comedy drumroll (it has its own ending, so no crash)
      ghostPose('surprised', 1200);
      await showVoters(d.choices, fast);
      if (!fast) Sound.cue('murmurs');
      await wait(600, fast);
    },
    'ox.unanimous'(d, fast) { stampIt(A1.stamp, `UNANIMOUS ×${d.streak}`, fast); ghostPose('wink', 1600); },
    async 'betrayal.offered'(d, fast) {
      A1.btrSeat = d.seat;                                // the seat that got the betrayal chance on this question (wah-wah if wrong)
      await slamStamp(A1.stamp, 'BETRAYAL CHANCE', fast);
      const order = d.selection === 'tied_random' && d.tiedSeats.length > 1 ? d.tiedSeats : [d.seat];
      const spotOn = (i, f) => { const p = bodyAt(i); setDark(.62, [p[0], p[1], 190, 170], f); };
      if (!fast) {
        const hops = 9 + order.indexOf(d.seat);
        for (let n = 0; n <= hops; n++) { spotOn(n === hops ? d.seat : order[n % order.length]); Sound.cue('tick'); await wait(90 + n * n * 4); }
        Sound.cue('ding');
        Sound.bgm('betrayal', { fade: .8 });             // betrayal chance BGM: only while choosing
      } else spotOn(d.seat, true);
      const vt = A1.voters[d.seat];
      if (vt) anim(800, k => { vt.box.style.rotate = `${(Math.sin(k * 32) * 5 * (1 - k)).toFixed(1)}deg`; }, { fast, ease: k => k }).then(() => { vt.box.style.rotate = ''; });
      else { const v = viewOf(d.seat); if (v) v.shake = clock; }
      if (ghost) ghost.focus = d.seat;
      ghostPose('peek', 0);
      A1.betray = betrayPick(d.currentChoice, fast);
      await wait(800, fast);
    },
    'betrayal.listening'(d, fast) {
      const v = viewOf(d.seat); if (!v) return;
      const vt = A1.voters[d.seat];
      if (vt) { sayBubble(vt.x + 34,LY.ledgeY - vt.h + 30, '…', fast, { w: 124, size: 44 }); vt.talking = true; }   // the body standing on the ledge speaks
      else { const F = LY.slots[d.seat].frame; sayBubble(F[2] - 14, F[1] + 66, '…', fast, { w: 124, size: 44 }); v.talking = true; } // top right of the scoreboard
    },
    async 'betrayal.decided'(d, fast) {
      Sound.bgm(null, { fade: .5 });
      const v = viewOf(d.seat);
      fx.querySelectorAll('.bubble').forEach(e => e.remove());
      if (v) v.talking = false;
      if (A1.voters[d.seat]) { A1.voters[d.seat].talking = false; A1.voters[d.seat].box.style.rotate = ''; }
      if (ghost) ghost.focus = null;
      if (d.changed) ghostPose('angry', 1800); else ghostPose(null);
      if (A1.betray) { betrayPicked(A1.betray, d.changed, fast); A1.betray = null; }
      // Move the light toward the cards so the crossing does not vanish in the dark
      const C = LY.cards;
      setDark(.5, [(C.O[0] + C.X[2]) / 2, (C.O[1] + LY.ledgeY) / 2 + 20, (C.X[2] - C.O[0]) * .6, 190], fast);
      const voter = A1.voters[d.seat];
      if (d.changed) { if (!fast) { Sound.cue('whoosh'); Sound.cue('stamp'); } await moveVoter(d.seat, d.to, fast); if (!fast) { Sound.cue('gasp'); shock(1.4); } }
      else if (voter) { if (!fast) Sound.cue('murmurs'); await anim(700, k => { voter.box.style.rotate = `${(9 * Math.sin(k * Math.PI * 4) * (1 - k)).toFixed(1)}deg`; }, { fast, ease: k => k }); voter.box.style.rotate = ''; }   // shakes the head
      setDark(0, null, fast);
      await wait(400, fast);
    },

    /* ---- Shared: suspense → reveal → settle ---- */
    'answer.suspense'(d, fast) {
      const r = act === 1 ? LY.board : act === 2 ? LY.board : LY.inner;
      setDark(.55, [cx(r), cy(r), (r[2] - r[0]) * .62, (r[3] - r[1]) * 1.1], fast);
      light.chase = 1;
      ghostPose('worried', 0);
      if (!fast) Sound.loop('roll', true);
    },
    async 'answer.revealed'(d, fast) {
      Sound.loop('roll', false);
      light.chase = 0;
      setDark(0, null, fast);
      const anyRight = d.results.some(r => r.correct), anyWrong = d.results.some(r => !r.correct);
      // Act 2 (user 2026-11-27: the MC's answer explanation had only a drumroll): the roll ends on the comedy 'ba-dum-tss' (rollComedy) as the
      // 'THE ANSWER IS…' bubble appears, whether or not someone was right. Act 1 keeps its cymbal; act 3 has none (2026-11-25)
      if (!fast) { if (act === 1) Sound.cue('crash'); else if (act === 2) Sound.cue('rollComedy'); light.flash = 1; }
      markAnswer(d.answer, d, fast);
      if (act === 2) ghostPose('present', 3200); // the moment it holds out the answer bubble
      else ghostPose(anyRight ? (anyWrong ? 'wink' : 'happy') : 'sad', 2400);
      // In act 2 the expression was already set at judging. Only acts 1 and 3 react here
      if (act !== 2) for (const r of d.results) { const v = viewOf(r.seat); if (v) { setPose(v, r.correct ? 'cheer' : 'sad'); v.hop = clock; } if (act === 1) voterPose(r.seat, r.correct ? 'cheer' : 'sad', r.correct && !fast); }
      if (!fast && act === 2) { if (!anyRight) { setTimeout(() => { Sound.cue('sad'); Sound.cue('boo'); }, 380); shock(1.6); } }   // act 2: wah-wah only when nobody got it, after the 'tss'
      else if (!fast) {
        // Act 1 OX (user decision 2026-11-17): if anyone is right, 'ding-dang-dong' (correct). Wah-wah only when all are wrong or the betrayal-chance player is wrong
        const btrWrong = act === 1 && A1 && A1.btrSeat != null && d.results.some(r => r.seat === A1.btrSeat && !r.correct);
        if (anyRight) {
          Sound.cue('correct');   // act 1 OX and act 3 final correct: ding-dang-dong (file). Act 3 used a synthetic ding before (2026-11-25)
          correctCheer();
          applause(2.2); burst(800, 330, 30);
        }
        if (anyWrong && !anyRight) { Sound.cue('sad'); Sound.cue('boo'); shock(1.6); }
        else if (anyWrong && (act !== 1 || btrWrong)) setTimeout(() => Sound.cue('sad'), 500);
      }
      await wait(2200, fast);
    },
    async 'score.settled'(d, fast) {
      d.deltas.forEach(x => { const p = seats[x.seat] && seats[x.seat].player; if (p) { p.score = x.score; p.rank = x.rank; } }); // keep scores when the act changes and seats are redrawn
      // Act 1: the player on the ledge goes down, pops back up on the scoreboard (same cheer/sad face), then the score rises
      if (act === 1) { clearVoters(fast); await Promise.all(occupied().map(s => duck(s.view, false, fast))); }
      // When act 3 (the last question) ends and scores start to rise, the crowd murmurs (user decision 2026-11-25: instead of BGM). Through the curtain, sign and lower-rank podiums
      // It swells from 0.4× to full volume over 8 s and stops dead just before the winner drumroll (rollTada) (finalePodiums)
      if (act === 3 && !fast && !finale) Sound.loop('crowdMurmur', true, { swell: [.4, 8] });
      await Promise.all(d.deltas.map(x => rollScore(viewOf(x.seat), x.score, x.delta, fast)));
      if (d.leadChange) ghostPose('wink', 1600);
      if (d.leadChange && !fast) { Sound.cue('twist'); applause(1.6); }   // comeback: synthetic 'twist' (user 2026-11-25: both the Gemini jingle and the crowd gasp felt off). The leadChange file stays for the sound lab
      await wait(600, fast);
      if (act !== 3) for (const s of occupied()) setPose(s.view, 'idle');
      // Act 2: the correct-answer ring stays while the answer bubble shows and is removed after settlement
      if (act === 2) for (const s of occupied()) if (s.view.verdict && s.view.verdict.correct) {
        const b = s.view.verdict.box;
        await anim(300, k => { b.style.opacity = 1 - k; }, { fast });
        clearVerdict(s.view);
      }
    },

    /* ---- Act 2 ---- */
    'buzzer.armed'(d) { for (const s of occupied()) s.view.armed = !s.view.locked; },
    'buzzer.pressed'(d, fast) {
      if (d.mediaInterrupted) stopMedia('interrupted');
      for (const s of occupied()) s.view.armed = false;
      const v = viewOf(d.seat); if (!v) return;
      v.buzzed = clock; v.hop = clock;
      setDark(.66, [v.focus[0], v.focus[1], 170, 200], fast);
      if (ghost) { ghost.status = 'idle'; ghost.focus = d.seat; }
      ghostPose('surprised', 1100);
      if (!fast) { Sound.cue('buzz'); light.flash = .6; }
      const bz = el('div', 'abs buzzimg', fx, { left: (v.focus[0] - 230) + 'px', top: (v.focus[1] - 120) + 'px', width: '200px', height: (200 * A.buzz.h / A.buzz.w) + 'px' });
      bz.dataset.rot = -10; img('buzz', bz, 200);
      text(bz, [14, 10, 176, 70], 'BUZZ!', 'slab', 36, { color: 'var(--red)', transform: 'rotate(-10deg)' });
      pop(bz, fast, 300);
    },
    'buzzer.answer_heard'(d, fast) {
      const v = viewOf(d.seat); if (!v) return;
      fx.querySelectorAll('.bubble').forEach(e => e.remove());
      sayBubble(v.focus[0] + 62, v.focus[1] - 34, d.text, fast);
    },
    async 'buzzer.judged'(d, fast) {
      const v = viewOf(d.seat);
      fx.querySelectorAll('.buzzimg, .bubble').forEach(e => e.remove()); // the verdict graphic appears where the answer bubble was
      ghostPose(d.correct ? 'happy' : 'tease', 1900);
      if (v) {
        setPose(v, d.correct ? 'cheer' : 'sad'); v.hop = clock;
        showVerdict(v, d.correct, fast);
        if (d.correct && !fast) burst(v.cx, v.top - 150, 26, 520);
        if (!fast) { if (d.correct) { Sound.cue('dingdong'); correctCheer(); applause(1.6); } else { Sound.cue('sad'); Sound.cue('aww'); shock(1.2); } }   // Act 2 (user decision 2026-11-17): correct = 'ding-dong', wrong = wah-wah + sad. The buzzer file plays on the press (buzz). 2026-11-25: crowd cheer added on correct
      }
      d.lockedOut.forEach(i => { const w = viewOf(i); if (w) w.locked = true; });
      await wait(1300, fast);
      if (v && !d.correct) setPose(v, 'sad');
      if (v && !d.correct) await stickVerdict(v, fast); // a wrong verdict shrinks and sticks to the podium like a stamp
      setDark(0, null, fast);
      if (ghost) ghost.focus = null;
    },
    'av.play'(d, fast) {
      if (fast) { send('stage.media_ended', { assetId: d.assetId, level: d.level, reason: 'ended', positionSec: d.endSec }); return; }
      stopMedia('interrupted');
      const dur = (d.endSec - d.startSec) * 1000;
      A2.music.style.opacity = 1;
      ghostPose('think', dur); // listening-along face. Turns to surprise when someone buzzes
      A2.media = { assetId: d.assetId, level: d.level, start: d.startSec, t0: clock, dur, timer: setTimeout(() => stopMedia('ended'), dur / speed) };
      Sound.loop('waltz', true);
    },
    async 'av.hint'(d, fast) {
      stampIt(A2.stamp, `HINT ${d.level} · LONGER!`, fast);
      ghostPose('present', 1200);
      if (!fast) Sound.cue('ding');
      await wait(900, fast);
    },

    /* ---- Act 3 ---- */
    async 'final.category'(d, fast) {
      A3.cat.textContent = 'CATEGORY';
      A3.big.textContent = d.category;
      fit(A3.big, 44);
      ghostPose('present', 1800);
      if (!fast) { Sound.cue('stab'); light.flash = .6; }
      await anim(600, k => { A3.big.style.opacity = k; A3.big.style.transform = `scale(${lerp(.6, 1, backOut(k)).toFixed(3)})`; }, { fast, ease: k => k });
      await wait(1200, fast);
    },
    'final.bet_placed'(d, fast) { betLocked(viewOf(d.seat), fast); },
    'final.bets_locked'(d, fast) { if (betBgm) stopBetMusic(); ghostPose('tease', 1400); if (!fast) { Sound.cue('crash'); light.flash = .4; } },
    'final.answer_placed'(d, fast) { const v = viewOf(d.seat); if (!v) return; v.badge.className = 'badge'; v.badge.textContent = '?'; pop(v.badge, fast); if (!fast) Sound.cue('pop'); },
    'final.answers_locked'(d, fast) { if (!fast) Sound.cue('stamp'); },
    async 'final.choices_revealed'(d, fast) {
      ghostPose('worried', 900);
      if (!fast) { Sound.loop('roll', true, { dur: .9 }); await wait(900); Sound.loop('roll', false); Sound.cue('crash'); }
      ghostPose('surprised', 1000);
      await Promise.all(d.choices.map(c => badge(viewOf(c.seat), 'ch', c.choice || '-', fast)));
      // Make the reveal readable from the sofa: one big pulse of every pick, then hold before the bets.
      if (!fast) await Promise.all(d.choices.map(c => { const v = viewOf(c.seat); return v && v.badge ? anim(700, k => { v.badge.style.transform = `scale(${(1 + .7 * Math.sin(Math.PI * k)).toFixed(3)})`; }).then(() => { v.badge.style.transform = ''; }) : null; }));
      await wait(1500, fast);
    },
    async 'final.bet_revealed'(d, fast) {
      const v = viewOf(d.seat); if (!v) return;
      setDark(.6, [v.focus[0], v.focus[1], 170, 150], fast);
      ghostPose('worried', 1100);
      if (!fast) { Sound.loop('roll', true, { dur: 1.1 }); await wait(1100); Sound.loop('roll', false); Sound.cue(d.allIn ? 'fanfare' : 'crash'); }
      ghostPose(d.allIn ? 'surprised' : null, 2000);
      await betShow(v, d, fast);
      if (d.allIn && !fast) { shock(1.8); Sound.cue('gasp'); burst(v.focus[0], v.focus[1] - 60, 40, 500); }   // all in: the crowd gasps (look + gasp sound, user request 2026-11-17)
      await wait(700, fast);
      setDark(0, null, fast);
    },
    // Winner announcement: curtain closes → AND THE WINNER IS… → curtain opens and the podiums rise. The host's announcement line comes after this gate closes
    'finale.winner'(d, fast) {
      finaleBusy = finaleReveal(standingsNow(d), fast);
      // The trophy and THE END appear right after the podiums (1.2 s after the crown) without waiting for the engine's game.ended (user request 2026-11-17: it came too late).
      // The gate (this promise) covers only up to the podiums, so the host's announcement still comes as before. Only the NEW SHOW button waits for the engine's end signal (finaleDone)
      finaleBusy.then(() => wait(1200, fast)).then(() => { if (finale && finale.part && !finale.ended) finaleEnding(fast); });
      return finaleBusy;
    },
    'game.ended'(d, fast) {
      if (!finale) setDark(.7, null, fast);
      else { finale.gameOver = true; if (finale.part && !finale.ended) finaleEnding(fast); else if (finale.endDone) finaleDone(fast); }
      ghostPose('wink', 4000);
    },
    // Results screen (khqs.stage/1 rev 1.1): if the podiums already stand, only finish up (trophy, THE END)
    async 'finale.results'(d, fast) {
      await finaleBusy;
      if (finale && finale.part) { finale.gameOver = true; return finale.ended ? (finale.endDone ? finaleDone(fast) : null) : finaleEnding(fast); }
      return drawFinale(d, fast);
    },
  };

  /* ===================== Finale: podiums in front of the closed curtain =====================
   * Art is made by tools/build_finale.py (KHQS_v9). Players use the current stickers (hands on the chin, so they look like faces peeking over the podium).
   * Way in: on finale.winner the curtain (transition curtain) closes and opens onto the podiums; finale.results (or game.ended) finishes it.
   * Order: the stage changes → results on the sign → podiums rise from the floor, lowest rank first → crown, trophy and confetti for first place → THE END sign.
   * d = { mode, tie, standings: [{ rank, name, score, fanType, winner }] } (finale.results, or standingsFromSeats) */
  let finale = null;
  function clearFinale() {
    if (!finale) return;
    finale.box.remove(); if (finale.btn) finale.btn.remove();
    finale = null;
    plateF.style.opacity = 0; ov.style.opacity = '';
  }
  function standingsFromSeats(d) {
    const st = d.seats.filter(s => s.player).map(s => ({ seat: s.seat, playerId: s.player.id, name: s.player.name, fanType: s.player.fanType, score: s.player.score, rank: s.player.rank, winner: s.player.rank === 1 }))
      .sort((a, b) => a.rank - b.rank || a.seat - b.seat);
    const winners = st.filter(x => x.winner).map(x => x.seat);
    return { mode: d.game.mode, winners, tie: winners.length > 1, standings: st };
  }
  const FIN_FLOOR = 742;                                                                // floor line the podiums rise from
  let finaleBusy = Promise.resolve();                                                   // when the winner announcement (finale.winner) ends. The results screen waits for it
  function standingsNow(d) {                                                            // build standings from finale.winner scores and the current seat occupants
    const st = d.finalScores.filter(x => seats[x.seat] && seats[x.seat].player).map(x => { const pl = seats[x.seat].player; return { seat: x.seat, playerId: pl.id, name: pl.name, fanType: pl.fanType, score: x.score, rank: x.rank, winner: d.winners.includes(x.seat) }; })
      .sort((a, b) => a.rank - b.rank || a.seat - b.seat);
    return { mode: st.length > 1 ? 'competitive' : 'solo', winners: d.winners, tie: d.tie, standings: st };
  }
  async function drawFinale(d, fast) {                                                  // all at once (no curtain): skip, snapshot, or a missed announcement
    await finaleStage(d, fast);
    await finalePodiums(fast);
    if (finale) finale.gameOver = true;               // drawing the results screen directly means the show is already over
    await finaleEnding(fast);
  }
  /* Winner announcement: lights dim and the curtain closes → behind it the stage becomes the finale → sign and drumroll, thumps behind the curtain → curtain opens and the podiums rise */
  async function finaleReveal(st, fast) {
    if (!fast) {
      ghostPose('worried', 1600);
      for (const sv of occupied()) setPose(sv.view, 'idle');
      setDark(.5, null);
      await wait(400);
    }
    await runTransition('curtain', async t => {
      await finaleStage(st, fast, true);
      if (!t) { Sound.loop('crowdMurmur', false); return; }
      await t.dropSign(st.mode === 'solo' ? 'sign_score' : 'sign_winner');
      // The drumroll plays only once, right before the winner is named at the ceremony (user request 2026-11-25): in front of the sign, only thumps behind the curtain over the BGM
      await wait(600); t.thump(-1); await wait(650); t.thump(1); await wait(550);
      await t.liftSign();
    }, fast);
    await finalePodiums(fast);
  }
  // The stage changes: act 3's boards go away and the closed-curtain stage appears. cut = swap at once with no crossfade (when a transition is covering)
  async function finaleStage(d, fast, cut) {
    clearFinale();
    const box = el('div', 'abs', finL, { left: 0, top: 0, width: '1600px', height: '900px' });
    finale = { box, btn: null, d, part: null, ended: false };
    Sound.loop('roll', false);
    if (!cut || fast) Sound.loop('crowdMurmur', false);   // crowd murmur: stop it here when drawing directly without the curtain. With the curtain it stops just before the winner drumroll (finalePodiums)
    setDark(0, null, fast || cut);
    ghostPose('present', 2400);
    await anim(700, k => { plateF.style.opacity = k; ov.style.opacity = 1 - k; }, { fast: fast || cut });
    if (!finale || finale.box !== box) return;
    ov.style.opacity = 0;                             // act 3's boards and seats are hidden, not removed (the question board uses visibility itself, so hide with opacity)
    if (ghost && ghost.front && ghost.front.firstChild) ghost.front.firstChild.src = A.frontF.src;
  }
  // Results on the sign, podiums rise lowest rank first, the crown settles on first place
  async function finalePodiums(fast) {
    if (!finale || finale.part) return;
    const { box, d } = finale;
    const FLOOR = FIN_FLOOR, PW = { 1: 232, 2: 204, 3: 200 }, LEDGE = { 1: .09, 2: 0, 3: 0 };   // floor line, podium widths, how far the top surface sits below the art's top
    const solo = d.mode === 'solo', n = Math.min(3, d.standings.length);
    const XS = n === 1 ? [800] : n === 2 ? [680, 920] : [800, 556, 1044];                 // first in the middle, second left, third right
    const mine = () => finale && finale.box === box;                                    // stop if the scene changes midway

    // results on the sign
    const title = text(box, [522, 80, 1083, 176], solo ? 'SHOW COMPLETE!' : d.tie ? "IT'S A TIE!" : 'WINNER', 'slab', 90, { color: '#3a2a20', letterSpacing: '4px', opacity: 0 });
    fit(title, 90, 40);
    const sub = text(box, [540, 174, 1065, 214], '★  KIRO HORROR QUIZ SHOW  ★', 'slab', 23, { color: 'var(--red)', opacity: 0 });
    if (!fast) { Sound.cue('stab'); light.flash = .5; }
    await anim(520, k => { title.style.opacity = sub.style.opacity = clamp(k * 2); title.style.transform = `scale(${lerp(.6, 1, backOut(k)).toFixed(3)})`; }, { fast, ease: k => k });

    // podiums: clipped below the floor line so they seem to rise out of the floor
    const pit = el('div', 'abs', box, { left: 0, top: 0, width: '1600px', height: FLOOR + 'px', overflow: 'hidden' });
    const cols = d.standings.slice(0, n).map((s, k) => {
      const rank = clamp(s.rank || k + 1, 1, 3), a = A[`fin_pod${rank}`], w = PW[rank], h = w * a.h / a.w, x = XS[k];
      const g = el('div', 'abs', pit, { left: x + 'px', top: FLOOR + 'px', width: 0, height: 0 });
      const fk = `fan_${fanKey(s.fanType)}_${s.winner ? 'cheer' : 'idle'}`, fw = 170, fh = fw * A[fk].h / A[fk].w, top = -h + h * LEDGE[rank];
      // player and crown in one group (pivot at the feet): the winner dances as a group (finaleDance in render)
      const body = el('div', 'abs', g, { left: 0, top: 0, width: 0, height: 0, transformOrigin: `0 ${top.toFixed(0)}px` });
      Object.assign(img(fk, body, fw).style, { left: (-fw / 2) + 'px', top: (top - fh + 9) + 'px' });
      Object.assign(img(`fin_pod${rank}`, g, w).style, { left: (-w / 2) + 'px', top: (-h) + 'px' });
      const q = a.plaque, px = -w / 2 + q[0] * w, py = -h + q[1] * h, pw = (q[2] - q[0]) * w, ph = (q[3] - q[1]) * h;
      const nm = text(g, [px + 10, py + 6, px + pw - 10, py + ph * .5], s.name, 'han ink', 34); fit(nm, 34, 16);
      text(g, [px + 10, py + ph * .46, px + pw - 10, py + ph - 6], String(s.score), 'slab', 38, { color: 'var(--red)' });
      let crown = null;
      if (s.winner && !solo) {
        const cw = 92, ch = cw * A.fin_crown.h / A.fin_crown.w;
        crown = img('fin_crown', body, cw); Object.assign(crown.style, { left: (-cw / 2) + 'px', top: (top - fh - ch * .5) + 'px', opacity: 0, transformOrigin: '50% 100%' });
        const rw = 50, ros = img('fin_rosette', g, rw); Object.assign(ros.style, { left: (px + pw - rw * .62) + 'px', top: (py - rw * .5) + 'px', rotate: '12deg' });
      }
      g.style.translate = `0 ${(h + fh + 80).toFixed(0)}px`;
      return { g, x, w, h, rise: h + fh + 80, s, crown, body };
    });
    for (let k = cols.length - 1; k >= 0; k--) {       // lowest rank first
      const c = cols[k], first = k === 0 || c.s.winner;
      const tada = first && !fast && cols.length > 1;                 // winner: drumroll + ta-da in one file; rises on the 'ta-da' at 2.0 s
      if (first) Sound.loop('crowdMurmur', false);                    // the crowd murmur stops dead just before the winner drumroll (ta-da if alone)
      if (tada) { Sound.cue('rollTada'); await wait(2000); }
      if (!mine()) return;
      if (!fast && !tada) Sound.cue(first ? 'fanfare' : 'pop');
      await anim(first ? 700 : 520, q => { c.g.style.translate = `0 ${((1 - backOut(q)) * c.rise).toFixed(1)}px`; }, { fast, ease: q => q });
      // When first place rises, the winner music (BGM 'winner' = The Tent Circus) plays to the end of the results screen. The grand orchestra (finaleMusic) was too big for the show's mood and was removed (user request 2026-11-25)
      if (first && !fast) { light.flash = .6; applause(5); Sound.bgm('winner', { fade: .2 }); setTimeout(() => Sound.cue('applause'), 200); burst(c.x, FLOOR - c.h - 120, 70, 700); }
      await wait(first ? 300 : 180, fast);
    }
    if (!mine()) return;

    // the crown settles; the trophy and bouquet are placed
    ghostPose(solo || !d.tie ? 'happy' : 'surprised', 0);
    const crowns = cols.filter(c => c.crown);
    if (crowns.length && !fast) Sound.cue('ding');
    await anim(480, q => { crowns.forEach(c => { c.crown.style.opacity = clamp(q * 3); c.crown.style.transform = `translateY(${((1 - backOut(q)) * -150).toFixed(1)}px) rotate(${lerp(-18, -6, q).toFixed(1)}deg)`; }); }, { fast, ease: q => q });
    if (mine()) finale.part = { cols, pit, title, sub, t0: clock };
  }
  // Finish: trophy and bouquet placed, THE END sign drops, new-game button appears
  async function finaleEnding(fast) {
    if (!finale || !finale.part || finale.ended) return;
    finale.ended = true;
    const { box, d } = finale, { cols, pit, title, sub } = finale.part, FLOOR = FIN_FLOOR;
    const mine = () => finale && finale.box === box;
    const left = Math.min(...cols.map(c => c.x - c.w / 2)), right = Math.max(...cols.map(c => c.x + c.w / 2));
    const winLeft = cols.length === 2 && !d.tie;       // in a two-player show first place stands on the left: the trophy goes there too
    const tw = 112, th = tw * A.fin_trophy.h / A.fin_trophy.w, bw = 84, bh = bw * A.fin_bouquet.h / A.fin_bouquet.w;
    const tx = winLeft ? left - 72 : right + 72, bx = winLeft ? right + 58 : left - 58;
    const trophy = img('fin_trophy', pit, tw); Object.assign(trophy.style, { left: (tx - tw / 2) + 'px', top: (FLOOR - th + 2) + 'px', opacity: 0, transformOrigin: '50% 100%' });
    const bouquet = img('fin_bouquet', pit, bw); Object.assign(bouquet.style, { left: (bx - bw / 2) + 'px', top: (FLOOR - bh + 4) + 'px', opacity: 0, transformOrigin: '50% 100%', rotate: winLeft ? '9deg' : '-9deg' });
    if (!fast) { Sound.cue('pop'); burst(800, 40, 110, 1500); }
    await anim(460, q => { for (const e of [trophy, bouquet]) { e.style.opacity = clamp(q * 3); e.style.transform = `scale(${lerp(.3, 1, backOut(q)).toFixed(3)})`; } }, { fast, ease: q => q });
    await wait(1800, fast);                             // from the trophy to THE END (was 3.2 s, shortened on user request)
    if (!mine()) return;

    // THE END: drops in front of the sign and closes the show
    const ew = 440, eh = ew * A.fin_theend.h / A.fin_theend.w;
    const end = img('fin_theend', box, ew); Object.assign(end.style, { left: (800 - ew / 2) + 'px', top: '-34px', transformOrigin: '50% 0' });
    if (!fast) Sound.cue('slide');
    let hit = false;
    await anim(900, k => {
      const fall = clamp(k / .55), rest = clamp((k - .55) / .45);
      const y = k < .55 ? -(eh + 40) * (1 - fall * fall) : -16 * Math.sin(rest * Math.PI) * (1 - rest);
      end.style.transform = k >= 1 ? '' : `translateY(${y.toFixed(1)}px) rotate(${(2 * Math.sin(k * 10) * (1 - k)).toFixed(2)}deg)`;
      title.style.opacity = sub.style.opacity = 1 - clamp((k - .2) / .3);
      if (!hit && k >= .55) { hit = true; if (!fast) { Sound.cue('tak'); light.flash = .3; } }
    }, { fast, ease: k => k });
    if (!mine()) return;
    finale.endDone = true;
    if (finale.gameOver) await finaleDone(fast);         // at once if the engine already signalled the end, otherwise on game.ended / finale.results
  }
  // The show is over: NEW SHOW button (only after the engine signals the end, so a new show never opens while the host is talking)
  async function finaleDone(fast) {
    if (!finale || finale.doneShown) return;
    finale.doneShown = true;
    if (window.KHQS_ENTRY && window.KHQS_ENTRY.reset) {
      const b = finale.btn = el('button', 'abs', fx, { left: '1330px', top: '820px', width: '240px', height: '56px', zIndex: 6, pointerEvents: 'auto', cursor: 'pointer', border: 0, borderRadius: '4px',
        background: 'var(--red)', color: '#fff3df', font: "26px 'Alfa Slab One', serif", letterSpacing: '1px', boxShadow: '0 4px 0 #6c0d17' });
      b.textContent = 'NEW SHOW ▶';
      b.addEventListener('click', () => { b.disabled = true; Sound.unlock(); newShow(() => window.KHQS_ENTRY.reset()).then(ok => { if (!ok) b.disabled = false; }); });
    }
    await wait(1500, fast);
    window.KHQS_showDone = true;                          // the show is over (the full-demo recorder review/tools/record_demo.py waits for this)
  }

  /* ===================== Scene transitions =====================
   * A transition covers the screen completely, changes the scene, then opens again. Register by name in TRANSITIONS (curtain; bats and pumpkins go here too).
   * What to register: layer => ({ cover(), uncover(), dispose(), ...transition-specific actions }). cover must finish when the screen is fully covered.
   * runTransition(name, during, fast): cover → change the scene in during(t) → open.
   * Only one runs at a time (overlapping calls wait for the previous one). fast (skipping) runs only during(null) with no transition.
   * When the whole scene changes (snapshot), clearTransition removes it */
  const TRANSITIONS = {};
  let transQueue = Promise.resolve(), transNow = null, transGen = 0;
  function clearTransition() {
    transGen++;
    if (transNow) { transNow.dispose(); transNow = null; }
    curL.innerHTML = ''; topL.innerHTML = '';
    transQueue = Promise.resolve();
  }
  function runTransition(name, during, fast) {
    const job = async () => {
      const gen = transGen, live = () => gen === transGen;
      if (fast || !TRANSITIONS[name]) return during(null);
      const t = transNow = TRANSITIONS[name](TRANSITIONS[name].top ? topL : curL);   // top: covers the audience too
      await t.cover(); if (!live()) return;
      await during(t); if (!live()) return;
      await t.uncover(); if (!live()) return;
      t.dispose();
      if (transNow === t) transNow = null;
    };
    return (transQueue = transQueue.then(job, job));
  }

  /* Curtain (KHQS_v14): two worn red halves come in from both sides and overlap in the middle. They move in jerks as the rope is pulled, the right one a little late.
   * dropSign(art name): a sign drops on ropes in front of the closed curtain. liftSign(): pulls it up. thump(direction): something bumps behind the curtain and it flinches */
  TRANSITIONS.curtain = layer => {
    const W = A.curtain.w, OUT = W + 40, lin = { ease: k => k };
    const box = el('div', 'abs', layer, { left: 0, top: 0, width: '1600px', height: '900px', overflow: 'hidden' });
    const sides = [-1, 1].map(side => {
      const e = img('curtain', box, W);
      Object.assign(e.style, { left: (side < 0 ? 0 : 1600 - W) + 'px', top: 0, transformOrigin: '50% 0' });
      return { e, side };
    });
    const tug = (q, n) => { const u = q * n, i = Math.floor(u); return Math.min(1, (i + easeOut(Math.min(1, (u - i) * 1.6))) / n); }; // pull in n tugs
    const place = (c, shut, sway) => { c.e.style.transform = `translateX(${(c.side * (1 - shut) * OUT).toFixed(1)}px) skewX(${sway.toFixed(2)}deg)${c.side > 0 ? ' scaleX(-1)' : ''}`; };
    sides.forEach(c => place(c, 0, 0));
    const move = (ms, n, closing) => {
      let last = -1;
      return anim(ms, k => {
        const step = Math.floor(k * n);
        if (step !== last && k < 1) { last = step; Sound.cue('fabric'); if (step % 2) Sound.cue('scratch'); }
        sides.forEach(c => {
          const q = clamp(k * 1.12 - (c.side > 0 ? .12 : 0)), shut = closing ? tug(q, n) : 1 - tug(q, n);
          place(c, shut, Math.sin(k * n * Math.PI * 2) * 1.1 * (1 - k) * c.side);
        });
      }, lin);
    };
    let sign = null;
    return {
      async cover() { await move(1350, 5, true); Sound.cue('stomp', { vel: .45 }); },
      uncover() { return move(1050, 4, false); },
      dispose() { box.remove(); },
      thump(dir = 1) {
        Sound.cue('stomp', { vel: .55 });
        anim(300, k => { const j = Math.sin(k * Math.PI) * (1 - k * .5); sides.forEach(c => { c.e.style.translate = `${(dir * 7 * j).toFixed(1)}px ${(-5 * j).toFixed(1)}px`; }); if (sign) sign.style.rotate = `${(dir * 2.4 * Math.sin(k * Math.PI * 2) * (1 - k)).toFixed(2)}deg`; }, lin);
      },
      async dropSign(key) {
        const a = A[key], w = 640, h = w * a.h / a.w, y = 236;
        sign = el('div', 'abs', box, { left: (800 - w / 2) + 'px', top: y + 'px', width: w + 'px', height: h + 'px', transformOrigin: '50% -500px' });
        for (const fx of a.ropes) el('div', 'abs tr-rope', sign, { left: (fx * w - 4) + 'px', top: '-900px', height: '912px' }); // extend the rope from the art's rope up to the ceiling
        img(key, sign, w);
        Sound.cue('whoosh');
        let hit = false;
        await anim(820, k => {
          const fall = clamp(k / .5), rest = clamp((k - .5) / .5);
          const dy = k < .5 ? -(y + h + 60) * (1 - fall * fall) : -22 * Math.sin(rest * Math.PI) * (1 - rest);
          sign.style.transform = `translateY(${dy.toFixed(1)}px) rotate(${(3 * Math.sin(k * 11) * (1 - k)).toFixed(2)}deg)`;
          if (!hit && k >= .5) { hit = true; Sound.cue('tak'); }
        }, lin);
        sign.style.transform = '';
      },
      async liftSign() {
        if (!sign) return;
        const e = sign; sign = null;
        Sound.cue('whoosh', { vel: .6 });
        await anim(240, k => { e.style.transform = `translateY(${(-(236 + e.offsetHeight + 80) * k * k).toFixed(1)}px)`; }, lin);
        e.remove();
      },
    };
  };

  /* Bat swarm, pumpkin pile (KHQS_v15, tools/build_bats_pumpkins.py). Both cover the whole screen including the audience and lobby (top).
   * One transition computes dozens of sprites every frame (ticker). It follows the stage clock (clock), so pause and speed apply.
   * ACT_TRANSITION is used when the act changes; the bats (newShow) when NEW SHOW returns to the lobby */
  const ACT_TRANSITION = { 2: 'bat-swarm', 3: 'pumpkin-pile' };
  const ACT_MUSIC = { 'bat-swarm': 'transBats', 'pumpkin-pile': 'transPumpkin' };   // act transition jingles (sound-files.js)
  let actMusic = null;
  function playActMusic(name) { stopActMusic(); actMusic = Sound.cue(name); }
  // Crowd cheer on a correct answer (user request 2026-11-25: act 1 OX, act 3, act 2 buzzer): 0.25 s after the correct sound, layer the real cheer/applause file for 2.6 s, fading over about 1 s
  function correctCheer() { setTimeout(() => { const h = Sound.cue('applause', { gain: .8 }); if (h) setTimeout(() => h.stop(.35), 2600); }, 250); }
  function stopActMusic() { if (actMusic) { actMusic.stop(); actMusic = null; } }
  function actTransition(name, during, fast) {   // no name (act 1) = no transition and no jingle
    if (!fast && ACT_MUSIC[name]) playActMusic(ACT_MUSIC[name]);
    return runTransition(name, during, fast);
  }
  let snapWait = null;
  // NEW SHOW: take the new game (snapshot) while the bats cover, and the bats scatter once the lobby is laid out. If reset fails, return to the finale
  function newShow(reset) {
    let ok = false;
    return runTransition('bat-swarm', async t => {
      if (t) t.span = true;                       // so a snapshot does not clear this transition
      const got = new Promise(r => { snapWait = r; });
      const r = await Promise.resolve().then(reset).catch(() => null);
      ok = !!(r && r.ok);
      if (ok) await Promise.race([got, new Promise(r2 => setTimeout(r2, 4000))]);
      snapWait = null;
    }).then(() => ok);
  }
  const rnd = (a, b) => a + Math.random() * (b - a);
  function ticker(fn) {                           // run fn every frame until stopped (fn gets seconds since start)
    const c0 = clock; let on = true;
    const step = () => { if (!on) return; fn((clock - c0) / 1000); requestAnimationFrame(step); };
    step();
    return () => { on = false; };
  }
  const until = (c0, sec) => anim(c0 + sec * 1000 - clock, () => {}, { keep: true, ease: k => k });
  const FULL = { left: 0, top: 0, width: '1600px', height: '900px' };

  // one small bat: three wing frames stacked, one visible at a time (up → side → down → side)
  const FLAP = [0, 1, 2, 1];
  function makeBat(parent, w) {
    const a = A.bat_0, h = w * a.h / a.w;
    const e = el('div', 'abs', parent, { left: 0, top: 0, width: w + 'px', height: h + 'px', display: 'none' });
    const fr = [0, 1, 2].map(n => { const i = img(`bat_${n}`, e, w); if (n) i.style.visibility = 'hidden'; return i; });
    let shown = 0;
    return { e, w, h, ox: w * a.body[0], oy: h * a.body[1], show(n) { if (n !== shown) { fr[shown].style.visibility = 'hidden'; fr[n].style.visibility = ''; shown = n; } } };
  }

  /* Bat swarm (night sweeping across at a slant): after a few distant bats, the swarm leads and a dark night sky follows, covering the screen left to right.
   * The edge leans with the top slightly ahead and is softly feathered. The big bat leads the swarm and only flies ahead; it never comes toward the screen.
   * While fully covered, a few small bats circle in the dark; when opening, a second swarm drags the night's tail out to the right */
  TRANSITIONS['bat-swarm'] = Object.assign(layer => {
    const box = el('div', 'abs', layer, { ...FULL, overflow: 'hidden', pointerEvents: 'auto' });
    const SL = .25, VW = 2400, FADE = 170;        // edge slant (top leads), width of the night band, edge feather
    const veil = el('div', 'abs', box, { left: 0, top: '-100px', width: VW + 'px', height: '1100px', transformOrigin: '0 550px',
      background: 'linear-gradient(to bottom, #12070c 0%, #2a121b 30%, #2e141c 62%, #160810 100%)' });
    const fadeMask = `linear-gradient(to right, transparent 0, #000 ${FADE}px, #000 ${VW - FADE}px, transparent ${VW}px)`;
    veil.style.maskImage = veil.style.webkitMaskImage = fadeMask;
    const swarm = el('div', 'abs', box, FULL);
    const edgeX = (y, xf) => xf - SL * (y - 450);  // front edge of the night at height y
    const XF0 = -300, XF1 = 1600 + SL * 450 + FADE + 60, XF2 = XF1 + VW + 40;
    let xf = XF0;
    const BB = A.bat_big, HW = 300, hs = HW / BB.w;
    const hero = img('bat_big', box, HW); Object.assign(hero.style, { display: 'none', transformOrigin: '50% 50%' });

    const bats = [];
    const add = o => { bats.push({ b: makeBat(swarm, o.w), amp: rnd(8, 30), wob: rnd(4, 8), ph: rnd(0, 7), hz: lerp(6.5, 4.2, o.d) * rnd(.9, 1.1), fp: Math.floor(rnd(0, 4)), drift: rnd(-50, 90), ...o }); };
    // distant bats (dark and small) pass first
    for (let i = 0; i < 4; i++) add({ kind: 'free', d: 0, w: rnd(34, 50), t0: i * .12 + rnd(0, .06), x0: -70, y0: rnd(90, 340), vx: rnd(560, 720), vy: rnd(-40, 20), dim: true });
    // the leading swarm rides the night's front edge (a little ahead of and behind it). Stragglers fly over the dark
    const band = (kind, n, lo, hi) => Array.from({ length: n }, () => Math.pow(Math.random(), .9)).sort()
      .forEach(d => add({ kind, d, w: lerp(56, 200, d), y0: rnd(-50, 950), off: rnd(lo, hi) }));
    band('lead', 34, -340, 280);                  // spread wide so they do not clump at the edge
    band('trail', 28, -320, 200);
    // bats circling in the dark: visible only inside the night
    for (let i = 0; i < 7; i++) add({ kind: 'loiter', d: rnd(.1, .5), w: rnd(60, 110), cx: rnd(220, 1380), cy: rnd(150, 720), rx: rnd(80, 160), ry: rnd(30, 60), sp: rnd(1.2, 2) * (Math.random() < .5 ? -1 : 1) });
    bats.forEach(b => { if (b.dim) b.b.e.style.filter = 'brightness(.5)'; });

    let cu = -1, nextFlut = 0, nextSq = 0, heroSq = false;
    const draw = (bt, x, y, vy, t) => {
      if (x - bt.b.w > 1650 || x + bt.b.w < -50 || y - bt.b.h > 980 || y + bt.b.h < -80) { bt.b.e.style.display = 'none'; return 0; }
      const tilt = clamp(vy / 900 * 20, -16, 16);
      bt.b.e.style.display = '';
      bt.b.e.style.transform = `translate(${(x - bt.b.ox).toFixed(1)}px, ${(y - bt.b.oy).toFixed(1)}px) rotate(${tilt.toFixed(1)}deg)`;
      bt.b.show(FLAP[Math.floor(t * bt.hz * 4 + bt.fp) % 4]);
      return 1;
    };
    const c0 = clock;
    const stop = ticker(t => {
      const glide = k => lerp(k, easeIO(k), .35);    // sweeps at an almost even speed (no whoosh through the middle)
      xf = cu < 0 ? lerp(XF0, XF1, glide(clamp((t - .25) / 1.75))) : lerp(XF1, XF2, glide(clamp((t - cu) / 1.4)));
      veil.style.transform = `translateX(${(xf - VW).toFixed(1)}px) skewX(${(-Math.atan(SL) * 180 / Math.PI).toFixed(2)}deg)`;
      let alive = 0;
      for (const bt of bats) {
        const s = Math.sin(t * bt.wob + bt.ph), vy = bt.amp * bt.wob * Math.cos(t * bt.wob + bt.ph);
        if (bt.kind === 'free') {
          const u = t - bt.t0;
          alive += u < 0 ? 0 : draw(bt, bt.x0 + bt.vx * u, bt.y0 + bt.vy * u + bt.amp * s, vy, t);
        } else if (bt.kind === 'loiter') {
          const a = t * bt.sp + bt.ph, out = cu < 0 ? 0 : 1600 * Math.pow(Math.max(0, t - cu - .1), 2);   // when opening, they leave to the right with the swarm
          const x = bt.cx + bt.rx * Math.sin(a) + out, y = bt.cy + bt.ry * Math.sin(2 * a);
          const inside = x < edgeX(y, xf) - 70 && x > edgeX(y, xf - VW) + 70;
          if (!inside) { bt.b.e.style.display = 'none'; continue; }
          alive += draw(bt, x, y, bt.ry * 2 * bt.sp * Math.cos(2 * a), t);
        } else {
          const y = bt.y0 + bt.amp * s, ex = edgeX(y, bt.kind === 'lead' ? xf : xf - VW);
          alive += draw(bt, ex + bt.off + bt.drift * Math.sin(t * .9 + bt.ph), y, vy, t);
        }
      }
      // the lead bat: passes in front of the swarm flapping its wings (only while covering)
      const hx = edgeX(420, xf) + 200, hy = 420 + 26 * Math.sin(t * 5);
      if (cu < 0 && hx > -HW && hx < 1600 + HW) {
        hero.style.display = '';
        hero.style.transform = `translate(${(hx - HW / 2).toFixed(1)}px, ${(hy - BB.h * hs / 2).toFixed(1)}px) rotate(${(4 * Math.cos(t * 5)).toFixed(1)}deg) scale(1, ${(1 + .06 * Math.sin(t * 14)).toFixed(3)})`;
        if (!heroSq && hx > 500) { heroSq = true; Sound.cue('squeak', { f: 1700, vel: .1 }); }
      } else hero.style.display = 'none';
      if (alive > 3 && t > nextFlut) { nextFlut = t + .09; Sound.cue('flutter', { vel: Math.min(1, alive / 16) }); }
      if (alive > 0 && t > nextSq) { nextSq = t + rnd(.1, .28); Sound.cue('squeak', { f: rnd(2200, 3600), vel: .045 }); }
    });
    Sound.cue('whoosh', { vel: .7 });
    return {
      cover() { return until(c0, 2.05); },
      uncover() { cu = (clock - c0) / 1000; Sound.cue('whoosh', { vel: .7 }); return until(c0, cu + 1.45); },
      dispose() { stop(); box.remove(); },
    };
  }, { top: true });

  /* Pumpkin pile: one or two fall, then a rush tumbles down and stacks from the bottom row. Each lands with a squash, bounces and rolls a little; the pumpkin below flinches and bits and seeds fly.
   * A dark backdrop fills up behind the pile to close the gaps. When opening, the pile shudders once and collapses downward */
  TRANSITIONS['pumpkin-pile'] = Object.assign(layer => {
    const box = el('div', 'abs', layer, { ...FULL, overflow: 'hidden', pointerEvents: 'auto' });
    const back = el('div', 'abs', box, { left: '-20px', top: 0, width: '1640px', height: '1100px', transform: 'translateY(960px)',
      background: 'linear-gradient(rgba(24, 11, 8, 0), #180b08 60px, #26120b 380px, #120604 1100px)' });
    const pile = el('div', 'abs', box, FULL), bitsL = el('div', 'abs', box, FULL);
    const G1 = 3800, G2 = 4200;
    // slots: bottom row up, staggered per row. No two identical pumpkins side by side
    const items = [], rowBase = [];
    let prevK = -1;
    // They must be big and varied so they do not read as a pattern (small and even looks like wallpaper). The backdrop fills the gaps
    for (let row = 0, base = 960; base > 100; row++, base -= rnd(168, 192)) {
      rowBase.push(base);
      for (let x = -70 - (row % 2) * 110 + rnd(-30, 30); x < 1680;) {
        let k; do { k = Math.floor(Math.random() * 6); } while (k === prevK || (k === 5 && Math.random() < .55));   // the bandaged dizzy pumpkin is a gag, so keep it rare
        prevK = k;
        const a = A[`pk_${k}`], h = rnd(250, 350) * (k === 1 ? 1.1 : k === 2 ? .85 : 1), w = h * a.w / a.h;
        items.push({ k, w, h, r: a.r * w, cx: x + w / 2, bottom: base + rnd(-28, 28), row, rot: rnd(-13, 13) });
        x += w * rnd(.74, .9);
      }
    }
    const order = [];
    rowBase.forEach((_, r) => order.push(...items.filter(p => p.row === r).sort(() => Math.random() - .5)));
    const N = order.length;
    order.forEach((p, i) => {
      p.i = i;
      p.land = i < 3 ? [.55, .92, 1.12][i] : lerp(1.28, 2.35, (i - 3) / (N - 4));   // the first three one at a time, then a rush
      p.y0 = -40 - rnd(0, 220);
      p.fall = Math.sqrt(2 * (p.bottom - p.y0) / G1);
      p.t0 = p.land - p.fall;
      p.x0 = p.cx + rnd(-90, 90); p.rot0 = p.rot + rnd(-60, 60);
      p.hop = rnd(12, 30) * (i < 3 ? 1.8 : 1); p.drift = rnd(-28, 28) * (i < 3 ? 2.5 : 1);
      p.jolt = -9; p.landed = false;
      p.e = img(`pk_${p.k}`, pile, p.w); Object.assign(p.e.style, { display: 'none', transformOrigin: '50% 100%' });
    });
    const shift = Math.max(0, .05 - Math.min(...order.map(p => p.t0)));
    order.forEach(p => { p.t0 += shift; p.land += shift; });
    const lastLand = Math.max(...order.map(p => p.land));
    // backdrop: when half a row has landed it fills up to that row's height
    const rowHalf = rowBase.map((_, r) => { const ls = order.filter(p => p.row === r).map(p => p.land).sort((a, b) => a - b); return ls[Math.floor(ls.length / 2)]; });
    const backTarget = t => t > lastLand + .05 ? -100 : Math.min(960, ...rowBase.map((b, r) => rowHalf[r] <= t ? b - 150 : 960));
    let backTop = 960;

    const bits = [];
    const spawnBit = (x, y, t) => {
      const q = Math.random(), n = q < .5 ? Math.floor(rnd(0, 4)) : q < .85 ? 4 + Math.floor(rnd(0, 3)) : 7 + Math.floor(rnd(0, 2));
      const leaf = n >= 7, seed = n >= 4 && n < 7, a = A[`pk_bit_${n}`], w = seed ? rnd(20, 28) : leaf ? rnd(55, 75) : rnd(60, 95);
      const e = img(`pk_bit_${n}`, bitsL, w);
      bits.push({ e, w, h: w * a.h / a.w, x, y, t0: t, vx: rnd(-420, 420), vy: leaf ? rnd(-500, -250) : rnd(-950, -450), g: leaf ? 600 : 2600, spin: rnd(-720, 720), leaf });
    };
    const placeBit = (b, t) => {
      const u = t - b.t0;
      const x = b.x + (b.leaf ? b.vx * (1 - Math.exp(-u * 1.5)) / 1.5 + 30 * Math.sin(u * 7) : b.vx * u), y = b.y + b.vy * u + .5 * b.g * u * u;
      b.e.style.opacity = (1 - clamp((u - .7) / .35)).toFixed(2);
      b.e.style.transform = `translate(${(x - b.w / 2).toFixed(1)}px, ${(y - b.h / 2).toFixed(1)}px) rotate(${(b.spin * u).toFixed(0)}deg)`;
      if (u > 1.05) { b.e.remove(); b.dead = true; }
    };
    let lastBonk = -1;
    const onLand = (p, t) => {
      if (t - lastBonk > .045) { lastBonk = t; Sound.cue('bonk', { f: lerp(230, 110, clamp((p.h - 170) / 100)) * rnd(.92, 1.08), vel: rnd(.25, .4) }); }
      if (p.i < 3) Sound.cue('stomp', { vel: .45 });
      for (const o of order) if (o.landed && o.row === p.row - 1 && Math.abs(o.cx - p.cx) < (o.w + p.w) / 2) o.jolt = t;   // the pumpkin below flinches
      const n = p.i < 3 ? 3 : Math.random() < .45 ? 1 + (Math.random() < .4) : 0;
      for (let j = 0; j < n; j++) spawnBit(p.cx + rnd(-p.w * .3, p.w * .3), p.bottom - p.h * .35, t);
    };
    const pose = (p, x, yb, rot, sx = 1, sy = 1) => {
      p.e.style.display = '';
      p.e.style.transform = `translate(${(x - p.w / 2).toFixed(1)}px, ${(yb - p.h).toFixed(1)}px) rotate(${rot.toFixed(1)}deg) scale(${sx.toFixed(3)}, ${sy.toFixed(3)})`;
    };
    const settled = p => [p.cx + p.drift, p.bottom, p.rot + p.drift / p.r * 34];

    const c0 = clock;
    let cu = -1, lastT = 0, booms = [];
    const stop = ticker(t => {
      const dt = Math.max(0, t - lastT); lastT = t;
      if (cu < 0) {                               // stacking
        for (const p of order) {
          const u = t - p.t0;
          if (u < 0) continue;
          if (t < p.land) { const k = u / p.fall; pose(p, lerp(p.x0, p.cx, k), p.y0 + .5 * G1 * u * u, lerp(p.rot0, p.rot, k)); continue; }
          if (!p.landed) { p.landed = true; onLand(p, t); }
          const v = t - p.land, q = clamp(v / .3), dr = easeOut(clamp(v / .45));
          const sq = .17 * Math.exp(-v * 16) + .06 * Math.exp(-(t - p.jolt) * 14);   // landing impact + the flinch when something lands on top
          pose(p, p.cx + p.drift * dr, p.bottom - p.hop * 4 * q * (1 - q), p.rot + p.drift * dr / p.r * 34, 1 + sq * .7, 1 - sq);
        }
        backTop = lerp(backTop, backTarget(t), 1 - Math.pow(.002, dt));
        back.style.transform = `translateY(${backTop.toFixed(1)}px)`;
      } else {                                    // collapsing
        const u = t - cu;
        for (const p of order) {
          const [x, yb, rot] = settled(p), w = Math.max(0, u - p.cd);
          if (!w) { pose(p, x + 4 * Math.sin(u * 60 + p.cx) * clamp(u / .28), yb, rot); continue; }   // shudder
          pose(p, x + p.cvx * w, yb + .5 * G2 * w * w, rot + p.cspin * w);
        }
        back.style.transform = `translateY(${(backTop + (u > .22 ? .5 * G2 * (u - .22) ** 2 : 0)).toFixed(1)}px)`;
        while (booms.length && u >= booms[0]) { booms.shift(); Sound.cue('bonk', { f: rnd(100, 200), vel: rnd(.2, .35) }); }
      }
      for (const b of bits) if (!b.dead) placeBit(b, t);
    });
    return {
      cover() { return until(c0, lastLand + .45); },
      uncover() {
        cu = (clock - c0) / 1000;
        order.forEach(p => { p.cd = .28 + p.row * .025 + rnd(0, .14); p.cvx = rnd(-260, 260); p.cspin = rnd(-220, 220); });
        booms = Array.from({ length: 8 }, () => rnd(.3, .8)).sort((a, b) => a - b);
        Sound.cue('scratch');
        setTimeout(() => Sound.cue('stomp', { vel: .7 }), 280 / speed);
        return until(c0, cu + 1.35);
      },
      dispose() { stop(); box.remove(); },
    };
  }, { top: true });

  /* ---- Act 2 correct / wrong verdict graphics ---- */
  const VERDICT_SVG = {
    // gold ring + sunburst spinning behind + CORRECT! ribbon
    true: `<g class="rays">${Array.from({ length: 16 }, (_, i) => `<polygon points="0,-6 ${i % 2 ? 100 : 118},0 0,6" transform="rotate(${i * 22.5})" fill="${i % 2 ? '#ffd36e' : '#fff0b0'}" opacity=".85"/>`).join('')}</g>
      <circle r="62" fill="none" stroke="#2a1a12" stroke-width="34"/>
      <circle r="62" fill="none" stroke="#f2b23a" stroke-width="24"/>
      <circle r="62" fill="none" stroke="#ffe596" stroke-width="8" stroke-dasharray="70 400" transform="rotate(-140)"/>
      <circle r="62" fill="none" stroke="#b4741a" stroke-width="4" stroke-dasharray="3 10" opacity=".7"/>
      <g transform="translate(0,82) rotate(-6)"><path d="M-92,-20 L92,-20 L104,0 L92,20 L-92,20 L-104,0 Z" fill="#c81e2c" stroke="#2a1a12" stroke-width="5"/>
      <text y="9" text-anchor="middle" font-family="Alfa Slab One" font-size="27" fill="#fff4dc" letter-spacing="2">CORRECT!</text></g>`,
    // bold ✕ on a red splat + crack marks + WRONG! ribbon
    false: `<path d="M-70,-58 C-40,-90 10,-72 30,-86 C62,-98 92,-60 78,-30 C104,-6 92,40 62,52 C58,86 10,96 -14,80 C-48,100 -92,72 -80,38 C-108,12 -98,-36 -70,-58 Z" fill="#5a0a12" opacity=".85"/>
      <circle cx="84" cy="-62" r="9" fill="#5a0a12" opacity=".8"/><circle cx="-92" cy="58" r="6" fill="#5a0a12" opacity=".8"/>
      ${[45, -45].map(a => `<g transform="rotate(${a})"><rect x="-74" y="-17" width="148" height="34" rx="12" fill="#2a1a12"/><rect x="-68" y="-11" width="136" height="22" rx="9" fill="#e8323f"/><rect x="-60" y="-9" width="70" height="6" rx="3" fill="#ff8a8a"/></g>`).join('')}
      <g transform="translate(0,84) rotate(5)"><path d="M-80,-20 L80,-20 L92,0 L80,20 L-80,20 L-92,0 Z" fill="#2a1a12" stroke="#e8323f" stroke-width="4"/>
      <text y="9" text-anchor="middle" font-family="Alfa Slab One" font-size="27" fill="#ff6b74" letter-spacing="3">WRONG!</text></g>`,
  };
  // verdict graphics with the same layout, size and motion plus Halloween trimmings
  const INK = '#2a1a12';
  const BAT = `<path d="M0,-8 L4,-15 L7,-8 C16,-14 30,-18 42,-12 C36,-6 36,2 38,8 C30,3 24,5 20,12 C15,5 8,6 0,14 C-8,6 -15,5 -20,12 C-24,5 -30,3 -38,8 C-36,2 -36,-6 -42,-12 C-30,-18 -16,-14 -7,-8 L-4,-15 Z" fill="${INK}" stroke="#f3e4c4" stroke-width="1.6" paint-order="stroke"/><circle cx="-3" cy="-5" r="1.7" fill="#ffb43a"/><circle cx="3" cy="-5" r="1.7" fill="#ffb43a"/>`;
  const PUMPKIN = `<path d="M-2,-22 C-3,-29 2,-33 8,-33 L9,-27 C5,-27 4,-24 5,-21 Z" fill="#4f7a2a" stroke="${INK}" stroke-width="3"/>
      <ellipse rx="29" ry="23" fill="${INK}" stroke="${INK}" stroke-width="6"/>
      <ellipse cx="-16" rx="13" ry="21" fill="#d9641a"/><ellipse cx="16" rx="13" ry="21" fill="#d9641a"/><ellipse rx="15" ry="23" fill="#f08a24"/>
      <path d="M-14,-9 L-6,-9 L-10,-1 Z M14,-9 L6,-9 L10,-1 Z" fill="${INK}"/>
      <path d="M-15,5 Q0,16 15,5 L10,11 L5,8 L0,13 L-5,8 L-10,11 Z" fill="${INK}"/>`;
  const boneShapes = `<rect x="-60" y="-11" width="120" height="22" rx="4"/><circle cx="-66" cy="-11" r="13"/><circle cx="-66" cy="11" r="13"/><circle cx="66" cy="-11" r="13"/><circle cx="66" cy="11" r="13"/>`;
  const VERDICT_HALLOWEEN = {
    // keep the ring, sunburst and ribbon; add bats and pumpkins
    true: `<g class="rays">${Array.from({ length: 16 }, (_, i) => `<polygon points="0,-6 ${i % 2 ? 100 : 118},0 0,6" transform="rotate(${i * 22.5})" fill="${i % 2 ? '#ffd36e' : '#fff0b0'}" opacity=".85"/>`).join('')}</g>
      <circle r="62" fill="none" stroke="${INK}" stroke-width="34"/>
      <circle r="62" fill="none" stroke="#f2b23a" stroke-width="24"/>
      <circle r="62" fill="none" stroke="#ffe596" stroke-width="8" stroke-dasharray="70 400" transform="rotate(-140)"/>
      <circle r="62" fill="none" stroke="#b4741a" stroke-width="4" stroke-dasharray="3 10" opacity=".7"/>
      <g transform="translate(26,-72) rotate(10) scale(.95)">${BAT}</g>
      <g transform="translate(0,82) rotate(-6)"><path d="M-92,-20 L92,-20 L104,0 L92,20 L-92,20 L-104,0 Z" fill="#c81e2c" stroke="${INK}" stroke-width="5"/>
      <text y="9" text-anchor="middle" font-family="Alfa Slab One" font-size="27" fill="#fff4dc" letter-spacing="2">CORRECT!</text></g>
      <g transform="translate(76,26) rotate(10) scale(.92)">${PUMPKIN}</g>`,
    // keep the splat and colours; the ✕ becomes red bones, a skull in the middle, torn ribbon ends
    false: `<path d="M-70,-58 C-40,-90 10,-72 30,-86 C62,-98 92,-60 78,-30 C104,-6 92,40 62,52 C58,86 10,96 -14,80 C-48,100 -92,72 -80,38 C-108,12 -98,-36 -70,-58 Z" fill="#5a0a12" opacity=".85"/>
      <circle cx="84" cy="-62" r="9" fill="#5a0a12" opacity=".8"/><circle cx="-92" cy="58" r="6" fill="#5a0a12" opacity=".8"/>
      ${[45, -45].map(a => `<g transform="rotate(${a})"><g fill="${INK}" stroke="${INK}" stroke-width="11">${boneShapes}</g><g fill="#e8323f">${boneShapes}</g><rect x="-56" y="-8" width="70" height="5" rx="2.5" fill="#ff8a8a"/></g>`).join('')}
      <g stroke="${INK}" stroke-width="5"><circle cy="-6" r="23" fill="#f3e4c4"/><rect x="-12" y="10" width="24" height="15" rx="4" fill="#f3e4c4"/></g>
      <rect x="-11" y="8" width="22" height="8" fill="#f3e4c4"/>
      <ellipse cx="-9" cy="-6" rx="6.5" ry="7.5" fill="${INK}"/><ellipse cx="9" cy="-6" rx="6.5" ry="7.5" fill="${INK}"/><path d="M0,1 L-3.5,8 L3.5,8 Z" fill="${INK}"/>
      <path d="M-4,15 V24 M4,15 V24" stroke="${INK}" stroke-width="2.5"/>
      <g transform="translate(0,84) rotate(5)"><path d="M-80,-20 L80,-20 L90,-13 L83,-6 L92,2 L84,9 L91,20 L-80,20 L-91,13 L-83,5 L-92,-3 L-84,-10 Z" fill="${INK}" stroke="#e8323f" stroke-width="4"/>
      <text y="9" text-anchor="middle" font-family="Alfa Slab One" font-size="27" fill="#ff6b74" letter-spacing="3">WRONG!</text></g>`,
  };
  // Verdict graphic switch. Toggle with the HUD button or the B key; set with &badge=halloween|plain
  let BADGE_STYLE = 'halloween';
  try { BADGE_STYLE = localStorage.getItem('khqs.verdictStyle') || BADGE_STYLE; } catch (e) { /* storage unavailable: keep the default */ }
  const mb = /badge=(halloween|plain)/.exec(location.hash);
  if (mb) BADGE_STYLE = mb[1];

  const VERDICT_DX = 126; // beside the head so the ribbon does not cover the player's eyes
  function showVerdict(v, correct, fast) {
    clearVerdict(v);
    // beside the head (top right) so the face stays visible, at 80% of the original size
    const box = el('div', 'abs', fx, { left: (v.cx + VERDICT_DX - 120) + 'px', top: (v.top - 140 - 120) + 'px', width: '240px', height: '240px', pointerEvents: 'none', zIndex: 4 });
    box.innerHTML = `<svg viewBox="-120 -120 240 240" width="240" height="240" style="overflow:visible;filter:drop-shadow(0 6px 0 rgba(0,0,0,.4))">${(BADGE_STYLE === 'plain' ? VERDICT_SVG : VERDICT_HALLOWEEN)[correct]}</svg>`;
    v.verdict = { box, correct, rays: box.querySelector('.rays'), t0: clock, stuck: false };
    return anim(480, k => {
      const s = .8 * (correct ? lerp(.2, 1, backOut(k)) : lerp(1.9, 1, easeOut(k)));
      box.style.opacity = clamp(k * 3);
      box.style.transform = `scale(${s.toFixed(3)}) rotate(${(correct ? lerp(-30, -4, k) : lerp(14, 6, k)).toFixed(1)}deg)`;
    }, { fast, ease: k => k });
  }
  function stickVerdict(v, fast) {
    const vd = v.verdict; if (!vd) return Promise.resolve();
    vd.stuck = true;
    const x0 = v.cx + VERDICT_DX - 120, y0 = v.top - 260, x1 = v.cx - 100 - 120, y1 = v.top - 18 - 120; // top left corner of the podium
    return anim(420, k => {
      vd.box.style.left = lerp(x0, x1, k) + 'px'; vd.box.style.top = lerp(y0, y1, k) + 'px';
      vd.box.style.transform = `scale(${lerp(.8, .34, k).toFixed(3)}) rotate(${lerp(6, -14, k).toFixed(1)}deg)`;
    }, { fast, ease: easeIO });
  }
  function clearVerdict(v) { if (v && v.verdict) { v.verdict.box.remove(); v.verdict = null; } }

  function markAnswer(ans, d, fast) {
    if (act === 1) {
      const right = ans === 'X' ? 'X' : 'O', wrong = right === 'O' ? 'X' : 'O';
      anim(600, k => { A1.cards[right].win = k; A1.cards[wrong].lose = k; }, { fast, ease: backOut });
    } else if (act === 2) {
      state.phase = 'buzzer.revealing_answer'; // so the render loop does not overwrite it with the answer countdown
      A2.st.textContent = 'THE ANSWER'; fit(A2.st, 24);
      if (A2.media) stopMedia('ended');
      A2.music.style.opacity = 0;
      A2.ansMain.textContent = (d && d.answerText) || ans;
      A2.ansSub.textContent = d && d.credit && d.credit.author ? d.credit.author : '';
      A2.ansSub.style.display = A2.ansSub.textContent ? '' : 'none';
      if (ghost) ghost.status = 'speaking';
      anim(520, k => { A2.ans.style.opacity = clamp(k * 3); A2.ans.style.transform = `scale(${lerp(.3, 1, backOut(k)).toFixed(3)}) rotate(${lerp(-8, -1.5, k).toFixed(2)}deg)`; }, { fast, ease: k => k });
    } else {
      const k = 'ABCD'.indexOf(ans);
      A3.choices.forEach((c, j) => { c.className = 'choice3 ' + (j === k ? 'right' : 'wrong'); c.style.opacity = 1; });
    }
  }
  function betLocked(v, fast) {
    if (!v) return;
    v.bet.innerHTML = '<span style="font-size:30px">🔒</span><span>LOCKED IN</span>';
    v.bet.style.color = 'var(--red)';
    if (!fast) Sound.cue('clip');
    v.hop = clock;
    pop(v.bet, fast, 300);
  }
  function betShow(v, b, fast) {
    if (!v) return Promise.resolve();
    v.bet.innerHTML = `<span style="font-family:'Alfa Slab One',serif;font-size:40px;color:var(--ink)">${b.bet}</span>` +
      (b.allIn ? '<span style="font-family:\'Alfa Slab One\',serif;font-size:18px;color:#fff1d6;background:var(--red);padding:1px 8px;border-radius:4px;transform:rotate(-6deg)">ALL IN!</span>' : b.remaining != null ? `<span style="font-size:17px;color:#8a6a4a">LEFT ${b.remaining}</span>` : '');
    return pop(v.bet, fast, 500);
  }

  /* ===================== Render ===================== */
  let last = performance.now();
  function frame(now) {
    const dt = Math.min(.25, (now - last) / 1000);
    last = now;
    if (!paused) clock += dt * 1000 * speed;
    for (const tw of [...tweens]) {
      const k = clamp((clock - tw.t0) / tw.ms);
      tw.fn(tw.ease(k));
      if (k >= 1) { tweens.delete(tw); tw.res(); }
    }
    render(paused ? 0 : dt);
    requestAnimationFrame(frame);
  }

  // The winner on the podium: bounces with the feet as the pivot, tilting left and right in turn. The crown follows a little late.
  // The art's bottom hides only 9 px behind the podium: while dancing it crouches 8 px and bounces up only 6 px, so the clipped bottom never shows above the stand when tilting
  function finaleDance(t) {
    const P = finale && finale.part;
    if (!P) return;
    const amp = clamp((clock - P.t0) / 600);
    P.cols.forEach((c, i) => {
      if (!c.s.winner) return;
      const ph = Math.PI * (t * 1.7 + i * .5), u = Math.abs(Math.sin(ph)) * amp;
      c.body.style.transform = `translateY(${(8 * amp - 6 * u).toFixed(1)}px) rotate(${(3.5 * Math.sin(ph) * amp).toFixed(2)}deg) scale(${(1 + .012 * amp - .04 * u).toFixed(3)}, ${(1 - .025 * amp + .07 * u).toFixed(3)})`;
      if (c.crown) c.crown.style.transform = `translateY(${(-5 * u).toFixed(1)}px) rotate(${(-6 - 6 * Math.sin(ph - .8) * amp).toFixed(2)}deg)`;
    });
  }

  function render(dt) {
    const t = clock / 1000, tq = q12(t);
    finaleDance(t);
    const s = 1 - Math.pow(.015, dt);
    for (const k of ['dark', 'fx', 'fy', 'rx', 'ry']) light[k] = lerp(light[k], target[k], k === 'dark' ? s : 1 - Math.pow(.0005, dt));
    light.flash = Math.max(0, light.flash - dt * 2.2);

    // blackout + hole (spotlight)
    darkness.style.opacity = light.dark.toFixed(3);
    const m = target.dark > .02 && target.rx < 1500 ? `radial-gradient(ellipse ${light.rx.toFixed(0)}px ${light.ry.toFixed(0)}px at ${light.fx.toFixed(0)}px ${light.fy.toFixed(0)}px, ${ghostLit.soft ? 'rgba(0,0,0,.62) 0, rgba(0,0,0,.74) 40%' : 'transparent 55%'}, #000 100%)` : 'none';
    darkness.style.maskImage = darkness.style.webkitMaskImage = m;
    plate.style.filter = plateQ.style.filter = plateF.style.filter = light.flash > .01 ? `brightness(${(1 + light.flash * .35).toFixed(3)})` : '';

    // sign, footlights
    if (signs) {
      signs.onairGlow.style.opacity = (.55 + .1 * Math.sin(t * 3)).toFixed(2);
      const ap = clock < applauseUntil ? .5 + .5 * Math.cos(t * Math.PI * 2 * 1.6) : 0;
      signs.applauseGlow.style.opacity = ap.toFixed(2);
      signs.applause.style.textShadow = ap > .1 ? `0 0 ${(16 * ap).toFixed(1)}px rgba(255,220,120,1)` : 'none';
      signs.applause.style.transform = `rotate(${LY.signs.applause[4]}deg) scale(${(1 + .05 * ap).toFixed(3)})`;
    }
    const chase = Math.floor(t * (light.chase ? 10 : 2.2));
    foot.forEach((g, i) => { g.style.opacity = (.35 + ((i + chase) % 3 === 0 ? .4 : 0) + .08 * Math.sin(t * 7 + i * 1.7) + light.flash * .4).toFixed(2); });

    // act 1 cards
    if (A1) for (const k of ['O', 'X']) {
      const c = A1.cards[k];
      c.halo.style.opacity = (c.win * (.75 + .25 * Math.sin(t * 8))).toFixed(2);
      c.ring.style.opacity = (c.win * (.8 + .2 * Math.sin(t * 8))).toFixed(2);
      c.shade.style.opacity = (c.lose * .9).toFixed(2);
    }
    // act 1 timer
    if (A1) {
      const on = state.phase === 'ox.answering' && state.deadline;
      A1.timer.style.opacity = on ? 1 : 0;
      if (on) A1.timer.textContent = Math.max(0, Math.ceil((state.deadline - Date.now()) / 1000));
    }
    // act 2 music
    if (A2) {
      if (A2.media) A2.fill.style.width = (clamp((clock - A2.media.t0) / A2.media.dur) * 100).toFixed(1) + '%';
      A2.notes.forEach((n, i) => { n.style.transform = A2.media ? `translateY(${(-8 * Math.abs(Math.sin(t * 4 + i))).toFixed(1)}px) rotate(${(Math.sin(t * 3 + i) * 12).toFixed(1)}deg)` : ''; });
      if (state.phase === 'buzzer.answering' && state.deadline) A2.st.textContent = `ANSWERING · ${Math.max(0, Math.ceil((state.deadline - Date.now()) / 1000))}`;
    }
    // act 3 timer
    if (A3) {
      const on = (state.phase === 'final.betting' || state.phase === 'final.answering') && state.deadline;
      if (on) { const r = Math.max(0, Math.ceil((state.deadline - Date.now()) / 1000)); A3.tClock.textContent = `00:${String(r).padStart(2, '0')}`; }
      else A3.tClock.textContent = A3.idleClock || '--:--';
    }

    // players: pop bounce and wobble (12 fps)
    for (const st of seats) {
      const v = st.view; if (!v) continue;
      if (v.vacant) {
        const blink = (tq + st.i * 1.3 + 2) % 3.7 < .15;
        v.vacant.eyes.style.background = blink ? 'rgba(10,5,5,.95)' : 'transparent';
        continue;
      }
      if (!v.inner) continue;
      const ht = (clock - v.hop) / 1000;
      let dy = ht >= 0 && ht < .5 ? -Math.abs(Math.sin(ht * Math.PI * 2)) * 14 * (1 - ht * 2) : 0;
      let rot = Math.sin(tq * 1.4 + st.i * 1.9) * 1.5;
      if (v.pose === 'cheer') dy -= Math.abs(Math.sin(tq * 9 + st.i)) * 7;
      if (v.pose === 'sad') { dy += 4; rot -= 2; }
      if (v.talking) rot += Math.sin(tq * 14) * 2;
      const sh = (clock - v.shake) / 1000;
      if (sh >= 0 && sh < .8) rot += Math.sin(sh * 40) * 4 * (1 - sh / .8);
      v.inner.style.transform = `translateY(${dy.toFixed(1)}px) rotate(${rot.toFixed(2)}deg)`;
      v.inner.style.filter = v.disconnected ? 'grayscale(1) brightness(.55)' : '';
      if (v.sign) {   // act 1 picket: nods slightly as if the hand holding the stick wobbles
        v.sign.style.rotate = v.ducked ? `${(Math.sin(tq * 2.2 + st.i * 2.1) * 3).toFixed(2)}deg` : '';
        v.sign.style.filter = v.disconnected ? 'grayscale(1) brightness(.55)' : '';
      }
      if (v.verdict && !v.verdict.stuck) { // verdict graphic: sunburst spins, gentle bob
        if (v.verdict.rays) v.verdict.rays.setAttribute('transform', `rotate(${((clock - v.verdict.t0) / 30 % 360).toFixed(1)})`);
        v.verdict.box.style.translate = `0 ${(Math.sin(t * 3) * 4).toFixed(1)}px`;
      }
      if (v.dome) {
        const bz = v.buzzed && clock - v.buzzed < 1500;
        v.dome.style.filter = v.locked ? 'grayscale(.9) brightness(.45)' : bz ? `brightness(${(1.4 + .4 * Math.sin(t * 30)).toFixed(2)})` : '';
        v.domeGlow.style.opacity = (bz ? .9 : v.armed ? .25 + .2 * Math.sin(t * 6 + st.i) : 0).toFixed(2);
      }
    }

    if (A1) for (const vt of Object.values(A1.voters)) if (vt.talking) vt.box.style.rotate = `${(Math.sin(tq * 14) * 3).toFixed(1)}deg`;   // betrayal chance: talking on the ledge

    // ghost: float, blink, gaze, talk
    if (ghost) {
      const g = ghost;
      if (g.pose && clock >= g.until) g.pose = null;
      if (!g.pose && g.status === 'idle' && !state.deadline && clock - lastEventAt > GHOST_SLEEP_AFTER) ghostPose('sleep', 0);
      const want = g.pose || (g.status === 'thinking' ? 'think' : null);
      if (want !== g.shown) {
        g.calm.style.visibility = want ? 'hidden' : 'visible';
        for (const k in g.poses) g.poses[k].style.visibility = k === want ? 'visible' : 'hidden';
        g.marks.innerHTML = GHOST_MARKS[want] ? `<svg viewBox="0 0 70 70" width="62" height="62" style="overflow:visible">${GHOST_MARKS[want]}</svg>` : '';
        g.shown = want; g.popT = clock;
      }
      // squash and bounce at the moment the expression changes, to hide the swap
      const pt = (clock - g.popT) / 1000, spring = Math.exp(-pt * 7) * Math.cos(pt * 20) * .17;
      let sq = 1 + Math.sin(t * 2.6) * .02, dy = Math.sin(t * 1.4) * 4, rot = Math.sin(t * .9) * 2 + (g.focus != null ? 6 : 0);
      if (want === 'happy') dy -= Math.abs(Math.sin(t * 8)) * 9;
      else if (want === 'surprised') dy -= 16 * Math.exp(-pt * 5);
      else if (want === 'worried') { dy *= .4; rot += Math.sin(t * 34) * 1.4; }
      else if (want === 'angry') { dy *= .3; rot += Math.sin(t * 28) * 1.2; }
      else if (want === 'sad') { dy = dy * .3 + 3; rot *= .4; }
      else if (want === 'tease') rot += Math.sin(t * 11) * 4;
      else if (want === 'sleep') { dy = 0; rot = 0; sq = 1 + Math.sin(t * 1.4) * .04; }
      sq *= 1 + spring;
      g.box.style.transform = `translateY(${dy.toFixed(1)}px) rotate(${rot.toFixed(2)}deg) scale(${(1 / sq).toFixed(3)}, ${sq.toFixed(3)})`;
      // shadow on the curtain (light from top left). Slightly darker during the blackout, but the face stays visible
      g.box.style.filter = `brightness(${lerp(1, ghostLit.ghost, clamp(light.dark / .7)).toFixed(3)}) drop-shadow(9px 7px 9px rgba(24,2,6,.55))`;
      g.front.style.filter = `brightness(${Math.max(1 - light.dark, ghostLit.front).toFixed(3)})`;
      g.marks.style.transform = `scale(${clamp(pt * 7).toFixed(3)}) rotate(${(Math.sin(t * 5) * 4).toFixed(1)}deg)`;
      g.glow.style.opacity = ((g.status === 'speaking' ? .95 : .7) + Math.sin(t * 1.4) * .12).toFixed(3);
      let look = [0, 0];
      if (g.focus != null) look = [1, .3];
      else if (target.dark > .3) look = [1, .1];
      const blink = ((t + 2) % 4.3) < .14;
      const open = blink ? .1 : g.status === 'listening' ? .75 : 1;
      const wide = light.flash > .3 ? 1.18 : 1;
      g.eyes.forEach(e => {
        const ex = e.x + look[0] * 6, ey = e.y + look[1] * 4;
        e.ball.setAttribute('cx', ex.toFixed(2)); e.ball.setAttribute('cy', ey.toFixed(2));
        e.ball.setAttribute('rx', (e.rx * wide).toFixed(2)); e.ball.setAttribute('ry', (e.ry * open * wide).toFixed(2));
        e.hi.setAttribute('cx', (ex + e.rx * .3).toFixed(2)); e.hi.setAttribute('cy', (ey - e.ry * .36 * open).toFixed(2));
        e.hi.setAttribute('opacity', open > .3 ? 1 : 0);
      });
      let talk = 0;
      if (g.status === 'speaking') {
        talk = .4 + .6 * Math.abs(Math.sin(tq * 11)) * (Math.sin(tq * 3.1) > -.6 ? 1 : 0);
        if (!g.voiceT || clock > g.voiceT) { Sound.cue('voice', { dur: 1.6 / speed }); g.voiceT = clock + 1700; }
      } else g.voiceT = 0;
      g.mouth.setAttribute('ry', (talk * 11).toFixed(2));
    }

    // audience: normally out of focus, in focus only at cheers and gasps
    const focus = clock < focusUntil ? 1 : 0;
    light.aud = lerp(light.aud, focus, 1 - Math.pow(.004, dt || .016));
    audL.style.filter = `blur(${lerp(3.4, .5, light.aud).toFixed(2)}px) brightness(${(lerp(.62, .92, light.aud) * ghostLit.aud).toFixed(3)})`;
    const cheerOn = clock < applauseUntil, shockOn = clock < shockUntil;
    heads.forEach(h => {
      let dy = 0, rot = Math.sin(tq * 1.2 + h.i * 2.1) * 2.2;
      if (cheerOn) dy -= Math.abs(Math.sin(tq * 9 + h.i)) * 16;
      if (shockOn) { const k = clamp((shockUntil - clock) / 1000); dy -= 10 * k; rot = Math.sin(tq * 30 + h.i) * 3; }
      if (target.dark > .3 && !shockOn && !cheerOn) rot *= .3;
      h.b.style.transform = `translateY(${dy.toFixed(1)}px) rotate(${rot.toFixed(2)}deg)`;
      h.bang.style.opacity = shockOn && h.i % 3 !== 1 ? 1 : 0;
    });

    // confetti
    for (let i = confetti.length - 1; i >= 0; i--) {
      const c = confetti[i];
      if (dt) { c.vy += 900 * dt; c.vx *= .99; c.x += c.vx * dt; c.y += c.vy * dt * .5; c.r += c.vr * dt; c.life -= dt; }
      c.c.style.transform = `translate(${c.x.toFixed(1)}px, ${c.y.toFixed(1)}px) rotate(${c.r.toFixed(0)}deg)`;
      if (c.life <= 0 || c.y > 950) { c.c.remove(); confetti.splice(i, 1); }
    }
  }

  /* ===================== Fit to window / HUD ===================== */
  function fitStage() {
    const k = Math.min(innerWidth / 1600, innerHeight / 900);
    stage.style.transform = `translate(${((innerWidth - 1600 * k) / 2).toFixed(1)}px, ${((innerHeight - 900 * k) / 2).toFixed(1)}px) scale(${k.toFixed(4)})`;
  }
  addEventListener('resize', fitStage);
  fitStage();

  const SCEN = { 1: 'duo-act1-ox-betrayal', 2: 'trio-act2-buzzer-music', 3: 'trio-act3-final-allin' };
  // for scenarios without labels, make chips at the key event positions
  const KEY_EVENTS = { 'final.category': 'Category', 'final.betting': 'Betting', 'final.choices_revealed': 'Picks', 'final.bet_revealed': 'Bets', 'answer.suspense': 'Answer', 'finale.winner': 'Winner' };
  let curAct = 1;
  const btnPlay = document.getElementById('btnPlay'), btnSpeed = document.getElementById('btnSpeed'),
    btnSound = document.getElementById('btnSound'), btnLog = document.getElementById('btnLog'), labelsEl = document.getElementById('labels'), actsEl = document.getElementById('acts');

  // Chain acts in preview: like the real engine, load the next act's scenario while covered by the transition (ACT_TRANSITION).
  // The new scenario's first snapshot changes the stage behind the cover (span), and its act.started is the same act, so it only cheers
  let crossing = false;
  function crossAct(n) {
    if (crossing) return;
    crossing = true;
    engine.stop(); Sound.loop('roll', false); Sound.loop('waltz', false); Sound.loop('clockTick', false); Sound.loop('crowdMurmur', false); thinkTick = false; stopBetMusic(.3); stopActMusic();
    if (paused) togglePause();
    return actTransition(ACT_TRANSITION[n] || 'bat-swarm', async t => {
      if (t) t.span = true;
      const got = new Promise(r => { snapWait = r; });
      loadAct(n, null, true);
      await Promise.race([got, new Promise(r => setTimeout(r, 3000))]);
      snapWait = null;
    }).finally(() => { crossing = false; });
  }
  // When an act scenario ends, move to the next act after a moment (act 3 ends with the finale). Not in review options that show a single scene
  engine.onEnd = (sc, run) => {
    if (curAct >= 3 || sc !== window.KHQS_SCENARIOS[SCEN[curAct]] || /trans=|finale=|verdict=/.test(location.hash)) return;
    wait(2500).then(() => { if (engine.run === run && !crossing && !opening) crossAct(curAct + 1); });
  };

  function loadAct(n, from = null, keepTrans = false) {
    curAct = n;
    engine.stop();
    engine.load(window.KHQS_SCENARIOS[SCEN[n]]);
    labelsEl.innerHTML = '';
    const steps = engine.scenario.steps, chips = [];
    steps.forEach((s, i) => {
      if (s.label) chips.push([s.label, s.label]);
      const ty = s.send && (s.send.type === 'phase.changed' ? s.send.data.phase : s.send.type);
      if (ty && KEY_EVENTS[ty] && !chips.some(c => c[1] === KEY_EVENTS[ty])) chips.push([i, KEY_EVENTS[ty]]);
    });
    for (const [at, name] of [[null, 'Start'], ...chips]) {
      const b = el('button', '', labelsEl);
      b.textContent = { q1: 'Q1', q2: 'Q2', betrayal: 'Betrayal', 'buzzer-q': 'Buzzer Q', 'music-q': 'Music Q' }[name] || name;
      b.addEventListener('click', () => restart(at));
    }
    [...actsEl.children].forEach((b, i) => b.classList.toggle('on', i + 1 === n));
    restart(from, keepTrans);
  }
  function restart(label = null, keepTrans = false) {
    Sound.loop('roll', false); Sound.loop('waltz', false); Sound.loop('clockTick', false); Sound.loop('crowdMurmur', false); thinkTick = false; stopBetMusic(.3);
    if (!keepTrans) stopActMusic();                // for a transition across acts (keepTrans) the transition jingle continues too
    if (A2 && A2.media) { clearTimeout(A2.media.timer); A2.media = null; }
    if (keepTrans) { for (const tw of [...tweens]) if (!tw.keep) tweens.delete(tw); }   // a transition across acts keeps running
    else { clearTransition(); tweens.clear(); }
    paused = false; engine.paused = false;
    lastSseq = null;
    logEl.innerHTML = '';
    engine.start(label);
    syncHud();
  }
  function syncHud() {
    btnPlay.textContent = paused ? '▶' : '❚❚';
    btnSpeed.textContent = speed + '×';
    btnSound.textContent = Sound.isEnabled() ? '♪ Sound off' : '♪ Sound on';
    btnSound.classList.toggle('on', Sound.isEnabled());
    btnLog.classList.toggle('on', !document.getElementById('log').classList.contains('hidden'));
  }
  function togglePause() { paused = !paused; engine.paused = paused; if (paused) { Sound.loop('roll', false); Sound.loop('waltz', false); Sound.loop('clockTick', false); } syncHud(); }
  [1, 2, 3].forEach(n => { const b = el('button', '', actsEl); b.textContent = ['Act 1 OX', 'Act 2 Buzzer', 'Act 3 Final'][n - 1];
    b.addEventListener('click', () => { if (crossing) return; if (opening || n === act) loadAct(n); else crossAct(n); }); });   // going to another act uses the transition
  { const b = el('button', '', actsEl); b.textContent = 'Opening'; b.addEventListener('click', () => loadOpening()); }
  btnPlay.addEventListener('click', togglePause);
  document.getElementById('btnRestart').addEventListener('click', () => restart());
  btnSpeed.addEventListener('click', () => { speed = speed === 1 ? 2 : 1; engine.speed = speed; syncHud(); });
  btnSound.addEventListener('click', () => { Sound.setEnabled(!Sound.isEnabled()); syncHud(); });
  btnLog.addEventListener('click', () => { document.getElementById('log').classList.toggle('hidden'); syncHud(); });
  // Verdict graphic switch: applies from the next verdict and survives a reload
  const btnBadge = el('button', '', btnLog.parentNode);
  const syncBadge = () => { btnBadge.textContent = BADGE_STYLE === 'plain' ? 'Badge: plain (B)' : 'Badge: Halloween (B)'; };
  syncBadge();
  btnBadge.addEventListener('click', () => {
    BADGE_STYLE = BADGE_STYLE === 'plain' ? 'halloween' : 'plain';
    try { localStorage.setItem('khqs.verdictStyle', BADGE_STYLE); } catch (e) { /* if saving fails, still apply to this screen */ }
    syncBadge();
  });
  addEventListener('keydown', e => {
    if (e.target.tagName === 'INPUT') return;
    if (e.target.tagName === 'BUTTON' && (e.key === ' ' || e.key === 'Enter')) return;
    if (opening && e.key === ' ') return; // in the opening, space is a space in the name box
    if (e.key === ' ') { e.preventDefault(); togglePause(); }
    else if (e.key === 'r' || e.key === 'R') restart();
    else if (e.key === 's' || e.key === 'S') btnSound.click();
    else if (e.key === 'l' || e.key === 'L') btnLog.click();
    else if (e.key === 'b' || e.key === 'B') btnBadge.click();
    else if (['1', '2', '3'].includes(e.key)) loadAct(+e.key);
    else if (e.key === '0') loadOpening();
  });
  addEventListener('pointerdown', () => { if (!Sound.isEnabled()) { Sound.unlock(); syncHud(); } }, { once: true });
  const hud = document.getElementById('hud');
  let idleT = 0;
  addEventListener('pointermove', () => { hud.classList.remove('idle'); clearTimeout(idleT); idleT = setTimeout(() => hud.classList.add('idle'), 2800); });

  /* ===================== Opening: cast-board lobby → blackout → 3-2-1 → sheet → host → lights ===================== */
  // One show.opening gate is the whole show opening. Closing the gate after the lights come up (MC_READY) lets the engine cue Gemini's first greeting.
  // URL: #opening (alias #showtime). &clean auto-registers two players and starts. &qr=URL previews the QR
  const GHOST_STAND = { x: 628, y: 66, scale: 2.4 }; // distance and scale from the act 1 lectern spot to the stage centre
  const ST = { // seconds
    motor: .7, film: 1.2, beam0: 1.3, beam1: 1.9, lead0: 2, title: 4.7, blink0: 7.7, eye1: 8.2, eye2: 8.8, slide: 11.4, yawn0: 12.4,
    pins: 14.3, pinGap: .22, drop: 16.2, die: 17.05, wig0: 17.55, pop: 18.9, end: 19.4,
  };
  const BULB = { x: 118, y: 372 };   // ghost-light bulb
  // 24 points around the sheet: top 9, right 3, bottom 9, left 3. The sagging cloth and the flat heap use the same order, so the shape morphs directly
  const SHEET_PTS = [[250, 192], [389, 194], [530, 192], [670, 195], [806, 192], [937, 195], [1078, 192], [1217, 194], [1350, 192],
    [1366, 380], [1370, 560], [1362, 720],
    [1360, 806], [1220, 798], [1080, 808], [940, 800], [800, 810], [660, 799], [520, 807], [380, 798], [240, 806],
    [234, 720], [230, 560], [236, 380]];
  const DROOP_PTS = [[560, 600], [600, 560], [660, 482], [722, 404], [800, 370], [878, 404], [940, 482], [1000, 560], [1040, 600],
    [1060, 680], [1062, 724], [1072, 764],
    [1100, 810], [1010, 802], [950, 812], [870, 802], [800, 814], [730, 802], [650, 812], [590, 802], [500, 810],
    [528, 764], [538, 724], [540, 680]];
  const PILE_PTS = [[470, 800], [540, 762], [620, 744], [700, 728], [800, 720], [900, 730], [980, 746], [1060, 764], [1130, 800],
    [1150, 806], [1152, 810], [1150, 812],
    [1120, 816], [1030, 810], [950, 818], [870, 810], [800, 818], [730, 810], [650, 818], [570, 810], [480, 816],
    [452, 812], [450, 810], [452, 806]];
  const WIGGLES = [[17.6, 690, 58], [17.98, 915, 66], [18.32, 760, 74]]; // something wriggles under the cloth: time, position, height
  const PIN_ORDER = [0, 8, 1, 7, 2, 6, 3, 5, 4]; // outside in

  // Cast-board lobby slots (1600×900). tools/build_cast_lobby.py makes the art with the same values
  const CAST = {
    qr: [332, 437, 522, 627], qrRot: -2.2, // the blank note slot inside the frame
    cards: [[681, 342, 922, 667], [953, 342, 1196, 667], [1226, 342, 1467, 667]],
    // 15 sign bulbs (clockwise from top left), one wall lamp, four bulbs on the board frame. [x, y, cover radius]
    bulbs: [[834, 116], [922, 92], [997, 86, 24], [1124, 86, 24], [1199, 92], [1289, 114], [1370, 210], [1311, 279], [1244, 267], [1165, 253], [1078, 246],
      [997, 250], [911, 261], [825, 277], [762, 213], [497, 168, 130], [632, 478, 28], [1511, 478, 28], [632, 733, 26], [694, 782, 24]],
    marquee: 15, badBulbs: [3, 9, 13, 17],  // number of sign bulbs; bulbs that flicker unusually often
    flames: [[155, 606, 100, 0], [94, 548, 120, 45], [254, 762, 170, 80], [1531, 795, 210, 400]], // flames that stay when the power goes: small candle, big candle, lantern, pumpkin. [x, y, cover radius, stagger (ms) when one gust blows them out]
    sign: { cx: 1066, floor: 838, w: 580 }, // start sign: centre, shelf top (where the legs stand), width
  };
  ['lobby', 'lobby_dark', 'lobby_off', 'lobby_cards', 'showtime_off', 'showtime_on', 'pointer_hand', 'pointer_word'].forEach(k => { if (A[k]) new Image().src = A[k].src; });

  let opening = null;
  function createOpening() {
    const NS = 'http://www.w3.org/2000/svg';
    let lobbyK = 0, kick = 0; // ghost-light brightness on the sheet; how much the cloth flinches

    const seg = (t, a, b) => clamp((t - a) / (b - a));
    const bump = (t, a, b) => Math.sin(seg(t, a, b) * Math.PI);
    const f1 = n => n.toFixed(1);
    const mk = (tag, a, parent) => { const e = document.createElementNS(NS, tag); for (const k in a) e.setAttribute(k, a[k]); if (parent) parent.appendChild(e); return e; };
    const set = (e, a) => { for (const k in a) e.setAttribute(k, a[k]); };
    const smooth = p => { // closed Catmull-Rom → Bézier
      const n = p.length;
      let d = `M${f1(p[0][0])},${f1(p[0][1])}`;
      for (let i = 0; i < n; i++) {
        const p0 = p[(i - 1 + n) % n], p1 = p[i], p2 = p[(i + 1) % n], p3 = p[(i + 2) % n];
        d += `C${f1(p1[0] + (p2[0] - p0[0]) / 6)},${f1(p1[1] + (p2[1] - p0[1]) / 6)} ${f1(p2[0] - (p3[0] - p1[0]) / 6)},${f1(p2[1] - (p3[1] - p1[1]) / 6)} ${f1(p2[0])},${f1(p2[1])}`;
      }
      return d + 'Z';
    };

    // sheet stage coordinates: the original opening coordinates fitted to the act 1 screen
    const SC = 1.05, OX = -40, OY = -135;
    const svg = mk('svg', { viewBox: '0 0 1600 900' });
    Object.assign(svg.style, { position: 'absolute', left: 0, top: 0, width: '1600px', height: '900px', overflow: 'visible', pointerEvents: 'none' });
    sheetL.appendChild(svg);
    const ART = window.KHQS_OPENING_ART;
    const INK = '#1c1210', SLAB = ART.SLAB;
    const defs = mk('defs', {}, svg);
    const grad = (kind, id, attrs, stops) => { const g = mk(kind, { id, ...attrs }, defs); for (const [o, c, a] of stops) mk('stop', { offset: o, 'stop-color': c, 'stop-opacity': a == null ? 1 : a }, g); };
    grad('linearGradient', 'stSheet', { x1: 0, y1: 0, x2: 0, y2: 1 }, [[0, '#fbf3df'], [.55, '#f1e5c8'], [1, '#dccaa2']]);
    grad('radialGradient', 'stPool', { gradientUnits: 'userSpaceOnUse', cx: 800, cy: 480, r: 700 }, [[0, '#1a0d08', 0], [.45, '#1a0d08', .06], [.8, '#1a0d08', .46], [1, '#0a0608', .82]]);
    grad('radialGradient', 'stBeam', { gradientUnits: 'userSpaceOnUse', cx: 800, cy: 990, r: 900 }, [[0, '#fffaf0', .95], [.25, '#ffecc8', .42], [1, '#f4d6a0', .05]]);
    grad('radialGradient', 'stWarm', { gradientUnits: 'userSpaceOnUse', cx: 150, cy: 480, r: 1250 }, [[0, '#ffcf8a', .5], [.45, '#ffb868', .2], [1, '#ffb868', .04]]);
    grad('linearGradient', 'stFall', { x1: 0, y1: 0, x2: 1, y2: 0 }, [[0, '#2a150c', .04], [.5, '#2a150c', .2], [1, '#1c0d09', .46]]);
    grad('linearGradient', 'stFoot', { gradientUnits: 'userSpaceOnUse', x1: 0, y1: 830, x2: 0, y2: 380 }, [[0, '#ffb45a', .62], [.5, '#ff9a48', .16], [1, '#ff9a48', 0]]);
    grad('radialGradient', 'stGate', { gradientUnits: 'userSpaceOnUse', cx: 800, cy: 500, r: 720 }, [[0, '#fffdf0', .62], [.6, '#fff6d8', .4], [1, '#ffeec2', .24]]);
    grad('radialGradient', 'stBulb', {}, [[0, '#fff2cf', .95], [.2, '#ffd98f', .5], [1, '#ffb868', 0]]);
    grad('radialGradient', 'stGlint', {}, [[0, '#fff0c8', 1], [.35, '#ffc35a', .7], [1, '#ffc35a', 0]]);
    const blur = mk('filter', { id: 'stBlur', x: '-20%', y: '-40%', width: '140%', height: '180%' }, defs);
    mk('feGaussianBlur', { stdDeviation: 8 }, blur);
    const noise = document.createElement('canvas'); noise.width = noise.height = 180;
    { // film grain
      const c = noise.getContext('2d'), d = c.createImageData(180, 180);
      for (let i = 0; i < d.data.length; i += 4) { const v = Math.random() < .5 ? 255 : 0; d.data[i] = d.data[i + 1] = d.data[i + 2] = v; d.data[i + 3] = Math.random() * 54; }
      c.putImageData(d, 0, 0);
    }
    const grainP = mk('pattern', { id: 'stGrain', patternUnits: 'userSpaceOnUse', width: 180, height: 180 }, defs);
    mk('image', { href: noise.toDataURL(), width: 180, height: 180 }, grainP);
    const sheetClip = mk('path', {}, mk('clipPath', { id: 'stClip' }, defs));
    // projection window: where one film frame shows. A little smaller than the cloth
    const GATE = { x: 265, y: 220, width: 1070, height: 562, rx: 28 };
    const GATE_D = `M${GATE.x + GATE.rx},${GATE.y} h${GATE.width - 2 * GATE.rx} a${GATE.rx},${GATE.rx} 0 0 1 ${GATE.rx},${GATE.rx} v${GATE.height - 2 * GATE.rx} a${GATE.rx},${GATE.rx} 0 0 1 ${-GATE.rx},${GATE.rx} h${-(GATE.width - 2 * GATE.rx)} a${GATE.rx},${GATE.rx} 0 0 1 ${-GATE.rx},${-GATE.rx} v${-(GATE.height - 2 * GATE.rx)} a${GATE.rx},${GATE.rx} 0 0 1 ${GATE.rx},${-GATE.rx} Z`;
    mk('rect', GATE, mk('clipPath', { id: 'stGateClip' }, defs));

    const beamCone = mk('path', { fill: 'url(#stBeam)', opacity: 0, filter: 'url(#stBlur)' }, svg);
    const root = mk('g', { transform: `translate(${OX},${OY}) scale(${SC})` }, svg);
    // clothesline
    const line = mk('g', {}, root);
    mk('path', { d: 'M150,186 Q800,202 1450,184', fill: 'none', stroke: '#3d2c1b', 'stroke-width': 6.5, 'stroke-linecap': 'round' }, line);
    mk('path', { d: 'M150,186 Q800,202 1450,184', fill: 'none', stroke: '#a3835a', 'stroke-width': 2.4, 'stroke-dasharray': '5 7', 'stroke-linecap': 'round' }, line);
    // cloth: crisp shadow like a paper puppet show, base colour, baked weave texture
    const shadowPath = mk('path', { fill: '#000', opacity: .3, transform: 'translate(9,15)' }, root);
    const sheetBody = mk('path', { fill: 'url(#stSheet)', stroke: '#b9a57e', 'stroke-width': 1.5 }, root);
    const clothImg = mk('image', { ...ART.REG, preserveAspectRatio: 'none', 'clip-path': 'url(#stClip)' }, root);

    // projected title: an old hand-printed film title card with a misregistered yellow underprint. Each piece slams in and drops off when its time comes
    const projG = mk('g', { 'clip-path': 'url(#stClip)' }, root);
    const marginPath = mk('path', { fill: '#1a0e0a', 'fill-rule': 'evenodd', opacity: 0 }, projG);
    const gateLight = mk('rect', { ...GATE, fill: 'url(#stGate)', opacity: 0 }, projG);
    const filmG = mk('g', { 'clip-path': 'url(#stGateClip)', opacity: 0 }, projG);
    let raysD = '';
    for (let i = 0; i < 26; i++) { const a0 = i / 26 * Math.PI * 2, a1 = a0 + Math.PI / 26; raysD += `M800,443 L${f1(800 + Math.cos(a0) * 1100)},${f1(443 + Math.sin(a0) * 1100)} L${f1(800 + Math.cos(a1) * 1100)},${f1(443 + Math.sin(a1) * 1100)} Z`; }
    const rays = mk('path', { d: raysD, fill: ART.MUST, opacity: 0 }, filmG);
    const fine = mk('g', { opacity: 0 }, filmG);
    [['A KIRO PICTURE', 734], ['REEL ONE · MCMLXXV', 757]].forEach(([t, y]) => { mk('text', { x: 310, y, 'font-family': ART.TYPE, 'font-size': 18, 'letter-spacing': 2, fill: INK }, fine).textContent = t; });
    mk('circle', { cx: 1288, cy: 264, r: 18, fill: 'none', stroke: INK, 'stroke-width': 4.8, opacity: .7 }, fine); // reel-change mark
    const PIECES = [];
    const piece = (x, y, t, slide, tilt) => {
      const P = { node: mk('g', {}, filmG), x, y, t: ST.title + t, slide: ST.slide + slide, tilt, id: PIECES.length };
      P.spin = (P.id % 2 ? 1 : -1) * (16 + (P.id * 7) % 13);
      PIECES.push(P);
      return P;
    };
    const duo = (parent, size, gap, col, txt) => { // main colour over the offset yellow underprint
      const g = mk('g', {}, parent);
      for (const [c, dx, dy] of [[ART.MUST, -size * .036, size * .03], [col, 0, 0]]) mk('text', { x: f1(dx + gap / 2), y: f1(dy), 'text-anchor': 'middle', 'font-family': SLAB, 'font-size': size, 'letter-spacing': gap, fill: c }, g).textContent = txt;
      return g;
    };
    const BAT = 'M0,-6 C4,-12 9,-12 10,-5 C16,-15 30,-15 40,-4 C32,-6 28,-2 26,4 C22,0 18,0 15,5 C11,1 6,2 0,10 C-6,2 -11,1 -15,5 C-18,0 -22,0 -26,4 C-28,-2 -32,-6 -40,-4 C-30,-15 -16,-15 -10,-5 C-9,-12 -4,-12 0,-6 Z';
    const kiro = piece(800, 322, 0, .45, -.8);
    duo(kiro.node, 102, 19, INK, 'KIRO');
    mk('path', { d: ART.starPath(-243, -36, 25) + ART.starPath(243, -36, 25), fill: INK }, kiro.node);
    mk('path', { d: 'M-476,-42 H-286 M-476,-31 H-286 M286,-42 H440 M286,-31 H440', stroke: INK, 'stroke-width': 4.8, fill: 'none' }, kiro.node);
    mk('path', { d: BAT, fill: INK, transform: 'translate(-377,-72) rotate(-14) scale(.76)' }, kiro.node);
    mk('path', { d: BAT, fill: INK, transform: 'translate(390,-76) rotate(12) scale(.6)' }, kiro.node);
    const JY = [3, -4, 5, -2, 4, -5], JR = [-1.6, 1.2, -.8, 1.8, -1.4, 1]; // lines are slightly off like hand-set type
    const BIG = 'HORROR'.split('').map((ch, i) => {
      const P = piece(395 + 162 * i, 491 + JY[i], [.12, .24, .48, .6, .96, 1.08][i], [.6, .5, .75, .65, .7, .85][i], JR[i]);
      P.inner = duo(P.node, 220, 0, ART.RED, ch);
      P.o = ch === 'O'; // an eye opens inside the O
      return P;
    });
    const fitTitle = () => { // fit the letter widths to the slots (condensed poster type). Call after fonts are ready
      const c = document.createElement('canvas').getContext('2d');
      c.font = `220px ${SLAB}`;
      const wide = Math.max(...['H', 'O', 'R'].map(ch => c.measureText(ch).width));
      BIG.forEach(P => P.inner.setAttribute('transform', `scale(${Math.min(1, 158 / wide).toFixed(3)},1)`));
    };
    { // QUIZ SHOW ribbon
      const g = mk('g', { transform: 'scale(.952)' }, piece(800, 688, 1.3, 0, -1.6).node);
      mk('path', { d: 'M-338,-30 L-268,-30 L-268,44 L-338,44 L-312,7 Z M338,-30 L268,-30 L268,44 L338,44 L312,7 Z', fill: '#8a5a12', stroke: INK, 'stroke-width': 5, 'stroke-linejoin': 'round' }, g);
      mk('path', { d: 'M-292,-44 L292,-44 L292,36 L-292,36 Z', fill: ART.MUST, stroke: INK, 'stroke-width': 5, 'stroke-linejoin': 'round' }, g);
      mk('path', { d: 'M-292,36 L-268,44 L-268,22 Z M292,36 L268,44 L268,22 Z', fill: INK }, g);
      mk('text', { x: 6.5, y: 20, 'text-anchor': 'middle', 'font-family': SLAB, 'font-size': 66, 'letter-spacing': 13, fill: INK }, g).textContent = 'QUIZ SHOW';
    }
    { // tag
      const g = mk('g', { transform: 'scale(.952)' }, piece(1217, 677, 1.6, .3, 11).node);
      const burst = (n, r0, r1) => { let d = ''; for (let i = 0; i < n * 2; i++) { const a = i * Math.PI / n, q = i % 2 ? r0 : r1; d += (i ? 'L' : 'M') + f1(Math.cos(a) * q) + ',' + f1(Math.sin(a) * q); } return d + 'Z'; };
      mk('path', { d: burst(16, 66, 86), fill: ART.RED }, g);
      mk('path', { d: burst(16, 60, 76), fill: 'none', stroke: ART.CREAM, 'stroke-width': 2.2 }, g);
      [['ONE', -20, 23], ['NIGHT', 8, 27], ['ONLY!', 36, 27]].forEach(([t, y, s]) => { mk('text', { x: 0, y, 'text-anchor': 'middle', 'font-family': SLAB, 'font-size': s, fill: ART.CREAM }, g).textContent = t; });
    }

    // folds and stitching while hanging (baked art). The folds show through the projected image too
    const detail = mk('image', { ...ART.REG, preserveAspectRatio: 'none', 'clip-path': 'url(#stClip)' }, root);
    ART.textures().then(t => { if (t.cloth) clothImg.setAttribute('href', t.cloth); if (t.folds) detail.setAttribute('href', t.folds); });
    // when the ghost wears it: folds flowing from the head to the hem and a round volume
    const droopG = mk('g', { 'clip-path': 'url(#stClip)', opacity: 0 }, root);
    mk('ellipse', { cx: 752, cy: 452, rx: 150, ry: 104, fill: '#fffaf0', opacity: .14 }, droopG);
    ['M700,566 C690,650 660,740 640,808', 'M900,566 C912,650 940,740 962,808', 'M622,580 C598,660 566,744 540,802', 'M978,580 C1004,660 1036,744 1064,802', 'M800,612 C794,690 806,752 800,810'].forEach(d => {
      mk('path', { d, stroke: '#5f4627', 'stroke-width': 26, opacity: .07, fill: 'none', 'stroke-linecap': 'round' }, droopG);
      mk('path', { d, stroke: '#8a744f', 'stroke-width': 1.8, opacity: .5, fill: 'none', 'stroke-linecap': 'round' }, droopG);
    });

    // light pool, grain, darkness: all clipped to the sheet shape
    const grainPath = mk('path', { fill: 'url(#stGrain)' }, root);
    const poolPath = mk('path', { fill: 'url(#stPool)' }, root);
    const coverPath = mk('path', { fill: '#1c0f0a', opacity: .93 }, root);
    const fallPath = mk('path', { fill: 'url(#stFall)', opacity: 0 }, root);   // lobby: darker farther from the bulb
    const warmPath = mk('path', { fill: 'url(#stWarm)', opacity: 0 }, root);
    const footPath = mk('path', { fill: 'url(#stFoot)', opacity: 0 }, root);   // warm light rising from below when the ghost wears it
    // during the blackout only sleep-talk floats up in the dark
    const zzz = [0, 1, 2].map(i => { const e = mk('text', { 'font-family': SLAB, 'font-size': 40 + i * 17, fill: '#b78bff', stroke: '#2c1150', 'stroke-width': 2, opacity: 0 }, root); e.textContent = i ? 'Z' : 'z'; return e; });
    const dirt = Array.from({ length: 9 }, (_, i) => mk(i < 7 ? 'circle' : 'rect', i < 7 ? { r: 2 + (i % 3), fill: '#141011', opacity: 0 } : { width: 1.6, height: 260, fill: '#fffaf0', opacity: 0 }, root));
    // face: holes in the sheet
    const body = A.ghost_body, U = LY.ghost.w / body.w * GHOST_STAND.scale;
    const hemX = LY.ghost.cx + GHOST_STAND.x, hemY = LY.ghost.bottom + GHOST_STAND.y;
    const eyes = [[557, 412, 758, 450], [1043, 412, 842, 450]].map(([sx, sy, dx, dy], i) => {
      const g = mk('g', {}, root);
      return {
        sx, sy, dx, dy, i, g,
        stitch: mk('ellipse', { fill: 'none', stroke: '#141011', 'stroke-width': 2.2, 'stroke-dasharray': '3 6', opacity: 0 }, g),
        hole: mk('ellipse', { fill: '#0a0708' }, g),
        glow: mk('circle', { r: 18, fill: 'url(#stGlint)', opacity: 0 }, g),
        core: mk('circle', { fill: '#fff3d0', opacity: 0 }, g),
      };
    });
    const pileMarks = mk('g', { opacity: 0 }, root);
    ['M556,792 Q640,756 724,786', 'M846,790 Q934,752 1036,790', 'M616,808 Q700,790 792,808', 'M892,808 Q980,794 1074,806'].forEach(d => mk('path', { d, fill: 'none', stroke: '#7d6c4e', 'stroke-width': 2.4, opacity: .75 }, pileMarks));
    [[706, 762], [902, 766]].forEach(([cx, cy]) => {
      mk('ellipse', { cx, cy, rx: 30, ry: 8, fill: '#0a0708' }, pileMarks);
      mk('ellipse', { cx, cy, rx: 38, ry: 12, fill: 'none', stroke: '#141011', 'stroke-width': 1.8, 'stroke-dasharray': '3 5' }, pileMarks);
    });
    const mouthG = mk('g', { opacity: 0 }, root);
    const mouthD = (rx, ry) => `M${f1(-rx)},0 Q0,${f1(-ry * .55)} ${f1(rx)},0 Q0,${f1(ry)} ${f1(-rx)},0 Z`;
    const mouthStitch = mk('path', { fill: 'none', stroke: '#141011', 'stroke-width': 2, 'stroke-dasharray': '3 6' }, mouthG);
    const mouthHole = mk('path', { fill: '#0a0708', stroke: '#141011', 'stroke-width': 2.5 }, mouthG);
    const mouthThroat = mk('ellipse', { fill: '#7c0f1b', opacity: 0 }, mouthG);

    // red clothes pegs
    const pins = SHEET_PTS.slice(0, 9).map((p, k) => {
      const g = mk('g', {}, root);
      g.innerHTML = ART.pinMarkup(ART.PIN_COL[k]);
      return { g, x: p[0], rot: ART.PIN_ROT[k], t: ST.pins + PIN_ORDER.indexOf(k) * ST.pinGap, dir: k < 4 ? -1 : 1 };
    });
    // ghost light: the single bulb left on in an empty theatre
    const stand = mk('g', {}, svg);
    mk('path', { d: `M${BULB.x},${BULB.y + 24} L${BULB.x},735`, stroke: '#1a1214', 'stroke-width': 7 }, stand);
    mk('path', { d: `M${BULB.x - 34},738 L${BULB.x + 34},738 L${BULB.x + 18},722 L${BULB.x - 18},722 Z`, fill: '#1a1214' }, stand);
    const bulbGlow = mk('circle', { cx: BULB.x, cy: BULB.y, r: 150, fill: 'url(#stBulb)', opacity: 0, style: 'mix-blend-mode:screen' }, stand);
    const bulb = mk('ellipse', { cx: BULB.x, cy: BULB.y, rx: 14, ry: 18, fill: '#3a2c24' }, stand);
    mk('path', { d: `M${BULB.x - 16},${BULB.y + 18} L${BULB.x + 16},${BULB.y + 18} M${BULB.x - 16},${BULB.y} L${BULB.x + 16},${BULB.y} M${BULB.x},${BULB.y - 22} Q${BULB.x - 26},${BULB.y} ${BULB.x},${BULB.y + 22} M${BULB.x},${BULB.y - 22} Q${BULB.x + 26},${BULB.y} ${BULB.x},${BULB.y + 22}`, fill: 'none', stroke: '#1a1214', 'stroke-width': 2.2 }, stand);
    let bulbV = 0;
    const setBulb = v => {
      bulbV = clamp(v, 0, 1.6);
      bulb.setAttribute('fill', v > .05 ? '#ffe9b8' : '#3a2c24');
      bulbGlow.setAttribute('opacity', clamp(bulbV).toFixed(3));
      bulbGlow.setAttribute('r', (130 + 60 * bulbV).toFixed(0));
    };

    // film leader countdown 3-2-1 (black lines printed on film, so they read as shadows on the bright sheet)
    const leader = mk('g', { transform: 'translate(800,496)', opacity: 0 }, root);
    const leaderSweep = mk('path', { fill: INK, opacity: .16 }, leader);
    mk('circle', { r: 236, fill: 'none', stroke: INK, 'stroke-width': 13 }, leader);
    mk('circle', { r: 196, fill: 'none', stroke: INK, 'stroke-width': 4 }, leader);
    mk('path', { d: 'M-500,0 L500,0 M0,-262 L0,262', stroke: INK, 'stroke-width': 3.5, opacity: .8 }, leader);
    mk('path', { d: ART.starPath(-410, -196, 22) + ART.starPath(410, -196, 22) + ART.starPath(-410, 196, 22) + ART.starPath(410, 196, 22), fill: INK, opacity: .85 }, leader);
    const leaderNum = mk('text', { x: 0, y: 93, 'text-anchor': 'middle', 'font-family': SLAB, 'font-size': 262, fill: INK }, leader);
    leaderNum.textContent = '3';

    const motes = Array.from({ length: 22 }, (_, i) => ({ sx: Math.random() * 2 - 1, sy: Math.random() * 2 - 1, sp: .5 + Math.random(), e: mk('circle', { r: 1 + Math.random() * 1.6, fill: '#e7f0ff', opacity: 0 }, svg), i }));

    const GAZE = [[9.1, 0, .1], [9.6, 0, .1], [9.9, -.95, 0], [10.3, -.95, 0], [10.55, .95, .1], [11, .95, .1], [11.3, 0, .6]];
    const gazeAt = T => {
      if (T < GAZE[0][0]) return [0, .1];
      for (let i = 0; i < GAZE.length - 1; i++) if (T < GAZE[i + 1][0]) { const u = easeIO(seg(T, GAZE[i][0], GAZE[i + 1][0])); return [lerp(GAZE[i][1], GAZE[i + 1][1], u), lerp(GAZE[i][2], GAZE[i + 1][2], u)]; }
      return [0, .6];
    };
    const eyeOpen = (T, i) => {
      if (T < ST.blink0) return 0;
      let k = .3 * (bump(T, ST.blink0 + .05, ST.blink0 + .2) + bump(T, ST.blink0 + .32, ST.blink0 + .45));
      const t0 = i ? ST.eye2 : ST.eye1;
      k = Math.max(k, easeOut(seg(T, t0, t0 + .45)));
      let b = 0;
      for (const tb of [11.95, 13.85]) b = Math.max(b, bump(T, tb, tb + .2));
      return k * (1 - b) * (1 - .6 * bump(T, ST.yawn0, ST.yawn0 + 1.7));
    };

    // sounds fire once each on the timetable
    const CUES = [
      [ST.motor, () => Sound.cue('motor')], [ST.film, () => Sound.loop('film', true)],
      [ST.lead0, () => Sound.cue('tak')], [ST.lead0 + .9, () => Sound.cue('tak')], [ST.lead0 + 1.8, () => Sound.cue('tak')],
      [ST.title, () => Sound.bgm('opening', { fade: 2 })],   // after the countdown, the opening BGM (until the iris closes). The title's synthetic 'ta-dah' (stab) was removed on user request
      [ST.eye1, () => Sound.cue('pop')], [ST.eye2, () => Sound.cue('pop')], [ST.slide, () => Sound.cue('flap')], [ST.yawn0, () => Sound.cue('yawn')],
      ...pins.map(p => [p.t, () => Sound.cue('clip')]),
      [ST.drop, () => { Sound.loop('film', false); Sound.cue('fabric'); }], [ST.drop + .62, () => Sound.cue('tak')],
      ...WIGGLES.map(([t]) => [t, () => Sound.cue('flap')]),
      [ST.pop, () => { Sound.cue('fabric'); Sound.cue('pop'); ghostPose('surprised', 1500); }],
    ];
    let cueAt = 0;

    let glowOn = false;
    const paintSheet = T => {
      while (cueAt < CUES.length && T >= CUES[cueAt][0]) CUES[cueAt++][1]();
      const F = Math.floor(T * 12), wob = performance.now() / 1000;
      const c = easeOut(seg(T, ST.pop, ST.pop + .26)), m = easeIO(seg(T, ST.drop, ST.drop + .65));
      const flick = T < ST.beam1 ? (Math.sin(T * 61) > -.2 ? 1 : .35) : .96 + .04 * Math.abs(Math.sin(F * 12.9898));
      const beam = seg(T, ST.beam0, ST.beam1) * flick * (1 - seg(T, ST.drop, ST.drop + .25));
      const yawn = bump(T, ST.yawn0, ST.yawn0 + 1.7);

      // sheet → sagging cloth → flat heap
      const breath = (Math.sin(wob * 1.3) * .5 + .5) * .5 + yawn;
      const sp = SHEET_PTS.map((p, i) => {
        let [x, y] = p;
        if (i >= 12 && i <= 20) y += Math.sin(wob * 1.2 + x * .011) * 5 - breath * 7;
        if ((i >= 9 && i <= 11) || i >= 21) x += Math.sin(wob * .9 + i) * 3;
        return [x, y];
      });
      if (kick > .01) sp.forEach((p, i) => { p[0] += Math.sin(i * 2.1 + wob * 34) * 9 * kick; if (i >= 12 && i <= 20) p[1] -= 22 * kick * Math.abs(Math.sin(i * 1.7)); });
      pins.forEach((p, k) => {
        const s = easeOut(seg(T, p.t, p.t + .45));
        sp[k][1] += 40 * s;
        if (k === 0) { sp[23][1] += 22 * s; sp[23][0] += 8 * s; }
        if (k === 8) { sp[9][1] += 22 * s; sp[9][0] -= 8 * s; }
      });
      const fy = T >= ST.drop ? Math.min(620, 1300 * Math.pow(T - ST.drop, 2)) : 0;
      // wriggle: only the top of the cloth rises; the hem stays on the floor. Just before it bursts, the whole thing swells
      const wiggle = (x, y) => {
        let h = 40 * easeIO(seg(T, ST.pop - .4, ST.pop)) * (1 - seg(T, ST.pop, ST.pop + .1));
        for (const [t, wx, a] of WIGGLES) h += a * bump(T, t, t + .3) * Math.exp(-Math.pow((x - wx) / 120, 2));
        return h * clamp((814 - y) / 300);
      };
      const pts = sp.map((p, i) => {
        const hx = lerp(DROOP_PTS[i][0], PILE_PTS[i][0], c), hy = lerp(DROOP_PTS[i][1], PILE_PTS[i][1], c);
        return [lerp(p[0], hx, m), Math.min(814, lerp(p[1] + fy, hy - wiggle(hx, hy), m))];
      });
      // sag between pegs: insert sagging points between the top points. When it starts to fall, the sag releases
      const ext = [];
      pts.forEach((p, i) => { ext.push(p); if (i < 8) { const q = pts[i + 1]; ext.push([(p[0] + q[0]) / 2 + (i % 2 ? 6 : -5) * (1 - m), (p[1] + q[1]) / 2 + ART.SAG[i] * (1 - m)]); } });
      const d = smooth(ext);
      for (const e of [shadowPath, sheetBody, sheetClip, grainPath, poolPath, coverPath, fallPath, warmPath, footPath]) e.setAttribute('d', d);
      marginPath.setAttribute('d', d + GATE_D);
      detail.setAttribute('opacity', 1 - seg(T, ST.drop, ST.drop + .4));
      line.setAttribute('opacity', beam * .9 + (.1 + lobbyK * .6) * (1 - seg(T, ST.drop, ST.drop + .5)));
      grainP.setAttribute('patternTransform', `translate(${(F * 67) % 180},${(F * 41) % 180})`);
      poolPath.setAttribute('opacity', beam);
      coverPath.setAttribute('opacity', ((1 - beam) * lerp(lerp(lerp(.93, .66, seg(T, ST.drop, ST.drop + .4)), .48, seg(T, ST.wig0, ST.pop)), .2, seg(T, ST.pop, ST.pop + .25)) * (1 - lobbyK * .66)).toFixed(3));
      fallPath.setAttribute('opacity', lobbyK.toFixed(3));
      footPath.setAttribute('opacity', (m * (1 - c) * (1 - beam) * .9).toFixed(3));
      droopG.setAttribute('opacity', (m * (1 - c)).toFixed(3));
      gateLight.setAttribute('opacity', beam.toFixed(3));
      marginPath.setAttribute('opacity', (beam * .4).toFixed(3));
      shadowPath.setAttribute('opacity', (.3 * (1 - m)).toFixed(3));
      warmPath.setAttribute('opacity', (lobbyK * clamp(bulbV)).toFixed(3));

      zzz.forEach((e, i) => {
        const u = (wob * .55 + i * .31) % 1, on = lobbyK ? 0 : Math.sin(u * Math.PI) * (1 - seg(T, ST.beam0 - .2, ST.beam0 + .1));
        set(e, { x: f1(905 + i * 52 + Math.sin(u * 5 + i) * 9), y: f1(470 - i * 44 - u * 70), opacity: on.toFixed(2) });
      });

      // projector light and dust
      set(beamCone, { d: 'M788,990 L812,990 L1420,60 L180,60 Z', opacity: beam * .3 });
      motes.forEach(o => {
        const y = 960 - ((o.sp * wob * 22 + (o.sy + 1) * 400) % 760), k = (960 - y) / 930;
        set(o.e, { cx: f1(800 + o.sx * lerp(10, 620, k) + Math.sin(wob * .7 + o.i) * 6), cy: f1(y), opacity: (beam * .5 * (.4 + .6 * Math.abs(Math.sin(F * .5 + o.i * 2.1)))).toFixed(2) });
      });

      // title: each piece slams in and drops off when due. Moves at 12 frames per second like a paper puppet show
      const Tq = F / 12, jx = Math.sin(F * 91.3) * 1.2, jy = Math.sin(F * 47.7) * 1.2, wave = x => Math.sin(wob * 1.2 + x * .011) * 3;
      const lit = T >= ST.title - .1 ? beam : 0, shown = seg(T, ST.title, ST.title + .25) * (1 - seg(T, ST.slide + .2, ST.slide + .9));
      filmG.setAttribute('opacity', lit.toFixed(3));
      rays.setAttribute('opacity', (.3 * shown).toFixed(3));
      fine.setAttribute('opacity', (.9 * shown).toFixed(3));
      const blink = 1 - .5 * (bump(T, ST.blink0 + .05, ST.blink0 + .2) + bump(T, ST.blink0 + .32, ST.blink0 + .45));
      for (const P of PIECES) {
        if (T < P.t) { P.node.setAttribute('opacity', 0); continue; }
        const s = 1 + .35 * (1 - easeOut(seg(Tq, P.t, P.t + .14)));
        let x = P.x + jx, y = P.y + jy + wave(P.x), rot = P.tilt, op = P.o ? blink : 1;
        if (Tq >= P.slide) {
          const dt = Tq - P.slide;
          y += 30 * dt + 1000 * dt * dt; x += P.spin * 2.2 * dt; rot += P.spin * 5 * dt;
          if (y > 1000) op = 0;
        } else if (Tq >= P.slide - .25) rot += Math.sin(F * 2.4 + P.id) * 3; // dangles just before it drops
        P.node.setAttribute('transform', `translate(${f1(x)},${f1(y)}) rotate(${f1(rot)}) scale(${s.toFixed(3)})`);
        P.node.setAttribute('opacity', op.toFixed(2));
      }
      const dirtOn = T >= ST.title && T < ST.drop ? lit : 0;
      dirt.forEach((e, i) => {
        const k = F >> 1, h = (a, b) => Math.abs(Math.sin(a * 12.9898 + b * 78.233) * 43758.5453) % 1;
        if (i < 7) set(e, { cx: f1(300 + h(k, i) * 1000), cy: f1(220 + h(k, i + 9) * 520), opacity: (dirtOn * (h(k, i + 20) > .5 ? .55 : 0)).toFixed(2) });
        else set(e, { x: f1(300 + h(k >> 2, i) * 1000), y: 200, opacity: (dirtOn * (h(k, i + 30) > .65 ? .25 : 0)).toFixed(2) });
      });

      // 3-2-1
      const leadOn = T >= ST.lead0 && T < ST.title;
      leader.setAttribute('opacity', leadOn ? (beam * .86).toFixed(3) : 0);
      if (leadOn) {
        const u = (T - ST.lead0) / .9, i = Math.min(2, Math.floor(u)), a = (u - i) * Math.PI * 2 * .999, R = 240;
        leaderNum.textContent = String(3 - i);
        leader.setAttribute('transform', `translate(${f1(800 + Math.sin(F * 31.7) * 2.5)},${f1(496 + Math.sin(F * 17.3) * 2.5)})`); // the film jitters in the projection window
        leaderSweep.setAttribute('d', `M0,0 L0,${-R} A${R},${R} 0 ${a > Math.PI ? 1 : 0},1 ${f1(Math.sin(a) * R)},${f1(-Math.cos(a) * R)} Z`);
      }

      // eyes and mouth
      const place = (sx, sy, dx, dy) => {
        const y = lerp(sy + wave(sx) * (1 - m) + fy, dy - wiggle(dx, dy), m) + c * 240;
        return [lerp(sx, dx, m), y];
      };
      const scale = lerp(1, .7, m), [gzx, gzy] = gazeAt(T), alive = 1 - seg(T, ST.die, ST.die + .35), gone = 1 - seg(T, ST.pop, ST.pop + .12);
      eyes.forEach(e => {
        const open = eyeOpen(T, e.i), [x, y] = place(e.sx, e.sy, e.dx, e.dy);
        const rx = 34 * scale, ry = 56 * scale, rr = Math.max(1.5, ry * open);
        e.g.setAttribute('transform', `translate(${f1(x)},${f1(y)})`);
        e.g.setAttribute('opacity', gone.toFixed(2));
        e.g.style.visibility = T < ST.blink0 ? 'hidden' : '';
        set(e.hole, { rx: f1(rx), ry: f1(rr) });
        set(e.stitch, { rx: f1(rx + 10), ry: f1(ry + 10), opacity: seg(T, ST.slide, ST.slide + .5).toFixed(2) });
        const hx = gzx * 14 * scale, hy = gzy * 22 * scale;
        set(e.glow, { cx: f1(hx), cy: f1(hy), opacity: open > .05 ? (.6 * alive).toFixed(2) : 0 });
        set(e.core, { cx: f1(hx), cy: f1(hy), r: 5.5, opacity: open > .3 ? alive.toFixed(2) : 0 });
      });
      const [mx, my] = place(800, 566, 800, 520);
      pileMarks.setAttribute('opacity', seg(T, ST.pop + .12, ST.pop + .3).toFixed(2));
      const mOpen = T >= ST.yawn0 ? easeOut(seg(T, ST.yawn0, ST.yawn0 + .55)) * (1 - easeIO(seg(T, ST.yawn0 + 1.1, ST.yawn0 + 1.7))) + .06 : 0;
      const mrx = lerp(50, 40, clamp(mOpen * 1.4)), mry = 3 + 64 * mOpen;
      mouthG.setAttribute('opacity', T >= ST.yawn0 - .05 ? gone.toFixed(2) : 0);
      mouthG.setAttribute('transform', `translate(${f1(mx)},${f1(my)}) scale(${scale.toFixed(3)})`);
      mouthHole.setAttribute('d', mouthD(mrx, mry));
      mouthStitch.setAttribute('d', mouthD(mrx + 9, mry + 8));
      set(mouthThroat, { cy: f1(mry * .45), rx: f1(mrx * .5), ry: f1(mry * .3), opacity: (clamp(mOpen * 1.5) * .8).toFixed(2) });

      // pegs
      pins.forEach((p, k) => {
        if (T < p.t) { p.g.setAttribute('transform', `translate(${p.x},190) rotate(${(p.rot + Math.sin((F >> 2) * 3.1 + k) * 2).toFixed(1)}) scale(1.45)`); p.g.setAttribute('opacity', clamp(.1 + .9 * beam + lobbyK * .7).toFixed(2)); return; }
        const dt = T - p.t, y = 190 - 240 * dt + 1100 * dt * dt;
        p.g.setAttribute('transform', `translate(${f1(p.x + p.dir * (k === 4 ? .4 : 1) * 110 * dt)},${f1(y)}) rotate(${f1(p.rot + p.dir * 640 * dt)}) scale(1.45)`);
        p.g.setAttribute('opacity', y > 900 ? 0 : 1);
      });

      // The real ghost already stands inside the cloth; the moment the cloth collapses, its glow spreads over the stage
      if (T >= ST.wig0) ghost.box.style.opacity = 1;
      if (T >= ST.pop && !glowOn) {
        glowOn = true;
        light.rx = light.ry = 1;
        target.fx = light.fx = hemX; target.fy = light.fy = hemY - body.h * U * .45;
        target.rx = 560; target.ry = 500;
      }
    };

    /* ---- Lobby: the cast board on an old theatre wall (KHQS_v12). QR on the left, three TONIGHT'S CAST cards on the right ----
     * The background is one image; QR, names, portraits, bulb flicker and the start sign go on top. Positions are in CAST.
     * The sheet stage waits behind this wall with the lights off */
    const ui = el('div', 'abs lobby', stage, { left: 0, top: 0, width: '1600px', height: '900px', zIndex: 30, overflow: 'hidden', background: '#050208' });
    const wallImg = img('lobby', ui, 1600); wallImg.className = 'abs cb-plate';
    el('div', 'abs cb-dull', ui);                 // faded theatre back room: darken the edges (saturation/brightness via the .lobby filter)
    const outDark = img('lobby_dark', ui, 1600); outDark.className = 'abs cb-plate'; outDark.style.opacity = 0;
    // bulbs: cover a circle around one bulb of the unlit background to switch that bulb off
    const bulbs = CAST.bulbs.map(([x, y, r = 30]) => ({
      e: el('div', 'abs cb-bulb', ui, { left: x - r + 'px', top: y - r + 'px', width: 2 * r + 'px', height: 2 * r + 'px', backgroundImage: `url(${A.lobby_dark.src})`, backgroundPosition: `${r - x}px ${r - y}px`, opacity: 0 }),
      off: [], dead: false, was: false, next: performance.now() + 400 + Math.random() * 9000,
    }));
    const blink = (b, at, ms) => b.off.push([at, at + ms]);
    const paintBulbs = now => bulbs.forEach((b, i) => {
      if (now >= b.next) { // old bulbs: now and then flicker once or twice. A few do it unusually often
        const ms = 40 + Math.random() * 130;
        blink(b, now, ms);
        if (Math.random() < .4) blink(b, now + ms + 60 + Math.random() * 90, 30 + Math.random() * 80);
        b.next = now + (CAST.badBulbs.includes(i) ? 500 + Math.random() * 2600 : 5000 + Math.random() * 16000);
      }
      b.off = b.off.filter(o => o[1] > now);
      const off = b.dead || b.off.some(o => o[0] <= now);
      if (i === LAMP) {   // the wall lamp wavers slightly even when on, and its occasional flicker only sags, never goes out (it goes out only at power-up and blackout)
        b.e.style.opacity = b.dead ? 1 : off ? .55 : lampSag(now).toFixed(3);
        b.was = b.dead; return;
      }
      if (off !== b.was) { b.was = off; b.e.style.opacity = off ? 1 : 0; }
    });
    /* Wall lamp: old wiring makes its brightness ripple very slightly, with an occasional short sag. The value is how much of the unlit art covers it (0 = fully on) */
    const LAMP = CAST.marquee, LAMP_AT = [497, 170];
    let sagUntil = 0, sagDepth = 0, sagNext = performance.now() + 2500;
    const lampSag = now => {
      const t = now / 1000;
      if (now >= sagNext) { sagUntil = now + 70 + Math.random() * 160; sagDepth = .18 + Math.random() * .2; sagNext = now + 1800 + Math.random() * 5200; }
      const hum = .05 + .035 * Math.sin(t * 7.3) + .025 * Math.sin(t * 13.7 + 1.3) + .02 * Math.sin(t * 2.1 + .4);
      return clamp(hum + (now < sagUntil ? sagDepth : 0), 0, .5);
    };
    const chase = (rounds = 2, gap = 30) => { // the sign bulbs chase one lap at a time (registration done)
      const now = performance.now(), n = CAST.marquee;
      for (let r = 0; r < rounds; r++) for (let k = 0; k < n; k++) blink(bulbs[k], now + (r * n + k) * gap, gap * 2.4);
    };

    // things on the wall. When the power goes they all darken together
    const over = el('div', 'abs', ui, { left: 0, top: 0, width: '1600px', height: '900px' });
    const outBlack = el('div', 'abs', ui, { left: 0, top: 0, width: '1600px', height: '900px', background: '#050208', opacity: 0, pointerEvents: 'none' });
    /* A few moths around the wall lamp. They whirl in the light under the shade and now and then bonk into the bulb and bounce off.
     * Brighter the closer they are to the bulb; invisible while the lamp is off (before power-up, flickers, blackout) */
    const mothLayer = el('div', 'abs', ui, { left: 0, top: 0, width: '1600px', height: '900px', pointerEvents: 'none' });
    ui.insertBefore(mothLayer, over);
    const moths = [0, 1, 2, 3, 4].map(i => {
      const e = el('div', 'abs', mothLayer, { left: 0, top: 0, width: '14px', height: '10px' });
      e.innerHTML = '<svg viewBox="-7 -5 14 10" width="14" height="10" overflow="visible"><g class="w" fill="#f0dfba" stroke="#3a2614" stroke-width=".9" stroke-linejoin="round">'
        + '<path d="M0 0 L-6.5 -3.6 Q-7.2 0 -5.2 2.4 Z"/><path d="M0 0 L6.5 -3.6 Q7.2 0 5.2 2.4 Z"/></g><ellipse rx="1.1" ry="2.8" fill="#4a3220"/></svg>';
      const s = i * 2.39 + 1;
      return { e, w: e.querySelector('.w'), s, R: 42 + (i % 3) * 26, sp: (i % 2 ? 1 : -1) * (1.1 + (i * .37) % .9), size: .5 + (i * .29) % .25 };   // small enough to barely notice (wingspan 7–10 px)
    });
    const paintMoths = (now, lit) => {
      mothLayer.style.opacity = lit ? 1 : 0;
      if (!lit) return;
      const t = now / 1000, glow = 1 - lampSag(now) * 1.4;
      for (const m of moths) {
        const a = m.s + t * m.sp + 1.3 * Math.sin(t * .8 + m.s);
        let r = m.R + 22 * Math.sin(t * 1.7 + m.s * 3);
        const bump = Math.sin(t * .45 + m.s * 5);                       // now and then dives at the bulb and bounces off
        if (bump > .93) r *= lerp(1, .15, Math.sin((bump - .93) / .07 * Math.PI));
        const x = LAMP_AT[0] + r * Math.cos(a) + 5 * Math.sin(t * 17 + m.s);
        const y = LAMP_AT[1] + 22 + r * .5 * Math.sin(a) + 6 * Math.sin(t * 21 + m.s * 2);   // toward the light under the shade
        const d = Math.hypot(x - LAMP_AT[0], (y - LAMP_AT[1]) * 1.6), near = clamp(1 - d / 150);
        m.e.style.transform = `translate(${(x - 7).toFixed(1)}px, ${(y - 5).toFixed(1)}px) scale(${m.size.toFixed(2)}) rotate(${(Math.cos(a) * 25).toFixed(0)}deg)`;
        m.w.setAttribute('transform', `scale(1 ${(Math.floor(now / 42 + m.s * 7) % 2 ? .35 : 1)})`);   // wingbeat: flaps every frame
        m.e.style.opacity = (.35 + .65 * near).toFixed(2);
        m.e.style.filter = `brightness(${(glow * lerp(.55, 1.35, near)).toFixed(2)})`;
      }
    };
    const dim = k => { outDark.style.opacity = k; over.style.filter = k ? `brightness(${lerp(1, .45, k).toFixed(3)}) saturate(${lerp(1, .85, k).toFixed(3)})` : ''; }; // .45: matches the paper brightness of the unlit background

    // QR: stick a note printed with the real join URL on the frame's blank paper. If phones cannot reach the URL, print a notice instead
    const joinUrl = lobbyJoinUrl();
    {
      const [x0, y0, x1] = CAST.qr, s = x1 - x0;
      const slip = el('div', 'abs cb-qr', over, { left: x0 + 'px', top: y0 + 'px', width: s + 'px', height: s + 'px', rotate: CAST.qrRot + 'deg' });
      if (joinUrl) {
        const q = window.KHQS_QR(joinUrl), pad = 13, m = (s - 2 * pad) / q.size, w = (m + .04).toFixed(3);
        let d = '';
        for (let y = 0; y < q.size; y++) for (let x = 0; x < q.size; x++) if (q.at(x, y)) d += `M${(pad + x * m).toFixed(2)},${(pad + y * m).toFixed(2)}h${w}v${w}h-${w}z`;
        slip.innerHTML = `<svg viewBox="0 0 ${s} ${s}" width="${s}" height="${s}"><path d="${d}" fill="#1c1210"/></svg>`;
        slip.setAttribute('aria-label', 'QR code to join from your phone');
      } else {
        slip.classList.add('cb-noqr');
        slip.innerHTML = '<b>NO PHONE<br>NEEDED</b><span>TYPE YOUR NAME<br>ON A CARD</span>';
      }
    }

    /* Cards: a copy of the card art (mover) sits on top of the card painted in the background and does the moving. At rest it overlaps the background invisibly.
     * q is the "?" silhouette face, blank the empty paper face. The portrait (face) and name (name) are printed on top */
    const seeded = s => () => (s = (s * 16807 + 11) % 2147483647) / 2147483647;
    const cards = CAST.cards.map(([x0, y0, x1, y1], i) => {
      const w = x1 - x0, h = y1 - y0, S = A.lobby_cards;
      const box = el('div', 'abs cb-card', over, { left: x0 + 'px', top: y0 + 'px', width: w + 'px', height: h + 'px' });
      const gap = el('div', 'abs cb-gap', box);
      const mover = el('div', 'abs cb-mover', box);
      el('div', 'abs cb-side', mover, { backgroundImage: `url(${A.lobby.src})`, backgroundSize: '1600px 900px', backgroundPosition: `${-x0}px ${-y0}px` });
      const blank = el('div', 'abs cb-side', mover, { backgroundImage: `url(${S.src})`, backgroundSize: `${S.w}px ${S.h}px`, backgroundPosition: `${S.x - x0}px ${S.y - y0}px`, opacity: 0 });
      const face = el('div', 'abs cb-face', mover, { width: (w - 52) + 'px', height: '190px' });
      const name = el('div', 'abs cb-name han', mover);
      return { i, w, h, box, gap, mover, blank, face, name, tk: 0, tilt: [-.9, .7, -.6][i], printRot: [-3.2, 2.4, -1.6][i] };
    });
    const cardRest = (c, on) => { c.mover.style.transform = on ? `rotate(${c.tilt}deg)` : ''; c.gap.style.opacity = on ? 1 : 0; };
    const showFace = (c, p) => { // draw the card content at once with no motion. Returns the letters to stamp one by one
      c.blank.style.opacity = p ? 1 : 0;
      c.face.innerHTML = ''; c.name.innerHTML = '';
      c.face.style.opacity = ''; c.face.style.scale = '';
      c.box.classList.toggle('cb-away', !!p && p.connected === false);
      if (!p) return [];
      // portrait: the current monster art as if printed on paper. The red underplate is slightly off and the whole thing a little crooked
      const k = `fan_${fanKey(p.fanType)}_idle`, a = A[k], fw = c.w - 52, fh = 190;
      const pw = Math.min(fw * .88, (fh - 10) * a.w / a.h), ph = pw * a.h / a.w;
      for (const cls of ['cb-under', '']) {
        const e = img(k, c.face, pw); e.className = `abs cb-print ${cls}`;
        e.style.left = (fw - pw) / 2 + 'px'; e.style.top = (fh - ph + 6) + 'px';
      }
      c.face.style.rotate = c.printRot + 'deg';
      // name: each letter differs slightly in height, tilt and ink. Long names shrink to fit
      const chars = [...p.name], units = chars.reduce((s, ch) => s + (ch.charCodeAt(0) < 128 ? .62 : 1), 0);
      c.name.style.fontSize = Math.min(40, Math.floor(176 / Math.max(1, units))) + 'px';
      const r = seeded(977 + c.i * 131 + chars.reduce((s, ch) => s + ch.codePointAt(0), 0));
      return chars.map(ch => {
        const s = el('span', '', c.name);
        s.textContent = ch === ' ' ? ' ' : ch;
        s.style.transform = `translateY(${((r() - .5) * 4.4).toFixed(1)}px) rotate(${((r() - .5) * 7).toFixed(1)}deg)`;
        s.style.opacity = (.7 + r() * .3).toFixed(2);
        return s;
      });
    };
    const drawCard = i => { const c = cards[i], p = seats[i].player; c.tk++; showFace(c, p); cardRest(c, !!p); };
    // registration: clunk → clack (flips to blank paper) → the name letter by letter → portrait stamp bang → bulbs chase and the card settles
    const fill = async i => {
      const c = cards[i], p = seats[i].player, tk = ++c.tk, live = () => c.tk === tk && !disposed && seats[i].player === p;
      const lin = { ease: k => k };
      Sound.cue('clip');
      c.gap.style.opacity = 1;
      await anim(280, k => { const d = 1 - k; c.mover.style.transform = `translate(${(Math.sin(k * 31) * 3 * d).toFixed(1)}px, ${(-Math.abs(Math.sin(k * 19)) * 4 * d).toFixed(1)}px) rotate(${(Math.sin(k * 25) * 2.6 * d).toFixed(2)}deg)`; }, lin);
      if (!live()) return;
      Sound.cue('tak');
      await anim(130, k => { c.mover.style.transform = `perspective(600px) rotateX(${(k * k * 90).toFixed(1)}deg)`; }, lin);
      if (!live()) return;
      const letters = showFace(c, p);
      c.face.style.opacity = 0;
      letters.forEach(s => { s.style.visibility = 'hidden'; });
      Sound.cue('clip');
      await anim(220, k => { c.mover.style.transform = `perspective(600px) rotateX(${(-90 * (1 - backOut(k))).toFixed(1)}deg)`; }, lin);
      if (!live()) return;
      c.mover.style.transform = `rotate(${c.tilt}deg)`;
      for (const s of letters) {
        await wait(70 + Math.random() * 80);
        if (!live()) return;
        s.style.visibility = '';
        Sound.cue('tick');
      }
      await wait(140);
      if (!live()) return;
      Sound.cue('handbell', { f: 1568 }); // the bell at the end of the line
      await wait(260);
      if (!live()) return;
      Sound.cue('stamp');
      await anim(100, k => { c.face.style.opacity = k; c.face.style.scale = lerp(1.6, 1, k).toFixed(3); }, { ease: k => k * k });
      if (!live()) return;
      chase();
      await anim(440, k => { const d = 1 - k; c.mover.style.transform = `translateY(${(Math.sin(k * 22) * 5 * d * d).toFixed(1)}px) rotate(${(c.tilt + Math.sin(k * 18) * 2.2 * d).toFixed(2)}deg)`; }, lin);
      if (live()) cardRest(c, true);
    };
    const vacate = async i => { // when a seat empties, the card flips back to the "?" face
      const c = cards[i], tk = ++c.tk, live = () => c.tk === tk && !disposed;
      if (+c.blank.style.opacity === 0) return cardRest(c, false);
      Sound.cue('flap');
      c.gap.style.opacity = 1;
      await anim(130, k => { c.mover.style.transform = `perspective(600px) rotateX(${(k * k * 90).toFixed(1)}deg)`; }, { ease: k => k });
      if (!live()) return;
      showFace(c, null);
      await anim(200, k => { c.mover.style.transform = `perspective(600px) rotateX(${(-90 * (1 - backOut(k))).toFixed(1)}deg)`; }, { ease: k => k });
      if (live()) cardRest(c, false);
    };

    // typing a name on the PC: type straight onto the first empty card's name tag
    const form = el('form', 'abs cb-entry', over);
    const input = el('input', '', form);
    input.maxLength = 12; input.placeholder = 'TYPE YOUR NAME'; input.autocomplete = 'off'; input.setAttribute('aria-label', 'Your stage name');
    const errEl = el('div', 'abs cb-err', over);
    errEl.setAttribute('role', 'alert');
    const submit = async e => {
      e.preventDefault();
      const name = input.value.trim();
      if (!name) return;
      Sound.unlock();
      errEl.textContent = '';
      const r = await lobbyEntry().join(name);
      if (r && r.error) { errEl.textContent = r.error; return; }
      input.value = '';
      if (!disposed && lobbyOn && !/clean/.test(location.hash)) input.focus();
    };
    form.addEventListener('submit', submit);

    /* Start sign IT'S SHOWTIME!: once anyone has registered, it rattles up from behind the shelf under the board. Clicking it starts the show.
     * The lit art (showtime_on) is layered over the unlit art (showtime_off) and shown or hidden */
    const SG = CAST.sign;
    const sw = SG.w, sh = Math.round(sw * A.showtime_on.h / A.showtime_on.w);
    const pit = el('div', 'abs', over, { left: (SG.cx - sw / 2 - 30) + 'px', top: (SG.floor - sh - 40) + 'px', width: (sw + 60) + 'px', height: (sh + 40) + 'px', overflow: 'hidden' });
    const startBtn = el('button', 'abs cb-sign', pit, { left: '30px', top: '40px', width: sw + 'px', height: sh + 'px' });
    startBtn.type = 'button'; startBtn.disabled = true;
    startBtn.setAttribute('aria-label', 'Start the show');
    img('showtime_off', startBtn);
    const signLamp = img('showtime_on', startBtn);
    const signLit = v => { signLamp.style.opacity = v; };
    let signUp = false, signTk = 0, signY = 1, signLive = false, signNext = 0;
    const setSignY = v => { signY = v; startBtn.style.translate = `0 ${(v * (sh + 44)).toFixed(1)}px`; };

    /* Pointer (KHQS_v18, tools/build_pointer.py): shortly after the sign lights up, an old-fashioned pointing hand (☞, same voice as the JOIN poster) and
     * the word CLICK! pop out to the left of the sign. The hand pokes the sign and the word blinks. It tells first-time visitors the sign is a button.
     * The delivered art was a plywood picket, but it looked crude, so only the hand and the word are cut out and floated like UI elements (2026-11-15) */
    // The word sits above the hand (on the dark wooden wall; on the red strip below the hand it was unreadable). y is the top of the word; the fingertip is just in front of the sign's left end (about x 805) at the height of the sign's lettering
    const PT = { x: 613, y: 672, w: 190, wordW: 132 };
    const ptHandH = Math.round(PT.w * A.pointer_hand.h / A.pointer_hand.w), ptWordH = Math.round(PT.wordW * A.pointer_word.h / A.pointer_word.w);
    const pointer = el('div', 'abs', over, { left: PT.x + 'px', top: PT.y + 'px', width: PT.w + 'px', height: (ptWordH + 4 + ptHandH) + 'px', pointerEvents: 'none', transformOrigin: '100% 70%', scale: 0 });
    const ptHand = img('pointer_hand', pointer, PT.w);
    Object.assign(ptHand.style, { position: 'absolute', left: 0, top: (ptWordH + 4) + 'px', filter: 'drop-shadow(0 3px 4px rgba(0,0,0,.55))' });
    const ptWord = img('pointer_word', pointer, PT.wordW);
    Object.assign(ptWord.style, { position: 'absolute', left: ((PT.w - PT.wordW) / 2 - 10) + 'px', top: 0 });
    let ptOn = false, ptTk = 0, ptT0 = 0, ptKnock = -1;
    const setPtS = v => { pointer.style.scale = v.toFixed(3); };
    const showPointer = async up => {
      const tk = ++ptTk;
      if (!up) { if (!ptOn) return; ptOn = false; return anim(180, k => { if (tk === ptTk) setPtS(1 - k); }, { ease: k => k * k }); }
      await wait(900);
      if (tk !== ptTk || disposed || !signLive) return;
      Sound.cue('whistleUp'); Sound.cue('pop');
      ptOn = true; ptT0 = performance.now(); ptKnock = -1;
      return anim(380, k => { if (tk === ptTk) setPtS(backOut(k)); }, { ease: k => k });
    };
    // every frame (lobby loop): the hand pokes twice every 1.6 s; the word lights and dims every 0.45 s
    const paintPointer = now => {
      if (!ptOn) return;
      const t = (now - ptT0) % 1600, poke = q => (q >= 0 && q < 170 ? Math.sin(q / 170 * Math.PI) : 0);
      ptHand.style.translate = `${(11 * (poke(t) + poke(t - 260))).toFixed(1)}px 0`;
      // 'tap tap' the moment the fingertip touches the sign (middle of the poke). It would get annoying, so only the first three (1.6 s × 3)
      const cyc = Math.floor((now - ptT0) / 1600), hitN = cyc * 2 + (t >= 345 ? 1 : 0);
      if (cyc < 3 && t >= 85 && hitN > ptKnock) { ptKnock = hitN; Sound.cue('knock', { f: t >= 345 ? 820 : 900 }); }
      const lit = Math.floor((now - ptT0) / 450) % 2 === 0;
      ptWord.style.filter = lit ? 'brightness(1.3) saturate(1.15) drop-shadow(0 0 6px rgba(255,140,50,.95))' : 'drop-shadow(0 2px 3px rgba(0,0,0,.6))';
    };
    setSignY(1); signLit(0);
    const raiseSign = async up => {
      if (up === signUp) return;
      signUp = up;
      const tk = ++signTk, live = () => tk === signTk && !disposed;
      signLive = false;
      if (!up) {
        showPointer(false);
        startBtn.disabled = true; signLit(0); Sound.cue('tak');
        const y0 = signY;
        return anim(260, k => { if (live()) setSignY(lerp(y0, 1, k)); }, { ease: k => k * k });
      }
      const stops = [signY, .7, .76, .42, .5, .16, .22, -.03, 0]; // like winding up with a crank: rises, then sinks back a little, repeatedly
      for (let n = 1; n < stops.length; n++) {
        const a = stops[n - 1], b = stops[n], rise = b < a;
        if (rise) Sound.cue('tak');
        // metal 'creak' (sample, OPENING_SOUND_FILES.creak in index.html): on the first and third of four winds, the second a bit higher. Synthetic if the sample is missing
        if (n === 1 || n === 5) Sound.cue('creak', { f: 470 + n * 20 + Math.random() * 30, rate: (n === 1 ? 1 : 1.08) + Math.random() * .04, gain: .5 });
        await anim(rise ? 120 : 70, k => { if (live()) setSignY(lerp(a, b, k)); }, { ease: k => k });
        if (!live()) return;
        await wait(rise ? 40 : 90);
        if (!live()) return;
      }
      for (const [v, ms] of [[1, 60], [0, 150], [1, 40], [0, 230], [1, 90], [0, 60], [1, 0]]) { // bad contact: flickers a few times, then lights
        signLit(v);
        if (v) Sound.cue('tick');
        if (ms) await wait(ms);
        if (!live()) return;
      }
      Sound.cue('ding');
      startBtn.disabled = false;
      signLive = true; signNext = performance.now() + 1500 + Math.random() * 3000;
      showPointer(true);
    };
    startBtn.addEventListener('click', () => {
      if (startBtn.disabled) return;
      Sound.unlock();
      startBtn.disabled = true; signLive = false; signLit(1);
      showPointer(false);
      Sound.cue('handbell', { f: 880 }); Sound.cue('clip');
      lobbyEntry().start();
    });

    const syncEntry = () => {
      const n = seats.filter(s => s.player).length, v = seats.findIndex(s => !s.player);
      form.style.display = v < 0 ? 'none' : '';
      if (v >= 0) { const [x0, y0, x1] = CAST.cards[v]; Object.assign(form.style, { left: (x0 + 30) + 'px', top: (y0 + 221) + 'px', width: (x1 - x0 - 58) + 'px' }); }
      if (v < 0) errEl.textContent = 'HOUSE FULL'; else if (errEl.textContent === 'HOUSE FULL') errEl.textContent = '';
      if (lobbyOn) raiseSign(n > 0);
    };

    /* Power-up: when the lobby first appears. On a dark wall with only candles, the switch goes up, the wall lamp flickers on,
     * the sign bulbs come on in one lap from the top left, then the frame bulbs light. Pairs with the blackout at the end (wallOut) */
    const lightsUp = async () => {
      const on = () => lobbyOn && !disposed;
      bulbs.forEach(b => { b.dead = true; });
      dim(1);
      await wait(900);
      if (!on()) return;
      Sound.cue('tak');
      for (const [v, ms] of [[.5, 70], [1, 120], [.35, 50], [.8, 160], [.3, 0]]) { // wall lamp: the contact connects and drops
        dim(v); bulbs[CAST.marquee].dead = v > .6;
        if (ms) await wait(ms);
        if (!on()) return;
      }
      for (let k = 0; k < bulbs.length; k++) {
        if (k === CAST.marquee) continue;
        bulbs[k].dead = false;
        if (k % 2 === 0) Sound.cue('tick');
        dim(.3 * (1 - (k + 1) / bulbs.length));
        await wait(k < CAST.marquee ? 55 : 130);
        if (!on()) return;
      }
      dim(0);
      Sound.cue('ding');
      chase(1, 24);
    };

    // set the stage side to the darkness just after the fuse blows. When the wall goes dark, the projector runs in this darkness
    const fuseState = () => {
      setBulb(0);
      kick = 0; lobbyK = 0;
      light.dark = target.dark = .97;
      light.rx = target.rx = light.ry = target.ry = 1600;
      ghostLit.aud = .1;
      paintSheet(0);
    };
    /* Blackout: when the switch is thrown the old wiring gives up. The bulbs flare once, then die one by one,
     * leaving only the candles, the lantern and the pumpkin. One gust blows out the candles and lantern; the pumpkin goes a little later. step belongs to the run that accepts skipping */
    const wallOut = async step => {
      signLive = false;
      if (ptOn) { ptTk++; ptOn = false; setPtS(0); }
      signLit(1);
      Sound.cue('saw', { dur: .7 });
      wallImg.style.filter = 'brightness(1.28) saturate(1.1)';
      await step(wait(140));
      wallImg.style.filter = '';
      bulbs.forEach(b => { b.dead = false; b.e.style.opacity = 0; });
      dim(0);
      const order = bulbs.map((_, n) => n).sort(() => Math.random() - .5);
      order.forEach((n, k) => { bulbs[n].dieAt = (k + Math.random() * .6) / (order.length + 1); });
      let pops = 0;
      await step(anim(640, k => {
        bulbs.forEach(b => {
          if (b.dead || k < b.dieAt) return;
          b.dead = true; b.e.style.opacity = 1;
          if (pops++ % 2 === 0) Sound.cue('tick');
        });
        paintMoths(performance.now(), !bulbs[LAMP].dead);   // the lobby loop has already stopped. The moths vanish with the wall lamp
      }, { ease: k => k }));
      paintMoths(0, false);
      signLit(0);
      Sound.cue('fuse');
      await step(anim(90, dim, { ease: k => k }));
      await step(wait(1000));
      if (A.lobby_off) {
        /* The remaining flames go out with a whoosh. They were what lit the room, so the whole room darkens (the fully unlit background lobby_off fills in),
         * and pools of light (the power-only-out background lobby_dark) stay only around flames still lit. Covering only around a flame would leave a black hole there, hence this */
        const offWall = img('lobby_off', ui, 1600); offWall.className = 'abs cb-plate'; offWall.style.opacity = 0;
        ui.insertBefore(offWall, over);
        const pools = CAST.flames.map(([x, y, r]) => {
          const R = r * 1.7;
          const p = el('div', 'abs cb-bulb', ui, { left: x - R + 'px', top: y - R + 'px', width: 2 * R + 'px', height: 2 * R + 'px', backgroundImage: `url(${A.lobby_dark.src})`, backgroundPosition: `${R - x}px ${R - y}px` });
          ui.insertBefore(p, over);
          return p;
        });
        const room = g => {                       // g: how dark the room is (0–1). Cards and notes on the board darken and cool too
          offWall.style.opacity = g;
          over.style.filter = `brightness(${lerp(.45, .13, g).toFixed(3)}) saturate(${lerp(.85, .2, g).toFixed(3)})`;
        };
        /* The pools overlap (the two candles touch and the lantern's light reaches the candles). So a snuffed candle is covered with a patch with only the flame removed (lobby_snuff) inside its neighbours' light.
         * The patch shows only as much as light still falls on that spot (when every light on it is out, the unlit background below shows) */
        const SN = A.lobby_snuff, SNUFF = SN ? [44, 50] : [];      // the two candles only. The lantern and pumpkin darken with their own light
        const poolOp = pools.map(() => 1), snuffOn = SNUFF.map(() => 0);
        const covers = SNUFF.map((_, n) => CAST.flames.map(([px, py, pr]) => Math.hypot(CAST.flames[n][0] - px, CAST.flames[n][1] - py) < pr * 1.7));   // out to the pool edge (the .cb-bulb mask feathers to the full radius)
        /* Put one patch inside every pool that lights that candle (it must fade with the pool to erase the flame exactly; laid on top separately, the flame would show while fading).
         * Put one under the unlit background too (so while the room is not fully dark, the power-only-out background below does not leave a flame) */
        const snuffAt = (n, parent, ox, oy) => {
          const [x, y] = CAST.flames[n], s = SNUFF[n];
          return el('div', 'abs cb-bulb', parent, { left: x - s - ox + 'px', top: y - s - oy + 'px', width: 2 * s + 'px', height: 2 * s + 'px', opacity: 0,
            backgroundImage: `url(${SN.src})`, backgroundSize: `${SN.w}px ${SN.h}px`, backgroundRepeat: 'no-repeat', backgroundPosition: `${SN.x - x + s}px ${SN.y - y + s}px` });
        };
        const snuffs = SNUFF.map((_, n) => [
          ...CAST.flames.map(([px, py, pr], m) => covers[n][m] ? snuffAt(n, pools[m], px - pr * 1.7, py - pr * 1.7) : null).filter(Boolean),
          (() => { const e = snuffAt(n, ui, 0, 0); ui.insertBefore(e, offWall); return e; })(),
        ]);
        const lit = () => snuffs.forEach((es, n) => es.forEach(e => { e.style.opacity = snuffOn[n].toFixed(3); }));
        /* One gust blows out the candles and lantern together (tiny staggers look natural); only the pumpkin lingers briefly, then goes out too.
         * A room lit by the pumpkin alone is not detailed enough to show for long (it goes out before the room is fully dark) */
        const LEN = 170, SPAN = LEN + Math.max(...CAST.flames.map(f => f[3]));
        Sound.cue('whoosh', { vel: .55 });
        let last = false;
        await step(anim(SPAN, k => {
          CAST.flames.forEach(([, , , lag], n) => {
            const q = Math.min(1, Math.max(0, (k * SPAN - lag) / LEN));
            const f = q < .5 ? .75 + .25 * Math.sin(q * 40) : 1;                     // flutters once, then goes out
            poolOp[n] = (1 - q) * f; pools[n].style.opacity = poolOp[n];
            if (n < snuffs.length) snuffOn[n] = 1 - (1 - q) * f;
          });
          if (!last && k * SPAN > CAST.flames.at(-1)[3]) { last = true; Sound.cue('whoosh', { vel: .3 }); }   // the breath that blows out the pumpkin
          lit();
          room(k);
        }, { ease: k => k }));
        pools.forEach(p => p.remove());
        await step(wait(220));
      } else Sound.cue('whoosh', { vel: .5 });
      await step(anim(A.lobby_off ? 300 : 380, k => { outBlack.style.opacity = k; }, { ease: k => k }));
      fuseState();
      ui.remove();
    };

    let disposed = false, lobbyOn = false, stopRun = () => {};
    const stayAwake = setInterval(() => { lastEventAt = clock; }, 500);
    const hudEl = document.getElementById('hud');
    const hideGhost = () => {
      const g = ghost;
      g.pose = null;
      g.glow.style.visibility = 'hidden';
      g.marks.style.visibility = 'hidden';
      g.front.style.opacity = 0;
      g.box.style.opacity = 0;
      g.box.style.translate = `${GHOST_STAND.x}px ${GHOST_STAND.y}px`;
      g.box.style.scale = GHOST_STAND.scale;
    };

    // set the stage side to darkness. Only the area around the ghost light is faintly visible
    const darkStage = () => {
      ghostLit.ghost = 1; ghostLit.soft = true;
      light.dark = target.dark = .9;
      light.fx = target.fx = BULB.x; light.fy = target.fy = BULB.y;
      light.rx = target.rx = 500; light.ry = target.ry = 460;
      lights.style.opacity = 0;
      hudEl.style.display = 'none';
    };

    const lobby = () => {
      hideGhost(); darkStage(); fuseState();
      lobbyOn = true;
      Sound.scene('lobby', .1); Sound.bgm('lobby');      // lobby: the BGM plays through an old radio (SFX stay clear)
      seats.forEach((_, i) => drawCard(i));
      syncEntry();
      document.fonts.load('220px "Alfa Slab One"').then(fitTitle, fitTitle);
      lightsUp();
      const loop = () => {
        if (disposed || !lobbyOn) return;
        const now = performance.now();
        paintBulbs(now);
        paintMoths(now, !bulbs[LAMP].was);
        paintPointer(now);
        if (signLive && now >= signNext) { // the sign loses contact now and then too
          signLit(0);
          setTimeout(() => { if (signLive) signLit(1); }, 40 + Math.random() * 110);
          signNext = now + 1200 + Math.random() * 5000;
        }
        requestAnimationFrame(loop);
      };
      loop();
      if (!/clean/.test(location.hash)) input.focus();
    };
    const seatChanged = i => { hideGhost(); if (seats[i].player) fill(i); else vacate(i); syncEntry(); };
    const connChanged = i => { const p = seats[i].player; cards[i].box.classList.toggle('cb-away', !!p && p.connected === false); };

    /* ---- Show: one show.opening gate. Ends at MC_READY ---- */
    const run = async fast => {
      const fromLobby = lobbyOn;
      if (!lobbyOn) { hideGhost(); darkStage(); } // started directly without the lobby
      lobbyOn = false;
      ui.querySelectorAll('input, button').forEach(e => { e.disabled = true; });
      const SKIP = Symbol('skip');
      let skipped = false, skipNow = () => {};
      const skipP = new Promise(r => { skipNow = () => { skipped = true; r(SKIP); }; });
      const step = p => Promise.race([p, skipP]).then(v => { if (v === SKIP || disposed) throw SKIP; return v; });
      const skipBtn = el('button', 'abs lb-skip', stage, { zIndex: 46 });
      skipBtn.textContent = 'SKIP ▸▸';
      skipBtn.addEventListener('click', skipNow);
      const onKey = e => { if (e.key === 'Escape') skipNow(); };
      addEventListener('keydown', onKey);
      const iris = el('div', 'abs', stage, { left: 0, top: 0, width: '1600px', height: '900px', zIndex: 44, pointerEvents: 'none' });
      const irisAt = (x, y, r) => { if (!skipped) iris.style.background = `radial-gradient(circle at ${x}px ${y.toFixed(0)}px, transparent ${Math.max(0, r - 3).toFixed(1)}px, #050208 ${Math.max(.1, r).toFixed(1)}px)`; };
      stopRun = () => { skipNow(); skipBtn.remove(); removeEventListener('keydown', onKey); iris.remove(); };

      const sequence = async () => {
        await step(document.fonts.load('220px "Alfa Slab One"').catch(() => {}));
        fitTitle();

        // the lobby's power goes (straight to darkness if there was no lobby). The music fades away with the lights
        Sound.bgm(null, { fade: 1.6 });
        if (fromLobby) await wallOut(step); else fuseState();
        Sound.scene('show', .05);                         // turn off the radio channel (the BGM has already faded)
        await step(wait(420));
        Sound.cue('snore');

        // projector: after 3-2-1 the title, the sheet wakes up
        let up = false;
        await step(new Promise(res => {
          const t0 = performance.now();
          const loop = () => {
            if (disposed || skipped) return res();
            const T = (performance.now() - t0) / 1000;
            if (T >= ST.beam0 && !up) { up = true; light.dark = target.dark = .9; ghostLit.aud = 1; }
            paintSheet(Math.min(T, ST.end));
            if (T < ST.end) requestAnimationFrame(loop); else res();
          };
          loop();
        }));
        lastEventAt = clock;

        // it was a cute ghost all along: startled, then waves
        await step(wait(420));
        ghostPose('happy', 2600);
        Sound.cue('ding');
        await step(wait(1250));

        // the scene change is an old-film iris: it closes down to the face, winks, and shuts
        const faceX = hemX, faceY = hemY - body.h * U * .66;
        Sound.cue('slide', { up: false, dur: .6 });
        Sound.bgm(null, { fade: 1.5 });                    // the opening BGM fades over the 1.56 s the iris takes to close and ends when it goes black
        await step(anim(640, k => irisAt(faceX, faceY, lerp(1000, 168, k)), { ease: easeIO }));
        ghostPose('wink', 1000);
        Sound.cue('pop');
        await step(wait(680));
        await step(anim(240, k => irisAt(faceX, faceY, lerp(168, 0, k)), { ease: k => k * k }));
      };

      if (!fast) {
        try { await sequence(); } catch (e) { if (e !== SKIP) throw e; }
      }
      skipBtn.remove();
      removeEventListener('keydown', onKey);
      if (disposed) { iris.remove(); return; }
      skipped = true; // keeps the remaining iris motion from touching the black screen
      iris.style.background = '#050208';
      Sound.loop('film', false);

      // change the stage while it is black: remove the cloth and lobby, ghost behind the lectern, all lights on
      lobbyOn = false;
      Sound.bgm(null, { fade: .3 }); Sound.scene('show', .05);   // even when skipped, use the show's sound (without BGM)
      svg.remove();
      ui.remove();
      const gh = ghost;
      gh.box.style.translate = ''; gh.box.style.scale = ''; gh.box.style.opacity = '';
      gh.glow.style.visibility = '';
      gh.marks.style.visibility = '';
      gh.front.style.opacity = 1;
      ghostLit.front = 0; ghostLit.ghost = .72; ghostLit.soft = false;
      light.dark = target.dark = 0;
      lights.style.opacity = 1;
      ghostLit.aud = 1;
      if (fast) {
        iris.remove();
      } else {
        ghostPose('present', 2400);
        lastEventAt = clock;
        await wait(320);
        if (disposed) return;

        // when the blackout lifts, the stage is bright
        Sound.cue('jingle');                              // quiz-show intro jingle + cheer and applause (user's pick)
        setTimeout(() => Sound.cue('applause'), 200);
        applause(2.6);
        light.flash = 1; light.chase = 1;
        burst(430, 140, 34, 760); burst(1170, 140, 34, 760);
        anim(700, k => { iris.style.opacity = 1 - k; }, { ease: easeIO }).then(() => iris.remove());
        await wait(900);

        // the O/X cards light up in turn. This is MC_READY: now Gemini gives the first greeting
        for (const k of ['O', 'X']) {
          Sound.cue('ding');
          const c = A1 && A1.cards[k];
          if (c) anim(620, q => { c.win = Math.sin(q * Math.PI); }, { ease: e => e });
          await wait(300);
        }
        await wait(500);
        if (disposed) return;
        light.chase = 0;
      }
      clearInterval(stayAwake);
      hudEl.style.display = /clean/.test(location.hash) || DEMO ? 'none' : '';
      opening = null;
    };

    const dispose = () => {
      disposed = true; lobbyOn = false;
      Sound.bgm(null, { fade: .4 }); Sound.scene('show', .1);
      stopRun();
      clearInterval(stayAwake);
      svg.remove(); ui.remove();
      Sound.loop('film', false);
      ghostLit.front = 0; ghostLit.ghost = .72; ghostLit.soft = false;
      light.chase = 0;
      lights.style.opacity = 1;
      ghostLit.aud = 1;
      hudEl.style.display = /clean/.test(location.hash) || DEMO ? 'none' : '';
    };

    return { lobby, seatChanged, connChanged, run, dispose };
  }

  // Entry desk: when attached to a real engine, define window.KHQS_ENTRY = { join(name) → { ok } | { error }, start() } and window.KHQS_JOIN_URL
  const lobbyEntry = () => window.KHQS_ENTRY || demoEntry;
  function lobbyJoinUrl() {
    if (window.KHQS_JOIN_URL) return window.KHQS_JOIN_URL;
    const m = /[#&]qr=([^&]+)/.exec(location.hash);
    if (m) return decodeURIComponent(m[1]);
    // no QR for URLs a phone cannot reach (file, localhost)
    if (!/^https?:$/.test(location.protocol) || /^(localhost|127\.|\[::1\])/.test(location.hostname)) return null;
    return new URL('ticket.html', location.href).href;
  }
  const DEMO_FANS = ['sack', 'bolt', 'tophat_skull'];
  /* Full demo #demo: registration (three) → opening → act 1 → bats → act 2 → pumpkins → act 3 → finale, all by itself (for recording and introductions).
   * It is a highlight reel stitching per-act scenarios, so some questions are skipped between acts and scores do not carry over.
   * The act 1 scenario has two players (Mina, Junho), so an act 1 with Ray added is built to match the act 2/3 cast */
  const DEMO = /[#&]demo\b/.test(location.hash);
  function demoTrioAct1() {
    const sc = JSON.parse(JSON.stringify(window.KHQS_SCENARIOS['duo-act1-ox-betrayal']));
    const ray = JSON.parse(JSON.stringify(window.KHQS_SCENARIOS['trio-act2-buzzer-music'].steps[0].send.data.seats[2]));
    const out = [];
    let q = 0;
    for (const st of sc.steps) {
      const s = st.send, ty = s && s.type;
      if (ty === 'snapshot') { ray.player.score = 0; ray.player.rank = 1; s.data.seats[2] = ray; s.data.game.id = 'g-demo-full'; }
      if (ty === 'question.presented') q++;
      if (ty === 'ox.unanimous' && q === 1) continue;                 // Ray alone picks X, so it is not unanimous
      if (ty === 'ox.unanimous') s.data.streak = 1;
      if (ty === 'ox.choices_revealed') s.data.choices.push({ seat: 2, choice: 'X' });
      if (ty === 'answer.revealed') s.data.results.push({ seat: 2, correct: false });
      if (ty === 'score.settled') s.data.deltas.push({ seat: 2, delta: 0, score: 0, rank: 3 });
      out.push(st);
      if (ty === 'ox.submitted' && s.data.seat === (q === 1 ? 0 : 1)) out.push({ delayMs: 900, send: { type: 'ox.submitted', data: { seat: 2 } } });
    }
    sc.steps = out; sc.name = 'demo-trio-act1';
    return sc;
  }
  if (DEMO) { window.KHQS_SCENARIOS['demo-trio-act1'] = demoTrioAct1(); SCEN[1] = 'demo-trio-act1'; }
  const demoEntry = {
    async join(name) {
      if (seats.some(s => s.player && s.player.name === name)) return { error: 'THAT NAME IS TAKEN' };
      const s = seats.find(x => !x.player);
      if (!s) return { error: 'HOUSE FULL' };
      await engine.send({ type: 'seat.joined', data: { seat: s.i, player: { id: `p-demo-${s.i}`, name, fanType: DEMO_FANS[s.i], score: 0, rank: 1, connected: true } } }, false, engine.run);
      return { ok: true, seat: s.i };
    },
    async start() {
      if (!seats.some(s => s.player)) return;
      const src = window.KHQS_SCENARIOS['duo-act1-ox-betrayal'].steps;
      const a = src.findIndex(s => s.send && s.send.type === 'act.started'), b = src.findIndex(s => s.send && s.send.type === 'ox.submitted');
      const steps = [
        { send: { type: 'phase.changed', data: { phase: 'opening', deadline: null } } },
        { delayMs: 100, send: { type: 'show.opening', gate: { id: 'g-0', timeoutMs: 60000 }, data: { mode: seats.filter(s => s.player).length > 1 ? 'competitive' : 'solo', seats: seats.map(s => ({ seat: s.i, status: s.player ? 'occupied' : 'vacant', player: s.player })) } } },
        { send: { type: 'mc.status', data: { status: 'speaking' } } }, // where Gemini's first greeting goes
        { delayMs: 5200, send: { type: 'mc.status', data: { status: 'idle' } } },
        { delayMs: 200, send: { type: 'phase.changed', data: { phase: 'act_intro', deadline: null } } },
        ...(DEMO ? [] : src.slice(a, b).filter(s => s.send)),
      ];
      const run = engine.run;
      for (const st of steps) {
        if (st.delayMs) await engine.sleep(st.delayMs, run);
        engine.scenarioElapsed += st.delayMs || 0;
        if (run !== engine.run) return;
        await engine.send(st.send, false, run);
      }
      if (DEMO) { loadAct(1); return; }                 // from the lit stage straight into act 1 (three players); act chaining (onEnd) takes it from there
      engine.log('label', '— end of scenario —');
    },
  };
  function loadOpening() {
    engine.stop();
    engine.load({ name: 'opening-demo', steps: [{ send: { type: 'snapshot', sseq: 1, data: {
      game: { id: 'g-demo-opening', mode: 'competitive', act: 0, phase: 'lobby', phaseStartedAt: 1761300100000, deadline: null, questionNo: 0, questionTotal: 8 },
      seats: [0, 1, 2].map(seat => ({ seat, status: 'vacant', player: null })), question: null, round: null, mc: { status: 'idle' }, openGate: null, revealedAnswer: null,
    } } }, { await: 'lobby.closed', timeoutMs: 3600000 }] }); // the entry desk (demoEntry) sends the rest
    labelsEl.innerHTML = '';
    [...actsEl.children].forEach((b, i) => b.classList.toggle('on', i === 3));
    restart();
    if (/clean/.test(location.hash) || DEMO) { // auto-play for recording and review
      const m = /[#&]cast=([^&]*)/.exec(location.hash), names = m ? decodeURIComponent(m[1]).split(',').filter(Boolean) : DEMO ? ['Mina', 'Junho', 'Ray'] : ['Mina', 'Junho']; // try other names with &cast=name,name
      names.forEach((n, i) => setTimeout(() => demoEntry.join(n), 1300 + i * 3000));
      if (!/[#&]stay/.test(location.hash)) setTimeout(() => {
        if (!opening) return;
        const sign = document.querySelector('.cb-sign');                // the demo actually clicks the sign the pointer points at
        if (DEMO && sign && !sign.disabled) sign.click(); else lobbyEntry().start();
      }, 2200 + names.length * 3000 + (DEMO ? 2500 : 0));
    }
  }
  // accept names from the phone ticket demo (ticket.html) on the same origin
  if ('BroadcastChannel' in window) {
    const tc = new BroadcastChannel('khqs-ticket');
    tc.onmessage = async e => {
      if (e.data.type !== 'join' || !opening || state.phase !== 'lobby') return;
      const r = await lobbyEntry().join(String(e.data.name).trim().slice(0, 12));
      tc.postMessage({ ...r, reply: e.data.id });
    };
  }

  // URL options: #act=2 / #act=3&step=25 (freeze just before that step, for screenshots) / &clean
  window.KHQS_stage = { loadAct, jump: restart, pause: togglePause, engine, renderNow: () => render(0) };
  const ma = /act=(\d)/.exec(location.hash), ms = /step=(\d+)/.exec(location.hash);
  if (/clean/.test(location.hash) || DEMO) hud.style.display = 'none';
  if (/showtime|opening/.test(location.hash) || DEMO) loadOpening();
  else loadAct(ma ? +ma[1] : 1, ms ? +ms[1] : null);
  if (ms) togglePause();
  // Review: #act=3&finale=3 → the finale with that many players straight away (1, 2, 3, tie). Add &still to freeze on the finished look
  const mfin = /finale=(\w+)/.exec(location.hash);
  if (mfin) setTimeout(() => {
    const cast = [['Mina', 'sack', 220], ['Ray', 'tophat_skull', 160], ['Junho', 'bolt', 80]], tie = mfin[1] === 'tie', n = tie ? 2 : clamp(+mfin[1] || 3, 1, 3);
    const standings = cast.slice(0, n).map(([name, fanType, score], k) => ({ seat: k, name, fanType, score: tie ? 220 : score, rank: tie ? 1 : k + 1, winner: tie || k === 0 }));
    engine.stop(); if (paused) togglePause();          // stop the scenario running underneath and show only the finale
    const fd = { mode: n === 1 ? 'solo' : 'competitive', tie, standings };
    if (/still/.test(location.hash)) drawFinale(fd, true);
    else (finaleBusy = finaleReveal(fd, false)).then(() => wait(1200)).then(() => { if (finale) finale.gameOver = true; return finaleEnding(false); });   // like the real thing: curtain → podiums → (host line slot) → finish
  }, 600);
  // Review transitions: #act=1&trans=act (act 1 → 2 bats), #act=2&trans=act (act 2 → 3 pumpkins), #act=3&trans=newshow (finale → NEW SHOW bats → lobby)
  const mtr = /trans=(\w+)/.exec(location.hash);
  if (mtr) setTimeout(() => {
    engine.stop(); if (paused) togglePause();
    if (mtr[1] !== 'newshow') { HANDLERS['act.started']({ act: act % 3 + 1, assets: [] }, false); return; }
    drawFinale({ mode: 'competitive', tie: false, standings: [['Mina', 'sack', 220], ['Ray', 'tophat_skull', 160]].map(([name, fanType, score], k) => ({ seat: k, name, fanType, score, rank: k + 1, winner: !k })) }, true);
    const lobbySnap = { game: { act: 1, phase: 'lobby', deadline: null }, seats: [0, 1, 2].map(seat => ({ seat, status: 'empty', player: null })), round: null };
    setTimeout(() => newShow(() => { setTimeout(() => HANDLERS.snapshot(lobbySnap), 300); return { ok: true }; }), 1500);
  }, 900);
  // Review: #...&verdict=2x → a big verdict graphic (o/x) on seat 2. Add &stuck to show it stuck to the podium
  const mv = /verdict=(\d)([ox])/.exec(location.hash);
  if (mv) setTimeout(async () => { const v = viewOf(+mv[1]); if (v) { await showVerdict(v, mv[2] === 'o', true); if (/stuck/.test(location.hash)) stickVerdict(v, true); } }, 300);
  requestAnimationFrame(frame);
})();
