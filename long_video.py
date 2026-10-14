"""Unlimited-length H3 video, one part per queue run.

H3 makes ~10 s per generation. To go longer, every run continues the previous
part in latent space (MiniMaxH3GeneratedAVMaskedContext: the previous part's
last 39 frames + matching audio are copied into the new latent and kept frozen),
so motion, character and sound carry straight through the join.

All state lives in output/long_video/<project>/:
  latents/part_NNN.safetensors   sampler output of part N (what part N+1 continues)
  segments/part_NNN.mkv          the frames part N added (context removed)
  <project>_full.mp4             parts 1..N concatenated, rebuilt every run

A part with new_shot=True starts fresh (a hard cut, e.g. to a new location)
but is still appended. Re-rolling part N just runs N again: it continues from part N-1 and overwrites
part N. Later parts that continue from it no longer fit and are moved to _superseded/; the next
part that started as a new shot (shots.json) and everything after it are kept.
"""
import json
import logging
import os
import shutil
import subprocess
import tempfile

import folder_paths
import nodes
import numpy as np
import torch

try:
    from safetensors.torch import load_file as _st_load, save_file as _st_save
except ImportError:  # pragma: no cover
    _st_load = _st_save = None

_LOG = logging.getLogger("h3_long_video")
FPS = 24.0


def _project_dir(project):
    name = (project or "").strip().strip("/\\")
    if not name or ".." in name or os.sep in name:
        raise ValueError(f"long video: invalid project name {project!r}")
    return os.path.join(folder_paths.get_output_directory(), "long_video", name)


def _latent_path(project, part):
    return os.path.join(_project_dir(project), "latents", f"part_{part:03d}.safetensors")


def _segment_path(project, part):
    return os.path.join(_project_dir(project), "segments", f"part_{part:03d}.mkv")


def _shots_path(project):
    return os.path.join(_project_dir(project), "shots.json")


def _load_shots(project):
    """{part: frozen context frames}; 0 = part started as a new shot."""
    try:
        with open(_shots_path(project)) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save_shots(project, shots):
    with open(_shots_path(project), "w") as f:
        json.dump(shots, f, indent=1, sort_keys=True)


def _streams(latent):
    samples = latent["samples"]
    if hasattr(samples, "unbind"):
        return list(samples.unbind())
    return list(samples)


