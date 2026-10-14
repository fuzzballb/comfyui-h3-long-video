"""Example with dialogue: "Doorstep" (2 parts, ~18 s). The courier delivers a parcel; the second part continues the first.

    python3 ../run_story.py gen --check doorstep_dialogue.py doorstep      # with ComfyUI's venv python (needs openai-whisper)

H3 speaks the lines itself, in the voices of the two samples, and --check re-rolls a part until Whisper hears the script.
Put a 10-20 s recording of each voice in ComfyUI/input as voice_sam.wav and voice_lisa.wav (or set SAM_VOICE / LISA_VOICE).
The third element of a line says how it is said; it steers the acting.

DIALOGUE_MODE = 'tts' instead makes the speech with ChatterBox first and freezes it (exact words, flatter acting):
    python3 ../run_story.py dialogue doorstep_dialogue.py doorstep 1 && python3 ../run_story.py gen doorstep_dialogue.py doorstep 1
    (part 2 the same, after part 1 is generated; VOICES are then TTS Audio Suite voice names)
"""
import os

FACE = 'example_face.jpg'
BODY = 'example_body.jpg'
PROPS = {}
WIDTH, HEIGHT, SECONDS, TURBO = 1280, 704, 10.0, True

DIALOGUE_MODE = 'h3'   # H3 speaks the lines in the sample voices; run gen with --check. 'tts' = ChatterBox track, frozen.

# voice samples (10-20 s of clean speech) in ComfyUI/input; in 'tts' mode these are TTS Audio Suite voice names instead
VOICES = {
    'Sam': (os.environ.get('SAM_VOICE', 'voice_sam.wav'), 'his'),
    'Lisa': (os.environ.get('LISA_VOICE', 'voice_lisa.wav'), 'her'),
}

SAM = ("Sam from Picture 1 and Picture 2, a man in his early thirties with short dark brown curly hair and light stubble, "
       "wearing the DHL uniform from Picture 2: red and yellow DHL cap, yellow DHL polo shirt, yellow hi-vis vest and dark grey work trousers")
LISA = "Lisa, a woman in her thirties with shoulder-length dark hair, wearing a grey sweater"
SET = ("a static medium two-shot at eye level in front of the dark blue front door of a red brick house, Sam on the right and Lisa "
       "in the open doorway on the left, both faces clearly visible in three-quarter view")

PARTS = {
    1: (True, None, [],
        f"One continuous take, {SET}, no cuts and no close-ups. {SAM}, holds a small brown cardboard parcel and a handheld scanner. "
        f"{LISA}, has just opened the door. {{DIALOGUE}} Natural daylight, quiet street ambience.",
        [('Sam', 'Good afternoon! Urgent delivery for you. Could you sign here, please?', 'friendly and a bit out of breath'),
         ('Lisa', 'Oh, finally! I have been waiting all week.', 'relieved, laughing')]),
    2: (False, None, [],
        f"Continue the same shot without a cut. One continuous take, {SET}, the camera never moves, no close-ups. {SAM}, holds out the "
        f"handheld scanner and {LISA}, signs it with her finger, then takes the parcel. {{DIALOGUE}} Natural daylight, quiet street ambience.",
        [('Lisa', 'Is this the wedding present for my sister?', 'curious, lowering her voice'),
         ('Sam', 'It is. Handle it with care, it is fragile!', 'with a grin'),
         ('Lisa', 'I will. Thank you so much!', 'warmly')]),
}
