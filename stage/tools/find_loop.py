"""Find BGM loop points. Measure the tempo (beat length), then among loopStart candidates and loopEnd candidates
find the pair whose following 2 s spectra are most alike (a score of 0.9 or more usually sounds natural).
1) Source to a numpy array: instead of an_track, this one line
   uv run --with imageio-ffmpeg --with numpy python -c "import subprocess,numpy as np,imageio_ffmpeg as f;np.save('x.npy',np.frombuffer(subprocess.run([f.get_ffmpeg_exe(),'-v','quiet','-i','source.mp3','-ac','1','-ar','22050','-f','f32le','-'],capture_output=True).stdout,np.float32))"
2) uv run --with numpy python stage-v3/tools/find_loop.py x.npy <start min> <start max> <end min> <end max>
Then make the file with make_loop.py."""
import sys, numpy as np
x = np.load(sys.argv[1]); sr = 22050; hop = 256; n = 2048
fr = np.lib.stride_tricks.sliding_window_view(x, n)[::hop] * np.hanning(n)
S = np.abs(np.fft.rfft(fr, axis=1))[:, :400]          # ~0-4.3 kHz
L = np.log1p(S * 10)
onset = np.maximum(0, np.diff(L, axis=0)).sum(1); onset -= onset.mean()
fps = sr / hop
ac = np.correlate(onset, onset, 'full')[len(onset)-1:]
lo, hi = int(fps*60/200), int(fps*60/50)
lag = lo + np.argmax(ac[lo:hi]); print('beat %.3f s  = %.1f bpm' % (lag/fps, 60*fps/lag))
for k in (2, 3, 4, 6): print(' lag x%d acf %.3f' % (k, ac[lag*k]/ac[0]))
# loop search: similarity of 2 s of spectra after candidate start vs after candidate end
Ln = L / (np.linalg.norm(L, axis=1, keepdims=True) + 1e-9)
W = int(2 * fps)
def sim(a, b): return (Ln[a:a+W] * Ln[b:b+W]).sum(1).mean()
res = []
for s in range(int(float(sys.argv[2])*fps), int(float(sys.argv[3])*fps), 2):
    for e in range(int(float(sys.argv[4])*fps), int(float(sys.argv[5])*fps), 2):
        res.append((sim(s, e), s/fps, e/fps))
res.sort(reverse=True)
for r in res[:12]: print('sim %.4f  start %.3f  end %.3f  len %.3f  beats %.2f' % (r[0], r[1], r[2], r[2]-r[1], (r[2]-r[1])/(lag/fps)))
