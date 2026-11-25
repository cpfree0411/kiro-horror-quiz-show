"""Turn the user's picked SFX (KHQS_sound_v1/user-picked SFX folder) into stage OGG files.
uv run --offline --with imageio-ffmpeg --with numpy python stage-v3/tools/build_sfx.py <picks folder> <output folder> [name part]   (< /dev/null)
  With a name part, only outputs whose names contain it are made. Entries with parent=True are looked up in the folder just above the picks folder (KHQS_sound_v1)
- Trim leading silence (head) and, if needed, the tail (end). The last 15 ms are faded slightly to remove a click
- Match the level of the sounding part (active RMS) to −16 dBFS with peaks no higher than 0.89. Per-scene volume is the gain on the index.html side
- With loop=(start, end), pre-mix the last 80 ms with the sound just before loopStart, like make_loop.py (the drumroll's sustain section)
Processing is trimming and level only (SFX stay crisp: no filters, no reverb)."""
import sys, os, subprocess, wave, tempfile, numpy as np, imageio_ffmpeg

ff = imageio_ffmpeg.get_ffmpeg_exe(); sr = 44100
src_dir, out_dir = sys.argv[1], sys.argv[2]

# (source file number, output name, settings)
SPEC = [
    ('88344', 'sfx_roll.ogg', dict(loop=(2.0, 3.0), end=3.0)),     # default drumroll: after the 0–2 s intro, loop the flat 2–3 s section (when the length is unknown)
    ('88344', 'sfx_roll_up.ogg', dict()),                           # whole default drumroll: peak at about 4.1 s (when the length is known, start late to land on the peak)
    ('278576', 'sfx_roll_alt.ogg', dict()),                         # alternative default drumroll (for comparison in the sound lab)
    ('242242', 'sfx_roll_comedy.ogg', dict()),                      # comedy drumroll
    ('47995', 'sfx_roll_tada.ogg', dict()),                         # drumroll + ta-da (winner announcement)
    ('6313', 'sfx_tada.ogg', dict()),
    ('47489', 'sfx_correct.ogg', dict()),                           # ding-dang-dong correct (act 1 OX when someone is right)                               # ta-da~
    ('81717', 'sfx_correct_dingdong.ogg', dict()),                  # ding-dong correct (act 2 buzzer correct)
    ('6109', 'sfx_buzzer.ogg', dict()),                             # buzzer sound (pressing the buzzer in act 2)
    ('504456', 'sfx_jingle_brass.ogg', dict()),                     # the first-picked quiz-show intro jingle (brass sting). For comparison in the lab
    ('356787', 'sfx_jingle_intro.ogg', dict(parent=True, keep_head=True, end=4.0, fade=.03)),   # quiz-show intro jingle (replaced 2026-11-16): alex_besss 'The Clowns in Circus', start to 4 s. Cuts at the rest just before 4.0 s
    ('6347', 'sfx_wahwah_a.ogg', dict()),                           # wah-wah trombone
    ('207131', 'sfx_wahwah_b.ogg', dict()),                         # wah-wah brass (played at 1.5× speed)
    ('352766', 'sfx_crowd_gasp.ogg', dict()),                       # crowd gasp
    ('352718', 'sfx_crowd_aww.ogg', dict()),                        # crowd disappointment
    ('494319', 'sfx_crowd_boo.ogg', dict()),                        # crowd boo (partly distorted in the original)
    ('236786', 'sfx_applause.ogg', dict()),                         # cheer and applause (curtain up, winner)
    ('439124', 'bgm_betrayal.ogg', dict(keep_head=True)),           # betrayal chance BGM: the whole file is one lap (trimming the start would break the beat)
    ('75859', 'sfx_time_up.ogg', dict(parent=True, start=27.0)),    # the buzzer at the end of the clock-ticking file (27.1 s on): when thinking time runs out. The tick loop is sfx_clock_tick.ogg via make_loop.py
    ('531057', 'sfx_finale_orchestra.ogg', dict(parent=True)),        # grand closing orchestra (mrwashingt0n orchestral radio, 7.9 s): once when the first-place podium rises
    ('251858', 'bgm_betting.ogg', dict(parent=True, loopfile=True)),  # act 3 betting BGM (sergequadrado funky and jazzy gang loop): only the leading 37 ms of mp3 silence trimmed; the rest is one lap
    # Jingles cut from one-minute tracks made with Gemini (2026-11-17, ASSET_ORDER order 6). segs = source second ranges (several are joined with 20 ms crossfades)
    ('Puppet_s_Midnight', 'sfx_act_start.ogg', dict(parent=True, segs=[(21.5, 24.0)])),          # act 1 start: the phrase-ending 'ba-bam!' (bang at 1.6 s)
    ('Puppet_s_Midnight', 'sfx_trans_bats.ogg', dict(parent=True, segs=[(53.0, 57.7)])),        # act 1→2 bat transition: the track ending (bang at about 2.8 s)
    ('Pumpkin_Tumble', 'sfx_trans_pumpkin.ogg', dict(parent=True, segs=[(53.0, 57.7)])),        # act 2→3 pumpkin transition: the track ending (bang at about 3.0 s)
    ('Tiptoeing', 'sfx_final_bet_intro.ogg', dict(parent=True, segs=[(0, 3.85), (60.1, 63.5)])),  # act 3 betting intro: tiptoe intro + the track ending 'boom boom boom!'
    ('Trick_Question', 'sfx_lead_a.ogg', dict(parent=True, segs=[(3.45, 4.95)])),               # comeback hit (one of three at random)
    ('Trick_Question', 'sfx_lead_b.ogg', dict(parent=True, segs=[(5.55, 7.0)])),
    ('Trick_Question', 'sfx_lead_c.ogg', dict(parent=True, segs=[(106.5, 108.0)])),
    # stab candidates (2026-11-25, user: none were good → keep the synthetic stab. Files deleted; kept here for the record): Gemini 'The Grand Prize Awaits'
    # ('Grand_Prize', 'sfx_stab_a.ogg', dict(parent=True, segs=[(39.44, 39.86)])),   # one hit after a −40 dB rest (the track continues, so the end is faded)
    # ('Grand_Prize', 'sfx_stab_b.ogg', dict(parent=True, segs=[(45.09, 45.64)])),   # one hit after a −36 dB rest; dies away by itself before the next beat
    # ('Grand_Prize', 'sfx_stab_c.ogg', dict(parent=True, segs=[(42.43, 42.73)])),   # the first of a stop-time staccato run (short)
    # ('Grand_Prize', 'sfx_stab_d.ogg', dict(parent=True, segs=[(54.16, 54.62)])),   # one hit at the start of the last section (tail faded)
    # ('Grand_Prize', 'sfx_stab_e.ogg', dict(parent=True, segs=[(56.86, 57.70)])),   # the track's ending 'ba-bam!' (grace note + final chord ring)
    # ('Grand_Prize', 'sfx_stab_f.ogg', dict(parent=True, segs=[(0.30, 0.78)])),     # the track's first hit
]

