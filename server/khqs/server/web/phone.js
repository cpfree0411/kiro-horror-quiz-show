/* Phone / screen-pad controller. English only. Select, then LOCK IN: only the confirmed choice is sent. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const qs = new URLSearchParams(location.search);
  const padSeat = qs.get('pad');
  const store = padSeat !== null ? sessionStorage : localStorage;
  const key = padSeat !== null ? 'khqs.pad.' + padSeat : 'khqs.cred';
  let saved = null;
  try { saved = JSON.parse(store.getItem(key) || 'null'); } catch (e) { /* ignore */ }

  const S = { view: null, at: 0, offset: 0, pending: null, sig: '', ws: null, n: 0, sending: false, dead: false };
  window.KHQS_PHONE = { get view() { return S.view; }, get screen() { return S.view ? S.view.screen : 'connecting'; }, get pending() { return S.pending; } };
  const el = (tag, attrs = {}, kids = []) => {
    const e = document.createElement(tag);
    Object.entries(attrs).forEach(([k, v]) => { if (k === 'text') e.textContent = v; else if (k === 'class') e.className = v; else if (k.startsWith('on')) e[k] = v; else e.setAttribute(k, v); });
    [].concat(kids).forEach(c => c && e.appendChild(c));
    return e;
  };
  const toast = t => { $('pc-toast').textContent = t || ''; if (t) setTimeout(() => { if ($('pc-toast').textContent === t) $('pc-toast').textContent = ''; }, 3500); };
  const banner = t => { const b = $('pc-banner'); b.hidden = !t; b.textContent = t || ''; };

  function fatal(text, linkText) {
    S.dead = true;
    const main = $('pc-main'); main.dataset.screen = 'invalid'; main.innerHTML = '';
    main.append(el('p', { class: 'big', text: text }));
    if (linkText) main.append(el('p', { class: 'sub' }, [el('a', { href: '/ticket.html', text: linkText, style: 'color:#ffcf6b' })]));
    banner('');
  }

  // ---------------------------------------------------------------- connection
  function connect() {
    if (S.dead) return;
    if (!saved || !saved.cred) return fatal('NO TICKET YET', 'GET A TICKET');
    const ws = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws/phone`);
    S.ws = ws;
    ws.onopen = () => ws.send(JSON.stringify({ type: 'hello', cred: saved.cred }));
    ws.onmessage = e => {
      const m = JSON.parse(e.data);
      if (m.type === 'view') { banner(''); onView(m.view); }
      else if (m.type === 'result') { S.sending = false; if (!m.ok) { toast(({ not_now: 'Too late for that one.', busy: 'Someone else has the buzzer.', locked_out: 'You are locked out this round.',
        already_answered: 'Already locked in.', bad_input: 'That did not look right.', disconnected: 'Reconnecting…' })[m.error] || 'That did not go through.'); S.pending = null; render(true); } }
      else if (m.type === 'error' && m.code === 'bad_cred') { try { store.removeItem(key); } catch (x) { /* ignore */ } fatal('THIS TICKET IS NO LONGER VALID', 'SCAN THE QR CODE AGAIN'); }
      else if (m.type === 'gone') { try { store.removeItem(key); } catch (x) { /* ignore */ } fatal('A NEW SHOW IS STARTING', 'GET A NEW TICKET'); }
    };
    ws.onclose = () => { if (S.dead) return; banner('RECONNECTING…'); setTimeout(connect, 1000); };
  }
  function send(action) {
    if (!S.ws || S.ws.readyState !== 1 || S.sending) return;
    S.sending = true;
    S.ws.send(JSON.stringify({ type: 'action', id: ++S.n, action }));
  }

  // ---------------------------------------------------------------- screens
  function onView(v) {
    S.view = v; S.at = Date.now(); S.offset = v.game.serverTime - Date.now();
    $('pc-name').textContent = v.you.name; $('pc-score').textContent = v.you.score; $('pc-rank').textContent = 'RANK ' + v.you.rank;
    if (padSeat !== null && window.parent !== window) {   // a screen pad tells the stage page when it has something to do
      const quiet = ['waiting', 'locked', 'ox_locked', 'bet_locked', 'final_locked', 'done', 'invalid', 'connecting'];
      if (S.lastScreen !== v.screen) window.parent.postMessage({ khqs: 'pad', seat: +padSeat, screen: v.screen, needs: !quiet.includes(v.screen) }, location.origin);
    }
    S.lastScreen = v.screen;
    const sig = [v.screen, v.question && v.question.id, v.question && v.question.text, JSON.stringify(v.own)].join('|');
    if (sig !== S.sig) { S.sig = sig; S.pending = null; S.sending = false; render(true); }
  }
  const card = q => q && el('div', { class: 'card' }, [el('div', { class: 'cat', text: q.category || '' }), q.text ? el('div', { class: 'q', text: q.text }) : el('div', { class: 'q', text: 'Listen carefully…' })]);
  const lockBtn = (label, enabled, onclick) => {
    const b = el('button', { class: 'lock', id: 'lock', type: 'button', text: label || 'LOCK IN', onclick });
    b.disabled = !enabled;
    return b;
  };

  function render() {
    const v = S.view, main = $('pc-main');
    if (!v) return;
    main.dataset.screen = v.screen; main.innerHTML = '';
    const q = v.question, own = v.own || {};
    switch (v.screen) {
      case 'ox': {
        main.append(card(q), el('div', { class: 'row' }, ['O', 'X'].map(c => el('button', { class: 'oxbtn' + (S.pending === c ? ' sel' : ''), 'data-choice': c, type: 'button', text: c,
          onclick: () => { S.pending = c; render(); } }))), lockBtn('LOCK IN', !!S.pending, () => S.pending && send({ type: 'ox', choice: S.pending })));
        break;
      }
      case 'ox_locked':
        main.append(card(q), el('p', { class: 'big', text: 'LOCKED IN ✓' }), el('p', { class: 'sub', text: 'You picked ' + own.pick + '. Waiting for the others…' }));
        break;
      case 'buzzer':
        main.append(card(q), el('button', { class: 'buzz', id: 'buzz', type: 'button', text: 'BUZZ!', onclick: () => send({ type: 'buzz' }) }));
        break;
      case 'locked':
        main.append(card(q), el('p', { class: 'big', text: 'LOCKED OUT' }), el('p', { class: 'sub', text: 'Sit tight. You are back in for the next question.' }));
        break;
      case 'answer_voice':
        main.append(el('p', { class: 'big', text: 'YOU HAVE THE BUZZER!' }), el('p', { class: 'sub', text: 'Say your answer out loud.' }),
          el('button', { id: 'type-instead', type: 'button', text: 'TYPE IT INSTEAD', onclick: () => send({ type: 'choose_typing' }) }));
        break;
      case 'answer_text': {
        const inp = el('input', { type: 'text', id: 'answer-text', maxlength: '60', autocomplete: 'off', autocapitalize: 'off', placeholder: 'Type your answer' });
        const go = () => { const t = inp.value.trim(); if (t) send({ type: 'text_answer', text: t }); };
        inp.addEventListener('keydown', e => { if (e.key === 'Enter') go(); });
        main.append(el('p', { class: 'big', text: 'YOU HAVE THE BUZZER!' }), inp, el('button', { class: 'lock', id: 'send-answer', type: 'button', text: 'SEND ANSWER', onclick: go }));
        setTimeout(() => inp.focus(), 50);
        break;
      }
      case 'betrayal_reason': {
        const b = own.betrayal;
        main.append(el('p', { class: 'big', text: 'WHY DID YOU PICK ' + b.from + '?' }),
          el('div', { class: 'col' }, b.reasons.map(r => el('button', { class: S.pending === r.id ? 'sel' : '', 'data-reason': r.id, type: 'button', text: r.label,
            onclick: () => { S.pending = r.id; render(); } }))),
          lockBtn('LOCK IN', !!S.pending, () => S.pending && send({ type: 'betrayal_reason', reason: S.pending })));
        break;
      }
      case 'betrayal_decision': {
        const b = own.betrayal, other = b.from === 'O' ? 'X' : 'O';
        main.append(el('p', { class: 'big', text: 'SWITCH YOUR ANSWER?' }),
          el('div', { class: 'row' }, [['keep', 'KEEP ' + b.from], ['switch', 'SWITCH TO ' + other]].map(([id, label]) => el('button', { class: S.pending === id ? 'sel' : '', 'data-decision': id, type: 'button', text: label,
            onclick: () => { S.pending = id; render(); } }))),
          lockBtn('LOCK IN', !!S.pending, () => S.pending && send({ type: 'betrayal_decision', switch: S.pending === 'switch' })));
        break;
      }
      case 'bet': {
        const max = own.maxBet, val = S.pending == null ? Math.min(max, Math.round(max / 2)) : S.pending;
        const num = el('div', { class: 'betnum', id: 'bet-num', text: String(val) });
        const range = el('input', { type: 'range', id: 'bet-range', min: '0', max: String(max), step: '1', value: String(val) });
        range.addEventListener('input', () => { S.pending = +range.value; num.textContent = range.value; });
        main.append(el('p', { class: 'big', text: 'PLACE YOUR SECRET BET' }), el('p', { class: 'sub', text: 'Up to ' + max + ' points. Right answer wins it. Wrong answer loses it.' }), num, range,
          el('div', { class: 'row' }, [el('button', { type: 'button', id: 'bet-zero', text: 'BET 0', onclick: () => { S.pending = 0; render(); } }), el('button', { type: 'button', id: 'bet-all', text: 'ALL IN', onclick: () => { S.pending = max; render(); } })]),
          lockBtn('LOCK IN BET', true, () => send({ type: 'bet', amount: +range.value })));
        break;
      }
      case 'bet_locked':
        main.append(el('p', { class: 'big', text: 'BET LOCKED ✓' }), el('p', { class: 'sub', text: 'Your bet: ' + own.bet + '. Only you can see this.' }));
        break;
      case 'final_choice': {
        const letters = ['A', 'B', 'C', 'D'];
        main.append(card(q), el('div', { class: 'col' }, letters.map((L, i) => el('button', { class: 'choice' + (S.pending === L ? ' sel' : ''), 'data-choice': L, type: 'button',
          onclick: () => { S.pending = L; render(); } }, [el('b', { text: L }), document.createTextNode(q.choices ? q.choices[i] : L)]))),
          lockBtn('LOCK IN', !!S.pending, () => S.pending && send({ type: 'final_choice', choice: S.pending })));
        break;
      }
      case 'final_locked':
        main.append(el('p', { class: 'big', text: 'LOCKED IN ✓' }), el('p', { class: 'sub', text: 'You picked ' + own.choice + '. Waiting for the others…' }));
        break;
      case 'done':
        main.append(el('p', { class: 'big', text: 'THE END' }), el('p', { class: 'sub', text: 'Thanks for playing! Look at the big screen.' }));
        break;
      default:
        main.append(el('p', { class: 'big', text: 'LOOK AT THE BIG SCREEN' }), el('p', { class: 'sub', text: v.game.phase === 'lobby' ? 'You are in! Waiting for the show to start.' : 'Get ready…' }));
    }
  }

  // countdown from server time
  let barTotal = 0, barFor = null;
  setInterval(() => {
    const v = S.view, bar = $('pc-bar').firstElementChild, t = $('pc-timer');
    if (!v || !v.game.deadline) { t.textContent = ''; bar.style.width = '0'; barFor = null; return; }
    const left = Math.max(0, v.game.deadline - (Date.now() + S.offset));
    if (barFor !== v.game.deadline) { barFor = v.game.deadline; barTotal = Math.max(left, 1000); }
    t.textContent = Math.ceil(left / 1000) + 's';
    bar.style.width = Math.min(100, (left / barTotal) * 100) + '%';
  }, 250);

  connect();
})();
