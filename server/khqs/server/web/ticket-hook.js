/* Defines KHQS_TICKET_JOIN before the ticket page's own script runs (docs/HANDOFF.md section 5.5). */
(() => {
  'use strict';
  window.KHQS_TICKET_JOIN = async name => {
    let r;
    try {
      const resp = await fetch('/api/join', { method: 'POST', headers: { 'content-type': 'application/json', 'X-KHQS': '1' }, body: JSON.stringify({ name }) });
      r = await resp.json();
    } catch (e) { return { error: 'THE BOX OFFICE IS CLOSED' }; }
    if (r.error) return { error: r.error };
    try { localStorage.setItem('khqs.cred', JSON.stringify({ cred: r.credential, seat: r.seat, name })); } catch (e) { /* private mode */ }
    setTimeout(() => { location.href = '/phone'; }, 1600);   // after the ADMITTED stamp
    return { ok: true };
  };
})();
