/* Mock engine — replays the interface/scenarios scenarios exactly as the khqs.stage/1 protocol.
 *
 * - Fills proto / sseq / at / gate.id on stream messages (the scenarios' g-0 is a placeholder).
 * - A gate message does not advance until stage.beat_done arrives or timeoutMs passes.
 * - An await step waits for a stage reply (stage.media_ended etc.).
 * - Jumping to a label applies everything before it at once in fast mode (the stage draws the resting pose and acks skipped).
 * The stage only knows link.send / onMessage, so a real engine can be swapped in with the same shape.
 */
(() => {
  'use strict';
  const PROTO = 'khqs.stage/1';

  class MockEngine {
    constructor({ deliver, log }) {
      this.deliver = deliver;          // (msg, {fast}) => void   engine → stage
      this.log = log || (() => {});
      this.speed = 1;
      this.paused = false;
      this.run = 0;                    // playback generation. A restart stops the previous loop
      this.waiters = [];
    }

    load(scenario) { this.scenario = scenario; }

    labels() { return this.scenario.steps.filter(s => s.label).map(s => s.label); }

    // stage → engine
    receive(msg) {
      this.log('in', msg);
      this.waiters = this.waiters.filter(w => {
        if (w.match(msg)) { w.resolve(msg); return false; }
        return true;
      });
    }

    async start(label = null) {
      const run = ++this.run;
      const steps = this.scenario.steps;
      // label: a label name or a step number (for review). Everything before it is applied at once in fast mode
      const from = typeof label === 'number' ? label : label ? steps.findIndex(s => s.label === label) : 0;
      this.sseq = 0;
      this.scenarioBase = null;
      this.scenarioElapsed = 0;
      this.waiters.forEach(w => w.resolve(null));
      this.waiters = [];
      for (let i = 0; i < steps.length; i++) {
        if (run !== this.run) return;
        const step = steps[i];
        const fast = i < from;
        if (step.label) { this.log('label', step.label); continue; }
        if (!fast && step.delayMs) await this.sleep(step.delayMs, run);
        this.scenarioElapsed += step.delayMs || 0;
        if (run !== this.run) return;
        if (step.send) await this.send(step.send, fast, run);
        else if (step.await && !fast) {
          const got = await this.wait(m => m.type === step.await, step.timeoutMs);
          if (!got && run === this.run) this.log('timeout', `${step.await} (${step.timeoutMs}ms)`);
        }
      }
      if (run === this.run) { this.log('label', '— end of scenario —'); if (this.onEnd) this.onEnd(this.scenario, run); }
    }

    async send(template, fast, run) {
      const msg = JSON.parse(JSON.stringify(template));
      msg.proto = PROTO;
      if (msg.type === 'snapshot') {
        this.sseq = msg.sseq || 0;
        this.scenarioBase = msg.data.game.phaseStartedAt;
      } else {
        msg.sseq = ++this.sseq;
      }
      msg.at = Date.now();
      this.rebaseDeadline(msg);
      if (msg.gate) msg.gate.id = `g-${msg.sseq}`;
      this.log('out', msg, fast);
      const acked = msg.gate ? this.wait(m => m.type === 'stage.beat_done' && m.data.gate === msg.gate.id, fast ? 1500 : msg.gate.timeoutMs / this.speed) : null;
      this.deliver(msg, { fast });
      if (acked) {
        const got = await acked;
        if (!got && run === this.run) this.log('timeout', `${msg.gate.id} ${msg.type} — gate timeout, moving on`);
      }
    }

    // Shift the scenario's absolute deadline to now (for the timer display)
    rebaseDeadline(msg) {
      const d = msg.data && msg.data.deadline;
      if (typeof d !== 'number' || this.scenarioBase == null) return;
      const remain = Math.max(3000, Math.min(30000, d - (this.scenarioBase + this.scenarioElapsed)));
      msg.data.deadline = Date.now() + remain / this.speed;
    }

    wait(match, timeoutMs) {
      return new Promise(resolve => {
        const w = { match, resolve };
        this.waiters.push(w);
        setTimeout(() => { if (this.waiters.includes(w)) { this.waiters.splice(this.waiters.indexOf(w), 1); resolve(null); } }, timeoutMs);
      });
    }

    async sleep(ms, run) {
      let left = ms;
      while (left > 0 && run === this.run) {
        await new Promise(r => setTimeout(r, 40));
        if (!this.paused) left -= 40 * this.speed;
      }
    }

    stop() { this.run++; this.waiters.forEach(w => w.resolve(null)); this.waiters = []; }
  }

  window.MockEngine = MockEngine;
})();
