"""H3 long video: generate, upscale and face-detail videos of any length in parts."""
import os

from .face_detail import NODE_CLASS_MAPPINGS as _FACE_NODES, NODE_DISPLAY_NAME_MAPPINGS as _FACE_NAMES
from .long_video import NODE_CLASS_MAPPINGS as _LONG_NODES, NODE_DISPLAY_NAME_MAPPINGS as _LONG_NAMES

NODE_CLASS_MAPPINGS = {**_LONG_NODES, **_FACE_NODES}
NODE_DISPLAY_NAME_MAPPINGS = {**_LONG_NAMES, **_FACE_NAMES}

# local extras that are not part of the repo (output video picker + its web preview)
if os.path.exists(os.path.join(os.path.dirname(__file__), "output_picker.py")):
    from .output_picker import NODE_CLASS_MAPPINGS as _PICK_NODES, NODE_DISPLAY_NAME_MAPPINGS as _PICK_NAMES

    NODE_CLASS_MAPPINGS.update(_PICK_NODES)
    NODE_DISPLAY_NAME_MAPPINGS.update(_PICK_NAMES)
    WEB_DIRECTORY = "./web"

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"] + (["WEB_DIRECTORY"] if "WEB_DIRECTORY" in globals() else [])
