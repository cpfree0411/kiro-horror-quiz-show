"""Make three stretched versions of the sign-crank 'creak' sample (2026-11-16).
Source: Pixabay 'Metallic creak' (freesound_community, Crinkem, Pixabay Content License); 0.46 s, of which about 0.25 s is sound.
uv run --with imageio-ffmpeg --with numpy python stage-v3/tools/make_creak.py <source.mp3> <output folder>
  creak_a.ogg  stretched: same pitch, about 1.9× longer ('cree~eak')
  creak_b.ogg  slowed: 1.6× longer and that much lower (heavier, rustier 'cree~eeak')
  creak_c.ogg  twice: the original + a slightly lower, stretched one ('creak-eek')
All mono 44.1 kHz, leading/trailing silence trimmed, peak 0.9."""
import sys, subprocess, numpy as np, imageio_ffmpeg, wave, tempfile, os
src, outdir = sys.argv[1], sys.argv[2]; ff = imageio_ffmpeg.get_ffmpeg_exe(); SR = 44100
def dec(af=''):
    cmd = [ff, '-v', 'quiet', '-nostdin', '-i', src] + (['-af', af] if af else []) + ['-ac', '1', '-ar', str(SR), '-f', 'f32le', '-']
    return np.frombuffer(subprocess.run(cmd, capture_output=True).stdout, np.float32).astype(np.float64)
def trim(x, th=.012):
    nz = np.where(np.abs(x) > th * np.abs(x).max() / .14)[0]
    a, b = max(0, nz[0] - int(.004 * SR)), min(len(x), nz[-1] + int(.03 * SR))
    y = x[a:b].copy(); f = int(.004 * SR); y[:f] *= np.linspace(0, 1, f); y[-int(.02 * SR):] *= np.linspace(1, 0, int(.02 * SR))
    return y
def save(y, name):
    y = y / np.abs(y).max() * .9
    tmp = os.path.join(tempfile.mkdtemp(), 't.wav')
    with wave.open(tmp, 'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR); w.writeframes((y * 32767).astype('<i2').tobytes())
    out = os.path.join(outdir, name)
    subprocess.run([ff, '-v', 'error', '-nostdin', '-y', '-i', tmp, '-c:a', 'libvorbis', '-q:a', '6', out], check=True)
    print('%-12s %.3f s' % (name, len(y) / SR))
base = trim(dec())
print('trimmed original %.3f s' % (len(base) / SR))
save(trim(dec('atempo=0.72,atempo=0.72')), 'creak_a.ogg')                      # 0.72² ≈ 0.52 → 1.9×
save(trim(dec('asetrate=24000*0.625,aresample=44100')), 'creak_b.ogg')          # the 24 kHz source at 1/1.6 speed
second = trim(dec('asetrate=24000*0.85,aresample=44100,atempo=0.8'))
gap = np.zeros(int(.035 * SR)); save(np.concatenate([base, gap, second * .85]), 'creak_c.ogg')
