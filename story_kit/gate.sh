#!/bin/bash
# Gate mode: render a story one part at a time and hold each part at a gate until it is reviewed.
#
#   story_kit/gate.sh <story.py> <project> <part> [<part> ...]
#
# Per part: `run_story.py gen` (cut check + Whisper word check, re-rolls up to 3 takes), then a loudness check
# (ebur128 max momentary loudness above GATE_LOUD = shouting), a join check for continuations (last frame of the previous
# part vs first frame of this one; above GATE_JOIN = the background was swapped without a visible cut) and a contact sheet at 2 fps. Then it WAITS for a file in
# the gate folder: `approve_N` goes on to the next part, `reroll_N` renders part N again (edit the story file first to
# change its prompt). `skipgen_N` + `reroll_N` re-checks part N without rendering it again. Status lines go to gate.log.
# A reviewer (a person or an agent) looks at sheet_NNN.jpg and the status line, against a checklist per part: who else is
# in the scene, positions relative to the camera, props/style, volume, hands, and that the part starts where the
# previous one ended. Nothing is built on a part that hasn't passed.
set -u
STORY=$(realpath "$1"); PROJECT=$2; shift 2
COMFYUI=${COMFYUI:-$HOME/ComfyUI}
PY=${PY:-$COMFYUI/venv/bin/python}
D=$COMFYUI/output/long_video/$PROJECT
G=${GATE_DIR:-$D/gate}
LOUD_MAX=${GATE_LOUD:--21}      # LUFS; normal dialogue peaked at -23..-26, shouted lines at -15..-19
JOIN_MAX=${GATE_JOIN:-25}       # mean luma difference; good joins were 1-9, swapped backgrounds 29-44
mkdir -p "$G"
HERE=$(dirname "$(realpath "$0")")
cd "$HERE"
for P in "$@"; do
  p=$(printf %03d "$P")
  while true; do
    if [ -f "$G/skipgen_$P" ]; then rm -f "$G/skipgen_$P"
    else PYTHONUNBUFFERED=1 "$PY" run_story.py gen "$STORY" "$PROJECT" "$P" >> "$G/gen.log" 2>&1; fi
    M=$(ffmpeg -nostats -i "$D/segments/part_$p.mkv" -af ebur128 -f null - 2>&1 | grep -o "M: *-\?[0-9.]*" | awk '{print $2}' | sort -g | tail -1)
    LOUD=ok; awk -v m="$M" -v t="$LOUD_MAX" 'BEGIN{exit !(m > t)}' && LOUD=TOO_LOUD
    JOIN=""
    q=$(printf %03d $((10#$P - 1)))
    CTX=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1])).get(sys.argv[2], 0))" "$D/shots.json" "$P" 2>/dev/null || echo 0)
    if [ "$CTX" != 0 ] && [ -f "$D/segments/part_$q.mkv" ]; then
      ffmpeg -v error -y -sseof -0.05 -i "$D/segments/part_$q.mkv" -frames:v 1 -vf scale=320:180 "$G/join_a.png"
      ffmpeg -v error -y -i "$D/segments/part_$p.mkv" -frames:v 1 -vf scale=320:180 "$G/join_b.png"
      J=$(ffmpeg -v error -i "$G/join_a.png" -i "$G/join_b.png" -filter_complex "blend=all_mode=difference,signalstats,metadata=print:file=-" \
          -f null - 2>/dev/null | grep -o "YAVG=[0-9.]*" | cut -d= -f2)
      JOIN=" | join $J"; awk -v j="$J" -v t="$JOIN_MAX" 'BEGIN{exit !(j > t)}' && JOIN="$JOIN (JUMP)" || JOIN="$JOIN (ok)"
    fi
    ffmpeg -v error -y -i "$D/segments/part_$p.mkv" -vf "fps=2,scale=320:-1,tile=10x2" -frames:v 1 "$G/sheet_$p.jpg"
    echo "$(date +%H:%M) part $P ready: $(grep "^part $P take" "$G/gen.log" | tail -1 | cut -c1-200) | loudness max $M ($LOUD)$JOIN | WAITING" >> "$G/gate.log"
    until [ -f "$G/approve_$P" ] || [ -f "$G/reroll_$P" ]; do sleep 10; done
    if [ -f "$G/approve_$P" ]; then echo "$(date +%H:%M) part $P approved" >> "$G/gate.log"; break; fi
    rm -f "$G/reroll_$P"; echo "$(date +%H:%M) part $P re-roll" >> "$G/gate.log"
  done
done
echo "$(date +%H:%M) GATE DONE" >> "$G/gate.log"