class H3LongVideoContinue:
    """Part 1: pass the fresh latent through. Part N: continue from part N-1."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "latent": ("LATENT", {"tooltip": "Fresh AV latent from the H3 encode node (PK Combined / Reference to Video)."}),
                "project": ("STRING", {"default": "my_long_video",
                                       "tooltip": "Folder under output/long_video/. Use the same name on the Append node."}),
                "part": ("INT", {"default": 1, "min": 1, "max": 999,
                                 "tooltip": "Which part this run makes. 1 = start fresh; N = continue from part N-1. "
                                            "Raise by one after each part you keep; run the same number again to re-roll it."}),
                "context_length": ("INT", {"default": 39, "min": 5, "max": 9999,
                                           "tooltip": "Frames of the previous part kept frozen at the start (39/90/141...)."}),
                "audio_feather_ticks": ("INT", {"default": 8, "min": 0, "max": 256,
                                                "tooltip": "Soft release of the frozen audio (8 = 0.2 s)."}),
            },
            "optional": {
                "new_shot": ("BOOLEAN", {"default": False,
                                         "tooltip": "Start this part as a fresh shot (hard cut, e.g. a new location) "
                                                    "instead of continuing the previous part. It is still appended to the long video."}),
            },
        }

    RETURN_TYPES = ("LATENT", "INT")
    RETURN_NAMES = ("latent", "trim_frames")
    FUNCTION = "prepare"
    CATEGORY = "video/long"
    DESCRIPTION = "Continue a long H3 video from the previous part's saved latent."

    @classmethod
    def IS_CHANGED(cls, latent, project, part, context_length, audio_feather_ticks, new_shot=False):
        if part <= 1 or new_shot:
            return "start"
        try:
            p = _latent_path(project, part - 1)
            return f"{p}:{os.stat(p).st_mtime_ns}"
        except (OSError, ValueError):
            return float("nan")

    def prepare(self, latent, project, part, context_length, audio_feather_ticks, new_shot=False):
        if part <= 1 or new_shot:
            return (latent, 0)
        path = _latent_path(project, part - 1)
        if not os.path.isfile(path):
            raise ValueError(
                f"long video: part {part - 1} of '{project}' does not exist yet ({path}). "
                f"Make part {part - 1} first, or set part to 1 to start over."
            )
        data = _st_load(path)
        prev = {"samples": [data["video"], data["audio"]]}
        ctx = nodes.NODE_CLASS_MAPPINGS["MiniMaxH3GeneratedAVMaskedContext"]()
        out, trim = ctx.prepare(latent, prev, context_length, audio_feather_ticks)
        _LOG.info("long video: part %d continues part %d (%s), %d frames frozen", part, part - 1, path, trim)
        return (out, trim)


class H3LongVideoAppend:
    """Save this part and rebuild the long video."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "latent": ("LATENT", {"tooltip": "Sampler output (saved so the next part can continue from it)."}),
                "images": ("IMAGE", {"tooltip": "Decoded frames of this part."}),
                "audio": ("AUDIO", {"tooltip": "Decoded audio of this part."}),
                "trim_frames": ("INT", {"default": 0, "min": 0, "max": 9999, "forceInput": True,
                                        "tooltip": "From the Continue node: frozen frames already in the previous part."}),
                "project": ("STRING", {"default": "my_long_video"}),
                "part": ("INT", {"default": 1, "min": 1, "max": 999}),
                "crf": ("INT", {"default": 14, "min": 0, "max": 51}),
            }
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("full_video_path",)
    FUNCTION = "append"
    OUTPUT_NODE = True
    CATEGORY = "video/long"
    DESCRIPTION = "Store this part (latent + new frames) and rebuild <project>_full.mp4 from parts 1..N."

    def append(self, latent, images, audio, trim_frames, project, part, crf):
        root = _project_dir(project)
        for missing in range(1, part):
            if not os.path.isfile(_segment_path(project, missing)):
                raise ValueError(f"long video: part {missing} of '{project}' is missing; cannot build up to part {part}")
        os.makedirs(os.path.join(root, "latents"), exist_ok=True)
        os.makedirs(os.path.join(root, "segments"), exist_ok=True)
        self._supersede_after(project, part)
        shots = _load_shots(project)
        shots[str(part)] = int(trim_frames)
        _save_shots(project, shots)

        video, aud = _streams(latent)[:2]
        _st_save({"video": video.cpu().contiguous(), "audio": aud.cpu().contiguous()},
                 _latent_path(project, part), metadata={"format": "h3_motion_context_av_v1"})

        # Drop the frozen context (already in the previous part), picture and
        # sound together, and conform the audio to exactly frames/24 s so the
        # parts never drift apart.
        trim = nodes.NODE_CLASS_MAPPINGS["MiniMaxH3MotionContextTrim"]()
        imgs, aud_out = trim.trim(images, int(trim_frames), audio=audio, fps=FPS, match_tail=True)[:2]
        # H3 pads sizes that are not a multiple of 32 and fills the padded
        # strip (bottom/right) with garbage, e.g. rows 704-719 at 720p.
        h, w = int(imgs.shape[1]) // 32 * 32, int(imgs.shape[2]) // 32 * 32
        if (h, w) != tuple(imgs.shape[1:3]):
            _LOG.warning("long video: %dx%d is not a multiple of 32; cropping to %dx%d (H3 garbage strip)",
                         imgs.shape[2], imgs.shape[1], w, h)
            imgs = imgs[:, :h, :w]
        seg = _segment_path(project, part)
        self._write_segment(imgs, aud_out, seg, crf)

        full = os.path.join(root, f"{project}_full.mp4")
        last = part
        while os.path.isfile(_segment_path(project, last + 1)):
            last += 1
        self._concat(project, last, full)
        _LOG.info("long video: part %d saved (%d new frames); %s now has parts 1-%d", part, imgs.shape[0], full, last)
        rel = os.path.relpath(root, folder_paths.get_output_directory())
        return {"ui": {"images": [{"filename": os.path.basename(full), "subfolder": rel, "type": "output"}],
                       "animated": (True,)},
                "result": (full,)}

    @staticmethod
    def _supersede_after(project, part):
        """Move aside the later parts that continue (directly or in a chain)
        from this one. The first later part that started as a new shot does
        not depend on it, so it and everything after it are kept."""
        root = _project_dir(project)
        old = os.path.join(root, "_superseded")
        shots = _load_shots(project)
        nxt = part + 1
        while os.path.isfile(_segment_path(project, nxt)) or os.path.isfile(_latent_path(project, nxt)):
            if shots.get(str(nxt)) == 0:
                break
            os.makedirs(old, exist_ok=True)
            for path in (_segment_path(project, nxt), _latent_path(project, nxt)):
                if os.path.isfile(path):
                    shutil.move(path, os.path.join(old, os.path.basename(path)))
            shots.pop(str(nxt), None)
            nxt += 1
        _save_shots(project, shots)

    @staticmethod
    def _write_segment(images, audio, path, crf):
        n, h, w, _ = images.shape
        wave = audio["waveform"][0].float().cpu().numpy()  # [C, S]
        sr = int(audio["sample_rate"])
        with tempfile.TemporaryDirectory(dir=os.path.dirname(path)) as tmp:
            pcm = os.path.join(tmp, "a.f32")
            np.ascontiguousarray(wave.T).astype("<f4").tofile(pcm)
            tmp_out = os.path.join(tmp, "seg.mkv")
            cmd = ["ffmpeg", "-v", "error", "-y",
                   "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-r", "24", "-i", "-",
                   "-f", "f32le", "-ar", str(sr), "-ac", str(wave.shape[0]), "-i", pcm,
                   "-c:v", "libx264", "-preset", "medium", "-crf", str(crf), "-pix_fmt", "yuv420p",
                   "-c:a", "flac", tmp_out]
            proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
            for i in range(0, n, 16):
                chunk = (images[i:i + 16].clamp(0, 1) * 255).round().to(torch.uint8).cpu().numpy()
                proc.stdin.write(chunk.tobytes())
            proc.stdin.close()
            if proc.wait() != 0:
                raise RuntimeError(f"long video: ffmpeg failed writing {path}")
            os.replace(tmp_out, path)

    @staticmethod
    def _concat(project, part, full):
        root = _project_dir(project)
        lst = os.path.join(root, "segments", "concat.txt")
        with open(lst, "w") as f:
            for i in range(1, part + 1):
                f.write(f"file '{os.path.basename(_segment_path(project, i))}'\n")
        tmp = full + ".tmp.mp4"
        cmd = ["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst,
               "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", tmp]
        if subprocess.run(cmd).returncode != 0:
            raise RuntimeError(f"long video: ffmpeg concat failed for {full}")
        os.replace(tmp, full)


