"""Example story: "Urgent delivery" (16 parts, ~2:35), the DHL courier racing a parcel with the wedding rings to a chapel.

Run with:  python3 ../run_story.py gen dhl_enduro.py my_project     then   python3 ../run_story.py upscale my_project 1 16

Images in ComfyUI/input:
  Copy everything in ../refs/ into ComfyUI/input. All of it is generated (Qwen Image 2.1): a fictional courier "Sam" and
  fictional Dutch streets. Replace them with your own character and locations:
  FACE  a tight face crop of the main character (Picture 1)
  BODY  an outfit sheet of the character, front/back/three-quarter/side (Picture 2)
  location photos (Picture 3 in the parts that use one): a street to park the van, a brick street, a canal road, a tram crossing
  prop sheets: the bike and the parcel (make your own with example workflow 4)
LoRAs in models/loras: see the README section "Make your own story video".
"""

FACE = 'example_face.jpg'
BODY = 'example_body.jpg'
PROPS = {'<BIKEREF>': 'example_bike.png', '<PARCELREF>': 'example_parcel.png'}
WIDTH, HEIGHT, SECONDS, TURBO = 1280, 704, 10.0, True

A = ("Sam from Picture 1 and Picture 2, a man in his early thirties with short dark brown curly hair and light stubble, "
     "wearing the DHL uniform from Picture 2: red and yellow DHL cap, yellow DHL polo shirt, yellow hi-vis vest and dark grey work trousers")
AH = ("Sam from Picture 1 and Picture 2 in the DHL uniform from Picture 2 (yellow DHL polo shirt, yellow hi-vis vest, dark grey work trousers), "
      "now wearing a yellow motocross helmet with a red DHL stripe and goggles")
BIKE = "the yellow DHL enduro motorbike with the small red DHL top case from <BIKEREF>"
CONT = "Continue the same shot without a cut. "
# Extra LoRAs (models/loras), all from Civitai:
#   CAM  Camera Motion H3        https://civitai.com/models/2914784/cameramotionh3?modelVersionId=3297480            trigger "camera motion,"
#   DY   Authentic Cinematic Texture  https://civitai.com/models/2890588/minimax-h3-authentic-cinematic-texture?modelVersionId=3267949
#        (rename the download to mmh3_cinematic_texture_DY.safetensors)                                               trigger "DY"
#   HUM  Better Human Motion     https://civitai.com/models/2734359/better-human-motion-minimax-h3?modelVersionId=3256084
#   END  Extreme Enduro          https://civitai.com/models/2989996/extreme-enduro-better-bike-povs-and-motion?modelVersionId=3390388
#   BT   Bullet Time             https://civitai.com/models/2934116/mmh3-bullet-time?modelVersionId=3321093           trigger "bullet-time" + timestamps
CAM, DY, HUM, END, BT = ("camera_motion_h3_lora_v1_3000_pruned.safetensors", "mmh3_cinematic_texture_DY.safetensors",
                         "mvmt_h3_lora_v1_500.safetensors", "extremeEnduroBetterBike_v1.safetensors", "BulletTime-MMH3.safetensors")

PARCEL = "the small brown cardboard parcel with the red URGENT sticker from <PARCELREF>"
CHAPEL = ("a small white stone chapel with a little bell tower on a grassy hilltop, a white flower arch in front of it and mountains behind")
GROOM = "a young groom in a dark blue suit with a white flower on his lapel"
BRIDE = "a bride in a white lace wedding dress with a veil"
GUESTS = "wedding guests in suits and summer dresses"

