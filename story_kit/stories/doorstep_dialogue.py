"""Example with dialogue: "Doorstep" (2 parts, ~18 s). The courier delivers a parcel; the second part continues the first.

    python3 ../run_story.py dialogue doorstep_dialogue.py doorstep 1     # speak part 1's lines, upload the track
    python3 ../run_story.py gen      doorstep_dialogue.py doorstep 1
    # wait until part 1 is generated: part 2 continues it, and its track starts with part 1's last 39 frames of audio
    python3 ../run_story.py dialogue doorstep_dialogue.py doorstep 2
    python3 ../run_story.py gen      doorstep_dialogue.py doorstep 2

Voices are names from the TTS Audio Suite voice list. Put your own recording (10-20 s of clean speech) in
ComfyUI/models/voices/ and use its file name, e.g. SAM_VOICE=my_voice.wav. The defaults are example voices that ship with
TTS Audio Suite.
"""
import os

FACE = 'example_face.jpg'
BODY = 'example_body.jpg'
PROPS = {}
WIDTH, HEIGHT, SECONDS, TURBO = 1280, 704, 10.0, True

VOICES = {
    'Sam': (os.environ.get('SAM_VOICE', 'voices_examples/male/male_01.wav'), 'his'),
    'Lisa': (os.environ.get('LISA_VOICE', 'voices_examples/female/female_01.wav'), 'her'),
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
        [('Sam', 'Good afternoon! Urgent delivery for you. Could you sign here, please?'),
         ('Lisa', 'Oh, finally! I have been waiting all week.')]),
    2: (False, None, [],
        f"Continue the same shot without a cut. One continuous take, {SET}, the camera never moves, no close-ups. {SAM}, holds out the "
        f"handheld scanner and {LISA}, signs it with her finger, then takes the parcel. {{DIALOGUE}} Natural daylight, quiet street ambience.",
        [('Lisa', 'Is this the wedding present for my sister?'),
         ('Sam', 'It is. Handle it with care, it is fragile!'),
         ('Lisa', 'I will. Thank you so much!')]),
}
