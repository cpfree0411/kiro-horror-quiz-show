/* Kiro Horror Quiz Show · static art for the opening
 * Cloth texture (baked once), pegs, the title card's colours and fonts, star shapes. (The lobby became image assets: CAST in stage.js)
 * Motion and order belong to createOpening in stage.js; this file only makes pictures.
 * Style: hand-printed paper and cloth. Cute and lovable; nothing creepy. */
window.KHQS_OPENING_ART = (() => {
  const RED = '#c2141f', INK = '#17100f', MUST = '#e9a22b', CREAM = '#f6ecd2';
  const SLAB = "'Alfa Slab One', serif", TYPE = "'Special Elite', monospace";
  const f = n => (+n).toFixed(1);
  const rng = seed => () => { seed = (seed * 16807) % 2147483647; return (seed - 1) / 2147483646; };

  /* ---------- Cloth: sheet coordinates (root coordinates in stage.js) ---------- */
  const PIN_X = [250, 389, 530, 670, 806, 937, 1078, 1217, 1350];   // peg spacing is uneven
  const SAG = [14, 20, 11, 17, 21, 12, 18, 15];                      // how deep the cloth sags between pegs
  const PIN_ROT = [-7, 4, -3, 6, -2, 5, -6, 3, 8];
  const PIN_COL = ['#c8202f', '#c8202f', '#c8202f', '#e0a53a', '#c8202f', '#c8202f', '#c8202f', '#d9c39a', '#c8202f'];
  const REG = { x: 200, y: 170, width: 1200, height: 660 };          // area covered by the baked texture
  const BAKE = 1.3;

  // peg: the bite point is the origin
  const pinMarkup = col => `<path d="M-7,-18 L7,-18 L6,22 L1,24 L1,-4 L-1,-4 L-1,24 L-6,22 Z" fill="${col}" stroke="#1a1012" stroke-width="2" stroke-linejoin="round"/>` +
    '<path d="M-4,-15 L-4,-7" stroke="#fff" stroke-opacity=".4" stroke-width="1.6" stroke-linecap="round"/>' +
    '<path d="M-8.5,-3.4 L8.5,-3.4 M-8.5,-.4 L8.5,-.4" stroke="#2b2526" stroke-width="2.1" stroke-linecap="round"/>' +
    '<path d="M-7,-2 L7,-2" stroke="#c9ccd0" stroke-width=".7"/>';

  const svgOpen = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${REG.x} ${REG.y} ${REG.width} ${REG.height}" width="${Math.round(REG.width * BAKE)}" height="${Math.round(REG.height * BAKE)}">`;
  const regRect = extra => `<rect x="${REG.x}" y="${REG.y}" width="${REG.width}" height="${REG.height}" ${extra}/>`;

  // weave and faint stains. A base texture that can be cut to any shape
  const clothSvg = () => `${svgOpen}
    <defs><filter id="w" x="0" y="0" width="100%" height="100%" color-interpolation-filters="sRGB">
      <feTurbulence type="fractalNoise" baseFrequency=".04 .95" numOctaves="2" seed="11" result="wH"/>
      <feColorMatrix in="wH" type="matrix" values="0 0 0 0 .42  0 0 0 0 .31  0 0 0 0 .16  1.1 0 0 0 -.5" result="wHc"/>
      <feTurbulence type="fractalNoise" baseFrequency=".95 .04" numOctaves="2" seed="12" result="wV"/>
      <feColorMatrix in="wV" type="matrix" values="0 0 0 0 .42  0 0 0 0 .31  0 0 0 0 .16  1.1 0 0 0 -.5" result="wVc"/>
      <feTurbulence type="fractalNoise" baseFrequency=".005 .008" numOctaves="3" seed="21" result="bl"/>
      <feColorMatrix in="bl" type="matrix" values="0 0 0 0 .5  0 0 0 0 .34  0 0 0 0 .14  1.5 0 0 0 -.74" result="blc"/>
      <feMerge><feMergeNode in="wHc"/><feMergeNode in="wVc"/><feMergeNode in="blc"/></feMerge>
    </filter></defs>
    ${regRect('filter="url(#w)"')}</svg>`;

  // visible only while hanging: vertical folds, fine wrinkles at the sags, hem stitching, patches
  const foldsSvg = () => {
    const rnd = rng(1031);
    let soft = '', lines = '', swags = '', bands = '';
    PIN_X.forEach(x => {
      const a = (rnd() - .5) * 32, b = (rnd() - .5) * 38, c = (rnd() - .5) * 28, w = 25 + rnd() * 25, o = .1 + rnd() * .1;
      const d = dx => `M${f(x + dx)},197 C${f(x + dx + a)},376 ${f(x + dx - b)},576 ${f(x + dx + c)},812`;
      soft += `<path d="${d(0)}" stroke="#5f4627" stroke-opacity="${o.toFixed(2)}" stroke-width="${f(w)}" fill="none"/>`;
      soft += `<path d="${d(w * .62)}" stroke="#fffaf0" stroke-opacity=".3" stroke-width="${f(w * .55)}" fill="none"/>`;
      lines += `<path d="${d(-w * .1)}" stroke="#7d6642" stroke-opacity=".35" stroke-width="1.5" fill="none"/>`;
      for (let k = -2; k <= 2; k++) if (k) swags += `<path d="M${x + k * 2},200 Q${x + k * 9},${219 + Math.abs(k) * 4} ${x + k * 16},${f(238 + rnd() * 21)}" stroke="#6f5836" stroke-opacity=".38" stroke-width="1.4" fill="none"/>`;
    });
    for (let i = 0; i < 8; i++) {
      const x0 = PIN_X[i] + 11, x1 = PIN_X[i + 1] - 11, m = (x0 + x1) / 2, s = SAG[i];
      bands += `<path d="M${x0},203 Q${f(m)},${f(203 + s * 2.8)} ${x1},203" stroke="#4d381f" stroke-opacity=".12" stroke-width="19" fill="none"/>`;
      swags += `<path d="M${x0 + 6},209 Q${f(m)},${f(209 + s * 3.2)} ${x1 - 6},209" stroke="#6f5836" stroke-opacity=".42" stroke-width="1.6" fill="none"/>`;
      swags += `<path d="M${x0 + 19},216 Q${f(m + 6)},${f(216 + s * 5)} ${x1 - 19},216" stroke="#6f5836" stroke-opacity=".22" stroke-width="1.3" fill="none"/>`;
    }
    return `${svgOpen}
    <defs>
      <linearGradient id="fade" gradientUnits="userSpaceOnUse" x1="0" y1="195" x2="0" y2="812"><stop offset="0" stop-color="#fff"/><stop offset=".55" stop-color="#fff" stop-opacity=".7"/><stop offset="1" stop-color="#fff" stop-opacity=".15"/></linearGradient>
      <mask id="fm">${regRect('fill="url(#fade)"')}</mask>
      <filter id="soft" x="-20%" y="-5%" width="140%" height="110%"><feGaussianBlur stdDeviation="7"/></filter>
      <pattern id="dots" width="9" height="9" patternUnits="userSpaceOnUse" patternTransform="rotate(28)"><circle cx="4.5" cy="4.5" r="2.1" fill="#17100f"/></pattern>
    </defs>
    <g mask="url(#fm)"><g filter="url(#soft)">${soft}</g>${lines}</g>
    <g filter="url(#soft)">${bands}</g>${swags}
    <path d="M236,784 Q520,794 800,786 T1364,784" fill="none" stroke="#6f5836" stroke-opacity=".6" stroke-width="1.7" stroke-dasharray="9 7"/>
    <g transform="translate(420,606) rotate(-6)">
      <rect x="-42" y="-34" width="84" height="68" rx="3" fill="#d9773f"/>
      <rect x="-42" y="-34" width="84" height="68" rx="3" fill="url(#dots)" opacity=".22"/>
      <rect x="-42" y="-34" width="84" height="68" rx="3" fill="none" stroke="#3a1a12" stroke-opacity=".5" stroke-width="1.5"/>
      <path d="M-48,-26 l12,5 M-48,-9 l12,4 M-48,8 l12,5 M-48,24 l12,4 M36,-27 l12,5 M36,-10 l12,4 M36,7 l12,5 M36,23 l12,4 M-28,-40 l4,12 M-9,-40 l5,12 M10,-40 l4,12 M27,-40 l5,12 M-28,28 l4,12 M-9,28 l5,12 M10,28 l4,12 M27,28 l5,12" stroke="#17100f" stroke-width="2.5" stroke-linecap="round"/>
    </g></svg>`;
  };

  const bake = svg => new Promise(done => {
    const w = Math.round(REG.width * BAKE), h = Math.round(REG.height * BAKE);
    const url = URL.createObjectURL(new Blob([svg], { type: 'image/svg+xml' }));
    const im = new Image();
    im.onload = () => {
      try {
        const c = document.createElement('canvas');
        c.width = w; c.height = h;
        c.getContext('2d').drawImage(im, 0, 0, w, h);
        c.toBlob(b => { URL.revokeObjectURL(url); done(b ? URL.createObjectURL(b) : null); }, 'image/png');
      } catch (e) { done(null); }
    };
    im.onerror = () => done(null);
    im.src = url;
  });
  let texP = null;
  // baked once per page. null on failure: the stage runs on without texture
  const textures = () => texP || (texP = Promise.all([bake(clothSvg()), bake(foldsSvg())]).then(([cloth, folds]) => ({ cloth, folds })));

  const starPath = (cx, cy, r) => { let d = ''; for (let i = 0; i < 10; i++) { const a = -Math.PI / 2 + i * Math.PI / 5, q = i % 2 ? r * .42 : r; d += (i ? 'L' : 'M') + f(cx + Math.cos(a) * q) + ',' + f(cy + Math.sin(a) * q); } return d + 'Z'; };

  return { PIN_X, SAG, PIN_ROT, PIN_COL, REG, RED, INK, MUST, CREAM, SLAB, TYPE, pinMarkup, textures, starPath };
})();
