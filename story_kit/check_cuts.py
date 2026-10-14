"""Find hard cuts in generated parts and make a contact sheet per part. Needs ffmpeg.

    python3 check_cuts.py <project folder> [part ...]       e.g. check_cuts.py ComfyUI/output/long_video/my_project 3 4

A hard cut is an isolated jump in the mean frame difference (64x36 gray, 0-255) above --cut (default 30).
Fast POV or tracking shots have many values of 12-25 from motion alone; those are not cuts.
Contact sheets (1 frame per second) are written next to the segments as part_NNN_sheet.png; open them to check
props, faces and continuity by eye.
"""
import argparse, glob, os, re, subprocess

ap = argparse.ArgumentParser()
ap.add_argument('project'); ap.add_argument('parts', nargs='*', type=int)
ap.add_argument('--cut', type=float, default=30.0)
a = ap.parse_args()

seg = os.path.join(a.project, 'segments')
files = sorted(glob.glob(os.path.join(seg, 'part_*.mkv')))
if a.parts:
    files = [f for f in files if int(re.search(r'part_(\d+)', f).group(1)) in a.parts]
for f in files:
    out = subprocess.run(['ffmpeg', '-v', 'error', '-i', f, '-vf',
                          'scale=64:36,format=gray,tblend=all_mode=difference,signalstats,'
                          'metadata=print:key=lavfi.signalstats.YAVG:file=-', '-f', 'null', '-'],
                         capture_output=True, text=True).stdout
    vals = [float(x) for x in re.findall(r'YAVG=([\d.]+)', out)]
    cuts = [(i + 1, v) for i, v in enumerate(vals) if v > a.cut]
    sheet = f[:-4] + '_sheet.png'
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', f, '-vf', 'fps=1,scale=400:-1,tile=5x2', '-frames:v', '1', sheet])
    name = os.path.basename(f)
    if cuts:
        print(f'{name}: {len(cuts)} cut(s) at ' + ', '.join(f'{n / 24:.1f}s ({v:.0f})' for n, v in cuts))
    else:
        print(f'{name}: no cuts')
