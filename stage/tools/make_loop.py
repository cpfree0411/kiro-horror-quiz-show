"""Make a BGM file into a seamless loop.
uv run --with imageio-ffmpeg --with numpy python stage-v3/tools/make_loop.py <source> <output.ogg> <loopStart s> <loopEnd s> [head s]
With head s, the file starts at that point of the source (everything before is dropped; output loopStart/loopEnd are relative to the new file). Without it, the intro (0–loopStart) is kept.
The last 80 ms of the file are pre-mixed with the sound just before loopStart to hide the seam. Peak 0.89.
Put the output loopStart/loopEnd into KHQS_BGM in index.html. For finding loop points, see the sound section of the README."""
import sys, subprocess, numpy as np, imageio_ffmpeg, wave, tempfile, os
src, dst, s_sec, e_sec = sys.argv[1], sys.argv[2], float(sys.argv[3]), float(sys.argv[4])
head_sec = float(sys.argv[5]) if len(sys.argv) > 5 else 0.
ff = imageio_ffmpeg.get_ffmpeg_exe(); sr = 44100
raw = subprocess.run([ff, '-v', 'quiet', '-nostdin', '-i', src, '-ac', '2', '-ar', str(sr), '-f', 'f32le', '-'], capture_output=True).stdout
x = np.frombuffer(raw, np.float32).reshape(-1, 2).astype(np.float64)
s, e = round(s_sec * sr), round(e_sec * sr)
# put the seam near a zero crossing: fine-tune e within ±5 ms to where it best matches the waveform just before s
W = int(.03 * sr); best = None
for d in range(-int(.005*sr), int(.005*sr)):
    c = np.sum(x[e+d-W:e+d] * x[s-W:s])
    if best is None or c > best[0]: best = (c, d)
e += best[1]
f = int(.08 * sr); r = np.linspace(0, 1, f)[:, None]
h = round(head_sec * sr)
y = x[:e].copy()
y[e-f:e] = x[e-f:e] * np.sqrt(1 - r) + x[s-f:s] * np.sqrt(r)   # replace the end with the sound just before loopStart
y = y[h:]
y *= .89 / np.abs(y).max()
tmp = os.path.join(tempfile.mkdtemp(), 't.wav')
with wave.open(tmp, 'wb') as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(sr); w.writeframes((np.clip(y, -1, 1) * 32767).astype('<i2').tobytes())
subprocess.run([ff, '-v', 'error', '-nostdin', '-y', '-i', tmp, '-c:a', 'libvorbis', '-q:a', '5', dst], check=True)
print('loopStart %.6f  loopEnd %.6f  (shift %+.2f ms)  file %.2f s  scale %.3f' % ((s-h)/sr, (e-h)/sr, best[1]/sr*1000, len(y)/sr, .89/np.abs(x[h:e]).max()))
