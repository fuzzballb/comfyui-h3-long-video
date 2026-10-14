"""Queue a multi-part story on a running ComfyUI (127.0.0.1:8188).

    python3 run_story.py gen     <story.py> <project> [part ...]   # generate parts (default: all, in STORY order)
    python3 run_story.py upscale <project> <first> <last>            # queue the upscale of parts first..last
    python3 run_story.py prompts <story.py>                          # print the final prompts (Picture numbers filled in)

A part spec is the video part number (1, 2, ...) or `<story part>:<video part>` to put story part 10 at video position 8.
FRONT=1 queues at the front of the queue (later front jobs run first, so queue a re-roll and its follow-up in reverse order).
COMFY=http://host:port overrides the server.

The story file is plain Python; see stories/dhl_enduro.py. It defines:
    FACE, BODY      image names in ComfyUI/input (Picture 1 and 2: face crop and outfit sheet of the main character)
    PROPS           {'<TOKEN>': 'image.png'}: a prop sheet is added as an extra reference only to parts whose prompt has the token
    PARTS           {story part: (new_shot, location image or None, [(lora file, strength)], prompt)}
    STORY           optional list: video part n = story part STORY[n-1] (to drop story parts without renumbering)
    WIDTH, HEIGHT, SECONDS, TURBO   optional (defaults 1280, 704, 10.0, True)
"""
import json, os, random, runpy, sys, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
COMFY = os.environ.get('COMFY', 'http://127.0.0.1:8188')


def post(q):
    body = {'prompt': q, **({'front': True} if os.environ.get('FRONT') else {})}
    r = urllib.request.urlopen(urllib.request.Request(COMFY + '/prompt', json.dumps(body).encode(), {'Content-Type': 'application/json'}))
    return json.loads(r.read())['prompt_id']


def build(st, project, part, video_part, seed=None):
    """API prompt for one part. Node ids are those of templates/generate_api.json (= example workflow 1)."""
    new, loc, loras, prompt = st['PARTS'][part]
    q = json.load(open(os.path.join(HERE, 'templates', 'generate_api.json')))
    q['11']['inputs']['image'] = st['FACE']
    q['12']['inputs']['image'] = st['BODY']
    refs = q['23']['inputs']
    if loc:
        q['13']['inputs']['image'] = loc
    else:
        del q['13'], refs['reference_images.reference_image_2']
    n = 4 if loc else 3                                    # next free "Picture n"
    for i, (tok, img) in enumerate(st.get('PROPS', {}).items()):
        if tok in prompt:
            nid = str(14 + i)
            q[nid] = {'class_type': 'LoadImage', 'inputs': {'image': img}}
            refs[f'reference_images.reference_image_{n - 1}'] = [nid, 0]
            prompt = prompt.replace(tok, f'Picture {n}')
            n += 1
    prev = ['73', 0]                                       # extra LoRAs go after the turbo switch
    for i, (name, strength) in enumerate(loras):
        q[str(90 + i)] = {'class_type': 'LoraLoaderModelOnly', 'inputs': {'lora_name': name, 'strength_model': strength, 'model': prev}}
        prev = [str(90 + i), 0]
    q['9']['inputs']['model'] = prev
    q['70']['inputs']['value'] = st.get('TURBO', True)    # turbo LoRA + 8 steps
    q['77']['inputs']['value'] = False                     # SLA attention off (it warps straight lines)
    q['79']['inputs']['value'] = bool(new or video_part == 1)
    q['22']['inputs']['value'] = prompt
    q['30']['inputs']['value'] = project
    q['31']['inputs']['value'] = video_part
    refs.update(width=st.get('WIDTH', 1280), height=st.get('HEIGHT', 704))
    q['20']['inputs']['value'] = float(st.get('SECONDS', 10.0))
    q['40']['inputs']['noise_seed'] = seed or random.randrange(2 ** 48)
    return q


def parse(st, specs):
    order = st.get('STORY') or sorted(st['PARTS'])
    if not specs:
        return [(s, v) for v, s in enumerate(order, 1)]
    out = []
    for spec in specs:
        a, _, b = spec.partition(':')
        out.append((int(a), int(b)) if b else (order[int(a) - 1], int(a)))
    return out


def main(argv):
    if len(argv) < 2 or argv[0] not in ('gen', 'upscale', 'prompts'):
        sys.exit(__doc__)
    cmd = argv[0]
    if cmd == 'upscale':
        project, first, last = argv[1], int(argv[2]), int(argv[3])
        base = json.load(open(os.path.join(HERE, 'templates', 'upscale_api.json')))
        ids = []
        for p in range(first, last + 1):
            q = json.loads(json.dumps(base))
            q['500']['inputs']['value'] = project
            q['501']['inputs']['value'] = p
            ids.append(post(q))
        print(len(ids), 'upscales queued')
        return
    st = runpy.run_path(argv[1])
    if cmd == 'prompts':
        for s, v in parse(st, argv[2:]):
            print(f'--- video part {v} (story part {s})\n' + build(st, 'x', s, v)['22']['inputs']['value'])
        return
    project = argv[2]
    ids = [post(build(st, project, s, v)) for s, v in parse(st, argv[3:])]
    print(len(ids), 'parts queued')


if __name__ == '__main__':
    main(sys.argv[1:])