# part: (new_shot, location ref or None, [(lora, strength)], prompt)
PARTS = {
 1: (True, "example_street_van.jpg", [(CAM, .8), (HUM, .5), (DY, .6)],
     f"camera motion, DY, a slow aerial crane shot descending from above the rooftops down to street level in front of the red brick apartment building "
     f"with dark balconies and white front doors from Picture 3, ending in a wide shot of both vehicles. A yellow DHL delivery van is parked at the curb, with one single red DHL logo in the middle of its side panel and nothing else written on it. "
     f"In the foreground, on the pavement between the van and the camera, {BIKE} stands on its kickstand, large and clearly visible in the lower part of the frame "
     f"for the whole shot. "
     f"{A} slides open the side door of the van, takes out {PARCEL} and looks at the label. "
     f"Natural overcast daylight. Quiet street ambience, a van door sliding open."),
 2: (False, "example_street_van.jpg", [(HUM, .5), (DY, .6)],
     f"{CONT}One continuous take, static wide shot, the framing never changes. DY. {A} frowns at the parcel's label and walks to "
     f"the back of {BIKE}, which stands on its kickstand on the pavement in the foreground. Standing behind the bike, he opens the lid of the red top case "
     f"and takes a yellow motocross helmet out of it, puts the parcel into the empty top case and closes the lid. Then he steps to the left side of the bike "
     f"and pulls the yellow helmet on. The seat of the bike stays empty. Street ambience, footsteps."),
 3: (False, "example_street_van.jpg", [(HUM, .5), (END, .6), (DY, .6)],
     f"{CONT}One continuous take, static wide shot, the framing never changes, the yellow DHL van stays parked in the background. DY. "
     f"{A}, standing on the left side of {BIKE} with the yellow motocross helmet in his hands, pulls the helmet on over his head, swings his right leg over "
     f"the seat, kicks up the kickstand and starts the engine, which roars to life. Then he twists the throttle and rides off along the street, "
     f"leaving the frame, while the camera stays where it is. Loud enduro engine starting and accelerating away, street ambience."),
 4: (True, "example_street_brick.jpg", [(END, .9), (DY, .5)],
     f"DY, first-person POV from the helmet of the rider of {BIKE}, riding fast down the narrow brick street from Picture 3 with parked cars on both sides, trees and "
     f"apartment buildings: the handlebars with yellow hand guards in the lower frame and the rider's arms in the yellow DHL sleeves from Picture 2. "
     f"He weaves past a parked car and a cyclist and reaches the end of the street. Loud enduro engine, wind noise, a bicycle bell."),
 5: (True, "example_canal.jpg", [(CAM, .8), (END, .8), (DY, .5)],
     f"camera motion, DY, a fast tracking shot moving alongside the rider on the road that runs along the canal from Picture 3, the tall trees, "
     f"the green grass bank and the water of the canal behind. {AH} rides {BIKE} fast from right to left, leaning forward, overtaking a slow car. "
     f"City traffic, loud enduro engine."),
 6: (True, "example_tram_crossing.jpg", [(HUM, .5), (END, .6), (DY, .6)],
     f"DY, static camera at the crossing from Picture 3: a road with tram tracks in the grass median, a cycle path, overhead tram wires and brick corner buildings. "
     f"A red and white ROAD CLOSED barrier with a detour sign blocks the road out of the city. {AH} rides {BIKE} up to the barrier and stops, looks at the barrier, "
     f"looks at his wristwatch, then turns the bike off the road and rides over the grass median and down a dirt path beside the crossing, out of view. "
     f"City traffic ambience, enduro engine."),
 7: (True, None, [(END, .9), (DY, .5)],
     f"DY, first-person POV from the helmet of the rider of {BIKE}: the handlebars with yellow hand guards in the lower frame and the rider's arms in the "
     f"yellow DHL sleeves from Picture 2. Riding fast along a dirt path on top of a grassy dike, leaving the edge of the city behind, open green fields and "
     f"a line of trees ahead, accelerating hard, the bike bouncing over bumps. Loud enduro engine, wind noise."),
 8: (False, None, [(END, .9), (DY, .5)],
     f"{CONT}DY, first-person POV from the rider's helmet. The path leaves the dike and enters a dense forest, turning into a muddy single track, mud splashing "
     f"onto the front fender, branches whipping past, leaning hard into a tight turn. Loud enduro engine, mud splashes."),
 9: (False, None, [(END, .9), (DY, .5)],
     f"{CONT}DY, first-person POV from the rider's helmet. The track climbs out of the forest onto open rocky hillside, then drops down a steep descent over "
     f"roots and rocks, the front wheel bouncing, the rider standing on the pegs. Loud enduro engine, rocks clattering."),
 10: (True, None, [(CAM, .8), (END, .8), (DY, .5)],
     f"camera motion, DY, a fast side tracking shot moving parallel with the rider at the same speed along a narrow ridge trail high above a green valley, "
     f"slowly pushing in. {AH} rides {BIKE}, standing on the pegs, the rear wheel kicking up dirt and small stones. He glances down at his wristwatch "
     f"while riding, then leans forward and twists the throttle harder. Bright afternoon sun, mountains in the distance. Loud enduro engine, wind."),
 11: (False, None, [(CAM, .8), (END, .8), (DY, .5)],
     f"{CONT}camera motion, DY, the camera keeps tracking alongside the rider. {AH} rides {BIKE} on along the ridge as the trail turns rocky and narrow, "
     f"the bike sliding on loose stones, he catches it and rides on toward a forest valley ahead. Loud enduro engine, stones clattering."),
 12: (True, None, [(HUM, .5), (END, .6), (DY, .6)],
     f"DY, static camera on the bank of a wide rocky creek in a forest valley with rushing water. There is no bridge over the creek, only a few broken wooden "
     f"posts sticking out of the water where a bridge used to be. {AH} rides {BIKE} down the dirt trail and skids to a stop at the edge, looks at the gap, looks at his wristwatch, "
     f"then turns the bike around and rides back up the trail to take a run-up. Rushing water, enduro engine idling, then revving."),
 13: (True, None, [(BT, .5), (END, .6), (DY, .5)],
     f"DY, a dirt trail in a forest valley leading to a wide rocky creek with rushing water. There is no bridge over the creek, only a few broken wooden posts sticking out of the water. A dirt ramp at the edge of the bank. "
     f"0.00-3.00s: {AH} rides {BIKE} toward the ramp at high speed, the camera tracking from a low front-left angle, engine roaring. "
     f"3.00-3.60s: the bike launches off the ramp over the creek; the lid of the red top case pops open and {PARCEL} flies out. At the exact instant the parcel "
     f"leaves the top case, the action transitions into bullet-time. "
     f"3.60-7.00s: bullet-time. Time slows almost completely: the rider, the bike and the parcel stay frozen in mid-air above the creek, the parcel hanging just "
     f"above the open top case, water droplets suspended in the air, while the camera performs a smooth 180-degree orbital movement from the front-left side "
     f"around to the rear-right side. The rider, the bike, the open top case and the parcel keep their exact positions and spatial relationships throughout the orbit. "
     f"7.00-10.00s: time snaps back to normal speed, the rider reaches back and catches the parcel with one hand as the bike lands hard on the far bank. "
     f"Sound: roaring engine, a deep slowed-down whoosh and a heartbeat during bullet-time, then the engine roar returns with the landing."),
 14: (True, None, [(HUM, .5), (END, .6), (DY, .5)],
     f"DY, one continuous take from a static camera on a dirt trail in a forest, a wide shot showing the whole bike, no cuts and no close-ups. "
     f"{AH} sits on {BIKE}, stopped on the trail with the engine idling. He holds up {PARCEL} in his gloved hand and laughs with relief, "
     f"tucks the parcel inside his yellow hi-vis vest and then rides off up the dirt trail away from the camera. A relieved laugh, engine idling, then revving."),
 15: (False, None, [(END, .8), (HUM, .4), (DY, .5)],
     f"{CONT}DY. {AH} rides {BIKE} up a steep rocky hill climb, the rear wheel spinning and slipping on loose rocks, he dabs a foot down, shifts his weight "
     f"forward and powers over the top, where {CHAPEL} comes into view in golden late-afternoon light. Loud enduro engine revving, rocks clattering, a distant church bell."),
 16: (True, None, [(CAM, .7), (HUM, .5), (DY, .7)],
     f"camera motion, DY, a slow push-in toward {CHAPEL}, golden late-afternoon light. {GUESTS} wait outside the chapel. {GROOM} paces nervously in front of the "
     f"flower arch, checks his watch and shakes his head; {BRIDE} stands beside him looking worried. Then everyone hears a distant engine and turns to look "
     f"down the hill. Murmuring guests, a church bell, a distant enduro engine getting louder."),
 17: (False, None, [(CAM, .7), (HUM, .5), (DY, .7)],
     f"{CONT}camera motion, DY, the camera slowly orbits around the arrival. {AH} roars up the hill on {BIKE}, slides to a stop beside {GUESTS} in front of "
     f"{CHAPEL}, pulls off his yellow motocross helmet revealing his face from Picture 1 and his DHL cap, and hops off the bike. The guests gasp and point. "
     f"Engine revving then cutting out, guests gasping."),
 18: (False, None, [(HUM, .5), (DY, .7)],
     f"{CONT}DY, the camera stays steady. {A} runs to {GROOM}, unzips his hi-vis vest and hands him {PARCEL}. The groom tears it open and holds up a small "
     f"open ring box with two gold wedding rings. The guests cheer and clap, {BRIDE} laughs and hugs Sam, and the groom shakes his hand. "
     f"Cheering, applause, laughter."),
 19: (True, None, [(HUM, .5), (DY, .7)],
     f"DY, one continuous take, a static medium-wide shot at dusk under the white flower arch in front of {CHAPEL}, warm string lights glowing, no cuts. "
     f"{GROOM} and {BRIDE} face each other and slide the gold wedding rings onto each other's fingers while {GUESTS} watch. Among the guests on the right "
     f"stands {A} with his yellow motocross helmet under his arm, smiling. Soft romantic music, a happy sigh from the guests."),
 20: (True, None, [(CAM, .9), (END, .5), (DY, .6)],
     f"camera motion, DY, a slow aerial pull-back rising high above {CHAPEL} at dusk, revealing the whole valley in deep blue evening light. In front of the chapel "
     f"{GROOM} and {BRIDE} kiss under the flower arch while {GUESTS} cheer and throw petals. {AH} rides {BIKE} away down the winding dirt trail into the "
     f"valley, the headlight on, waving back once. Cheering, romantic music swelling, a distant engine fading."),
}


