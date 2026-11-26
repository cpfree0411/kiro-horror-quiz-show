/* Kiro Horror Quiz Show: connector between the frozen stage and the real engine.
 * Injected by the server right after mock-engine.js. It replaces window.MockEngine with a WebSocket engine of the
 * same shape, wraps Sound.loop('waltz') to play the real question music, and defines the entry hooks.
 * It stays out of the way for every replay/demo hash (docs/HANDOFF.md section 5.6). */
(() => {
  'use strict';
  const CFG = __KHQS_CONFIG__;
  if (/[#&](act=|step=|opening|showtime|clean|verdict=|demo|finale=|trans=)/.test(location.hash)) return;
  const PROTO = 'khqs.stage/1';
  const live = { role: 'primary', status: 'connecting', phase: 'lobby', mc: CFG.mc, clip: null, engine: null, music: null };
  window.KHQS_LIVE = live;

  // ---- the stage creates its AudioContext on the first click; capture it so music shares it
  let sharedCtx = null;
  const AC0 = window.AudioContext || window.webkitAudioContext;
  if (AC0) {
    const Wrapped = class extends AC0 { constructor(...a) { super(...a); if (!sharedCtx) sharedCtx = this; } };
    window.AudioContext = Wrapped; window.webkitAudioContext = Wrapped;
  }
  window.KHQS_NativeAudioContext = AC0;          // for the mic capture context (never the stage's)
  window.KHQS_sharedCtx = () => sharedCtx;

  const cid = (() => {
    let v = null;
    try { v = sessionStorage.getItem('khqs.cid'); } catch (e) { /* storage blocked */ }
    if (!v) { v = Math.random().toString(36).slice(2) + Math.random().toString(36).slice(2); try { sessionStorage.setItem('khqs.cid', v); } catch (e) { /* ignore */ } }
    return v;
  })();

  // ---- real music: Sound.loop('waltz') plays [startSec, endSec] of the asset from the last av.play
  const raw = new Map();   // assetId -> ArrayBuffer
  const decoded = new Map();
  const prefetch = assets => (assets || []).forEach(a => {
    if (raw.has(a.assetId)) return;
    raw.set(a.assetId, null);
    fetch('/stage/assets/' + a.assetId).then(r => r.arrayBuffer()).then(b => raw.set(a.assetId, b)).catch(() => raw.delete(a.assetId));
  });
  async function bufferFor(id) {
    if (decoded.has(id)) return decoded.get(id);
    let ab = raw.get(id);
    if (!ab) ab = await (await fetch('/stage/assets/' + id)).arrayBuffer();
    const buf = await sharedCtx.decodeAudioData(ab.slice(0));
    decoded.set(id, buf);
    return buf;
  }
  let musicToken = 0;
  async function musicOn() {
    const clip = live.clip, token = ++musicToken;
    if (!clip || !sharedCtx || !Sound.isEnabled()) return;   // the stage still times the clip itself
    try {
      const buf = await bufferFor(clip.assetId);
      if (token !== musicToken) return;
      const src = sharedCtx.createBufferSource(), gain = sharedCtx.createGain();
      src.buffer = buf; src.connect(gain); gain.connect(sharedCtx.destination);
      src.start(0, clip.startSec, Math.max(0.1, clip.endSec - clip.startSec));
      live.music = { src, gain };
      if (window.KHQS_HOST) window.KHQS_HOST.setMicGate('media', false);
    } catch (e) { console.warn('music failed', e && e.message); }
  }
  function musicOff() {
    musicToken++;
    const m = live.music; live.music = null;
    if (m) { try { m.gain.gain.setTargetAtTime(0, sharedCtx.currentTime, 0.02); m.src.stop(sharedCtx.currentTime + 0.12); } catch (e) { /* already stopped */ } }
    if (window.KHQS_HOST) window.KHQS_HOST.setMicGate('media', true);
  }
  const loop0 = Sound.loop.bind(Sound), cue0 = Sound.cue.bind(Sound);
  Sound.loop = (name, on, opts) => (name === 'waltz' ? (on ? musicOn() : musicOff()) : loop0(name, on, opts));
  Sound.cue = (name, opts) => (CFG.liveVoice && name === 'voice' ? null : cue0(name, opts));   // the real voice replaces the placeholder chirp

  // ---- the engine
  class LiveEngine {
    constructor({ deliver, log }) {
      this.deliver = deliver; this.log = log || (() => {});
      this.speed = 1; this.paused = false; this.run = 0; this.scenario = null; this.waiters = [];
      this.queue = []; this.ws = null; this.last = null; this.hadOpen = false; this.beats = {}; this.gates = {};
      this.rt = null; this.pt = null;
      live.engine = this;
    }
    load(s) { this.scenario = s; }
    labels() { return []; }
    stop() { /* nothing to stop: the server owns the show */ }
    send() { return Promise.resolve(); }
    sleep() { return Promise.resolve(); }
    start() {
      if (this.ws && this.ws.readyState === 1) this.out({ proto: PROTO, type: 'stage.need_snapshot', data: { lastSseq: this.last, receivedSseq: null } });
      else if (!this.ws) this.open(false);
    }
    receive(msg) {
      this.log('in', msg);
      if (live.role !== 'primary' && /^stage\.(beat_done|media_)/.test(msg.type)) return;   // a viewer never answers gates
      if (msg.type === 'stage.beat_done') {
        const g = this.gates[msg.data.gate];
        if (g) { this.beats[g.type] = Math.round(performance.now() - g.t); delete this.gates[msg.data.gate]; }
      }
      this.out(msg);
    }
    out(msg) {
      if (this.ws && this.ws.readyState === 1) this.ws.send(JSON.stringify(msg));
      else if (this.queue.length < 200) this.queue.push(msg);
    }
    open(take, takeSecret) {
      clearTimeout(this.rt);
      const url = `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws/stage?cid=${encodeURIComponent(cid)}${take ? '&take=1' : ''}`;
      const ws = new WebSocket(url);
      this.ws = ws; live.status = 'connecting'; chipUpdate();
      ws.onopen = () => {
        if (this.ws !== ws) return;
        live.status = 'online'; live.role = 'primary';
        if (take && takeSecret) ws.send(JSON.stringify({ type: 'khqs.operator', secret: takeSecret }));  // before the hello, never in the URL
        ws.send(JSON.stringify({ proto: PROTO, type: 'stage.hello', data: { role: 'primary', stageVersion: 'khqs-live-0.1', lastSseq: this.last, clientTime: performance.now(), beats: this.beats } }));
        if (this.hadOpen) this.queue = []; // acks queued while offline refer to gates that are gone; the snapshot re-acks
        this.hadOpen = true;
        const q = this.queue; this.queue = []; q.forEach(m => ws.send(JSON.stringify(m)));
        clearInterval(this.pt);
        this.pt = setInterval(() => this.out({ proto: PROTO, type: 'stage.ping', data: { clientTime: performance.now() } }), 10000);
        chipUpdate();
      };
      ws.onmessage = e => { try { this.onWire(JSON.parse(e.data)); } catch (err) { console.error(err); } };
      ws.onclose = () => {
        if (this.ws !== ws) return;
        clearInterval(this.pt); live.status = 'offline'; chipUpdate();
        this.rt = setTimeout(() => this.open(false), 1000);   // 1 s backoff, hello with lastSseq
      };
    }
    onWire(msg) {
      if (msg.type === 'pong') return;
      if (msg.type === 'error') {
        this.log('in', msg);
        if (msg.data && msg.data.code === 'primary_taken') { live.role = 'viewer'; chipUpdate(); }
        return;
      }
      if (msg.type === 'snapshot') {
        this.last = msg.sseq; live.phase = msg.data.game.phase;
        if (msg.data.game.phase === 'lobby') padClear(msg.data.game.id);
      } else {
        if (this.last != null && msg.sseq <= this.last) return;   // duplicate
        this.last = msg.sseq;
        if (msg.type === 'phase.changed') live.phase = msg.data.phase;
      }
      if (msg.type === 'buzzer.pressed' && window.KHQS_HOST && window.KHQS_HOST.stopMc) window.KHQS_HOST.stopMc();
      if (msg.type === 'act.started') prefetch(msg.data.assets);
      if (msg.type === 'av.play') live.clip = msg.data;
      if (msg.gate) this.gates[msg.gate.id] = { type: msg.type, t: performance.now() };
      chipUpdate();
      this.deliver(msg, { fast: false });
    }
  }
  window.MockEngine = LiveEngine;

  // ---- entry hooks
  // The operator secret is typed by the operator when needed and lives only in this variable: not in the page, a URL, storage or a log.
  let opSecret = null;
  function secret() {
    if (!CFG.secretRequired) return null;
    if (!opSecret) opSecret = window.prompt('Operator secret (kept in this page only)') || null;
    return opSecret;
  }
  const post = async (path, body, op) => {
    const headers = { 'content-type': 'application/json', 'X-KHQS': '1', 'X-KHQS-Cid': cid };
    if (op && CFG.secretRequired) { const s = secret(); if (s) headers['X-KHQS-Operator'] = s; }
    try {
      const resp = await fetch(path, { method: 'POST', headers, body: JSON.stringify(body || {}) });
      if (resp.status === 403 && op) opSecret = null;  // a wrong secret is asked for again next time
      return await resp.json();
    } catch (e) { return { error: 'SERVER NOT REACHABLE' }; }
  };
  window.KHQS_JOIN_URL = CFG.joinUrl;
  window.KHQS_ENTRY = {
    async join(name) {
      const r = await post('/api/join', { name });
      if (r.error) return { error: r.error };
      padAdd(r.seat, name, r.credential);
      return { ok: true, seat: r.seat };
    },
    async start() {
      const fail = msg => {
        const e = document.querySelector('.cb-err, .lb-err'); if (e) e.textContent = msg;
        const b = document.querySelector('.cb-sign, .lb-start'); if (b) b.disabled = false;
      };
      if (CFG.liveVoice) { const m = await ensureMc(); if (m) return fail(m); }   // mic + session first, then the show
      const r = await post('/api/start');
      if (r.error) fail(r.error);
    },
    async reset(force) {
      const r = await post('/api/reset', { force: !!force }, !!force);
      return r.ok ? { ok: true } : { error: r.error || 'NOT NOW' };
    },
  };

  // ---- live MC: mic permission, audio socket, then the Live session (an explicit operator action each time)
  let mcInfo = { state: CFG.liveVoice ? 'offline' : 'online', reason: '' };
  const loadScript = src => new Promise((res, rej) => { const s = document.createElement('script'); s.src = src; s.onload = res; s.onerror = rej; document.head.appendChild(s); });
  async function ensureMc() {
    try {
      if (!window.KHQS_McAudio) await loadScript('/play/mc-audio.js');
      await window.KHQS_McAudio.connect(secret());
    } catch (e) { return e && e.message === 'MIC NEEDED' ? 'MIC NEEDED' : 'MC OFFLINE — TRY AGAIN'; }
    const r = await post('/api/mc/connect', {}, true);
    mcPoll();
    return r.error ? 'MC OFFLINE — TRY AGAIN' : null;
  }
  async function mcPoll() {
    if (!CFG.liveVoice) return;
    if (!CFG.operator || (CFG.secretRequired && !opSecret)) return;  // public clients and a not-yet-authorised operator do not poll
    try {
      const h = CFG.secretRequired ? { 'X-KHQS-Operator': opSecret } : {};
      const resp = await fetch('/api/mc/status', { headers: h });
      if (resp.status === 403) { opSecret = null; return; }
      mcInfo = await resp.json();
    } catch (e) { mcInfo = { state: 'offline', reason: 'server not reachable' }; }
    chipUpdate();
  }
  if (CFG.liveVoice) setInterval(mcPoll, 2000);

  // ---- operator chip and the screen pad (outside the stage's own DOM)
  let chip = null, padBox = null;
  function pads() { try { return JSON.parse(sessionStorage.getItem('khqs.pads') || '{}'); } catch (e) { return {}; } }
  function padAdd(seat, name, cred) {
    const p = pads(); p[seat] = { name };
    try { sessionStorage.setItem('khqs.pads', JSON.stringify(p)); sessionStorage.setItem('khqs.pad.' + seat, JSON.stringify({ cred, seat, name })); } catch (e) { /* ignore */ }
    padRender();
  }
  let padGame = null;
  function padClear(gameId) {
    if (padGame && padGame !== gameId) {
      const p = pads();
      Object.keys(p).forEach(s => sessionStorage.removeItem('khqs.pad.' + s));
      sessionStorage.removeItem('khqs.pads');
      padRender();
    }
    padGame = gameId;
  }
  // The pad stays collapsed to an edge tab unless a pad player has something to do (the iframe tells us), so it never
  // sits on the stage's own buttons. The tab (or the chip button) overrides until the next change.
  const padState = { needs: {}, manual: null };
  let padTab = null;
  window.addEventListener('message', e => {
    const m = e.data;
    if (e.origin !== location.origin || !m || m.khqs !== 'pad') return;
    padState.needs[m.seat] = !!m.needs; padState.manual = null; padRender();
  });
  function padOpen() {
    if (!Object.keys(pads()).length) return false;
    return padState.manual !== null ? padState.manual : Object.values(padState.needs).some(Boolean);
  }
  function padRender() {
    if (!padBox) return;
    const p = pads(), seats = Object.keys(p);
    // the pad steps aside at the curtain so it never covers the stage's NEW SHOW button
    const over = live.phase === 'finale.curtain' || live.phase === 'ended';
    const open = padOpen();
    padBox.style.display = seats.length && open && !over ? '' : 'none';
    padTab.style.display = seats.length && !over ? '' : 'none';
    padTab.classList.toggle('alert', Object.values(padState.needs).some(Boolean));
    padTab.textContent = open ? 'PAD ›' : '‹ PAD';
    const frames = padBox.querySelector('.frames');
    [...frames.children].forEach(f => { if (!p[f.dataset.seat]) f.remove(); });
    seats.forEach(s => {
      if (frames.querySelector(`[data-seat="${s}"]`)) return;
      const fr = document.createElement('iframe');
      fr.dataset.seat = s; fr.title = `Screen pad for ${p[s].name}`; fr.src = `/phone?pad=${s}`;
      frames.appendChild(fr);
    });
  }
  function chipUpdate() {
    if (!chip) return;
    chip.dataset.role = live.role; chip.dataset.status = live.status; chip.dataset.phase = live.phase;
    const mcText = CFG.liveVoice ? `MC ${mcInfo.state.toUpperCase()}` : 'MOCK MC';
    chip.dataset.mc = mcInfo.state;
    chip.querySelector('.st').textContent = `${live.status === 'online' ? '●' : '○'} ${live.role.toUpperCase()} · ${mcText} · ${live.phase}`;
    const mcre = chip.querySelector('.mcre');
    if (mcre) mcre.style.display = CFG.liveVoice && mcInfo.state === 'offline' ? '' : 'none';
    const take = chip.querySelector('.take');
    if (take) take.style.display = live.role === 'viewer' ? '' : 'none';
    padRender();
  }
  function buildChrome() {
    const css = document.createElement('style');
    css.textContent = `#hud{display:none!important}
#khqs-chip{position:fixed;left:6px;bottom:6px;z-index:2147483000;font:600 11px/1.3 system-ui,sans-serif;color:#f3e6c8;background:rgba(20,10,6,.72);border:1px solid #6b4a2b;border-radius:6px;padding:4px 6px;display:flex;gap:6px;align-items:center;opacity:.6}
#khqs-chip:hover{opacity:1}#khqs-chip button{font:inherit;color:#2a1608;background:#f3e6c8;border:0;border-radius:4px;padding:2px 6px;cursor:pointer}
#khqs-pad{position:fixed;right:0;top:34px;z-index:2147483000;background:#1b0f0a;border:2px solid #ffcf6b;border-right:0;border-radius:8px 0 0 8px;padding:4px;width:max-content;max-width:96vw;max-height:calc(100vh - 150px);overflow:auto}
#khqs-padtab{position:fixed;right:0;top:6px;z-index:2147483001;font:700 11px system-ui,sans-serif;color:#2a1608;background:#ffcf6b;border:0;border-radius:6px 0 0 6px;padding:4px 7px;cursor:pointer;opacity:.75}
#khqs-padtab.alert{opacity:1;box-shadow:0 0 8px #ffcf6b}#khqs-padtab:hover{opacity:1}
#khqs-pad .lbl{font:600 10px/1.25 system-ui,sans-serif;color:#ffcf6b;margin:0 0 3px;width:0;min-width:100%}
#khqs-pad .frames{display:flex;gap:4px}#khqs-pad iframe{width:210px;height:380px;border:0;background:#1b0f0a;border-radius:6px}`;
    document.head.appendChild(css);
    chip = document.createElement('div'); chip.id = 'khqs-chip';
    chip.innerHTML = '<span class="st"></span><button class="pad" type="button">PAD</button><button class="mcre" type="button" style="display:none">RECONNECT MC</button><button class="take" type="button" style="display:none">TAKE OVER</button><button class="new" type="button">NEW SHOW</button>';
    document.body.appendChild(chip);
    padTab = document.createElement('button'); padTab.id = 'khqs-padtab'; padTab.type = 'button'; padTab.style.display = 'none'; padTab.textContent = '‹ PAD';
    padTab.onclick = () => { padState.manual = !padOpen(); padRender(); };
    document.body.appendChild(padTab);
    padBox = document.createElement('div'); padBox.id = 'khqs-pad'; padBox.style.display = 'none';
    padBox.innerHTML = '<div class="lbl">SCREEN PAD: visible to everyone in the room. Use your phone to keep your answers private.</div><div class="frames"></div>';
    document.body.appendChild(padBox);
    chip.querySelector('.pad').onclick = () => { padState.manual = !padOpen(); padRender(); };
    chip.querySelector('.take').onclick = () => {
      const s = secret();
      if (CFG.secretRequired && !s) return;
      live.engine.ws && live.engine.ws.close(); clearTimeout(live.engine.rt); live.engine.open(true, s);
    };
    if (!CFG.operator) chip.querySelectorAll('.take, .new, .mcre').forEach(b => b.remove());   // public clients get no operator buttons
    if (chip.querySelector('.mcre')) chip.querySelector('.mcre').onclick = async () => { const m = await ensureMc(); if (m) alert(m); mcPoll(); };
    if (chip.querySelector('.new')) chip.querySelector('.new').onclick = () => { if (confirm('Start a new show now? The current game will be lost.')) KHQS_ENTRY.reset(true); };
    chipUpdate(); padRender();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', buildChrome); else buildChrome();
})();
