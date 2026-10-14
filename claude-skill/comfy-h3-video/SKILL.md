---
name: comfy-h3-video
description: Replace a person in a video with a character (e.g. the DHL guy), give them the user's voice, add a voice-over, or join separately generated clips without a visible jump — using MiniMax H3 workflows in this ComfyUI install. Use when the user asks to swap/replace a person in a video, make a character speak with their voice, fix lip sync, fix a cut between two generated video parts, or make a long multi-part video (story in parts, re-roll a part, upscale, face pass).
---

# MiniMax H3 video: swap, voice, joining clips, long videos

ComfyUI runs at `127.0.0.1:8188` from `~/ComfyUI` (see its CLAUDE.md for restart and storage rules).
All workflows below are in the Workflows sidebar folder `H3 Video/` (`user/default/workflows/H3 Video/`), except `Voice-over - my voice` (in `Tools/`). Verified on 2026-09-26.
File names carry a date prefix (`2026-09-26 DHL Swap - H3 voice.json`); the tables below use the name without it.

## Workflows

| Workflow | Use |
|---|---|
| `DHL Swap - H3 voice` | Replace the person in a video (SAM3 tracks `person`) with the DHL guy; H3 generates the voice from `ref_audios` = `input/my_voice_en.wav`. Output `output/DHL-Swap_*.mp4`. |
| `AV Bridge - join two clips (low res)` | Regenerate the stretch around a cut between clip A and clip B so the motion continues. 640×448, ~4 min. |
| `Voice-over - my voice` | Any video: Whisper → SRT → ChatterBox TTS in voice `my_voice.wav` (smart_natural timing) → normalize → video. Output `output/voiceover/`. |
| `MiniMaxH3 Face-Body Swap - Workflow 1` | Head-only swap (tracks `head`). |

Character references in `input/`: `dhl_body.png` (4-view sheet), `dhl_Face.png`, `dhl_head_34.png`, `dhl_head_side.png`.
User voice: `models/voices/my_voice.wav` (+ `.reference.txt`), same audio as `input/my_voice_en.wav`.

## Running a workflow from the shell

1. Convert the UI workflow to an API prompt with the real frontend:
   `node ~/.claude/skills/comfy-h3-video/scripts/convert.mjs ui2api "<workflow.json>" out_api.json`
2. Edit inputs in the API JSON (video file, prompt, frame caps, seed), `POST /prompt`, poll `/history/<id>`.
3. To save a changed setup back to the sidebar: `convert.mjs api2ui out_api.json out_ui.json "<name>"`, then
   `POST /api/userdata/workflows%2FH3%20Video%2F<YYYY-MM-DD name>.json?overwrite=false`. Pin seeds to `fixed`. Re-run `ui2api` on the saved file and
   diff against the working prompt: custom widgets can silently change on load (NKDSigmasCurve reset to a straight line once).

## Swap: settings that matter

- Source video must be constant 24 fps. Copy it into `input/`; never modify the user's original.
- Size/length per pass: ~10 s at ≤1280×896. 15 s of 1440×2560 OOM-killed ComfyUI (62 GB RAM). Use `custom_width/height` and `frame_load_cap`.
  1280×896 takes ~4 min per sampling step (8 steps); 960×544 about 1/3 of that.
- LoRA: `minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16` at 1.0. Never the `*_int8convrot` LoRAs with LoraLoaderModelOnly: they are quantized, log "lora key not loaded … comfy_quant" and produce pure noise.
- Text encoder: `qwen3vl_32b_minimax_h3_int8_convrot` (NVFP4 is for newer GPUs than the 3090).
- Audio (`NKDAVLatent.audio_mode`):
  - `regenerate` + voice in `ref_audios`: H3 makes voice and lips together → in sync. Needs a `VAEDecodeAudio(sampler latent, audio VAE)` into Video Combine;
    the author's Workflow 2 wires the *source* audio to the output, so regenerated audio is silently discarded.
  - `keep`: lips follow the source audio track. To give a character another voice this way, first replace the source video's audio track, then swap.
- Full-body source works best when the person is fully in frame; extreme close-ups make the model invent odd framings (a giant boot).
- Props outside the person mask stay (the runway wings survived); widen the SAM3 text if they must go.

## Videos longer than one pass

