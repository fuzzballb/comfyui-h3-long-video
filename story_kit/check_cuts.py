"""Find hard cuts in generated parts and make a contact sheet per part. Needs ffmpeg.

    python3 check_cuts.py <project folder> [part ...]       e.g. check_cuts.py ComfyUI/output/long_video/my_project 3 4

A hard cut is an isolated jump in the mean frame difference (64x36 gray, 0-255) above --cut (default 30).
Fast POV or tracking shots have many values of 12-25 from motion alone; those are not cuts.
Contact sheets (1 frame per second) are written next to the segments as part_NNN_sheet.png; open them to check
props, faces and continuity by eye. `run_story.py gen` uses find_cuts() to re-roll parts with cuts.
"""
import argparse, glob, os, re, subprocess

FPS = 24


def find_cuts(path, threshold=30.0):
    """[(seconds, value), ...] for every frame-to-frame jump above threshold."""
    out = subprocess.run(['ffmpeg', '-v', 'error', '-i', path, '-vf',
                          'scale=64:36,format=gray,tblend=all_mode=difference,signalstats,'
                          'metadata=print:key=lavfi.signalstats.YAVG:file=-', '-f', 'null', '-'],
                         capture_output=True, text=True).stdout
    vals = [float(x) for x in re.findall(r'YAVG=([\d.]+)', out)]
    return [((i + 1) / FPS, v) for i, v in enumerate(vals) if v > threshold]


def describe(cuts):
    return f'{len(cuts)} cut(s) at ' + ', '.join(f'{t:.1f}s ({v:.0f})' for t, v in cuts) if cuts else 'no cuts'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('project'); ap.add_argument('parts', nargs='*', type=int)
    ap.add_argument('--cut', type=float, default=30.0)
    a = ap.parse_args()
    files = sorted(glob.glob(os.path.join(a.project, 'segments', 'part_*.mkv')))
    if a.parts:
        files = [f for f in files if int(re.search(r'part_(\d+)', f).group(1)) in a.parts]
    for f in files:
        cuts = find_cuts(f, a.cut)
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', f, '-vf', 'fps=1,scale=400:-1,tile=5x2', '-frames:v', '1',
                        f[:-4] + '_sheet.png'])
        print(f'{os.path.basename(f)}: {describe(cuts)}')


if __name__ == '__main__':
    main()
