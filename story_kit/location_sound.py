"""Make dialogue sound recorded on location instead of in a studio. Needs ffmpeg.

    python3 location_sound.py <video.mp4> [out.mp4] [--echo 0.22] [--noise 0.02] [--no-noise]

H3 copies the sound of the voice samples it gets as reference audio; clean samples give dry, close, studio-like voices.
This re-mixes the finished video's audio (the picture is copied untouched):
  - band-limits it to 150-6500 Hz with a small dip at 2.5 kHz, like a camera microphone a few metres away;
  - adds short reflections (23/41/67 ms) as from nearby walls (--echo sets their level, 0 = off);
  - mixes in faint low street rumble (brown noise, --noise sets the level, --no-noise = off);
  - normalizes to -18 LUFS.
Default output: <video>_location.mp4. Run it on <project>_full_upscaled.mp4 as the last step.
"""
import argparse, os, subprocess

ap = argparse.ArgumentParser()
ap.add_argument('video'); ap.add_argument('out', nargs='?')
ap.add_argument('--echo', type=float, default=0.22)
ap.add_argument('--noise', type=float, default=0.02)
ap.add_argument('--no-noise', action='store_true')
a = ap.parse_args()
out = a.out or os.path.splitext(a.video)[0] + '_location.mp4'

voice = 'highpass=f=150,lowpass=f=6500,equalizer=f=2500:t=q:w=1:g=-2'
if a.echo > 0:
    e = a.echo
    voice += f',aecho=0.85:0.5:23|41|67:{e:.3f}|{e * 0.64:.3f}|{e * 0.36:.3f}'
cmd = ['ffmpeg', '-v', 'error', '-y', '-i', a.video]
if a.no_noise or a.noise <= 0:
    graph = f'[0:a]{voice},loudnorm=I=-18:TP=-1.5:LRA=11[a]'
else:
    cmd += ['-f', 'lavfi', '-i', f'anoisesrc=color=brown:amplitude={a.noise}:sample_rate=48000']
    graph = (f'[0:a]{voice},volume=0.95[v];[1:a]lowpass=f=900,highpass=f=60,volume=0.6[n];'
             f'[v][n]amix=inputs=2:duration=first:normalize=0,loudnorm=I=-18:TP=-1.5:LRA=11[a]')
cmd += ['-filter_complex', graph, '-map', '0:v', '-map', '[a]', '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k', '-shortest', out]
subprocess.run(cmd, check=True)
print(out)
