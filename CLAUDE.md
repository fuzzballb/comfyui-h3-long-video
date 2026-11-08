# comfyui-h3-long-video

ComfyUI custom nodes + scripts for MiniMax H3 videos of any length, rendered in 10 s parts that continue each other in
latent space. The README is the manual (how it works, node reference, prompting tips, troubleshooting); this file is for
working on the code.

## Layout

- `long_video.py`: continue / append / load part, conditioning save/load, upscale append (crossfade, hard-cut unblend),
  reference audios. `face_detail.py`: face crop (YuNet + SFace tracker) and paste. `__init__.py` merges both node maps.
- `example_workflows/1-4`: the UI workflows. `story_kit/templates/*_api.json` are workflows 1, 2 and 4 in API form;
  `run_story.py build()` addresses their nodes by id (`'22'` prompt, `'40'` seed, `'79'` new shot ...). Change a
  workflow and its template together, and check those ids still match.
- `story_kit/run_story.py`: runs a story file (`gen` = lint + one part at a time with cut/speech re-rolls,
  `--no-check`, `upscale`, `prompts`, `lint`, `dialogue`). `check_cuts.py` (`find_cuts()`), `gate.sh` (one part at a time, held until approved), `propsheet.py`,
  `location_sound.py`. Example stories in `story_kit/stories/`, their reference images in `story_kit/refs/`.
- `claude-skill/comfy-h3-video/`: a skill for *using* all this (copy to `~/.claude/skills/`). It is generated from a
  private copy by a sync script that strips personal names and paths: edit it there, not here, when you have that copy.
- `output_picker.py` and `web/` are local extras and git-ignored; `__init__.py` loads them only if present.

## Rules

- **The repo is public.** Never commit personal photos, real names, home or street names, e-mail addresses, absolute
  home paths or disk ids. Story files that use someone's photos stay untracked. Scan `git diff` before committing.
- **Keep the README in sync**: a node input, default, file name or story-kit command that changes must change in the
  README (node reference, steps, folder layout) in the same commit. Lessons from real runs go into "Prompting tips" or
  "Settings that matter" with what went wrong and what fixed it.
- Project output lives in `ComfyUI/output/long_video/<project>/` (`segments/`, `latents/`, `upscaled/`, `_superseded/`).
  Anything that rewrites a part must leave the files derived from it consistent (e.g. a re-upscale deletes that part's
  `noface.mkv`/`face.json`; a re-roll moves the continuations after it to `_superseded/`).
- Don't put `H3MiniMaxCache` in the generate chain (continuations ignore their context with it) and keep SLA off by
  default (backgrounds warp). See README "Settings that matter".
- Commits: short imperative subject, body with the why.

## Testing a change

Python changes to the nodes need a ComfyUI restart (only when the queue is empty: `curl -s 127.0.0.1:8188/queue`).
Cheap checks that don't render:

```bash
python3 -c "import ast; ast.parse(open('long_video.py').read())"
python3 story_kit/run_story.py prompts story_kit/stories/dhl_enduro.py     # final prompts, Picture numbering
python3 story_kit/run_story.py lint story_kit/stories/dhl_enduro.py
python3 story_kit/check_cuts.py <ComfyUI>/output/long_video/<existing project> 3
```

A real test is one part of a short story (~10 min on an RTX 3090 at 1280×704) or an upscale of one existing part
(~10 min). Check results by eye too: contact sheet (`segments/part_NNN_sheet.png`), the join between parts, and for
dialogue a Whisper transcript.