class H3LongVideoLoadPart:
    """A saved part latent as a normal (decodable / upscalable) H3 AV latent."""

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"project": ("STRING", {"default": "my_long_video"}),
                             "part": ("INT", {"default": 1, "min": 1, "max": 999})}}

    RETURN_TYPES = ("LATENT", "INT", "INT", "INT", "INT")
    RETURN_NAMES = ("latent", "context_frames", "frames", "width", "height")
    FUNCTION = "load"
    CATEGORY = "video/long"

    @classmethod
    def IS_CHANGED(cls, project, part):
        try:
            return os.stat(_latent_path(project, part)).st_mtime_ns
        except (OSError, ValueError):
            return float("nan")

    def load(self, project, part):
        import comfy.nested_tensor
        data = _st_load(_latent_path(project, part))
        latent = {"samples": comfy.nested_tensor.NestedTensor((data["video"], data["audio"]))}
        _, _, t, h, w = data["video"].shape
        return (latent, int(_load_shots(project).get(str(part), 0)), 5 + 17 * (t - 2) // 5, w * 16, h * 16)


def _cond_path(project, part):
    return os.path.join(_project_dir(project), "latents", f"part_{part:03d}.cond.pt")


class H3LongVideoSaveConditioning:
    """Keep the conditioning a part was generated with (for the later upscale)."""

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"conditioning": ("CONDITIONING",),
                             "project": ("STRING", {"default": "my_long_video"}),
                             "part": ("INT", {"default": 1, "min": 1, "max": 999})}}

    RETURN_TYPES = ()
    FUNCTION = "save"
    OUTPUT_NODE = True
    CATEGORY = "video/long"

    def save(self, conditioning, project, part):
        os.makedirs(os.path.join(_project_dir(project), "latents"), exist_ok=True)
        torch.save(conditioning, _cond_path(project, part))
        return ()


class H3LongVideoLoadConditioning:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"project": ("STRING", {"default": "my_long_video"}),
                             "part": ("INT", {"default": 1, "min": 1, "max": 999})}}

    RETURN_TYPES = ("CONDITIONING",)
    FUNCTION = "load"
    CATEGORY = "video/long"

    @classmethod
    def IS_CHANGED(cls, project, part):
        try:
            return os.stat(_cond_path(project, part)).st_mtime_ns
        except (OSError, ValueError):
            return float("nan")

    def load(self, project, part):
        path = _cond_path(project, part)
        if not os.path.isfile(path):
            raise ValueError(f"long video: no saved conditioning for part {part} of '{project}' ({path})")
        return (torch.load(path, weights_only=False),)


