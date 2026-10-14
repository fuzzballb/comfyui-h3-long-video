"""Face detail pass for upscaled long-video parts.

In wide shots the face is only a few latent cells big, so neither the
generation nor the upscale can hold a likeness. This tracks the face in an
upscaled part, cuts a steady square around it, and returns that as a small
"close-up" clip for H3 to re-render with the face reference. The paste node
puts the result back with a feathered oval mask and colour matching.

Faces larger than max_face (already detailed enough) or smaller than min_face
(too small to fix) are left alone, with soft ramps in between.
"""
import json
import logging
import os
import shutil

import cv2
import folder_paths
import numpy as np
import torch

from .long_video import _project_dir, _read_frames, _write_frames, _concat_upscaled, FPS

_LOG = logging.getLogger("h3_face_detail")
_MODEL = os.path.join(folder_paths.models_dir, "detection", "face_detection_yunet_2023mar.onnx")
_REC = os.path.join(folder_paths.models_dir, "detection", "face_recognition_sface_2021dec.onnx")


def _paths(project, part):
    up = os.path.join(_project_dir(project), "upscaled")
    return (os.path.join(up, f"part_{part:03d}.mkv"), os.path.join(up, f"part_{part:03d}.noface.mkv"),
            os.path.join(up, f"part_{part:03d}.face.json"))


def _smooth(x, win):
    if win <= 1 or len(x) < 3:
        return x
    k = np.ones(win) / win
    pad = win // 2
    xp = np.pad(x, (pad, win - 1 - pad), mode="edge")
    return np.convolve(xp, k, mode="valid")


def _track(frames, ref_bgr, min_face, max_face, conf, match):
    """Follow the face that matches the reference; other people are ignored."""
    det = cv2.FaceDetectorYN.create(_MODEL, "", (320, 320), conf)
    rec = cv2.FaceRecognizerSF.create(_REC, "")

    def faces(im):
        det.setInputSize((im.shape[1], im.shape[0]))
        r = det.detect(im)[1]
        return [] if r is None else list(r)

    # YuNet misdetects on very large images (a 2048 px full-body photo gave a
    # torso-sized "face"), so look for the reference face at <= 640 px
    sc = min(1.0, 640.0 / max(ref_bgr.shape[:2]))
    if sc < 1.0:
        ref_bgr = cv2.resize(ref_bgr, None, fx=sc, fy=sc, interpolation=cv2.INTER_AREA)
    rf = faces(ref_bgr)
    if not rf:
        raise ValueError("face detail: no face found in the reference image")
    ref = rec.feature(rec.alignCrop(ref_bgr, max(rf, key=lambda f: f[2] * f[3])))
    n = frames.shape[0]
    cx, cy, size, found, sims = np.zeros(n), np.zeros(n), np.zeros(n), np.zeros(n, bool), np.zeros(n)
    for i in range(n):
        im = cv2.cvtColor(frames[i], cv2.COLOR_RGB2BGR)
        best = None
        for f in faces(im):
            c = (f[0] + f[2] / 2, f[1] + f[3] / 2, max(f[2], f[3]))
            # recognition is unreliable on tiny or side-on faces (dancers in
            # profile matched at 0.35+): only frontal faces >= 40 px can confirm
            if f[2] < 40 or np.hypot(f[6] - f[4], f[7] - f[5]) < 0.33 * f[2]:
                continue
            sim = float(rec.match(ref, rec.feature(rec.alignCrop(im, f)), cv2.FaceRecognizerSF_FR_COSINE))
            # every frame must match the reference on its own: no "follow the
            # nearby face" chaining, which drifted onto dancers/audience in crowds
            if sim >= match and (best is None or sim > best[1]):
                best = (c, sim)
        if best is None:
            continue
        c, sim = best
        cx[i], cy[i], size[i], found[i], sims[i] = c[0], c[1], c[2], True, sim
    if found.sum() < 3:
        return None
    idx = np.nonzero(found)[0]
    # drop isolated hits far from their neighbours (a stranger matching once)
    keep = []
    for k, i in enumerate(idx):
        nb = [j for j in (idx[k - 1] if k else None, idx[k + 1] if k + 1 < len(idx) else None) if j is not None and abs(j - i) <= 24]
        if any(np.hypot(cx[i] - cx[j], cy[i] - cy[j]) < 1.5 * max(size[i], 20) for j in nb):
            keep.append(i)
    found[:] = False
    found[keep] = True
    if found.sum() < 3:
        return None
    idx = np.nonzero(found)[0]
    for arr in (cx, cy, size):
        arr[:] = np.interp(np.arange(n), idx, arr[idx])
    # weight: detected frames 1, fading out over gaps; 0 outside the useful size range
    dist = np.full(n, 1e9)
    for i in idx:
        dist = np.minimum(dist, np.abs(np.arange(n) - i))
    w = np.clip(1 - (dist - 2) / 10, 0, 1)
    sz = _smooth(size, 25)
    w *= np.clip((sz - min_face) / (0.25 * min_face), 0, 1)
    w *= np.clip((max_face - sz) / (0.25 * max_face), 0, 1)
    w = _smooth(w, 9)
    _LOG.info("face detail: matched the reference in %d/%d frames (similarity %.2f-%.2f)",
              len(idx), n, sims[idx].min(), sims[idx].max())
    return {"cx": _smooth(cx, 9).tolist(), "cy": _smooth(cy, 9).tolist(), "size": sz.tolist(), "weight": w.tolist()}


