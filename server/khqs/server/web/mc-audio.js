/* MC audio in the stage page (live MC only). Loaded by link.js. Creates window.KHQS_HOST (docs/HANDOFF.md section 5.5).
 *  down (server -> page): JSON {t:'a',k:token,d:base64 PCM16 24 kHz} {t:'end',k} {t:'flush'} {t:'mic',open}
 *  up   (page -> server): binary PCM16 16 kHz mic frames (only while the engine asked for an answer); JSON {t:'started'|'played',k}
 * Playback reports come from real audio output: 'started' when a line's first buffer starts, 'played' when its last one ends. */
(() => {
  'use strict';
  const M = window.KHQS_MC = { state: 'idle', micOpen: false, forwarded: 0, played: [], started: [] };
  let ws = null, out = null, nextTime = 0, stream = null, capCtx = null, node = null;
  const tokens = new Map(), cbs = [], gates = {};
  let serverMic = false;

  const ctx = () => window.KHQS_sharedCtx && window.KHQS_sharedCtx();
  const send = o => { if (ws && ws.readyState === 1) ws.send(JSON.stringify(o)); };
  const emit = what => cbs.forEach(f => { try { f(what); } catch (e) { /* a listener must not break playback */ } });
  const micForward = () => serverMic && Object.values(gates).every(v => v !== false);
  const syncMic = () => { M.micOpen = micForward(); };

  function ensureOut() {
    const c = ctx();
    if (!c) throw new Error('NO AUDIO');
    if (!out || out.context !== c) { out = c.createGain(); out.connect(c.destination); host.mcOutputNode = out; host.audioContext = c; }
    return c;
  }
  function tok(k) {
    if (!tokens.has(k)) tokens.set(k, { sources: [], ended: false, started: false, reported: false, dead: false, timer: null });
    return tokens.get(k);
  }
  function markStarted(k, t) {
    if (t.started || t.dead) return;
    t.started = true; M.started.push(k); send({ t: 'started', k }); emit('start');
  }
  function check(k, t) {
    if (t.dead || t.reported || !t.ended || t.sources.length) return;
    markStarted(k, t);
    t.reported = true; tokens.delete(k); M.played.push(k); send({ t: 'played', k });
    if (!tokens.size) { nextTime = 0; emit('end'); }
  }
  function play(k, b64) {
    const c = ensureOut(), t = tok(k);
    if (t.dead) return;
    const raw = atob(b64), n = raw.length >> 1, f = new Float32Array(n);
    for (let i = 0; i < n; i++) { let v = raw.charCodeAt(2 * i) | (raw.charCodeAt(2 * i + 1) << 8); if (v & 0x8000) v -= 0x10000; f[i] = v / 32768; }
    const buf = c.createBuffer(1, n, 24000); buf.copyToChannel(f, 0);
    const src = c.createBufferSource(); src.buffer = buf; src.connect(out);
    const at = Math.max(c.currentTime + 0.04, nextTime);
    src.start(at); nextTime = at + buf.duration;
    t.sources.push(src);
    if (!t.timer) t.timer = setTimeout(() => markStarted(k, t), Math.max(0, (at - c.currentTime) * 1000));
    src.onended = () => { const i = t.sources.indexOf(src); if (i >= 0) t.sources.splice(i, 1); check(k, t); };
  }
  function flush() {
    tokens.forEach(t => { t.dead = true; clearTimeout(t.timer); t.sources.forEach(s => { s.onended = null; try { s.stop(); } catch (e) { /* already stopped */ } }); });
    const had = tokens.size > 0;
    tokens.clear(); nextTime = 0;
    if (had) emit('end');
  }

  const host = {
    audioContext: null, mcOutputNode: null,
    onMcPlayback: cb => { cbs.push(cb); },
    stopMc: flush,
    setMicGate: (reason, open) => { gates[reason] = !!open; syncMic(); },
  };

  async function startCapture() {
    stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false, channelCount: 1 } });
    const AC = window.KHQS_NativeAudioContext || window.AudioContext;
    capCtx = new AC({ sampleRate: 16000 });
    const code = `class P extends AudioWorkletProcessor { constructor(){ super(); this.b = new Int16Array(320); this.n = 0; }
      process(inputs){ const ch = inputs[0][0]; if (!ch) return true;
        for (let i = 0; i < ch.length; i++) { let v = Math.max(-1, Math.min(1, ch[i])); this.b[this.n++] = v < 0 ? v * 32768 : v * 32767;
          if (this.n === 320) { this.port.postMessage(this.b.slice().buffer); this.n = 0; } }
        return true; } }
      registerProcessor('khqs-cap', P);`;
    await capCtx.audioWorklet.addModule(URL.createObjectURL(new Blob([code], { type: 'text/javascript' })));
    const src = capCtx.createMediaStreamSource(stream);
    node = new AudioWorkletNode(capCtx, 'khqs-cap');
    node.port.onmessage = e => { if (micForward() && ws && ws.readyState === 1) { ws.send(e.data); M.forwarded += 1; } };
    src.connect(node);
    if (capCtx.state === 'suspended') await capCtx.resume();
  }

  function openSocket(secret) {
    return new Promise((resolve, reject) => {
      const s = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws/mc`);
      const timer = setTimeout(() => reject(new Error('MC OFFLINE — TRY AGAIN')), 5000);
      s.onopen = () => { clearTimeout(timer); ws = s; if (secret) s.send(JSON.stringify({ t: 'hello', secret })); resolve(); };
      s.onerror = () => { clearTimeout(timer); reject(new Error('MC OFFLINE — TRY AGAIN')); };
      s.onmessage = e => {
        let m; try { m = JSON.parse(e.data); } catch (x) { return; }
        if (m.t === 'a') play(m.k, m.d);
        else if (m.t === 'end') { const t = tok(m.k); t.ended = true; check(m.k, t); }
        else if (m.t === 'flush') flush();
        else if (m.t === 'mic') { serverMic = !!m.open; syncMic(); }
      };
      s.onclose = () => { if (ws === s) { ws = null; M.state = 'closed'; flush(); } };
    });
  }

  window.KHQS_McAudio = {
    /* Mic permission first (MIC NEEDED), then the audio socket (MC OFFLINE). */
    async connect(secret) {
      if (ws && ws.readyState === 1 && stream) { window.KHQS_HOST = host; return; }
      try { ensureOut(); } catch (e) { throw new Error('MC OFFLINE — TRY AGAIN'); }
      if (!stream) { try { await startCapture(); } catch (e) { throw new Error('MIC NEEDED'); } }
      await openSocket(secret);
      window.KHQS_HOST = host;
      M.state = 'open';
    },
    disconnect() { if (ws) { const s = ws; ws = null; s.close(); } flush(); },
  };
})();