def _read_frames(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height", "-of", "csv=p=0", path], capture_output=True, text=True, check=True)
    w, h = map(int, out.stdout.strip().split(",")[:2])
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(-1, h, w, 3)


def _write_frames(frames, path, fps, crf):
    """uint8 [T,H,W,3] numpy or float tensor -> video-only mkv."""
    n, h, w, _ = frames.shape
    tmp = path + ".tmp.mkv"
    proc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}",
                             "-r", str(fps), "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", str(crf),
                             "-pix_fmt", "yuv420p", tmp], stdin=subprocess.PIPE)
    for i in range(0, n, 16):
        c = frames[i:i + 16]
        if isinstance(c, torch.Tensor):
            c = (c.clamp(0, 1) * 255).round().to(torch.uint8).cpu().numpy()
        proc.stdin.write(np.ascontiguousarray(c).tobytes())
    proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError(f"long video: ffmpeg failed writing {path}")
    os.replace(tmp, path)


def _concat_upscaled(project):
    """Rebuild <project>_full_upscaled.mp4 from upscaled parts 1..N (contiguous) + the original audio."""
    root = _project_dir(project)
    up = os.path.join(root, "upscaled")
    full = os.path.join(root, f"{project}_full_upscaled.mp4")
    last = 0
    while os.path.isfile(os.path.join(up, f"part_{last + 1:03d}.mkv")):
        last += 1
    if last == 0:
        return full
    lst = os.path.join(up, "concat.txt")
    with open(lst, "w") as f:
        for i in range(1, last + 1):
            f.write(f"file 'part_{i:03d}.mkv'\n")
    base = os.path.join(root, f"{project}_full.mp4")
    tmp = full + ".tmp.mp4"
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-i", base,
           "-map", "0:v", "-map", "1:a?", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest",
           "-movflags", "+faststart", tmp]
    if subprocess.run(cmd).returncode != 0:
        raise RuntimeError("long video upscale: concat failed")
    os.replace(tmp, full)
    _LOG.info("long video upscale: %s has parts 1-%d", full, last)
    return full


def _unblend_cuts(images, m, threshold, part):
    """Replace interpolated frames that blend across a hard cut with copies of the real frames."""
    real = images[::m]
    small = torch.nn.functional.interpolate(real.movedim(-1, 1).mean(1, keepdim=True).float(), size=(36, 64), mode="area")
    diff = (small[1:] - small[:-1]).abs().mean(dim=(1, 2, 3)) * 255
    cuts = torch.nonzero(diff > threshold).flatten().tolist()
    if not cuts:
        return images
    images = images.clone()
    for i in cuts:
        a, b = i * m, (i + 1) * m
        half = (m + 1) // 2
        images[a + 1:a + half] = images[a]
        images[a + half:b] = images[b]
    _LOG.info("long video upscale: part %d: no interpolation across %d cut(s) at source frames %s", part, len(cuts), [c + 1 for c in cuts])
    return images