def load(p):
    raw = subprocess.run([ff, '-v', 'quiet', '-nostdin', '-i', p, '-ac', '2', '-ar', str(sr), '-f', 'f32le', '-'], capture_output=True).stdout
    return np.frombuffer(raw, np.float32).reshape(-1, 2).astype(np.float64)

def save(y, dst):
    tmp = os.path.join(tempfile.mkdtemp(), 't.wav')
    with wave.open(tmp, 'wb') as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(sr); w.writeframes((np.clip(y, -1, 1) * 32767).astype('<i2').tobytes())
    subprocess.run([ff, '-v', 'error', '-nostdin', '-y', '-i', tmp, '-c:a', 'libvorbis', '-q:a', '6', dst], check=True)

only = sys.argv[3] if len(sys.argv) > 3 else ''
for key, name, o in SPEC:
    if only not in name: continue
    d = os.path.dirname(os.path.abspath(src_dir)) if o.get('parent') else src_dir
    x = load(os.path.join(d, next(f for f in os.listdir(d) if key in f)))
    if o.get('start'): x = x[round(o['start'] * sr):]               # use the source only from this second
    if o.get('segs'):                                               # cut from the middle of a track: 5 ms fade-in, 20 ms crossfades at joins, 80 ms fade-out at the end
        parts = [x[round(a * sr):round(b * sr)].copy() for a, b in o['segs']]
        y = parts[0]; t = int(.02 * sr); r = np.linspace(0, 1, t)[:, None]
        for p in parts[1:]: y = np.concatenate([y[:-t], y[-t:] * np.sqrt(1 - r) + p[:t] * np.sqrt(r), p[t:]])
        t = int(.005 * sr); y[:t] *= np.linspace(0, 1, t)[:, None]
        t = int(.08 * sr); y[-t:] *= np.linspace(1, 0, t)[:, None] ** .5
        x = y; o = dict(o, keep_head=True, loopfile=True)            # no further trimming or fading below
    m = np.abs(x).max(1); pk = m.max()
    if o.get('keep_head'): h = 0
    elif o.get('loopfile'): h = int(np.argmax(m > 1e-4))           # loop track: trim only the leading silence the encoder added (end unchanged, no fade)
    else:
        h = int(np.argmax(m > pk * 10 ** (-40 / 20)))           # where sound first rises above 40 dB below the peak
        h = max(0, h - int(.01 * sr))                            # 10 ms of room before the attack
    loop = o.get('loop')
    if loop:                                                     # source seconds. The last 80 ms become the sound just before loopStart
        s, e = round(loop[0] * sr), round(loop[1] * sr); f = int(.08 * sr); r = np.linspace(0, 1, f)[:, None]
        y = x[:e].copy(); y[e - f:e] = x[e - f:e] * np.sqrt(1 - r) + x[s - f:s] * np.sqrt(r)
    else:
        y = x[:round(o['end'] * sr)].copy() if o.get('end') else x.copy()
        last = len(m) - int(np.argmax(m[::-1] > pk * 10 ** (-60 / 20)))   # trim trailing silence (below −60 dB)
        if not (o.get('keep_head') or o.get('loopfile')): y = y[:min(len(y), last + int(.05 * sr))]
        if not o.get('loopfile'): t = min(len(y), int(o.get('fade', .015) * sr)); y[-t:] *= np.linspace(1, 0, t)[:, None] ** .5
    y = y[h:]
    a = np.abs(y).max(1); fr = 1024; n = len(a) // fr * fr
    rms = np.sqrt((y[:n] ** 2).mean(1).reshape(-1, fr).mean(1)); act = rms[rms > rms.max() * .1]
    g = min(10 ** (-16 / 20) / np.sqrt((act ** 2).mean()), .89 / np.abs(y).max())
    y *= g
    save(y, os.path.join(out_dir, name))
    extra = ('  loopStart %.6f loopEnd %.6f' % ((s - h) / sr, (e - h) / sr)) if loop else ''
    print('%-22s %6.3f s  head -%.3f s  gain %+.1f dB%s' % (name, len(y) / sr, h / sr, 20 * np.log10(g), extra))