# lower strengths: three LoRAs at full strength on top of the 8-step turbo made moving objects ghost (2026-10-13)
STRENGTHS = {
 1: [(CAM, .6), (HUM, .3), (DY, .4)], 2: [(HUM, .3), (DY, .4)], 3: [(HUM, .3), (END, .5), (DY, .4)],
 4: [(END, .8), (DY, .4)], 5: [(CAM, .6), (END, .6), (DY, .4)], 6: [(HUM, .3), (END, .5), (DY, .4)],
 7: [(END, .8), (DY, .4)], 8: [(END, .8), (DY, .4)], 9: [(END, .8), (DY, .4)],
 10: [(CAM, .6), (END, .6), (DY, .4)], 11: [(CAM, .6), (END, .6), (DY, .4)], 12: [(HUM, .3), (END, .5), (DY, .4)],
 13: [(BT, .5), (END, .4), (DY, .3)], 14: [(HUM, .3), (END, .5), (DY, .4)], 15: [(END, .6), (HUM, .3), (DY, .4)],
 16: [(CAM, .5), (HUM, .3), (DY, .4)], 17: [(CAM, .5), (HUM, .3), (DY, .4)], 18: [(HUM, .3), (DY, .4)],
 19: [(HUM, .3), (DY, .4)], 20: [(CAM, .65), (END, .4), (DY, .4)],
}
PARTS = {k: (v[0], v[1], STRENGTHS[k], v[3]) for k, v in PARTS.items()}

# Shortened cut (2026-10-13): story parts 8, 9, 11 and 15 dropped. Video part n = STORY[n-1];
# queue as '<story>:<video part>', e.g. 10:8.
STORY = [1, 2, 3, 4, 5, 6, 7, 10, 12, 13, 14, 16, 17, 18, 19, 20]