class H3LongVideoUpscaleAppend:
    """Store an upscaled part and rebuild <project>_full_upscaled.mp4.

    A part that continues the previous one starts with the same context frames
    the previous part ended with. Both upscales of those frames differ in fine
    detail, so instead of cutting from one to the other they are crossfaded.
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "images": ("IMAGE", {"tooltip": "Upscaled (and optionally interpolated/sharpened) frames of the WHOLE part, context included."}),
            "project": ("STRING", {"default": "my_long_video"}),
            "part": ("INT", {"default": 1, "min": 1, "max": 999}),
            "context_frames": ("INT", {"default": 0, "min": 0, "max": 9999, "forceInput": True}),
            "source_frames": ("INT", {"default": 0, "min": 0, "max": 99999, "forceInput": True,
                                      "tooltip": "Frame count of the part before interpolation (Load Part Latent 'frames')."}),
            "fps_multiplier": ("INT", {"default": 2, "min": 1, "max": 8, "tooltip": "Frame interpolation multiplier used (1 = none)."}),
            "crop_width": ("INT", {"default": 0, "min": 0, "max": 16384, "tooltip": "Crop to this width from the left (0 = keep)."}),
            "crop_height": ("INT", {"default": 0, "min": 0, "max": 16384, "tooltip": "Crop to this height from the top (0 = keep). Removes the padding strip of non-/32 sizes."}),
            "crf": ("INT", {"default": 14, "min": 0, "max": 51}),
        }, "optional": {
            "cut_threshold": ("FLOAT", {"default": 30.0, "min": 0.0, "max": 255.0, "step": 1.0,
                                        "tooltip": "Hard cuts inside a part: frame interpolation would blend the two shots into a smeared frame. "
                                                   "Where two real frames differ more than this (0-255, 64x36 gray), the in-between frames become copies "
                                                   "of the real frames instead. 0 = off."}),
        }}

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("full_video_path",)
    FUNCTION = "append"
    OUTPUT_NODE = True
    CATEGORY = "video/long"

    def append(self, images, project, part, context_frames, source_frames, fps_multiplier, crop_width, crop_height, crf, cut_threshold=30.0):
        root = _project_dir(project)
        up = os.path.join(root, "upscaled")
        os.makedirs(up, exist_ok=True)
        fps = FPS * fps_multiplier
        if crop_height:
            images = images[:, :crop_height]
        if crop_width:
            images = images[:, :, :crop_width]
        m = fps_multiplier
        n = source_frames or ((images.shape[0] - 1) // m + 1)
        # interpolation gives (n-1)*m+1 frames; pad the last frame so every
        # part lasts exactly n source frames and the audio never drifts
        want = n * m
        if images.shape[0] < want:
            images = torch.cat([images, images[-1:].repeat(want - images.shape[0], 1, 1, 1)])
        images = images[:want]
        if m > 1 and cut_threshold > 0:
            images = _unblend_cuts(images, m, cut_threshold, part)
        ctx = context_frames * m
        seg_path = os.path.join(up, f"part_{part:03d}.mkv")
        tail_path = os.path.join(up, f"part_{part:03d}.tail.mkv")
        prev_seg = os.path.join(up, f"part_{part - 1:03d}.mkv")
        prev_tail = os.path.join(up, f"part_{part - 1:03d}.tail.mkv")

        if ctx and os.path.isfile(prev_seg) and os.path.isfile(prev_tail):
            prev = _read_frames(prev_seg)
            raw_tail = _read_frames(prev_tail)[-ctx:]
            k = min(ctx, raw_tail.shape[0], prev.shape[0])
            cur = (images[:k].clamp(0, 1) * 255).cpu().numpy()
            w = np.linspace(0, 1, k + 2)[1:-1].reshape(-1, 1, 1, 1)
            blended = (raw_tail[-k:].astype(np.float32) * (1 - w) + cur * w).round().astype(np.uint8)
            prev = np.concatenate([prev[:-k], blended])
            _write_frames(prev, prev_seg, fps, crf)
            _LOG.info("long video upscale: crossfaded %d frames into the end of part %d", k, part - 1)
        elif ctx:
            _LOG.warning("long video upscale: part %d continues part %d, but that part is not upscaled yet; hard join", part, part - 1)

        _write_frames(images[ctx:], seg_path, fps, crf)
        _write_frames(images[-max(ctx, 2 * 39 * m):], tail_path, fps, 10)

        full = _concat_upscaled(project)
        if part > 1 and not os.path.isfile(os.path.join(up, f"part_{part - 1:03d}.mkv")):
            _LOG.info("long video upscale: part %d done; full video waits for parts before it", part)
        rel = os.path.relpath(up if not os.path.isfile(full) else root, folder_paths.get_output_directory())
        shown = os.path.basename(full) if os.path.isfile(full) else os.path.basename(seg_path)
        return {"ui": {"images": [{"filename": shown, "subfolder": rel, "type": "output"}], "animated": (True,)},
                "result": (full,)}


NODE_CLASS_MAPPINGS = {
    "H3LongVideoLoadPart": H3LongVideoLoadPart,
    "H3LongVideoSaveConditioning": H3LongVideoSaveConditioning,
    "H3LongVideoLoadConditioning": H3LongVideoLoadConditioning,
    "H3LongVideoUpscaleAppend": H3LongVideoUpscaleAppend,
    "H3LongVideoContinue": H3LongVideoContinue,
    "H3LongVideoAppend": H3LongVideoAppend,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "H3LongVideoLoadPart": "Long Video: Load Part Latent",
    "H3LongVideoSaveConditioning": "Long Video: Save Part Conditioning",
    "H3LongVideoLoadConditioning": "Long Video: Load Part Conditioning",
    "H3LongVideoUpscaleAppend": "Long Video: Append Upscaled Part",
    "H3LongVideoContinue": "Long Video: Continue From Previous Part",
    "H3LongVideoAppend": "Long Video: Append Part",
}