def _box(tr, i, scale, W, H):
    side = int(round(tr["size"][i] * scale))
    x0 = int(round(tr["cx"][i] - side / 2))
    y0 = int(round(tr["cy"][i] - side * 0.45))  # a little more room below (chin, collar)
    return x0, y0, side


def _crop(frame, x0, y0, side):
    H, W = frame.shape[:2]
    pad = side
    fp = np.pad(frame, ((pad, pad), (pad, pad), (0, 0)), mode="edge")
    return fp[y0 + pad:y0 + pad + side, x0 + pad:x0 + pad + side]


class H3LongVideoFaceCrop:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "reference": ("IMAGE", {"tooltip": "Photo of the person to detail. Only faces that match it are touched; everyone else is left alone."}),
            "project": ("STRING", {"default": "my_long_video"}),
            "part": ("INT", {"default": 1, "min": 1, "max": 999}),
            "crop_size": ("INT", {"default": 512, "min": 128, "max": 1024, "step": 32}),
            "box_scale": ("FLOAT", {"default": 2.6, "min": 1.5, "max": 5.0, "step": 0.1,
                                    "tooltip": "Crop square = face size x this."}),
            "min_face": ("INT", {"default": 30, "min": 8, "max": 1000, "tooltip": "Faces smaller than this (px) are left alone."}),
            "max_face": ("INT", {"default": 140, "min": 16, "max": 4000, "tooltip": "Faces larger than this (px) are already detailed; left alone."}),
            "confidence": ("FLOAT", {"default": 0.6, "min": 0.1, "max": 0.99, "step": 0.05}),
            "match": ("FLOAT", {"default": 0.35, "min": 0.0, "max": 1.0, "step": 0.05,
                                "tooltip": "Face-recognition similarity needed to count as the reference person (other people score ~0-0.15)."}),
        }}

    RETURN_TYPES = ("IMAGE", "INT", "BOOLEAN")
    RETURN_NAMES = ("crops", "frames", "has_work")
    FUNCTION = "crop"
    CATEGORY = "video/long"
    DESCRIPTION = "Track the face in an upscaled part and cut a steady square around it (H3 frame count)."

    def crop(self, reference, project, part, crop_size, box_scale, min_face, max_face, confidence, match):
        seg, noface, track_path = _paths(project, part)
        src = noface if os.path.isfile(noface) else seg
        frames = _read_frames(src)
        ref = cv2.cvtColor((reference[0].clamp(0, 1) * 255).round().to(torch.uint8).cpu().numpy(), cv2.COLOR_RGB2BGR)
        tr = _track(frames, ref, min_face, max_face, confidence, match)
        n = frames.shape[0]
        want = 5 + 17 * ((max(n, 5) - 5 + 16) // 17)  # H3 needs 17k+5 frames
        if tr is None or max(tr["weight"]) < 0.05:
            json.dump({"skip": True, "frames": n}, open(track_path, "w"))
            _LOG.info("face detail: part %d has no face in the %d-%d px range; nothing to do", part, min_face, max_face)
            return (torch.zeros((22, 64, 64, 3)), 22, False)
        tr.update({"skip": False, "frames": n, "box_scale": box_scale, "crop_size": crop_size})
        json.dump(tr, open(track_path, "w"))
        out = np.empty((want, crop_size, crop_size, 3), np.uint8)
        for i in range(n):
            x0, y0, side = _box(tr, i, box_scale, frames.shape[2], frames.shape[1])
            out[i] = cv2.resize(_crop(frames[i], x0, y0, side), (crop_size, crop_size), interpolation=cv2.INTER_LANCZOS4)
        out[n:] = out[n - 1]
        active = np.nonzero(np.array(tr["weight"]) > 0.05)[0]
        _LOG.info("face detail: part %d, %d frames, face %.0f-%.0f px, detailing frames %d-%d",
                  part, n, min(tr["size"]), max(tr["size"]), active[0], active[-1])
        return (torch.from_numpy(out).float() / 255, want, True)


class H3LongVideoFacePaste:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "images": ("IMAGE", {"tooltip": "Re-rendered face crops (same order/count as Face Crop)."}),
            "project": ("STRING", {"default": "my_long_video"}),
            "part": ("INT", {"default": 1, "min": 1, "max": 999}),
            "mask_size": ("FLOAT", {"default": 0.75, "min": 0.3, "max": 1.5, "step": 0.05,
                                    "tooltip": "Oval mask radius relative to the face size."}),
            "feather": ("FLOAT", {"default": 0.35, "min": 0.0, "max": 1.0, "step": 0.05}),
            "color_match": ("BOOLEAN", {"default": True}),
            "crf": ("INT", {"default": 14, "min": 0, "max": 51}),
        }}

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("full_video_path",)
    FUNCTION = "paste"
    OUTPUT_NODE = True
    CATEGORY = "video/long"

    def paste(self, images, project, part, mask_size, feather, color_match, crf):
        seg, noface, track_path = _paths(project, part)
        tr = json.load(open(track_path))
        if tr.get("skip"):
            _LOG.info("face detail: part %d skipped (no face to detail)", part)
            return {"result": ("",)}
        if not os.path.isfile(noface):
            shutil.copyfile(seg, noface)  # keep the clean upscale; re-runs always paste onto it
        frames = _read_frames(noface).copy()
        H, W = frames.shape[1:3]
        crops = (images.clamp(0, 1) * 255).round().to(torch.uint8).cpu().numpy()
        for i in range(min(tr["frames"], frames.shape[0])):
            w = tr["weight"][i]
            if w < 0.01:
                continue
            x0, y0, side = _box(tr, i, tr["box_scale"], W, H)
            face = cv2.resize(crops[i], (side, side), interpolation=cv2.INTER_AREA).astype(np.float32)
            # oval around the face centre, which sits at (side/2, side*0.45) in the box
            yy, xx = np.mgrid[0:side, 0:side].astype(np.float32)
            r = tr["size"][i] * mask_size
            d = np.sqrt(((xx - side / 2) / (r * 0.85)) ** 2 + ((yy - side * 0.45) / r) ** 2)
            m = np.clip((1 - d) / max(feather, 1e-3), 0, 1) * w
            fx0, fy0 = max(x0, 0), max(y0, 0)
            fx1, fy1 = min(x0 + side, W), min(y0 + side, H)
            if fx1 <= fx0 or fy1 <= fy0:
                continue
            sl = (slice(fy0 - y0, fy1 - y0), slice(fx0 - x0, fx1 - x0))
            orig = frames[i, fy0:fy1, fx0:fx1].astype(np.float32)
            f, mm = face[sl], m[sl][..., None]
            if color_match and mm.sum() > 10:
                for c in range(3):
                    wo, wf = orig[..., c], f[..., c]
                    mo, mf = (wo * mm[..., 0]).sum() / mm.sum(), (wf * mm[..., 0]).sum() / mm.sum()
                    f[..., c] = wf + (mo - mf)
            frames[i, fy0:fy1, fx0:fx1] = np.clip(orig * (1 - mm) + f * mm, 0, 255).astype(np.uint8)
        fps = _seg_fps(noface)
        _write_frames(frames, seg, fps, crf)
        full = _concat_upscaled(project)
        _LOG.info("face detail: part %d pasted; %s rebuilt", part, full)
        root = _project_dir(project)
        return {"ui": {"images": [{"filename": os.path.basename(full), "subfolder": os.path.relpath(root, folder_paths.get_output_directory()),
                                   "type": "output"}], "animated": (True,)},
                "result": (full,)}


def _seg_fps(path):
    import subprocess
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=r_frame_rate",
                          "-of", "csv=p=0", path], capture_output=True, text=True, check=True).stdout.strip()
    num, den = out.split("/")
    return float(num) / float(den)


NODE_CLASS_MAPPINGS = {"H3LongVideoFaceCrop": H3LongVideoFaceCrop, "H3LongVideoFacePaste": H3LongVideoFacePaste}
NODE_DISPLAY_NAME_MAPPINGS = {"H3LongVideoFaceCrop": "Long Video: Face Crop (track)",
                              "H3LongVideoFacePaste": "Long Video: Face Paste"}