New long video (no source to swap): sidebar workflow `H3 Video/<date> PlagueKind Long Video` (V11 model stack; 3 refs, add a 4th LoadImage on
`PK_MiniMaxH3Combined.reference_images.reference_image_3` for a location). Switches: Turbo, SLA, New shot, Save conditioning.
One part per run: `Part number` 1, 2, 3 … ; each part continues the previous part's saved latent (last 39 frames + audio frozen),
via `H3LongVideoContinue`/`H3LongVideoAppend` (`custom_nodes/h3_output_video/long_video.py`). Output
`output/long_video/<project>/<project>_full.mp4` (`output/long_video` is on the NVMe). ~10 min per 10 s part at 1152×768, turbo, SLA off.
Re-rolling part N moves the later parts that continue from it to `_superseded/`, stopping at the next New-shot part; re-generate those (and re-upscale N…).
Never put `H3MiniMaxCache` in that chain: with it the continuation ignores
the context (cut + garbage frames, seam diff 28 vs 9); verified 2026-10-10.
`H3SLAAttention` (sparsity 0.7, int8 QK) makes straight background lines warp (windows tilt, balconies morph); same seed
without it is stable but ~2.8× slower per step (86 vs 30 s/it turbo, 1152×864×10 s). Workflow switch defaults to SLA off.
Upscale with `H3 Video/... PlagueKind Long Video - Upscale` (one queue per part, in order; V11 H3 latent upscale ×1.5, sigmas `0.6316, 0.3158, 0` + FILM 48 fps + RCAS;
crossfades continuation joins and rewrites the previous upscaled part; ~11-13 min/part). Needs `latents/part_NNN.cond.pt`, which the main workflow saves.
Result `<project>_full_upscaled.mp4`. The LTX-2.3 chunked upscaler was tried and removed (barely better than lanczos).
V11's upscale start sigma 0.9035 re-generates small props from the prompt (a brown parcel got a pink URGENT label, then turned see-through at ~8.5 s,
original fine); 0.6316 keeps them, 0.45 is softer. Fixed in the sidebar and repo workflows on 2026-10-13. Re-upscaling part N overwrites its crossfade
into N+1: re-upscale N+1 afterwards. Compare props original vs upscale with a zoomed crop strip (`fps=3,crop=...,tile=9x1`) before reporting.
Face pass (optional): `H3 Video/... PlagueKind Long Video - Face Detail` re-renders small faces (30-140 px) of the reference person only as a 512² H3 v2v
close-up at sigma 0.8, pasted back with an oval mask. Tracker (YuNet + SFace in models/detection): only frontal faces >= 40 px confirm identity,
every frame must score >= match (0.3 in the workflow) on its own, no chaining (chaining drifted onto dancers/audience). Reference image is
shrunk to <= 640 px first (YuNet misdetects on 2048 px). Run it only after ALL parts are upscaled. 0.6 kept the wrong face, 0.8 matched (DHL);
0.95 looked bad and warped (angel). It can't reshape a face that a whole part got wrong: regenerate those parts instead.
Face consistency across a new shot: put a tight face crop of the person as Picture 1 and say "his face is exactly the face in Picture 1: <traits>"
(angel_catwalk option B fixed a wrong catwalk face this way). Side effect: H3 may cut away to a close-up copying that crop's white backdrop, and
small facial actions ("winks") pull it into close-ups. Fix: new seed + "One continuous take, the camera never cuts and there are no close-ups:
his whole body from head to sandals in frame", no small facial actions.
Extra LoRAs (models/loras: camera_motion_h3_lora_v1_3000_pruned "camera motion," trigger; mmh3_cinematic_texture_DY "DY"; mvmt_h3_lora_v1_500;
extremeEnduroBetterBike_v1; BulletTime-MMH3 "bullet-time" + timestamped phases; minimax_h3_vfx_edit_v1.0_r128_ffp = v2v edit, "vfx_edit:"):
chain LoraLoaderModelOnly after the turbo switch (node 73 -> ... -> node 9). Three at author strengths (0.8+0.5+0.6) on the 8-step turbo made moving
objects ghost (see-through parcel); keep the sum around 1.2-1.3 (e.g. camera 0.6 + human motion 0.3 + DY 0.4: solid). Script: dhl_enduro (2026-10-13).
The upscale append node now copies real frames across hard cuts instead of FILM-blending them (cut_threshold 30).
Props: anything only described in words (bike, top case, parcel) changes per part. Make a white-background product sheet with Qwen Image 2.1 edit
(sidebar `Image/2026-09-26 image_qwen_image_2_1_image_edit`, feed crops of an earlier part as Picture 1/2, ask for two views with the prop identical
in BOTH views) and add it as extra `reference_images.reference_image_N` only in parts whose prompt mentions it ("... from Picture 4"; number in
input order: face, body, [location], props). Story kit in the repo: `custom_nodes/h3_output_video/story_kit/` - `run_story.py gen <story.py> <project> [part|story:part ...]`,
`run_story.py upscale <project> <first> <last>`, `run_story.py prompts <story.py>`, `check_cuts.py <project dir> [parts]` (cuts + contact sheets),
`propsheet.py` (Qwen prop sheets); example story `stories/dhl_enduro.py` (PROPS tokens like <BIKEREF>, STORY order); templates = workflows 1, 2, 4
in API form. README section "Make your own story video" is the step-by-step for other people. (Old copies in tools/long_video.) Props then match across parts;
~40 px sticker text still smears at 1280×704. Say where every object comes from (helmet out of the top case) or it pops into existence.
Big logos can double ("DHL DHL" on the van): ask for "one single logo ... nothing else written on it" + new seed.
Cuts in dhl_enduro_v2 (16 parts, 2026-10-14) and their fixes: name what IS there ("no bridge, only broken posts"; "washed-away
footbridge" drew an intact bridge twice); the part after a mid-action ending (bullet-time landing) cut every time -> make it a new shot;
part N+1 must start where N ends (helmet in hands -> "pulls the helmet on"), few actions per continuation; "rushing water" in the sound line
went with water close-up cuts; a prop "in the background" with its reference doubled the bike -> leave it out of that shot.
Cut check: isolated YAVG spikes > ~30 = hard cut; POV/tracking parts have many values 12-25 from motion alone. Check every part right after it
renders and re-roll with FRONT=1 while later parts keep rendering (a re-roll only moves continuation parts up to the next new shot).
Stop one specific job with `POST /interrupt {"prompt_id": "<id>"}` (a bare /interrupt can land on the next job). Before upscaling after a
generation run, `POST /free {"unload_models":true,"free_memory":true}` (RAM was at 59/62 GB). 16 parts: ~3 h generate incl. 6 re-rolls,
~2.5 h upscale (~10 min/part).
To shorten a story, drop parts whose neighbours are new shots, and queue the rest as `story:videopart` (enduro.py STORY list).
Dialogue: best = H3 speaks itself with voice samples (story kit DIALOGUE_MODE h3, node H3LongVideoReferenceAudios -> PK combined
`references`, prompt "X says in the voice from <Audio n>, <how>, his lips moving clearly: ..."), `gen --check` (venv python, Whisper,
re-roll < 0.8 word match), then story_kit/location_sound.py (band-limit, wall echo, brown noise): clean samples make H3 voices sound
like a studio; user preferred the processed version (2026-10-14). Mode tts (ChatterBox + MiniMaxH3SongMaskedAVContext freeze) = exact
words but flat acting, fixed pauses ("bad acting"). TTS Suite narrator_voice must be in its dropdown (not vibevoice). SaveAudio cannot
write through the output/long_video symlink. /home has ~3 GB free: no big TTS model downloads there.
Pure noise / blank images from a workflow that used to work: check `sha256sum` of the model files against Hugging Face (`/api/models/<repo>?blobs=true`).
On 2026-10-13 `qwen3vl_8b_int8_convrot` and `qwen_image_2.1_int8_convrot` were corrupted (written next to an unfinished browser download); re-downloaded.
H3 width/height must be multiples of 32: 1280×720 gave a garbage strip in rows 704-719 (use 1280×704). Append now auto-crops.
Repo: github.com/fuzzballb/comfyui-h3-long-video (public, branch main) = `custom_nodes/h3_output_video` (README, 3 example workflows).
Keep README in sync when changing nodes; commit as fuzzballb. A copy of this skill is in the repo at `claude-skill/comfy-h3-video/`: after editing the skill, run `tools/sync_skill.sh` (copies it with personal names/paths replaced; the repo is PUBLIC) and commit. Never commit personal photos, names, home/street names or the user's email; author commits as `fuzzballb <3391337+fuzzballb@users.noreply.github.com>`. `output_picker.py` + `web/` (Pick Output Video, Latest Render) are local only (git-ignored).

For a swapped/existing video:
Render in parts, then remove the seam with `AV Bridge`. Crossfading overlapping renders does NOT work (visible fade plus a pose jump).
Bridge setup: target 192 frames, context 39 (contexts must be `39 + 51k`, target `5 + 17k`). Trim 57 frames off the end of A
(`frame_load_cap`) and the start of B (`skip_first_frames`) so the 114 generated frames replace the cut and total length stays the same.
Match the loader size to the source aspect ratio (e.g. 640×448 for 1280×896), or the frames get stretched.
Keep the bridge at low resolution: at 1280×896 (27 min) it invented camera cuts to extreme close-ups inside the generated middle.
For a full-res final, upscale the low-res bridge section and splice it between the full-res parts (softer middle, no jump).

## Voice and speech

- Voice conversion (TTS Audio Suite Voice Changer + ChatterBox) keeps timing but smears short words ("is just"); not used anymore.
- Voice-over workflow: `smart_natural` with stretch 0.9–1.1 keeps natural speed; `stretch_to_fit` makes lines too fast/slow.
- ASR: the local node `custom_nodes/whisper_srt` (Whisper, word timestamps snapped to audio loudness). The suite's Qwen3-ASR and Granite ASR do not work here (Python 3.14 + transformers 5.6).
- Prompt dialogue as quoted lines per speaker ("The man says: \"…\""); without quoted lines H3 produces gibberish. Ask for a medium close-up with faces toward the camera, or lips won't visibly move.
- Reference labels in H3 prompts: `<Picture n>` for images, `<Audio n>` for audio, in input order.

## Verify before reporting

- Frames: `ffmpeg -vf "fps=1,scale=320:-1,tile=5x2"` contact sheet, then Read the image. Zoom on mouths/seams with `crop`.
- Speech: transcribe with whisper (`download_root=models/whisper`); compare speech timing with `silencedetect=n=-35dB:d=0.25`.
- Audio really changed: correlate with the source audio (≈1.0 means the source was passed through).
- Seams: per-frame difference (`tblend=all_mode=difference,signalstats`) — a spike at the join means a jump.
- Loudness: `volumedetect`; normalize with `loudnorm=I=-16:TP=-1.5:LRA=11` (or `NormalizeAudioLoudness` in-graph).
