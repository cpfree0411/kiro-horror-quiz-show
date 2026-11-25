/* Ticket QR encoder (byte mode, error correction L, versions 1–10). window.KHQS_QR(text) → { size, at(x, y) } */
(() => {
  'use strict';
  // per version: error-correction codewords per block, [block count, data codewords per block] groups
  const BLOCKS = [null, [7, [1, 19]], [10, [1, 34]], [15, [1, 55]], [20, [1, 80]], [26, [1, 108]], [18, [2, 68]], [20, [2, 78]], [24, [2, 97]], [30, [2, 116]], [18, [2, 68], [2, 69]]];
  const ALIGN = [null, [], [6, 18], [6, 22], [6, 26], [6, 30], [6, 34], [6, 22, 38], [6, 24, 42], [6, 26, 46], [6, 28, 50]];

  const EXP = new Array(512), LOG = new Array(256);
  for (let i = 0, x = 1; i < 255; i++) { EXP[i] = x; LOG[x] = i; x = x << 1 ^ (x & 128 ? 0x11d : 0); }
  for (let i = 255; i < 512; i++) EXP[i] = EXP[i - 255];
  const mul = (a, b) => (a && b ? EXP[LOG[a] + LOG[b]] : 0);

  function ecBytes(data, n) {
    let gen = [1];
    for (let i = 0; i < n; i++) {
      const next = new Array(gen.length + 1).fill(0);
      gen.forEach((g, j) => { next[j] ^= g; next[j + 1] ^= mul(g, EXP[i]); });
      gen = next;
    }
    const rem = data.concat(new Array(n).fill(0));
    for (let i = 0; i < data.length; i++) {
      const f = rem[i];
      if (f) for (let j = 0; j < gen.length; j++) rem[i + j] ^= mul(gen[j], f);
    }
    return rem.slice(data.length);
  }

  function codewords(bytes, version) {
    const spec = BLOCKS[version], groups = spec.slice(1);
    const cap = groups.reduce((s, [n, d]) => s + n * d, 0);
    const bits = [], put = (v, n) => { for (let i = n - 1; i >= 0; i--) bits.push(v >> i & 1); };
    put(4, 4); put(bytes.length, version < 10 ? 8 : 16);
    bytes.forEach(b => put(b, 8));
    put(0, Math.min(4, cap * 8 - bits.length));
    while (bits.length % 8) bits.push(0);
    const data = [];
    for (let i = 0; i < bits.length; i += 8) data.push(parseInt(bits.slice(i, i + 8).join(''), 2));
    for (let k = 0; data.length < cap; k++) data.push(k % 2 ? 0x11 : 0xec);
    const blocks = [], ecs = [];
    let p = 0;
    for (const [n, d] of groups) for (let i = 0; i < n; i++) { const b = data.slice(p, p += d); blocks.push(b); ecs.push(ecBytes(b, spec[0])); }
    const out = [], maxD = Math.max(...blocks.map(b => b.length));
    for (let i = 0; i < maxD; i++) blocks.forEach(b => { if (i < b.length) out.push(b[i]); });
    for (let i = 0; i < spec[0]; i++) ecs.forEach(e => out.push(e[i]));
    return out;
  }

  const MASKS = [
    (x, y) => (x + y) % 2 === 0, (x, y) => y % 2 === 0, x => x % 3 === 0, (x, y) => (x + y) % 3 === 0,
    (x, y) => ((y >> 1) + (x / 3 | 0)) % 2 === 0, (x, y) => x * y % 2 + x * y % 3 === 0,
    (x, y) => (x * y % 2 + x * y % 3) % 2 === 0, (x, y) => ((x + y) % 2 + x * y % 3) % 2 === 0,
  ];

  function bch(v, poly, bits) {
    let d = v << bits - 1;
    const top = 32 - Math.clz32(poly);
    while (d && 32 - Math.clz32(d) >= top) d ^= poly << (32 - Math.clz32(d) - top);
    return d;
  }

  function build(words, version, mask) {
    const size = 17 + version * 4;
    const dark = Array.from({ length: size }, () => new Array(size).fill(false));
    const fixed = Array.from({ length: size }, () => new Array(size).fill(false));
    const set = (x, y, v) => { if (x >= 0 && y >= 0 && x < size && y < size) { dark[y][x] = v; fixed[y][x] = true; } };
    const finder = (cx, cy) => {
      for (let dy = -4; dy <= 4; dy++) for (let dx = -4; dx <= 4; dx++) {
        const r = Math.max(Math.abs(dx), Math.abs(dy));
        set(cx + dx, cy + dy, r !== 2 && r !== 4);
      }
    };
    finder(3, 3); finder(size - 4, 3); finder(3, size - 4);
    for (let i = 8; i < size - 8; i++) { set(i, 6, i % 2 === 0); set(6, i, i % 2 === 0); }
    const al = ALIGN[version];
    for (const ay of al) for (const ax of al) {
      if ((ax === 6 && ay === 6) || (ax === 6 && ay === al[al.length - 1]) || (ax === al[al.length - 1] && ay === 6)) continue;
      for (let dy = -2; dy <= 2; dy++) for (let dx = -2; dx <= 2; dx++) set(ax + dx, ay + dy, Math.max(Math.abs(dx), Math.abs(dy)) !== 1);
    }
    // format information (error correction L = 01)
    const fmtData = 1 << 3 | mask, fmt = (fmtData << 10 | bch(fmtData, 0x537, 11)) ^ 0x5412;
    const fbit = i => (fmt >> i & 1) === 1;
    for (let i = 0; i < 6; i++) set(8, i, fbit(i));
    set(8, 7, fbit(6)); set(8, 8, fbit(7)); set(7, 8, fbit(8));
    for (let i = 9; i < 15; i++) set(14 - i, 8, fbit(i));
    for (let i = 0; i < 8; i++) set(size - 1 - i, 8, fbit(i));
    for (let i = 8; i < 15; i++) set(8, size - 15 + i, fbit(i));
    set(8, size - 8, true);
    if (version >= 7) {
      const ver = version << 12 | bch(version, 0x1f25, 13);
      for (let i = 0; i < 18; i++) {
        const b = (ver >> i & 1) === 1, a = i / 3 | 0, c = i % 3 + size - 11;
        set(a, c, b); set(c, a, b);
      }
    }
    // data
    const fn = MASKS[mask];
    let bit = 0, up = true;
    for (let x = size - 1; x > 0; x -= 2) {
      if (x === 6) x--;
      for (let n = 0; n < size; n++) {
        const y = up ? size - 1 - n : n;
        for (const cx of [x, x - 1]) {
          if (fixed[y][cx]) continue;
          const v = bit < words.length * 8 && (words[bit >> 3] >> 7 - (bit & 7) & 1) === 1;
          bit++;
          dark[y][cx] = v !== fn(cx, y);
        }
      }
      up = !up;
    }
    return dark;
  }

  function penalty(m) {
    const n = m.length;
    let s = 0, total = 0;
    const lines = [m, m[0].map((_, x) => m.map(r => r[x]))];
    for (const rows of lines) for (const r of rows) {
      let run = 1;
      for (let i = 1; i <= n; i++) {
        if (i < n && r[i] === r[i - 1]) run++;
        else { if (run >= 5) s += run - 2; run = 1; }
      }
      const str = r.map(v => (v ? 1 : 0)).join('');
      s += 40 * ((str.match(/(?=10111010000|00001011101)/g) || []).length);
    }
    for (let y = 0; y < n; y++) for (let x = 0; x < n; x++) {
      if (m[y][x]) total++;
      if (y < n - 1 && x < n - 1 && m[y][x] === m[y][x + 1] && m[y][x] === m[y + 1][x] && m[y][x] === m[y + 1][x + 1]) s += 3;
    }
    return s + 10 * Math.floor(Math.abs(total * 100 / (n * n) - 50) / 5);
  }

  window.KHQS_QR = (text, forceMask = null) => {
    const bytes = [...new TextEncoder().encode(text)];
    let version = 1;
    const capacity = v => BLOCKS[v].slice(1).reduce((s, [n, d]) => s + n * d, 0) - (v < 10 ? 2 : 3);
    while (version <= 10 && capacity(version) < bytes.length) version++;
    if (version > 10) throw new Error('QR text too long');
    const words = codewords(bytes, version);
    let best = null, bestS = Infinity;
    for (let mask = 0; mask < 8; mask++) {
      if (forceMask != null && mask !== forceMask) continue;
      const m = build(words, version, mask), s = penalty(m);
      if (s < bestS) { bestS = s; best = m; }
    }
    return { size: best.length, version, at: (x, y) => best[y][x], matrix: best };
  };
})();
