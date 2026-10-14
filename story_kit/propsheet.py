"""Make a prop reference sheet with Qwen Image 2.1 (the same graph as example workflow 4).

    python3 propsheet.py <name> "<prompt>" [source image ...] [--count 4] [--aspect "16:9 (Widescreen)"]

Source images are names in ComfyUI/input (e.g. crops of the prop from an earlier part) and are Picture 1, 2, ... in the prompt.
Results: ComfyUI/output/props/<name>_NNNNN.png. Copy the one you like into ComfyUI/input and list it in the story's PROPS.

Prompt that worked for the bike (Picture 1 = bike crop, Picture 2 = top case crop):
  Create a clean product reference sheet on a plain white background, studio lighting, photorealistic. The object is the yellow DHL
  enduro motorbike from Picture 1, exactly the same bike: ... Mounted on the rear rack behind the seat is a small red hard-shell
  motorcycle top case, like the red box in Picture 2, ... The top case is fixed to the bike and is visible in BOTH views. Show the bike
  twice, side by side, full bike in frame with space around it: on the left a full side view from the right side, on the right a
  three-quarter rear view. No people, no text other than the DHL logos.
Ask for the prop "in BOTH views", or the second view often drops a part of it. Text on a prop ("URGENT") comes out readable.
"""
import argparse, json, os, random, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
COMFY = os.environ.get('COMFY', 'http://127.0.0.1:8188')

ap = argparse.ArgumentParser()
ap.add_argument('name'); ap.add_argument('prompt'); ap.add_argument('images', nargs='*')
ap.add_argument('--count', type=int, default=4); ap.add_argument('--aspect', default='16:9 (Widescreen)')
ap.add_argument('--megapixels', type=float, default=1.5)
a = ap.parse_args()

base = json.load(open(os.path.join(HERE, 'templates', 'propsheet_api.json')))
for _ in range(a.count):
    q = json.loads(json.dumps(base))
    te = q['459:474']['inputs']
    for i, img in enumerate(a.images, 1):
        q[f'60{i}'] = {'class_type': 'LoadImage', 'inputs': {'image': img}}
        te[f'images.image_{i}'] = [f'60{i}', 0]
    te['prompt'] = a.prompt
    q['13']['inputs'].update(aspect_ratio=a.aspect, megapixels=a.megapixels)
    q['459:458']['inputs']['seed'] = random.randrange(2 ** 48)
    q['461']['inputs']['filename_prefix'] = f'props/{a.name}'
    r = urllib.request.urlopen(urllib.request.Request(COMFY + '/prompt', json.dumps({'prompt': q}).encode(), {'Content-Type': 'application/json'}))
    print(json.loads(r.read())['prompt_id'])
