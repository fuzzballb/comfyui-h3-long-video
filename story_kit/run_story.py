"""Queue a multi-part story on a running ComfyUI (127.0.0.1:8188).

    python3 run_story.py dialogue <story.py> <project> [part ...]   # make the dialogue audio of parts with lines (waits)
    python3 run_story.py gen      <story.py> <project> [part ...]   # generate parts (default: all, in STORY order)
    python3 run_story.py gen --check <story.py> <project> [part ...]  # one at a time, re-roll parts whose speech doesn't match
    python3 run_story.py upscale  <project> <first> <last>            # queue the upscale of parts first..last
    python3 run_story.py prompts  <story.py> [<project>]              # print the final prompts (Picture numbers, dialogue timings)

A part spec is the video part number (1, 2, ...) or `<story part>:<video part>` to put story part 10 at video position 8.
FRONT=1 queues at the front of the queue (later front jobs run first, so queue a re-roll and its follow-up in reverse order).
COMFY=http://host:port overrides the server.

The story file is plain Python; see stories/dhl_enduro.py and stories/doorstep_dialogue.py. It defines:
    FACE, BODY      image names in ComfyUI/input (Picture 1 and 2: face crop and outfit sheet of the main character)
    PROPS           {'<TOKEN>': 'image.png'}: a prop sheet is added as an extra reference only to parts whose prompt has the token
    PARTS           {story part: (new_shot, location image or None, [(lora file, strength)], prompt[, lines])}
    STORY           optional list: video part n = story part STORY[n-1] (to drop story parts without renumbering)
    WIDTH, HEIGHT, SECONDS, TURBO   optional (defaults 1280, 704, 10.0, True)
    VOICES          {speaker: (voice, pronoun)} for dialogue, e.g. {'Sam': ('my_voice.wav', 'his')}; voice = a name from the
                    TTS Audio Suite voice list (models/voices/*.wav or its voices_examples)

Dialogue: give a part a 5th element `lines = [(speaker, "text"[, "how it is said"]), ...]` and put {DIALOGUE} in its prompt.
Two modes (DIALOGUE_MODE in the story file):
  'h3' (default)  H3 speaks the lines itself, in each speaker's voice: VOICES[speaker][0] is a voice sample in ComfyUI/input,
                  passed as reference audio (<Audio n>). Voice and face are made together, so intonation, emotion and
                  ambience are natural. H3 can still garble words, so run `gen --check`: every part is transcribed with
                  Whisper and re-rolled (up to CHECK_TRIES=3 times) until it matches the script (CHECK_MIN=0.8).
                  Needs openai-whisper in the Python that runs this script (e.g. ComfyUI's venv).
  'tts'           `dialogue` speaks every line with ChatterBox (VOICES[speaker][0] = a TTS Audio Suite voice) and `gen` freezes
                  that track (MiniMaxH3SongMaskedAVContext): exact words guaranteed, but TTS acting is flatter and the part
                  has no other sound.
"""
import difflib, json, os, random, re, runpy, subprocess, sys, tempfile, time, urllib.error, urllib.parse, urllib.request, uuid

HERE = os.path.dirname(os.path.abspath(__file__))
COMFY = os.environ.get('COMFY', 'http://127.0.0.1:8188')
CHECK = False
FPS, CONTEXT = 24, 39
LEAD, GAP = 0.5, 0.35          # 'tts' mode: silence before the first line / between lines (s)
# H3 copies the sound of clean voice samples (dry, close, studio-like). location_sound.py fixes that afterwards;
# a story can also add a sentence about the sound to every dialogue part (DIALOGUE_SOUND = '...')
DIALOGUE_SOUND = ''


def post(q):
    body = {'prompt': q, **({'front': True} if os.environ.get('FRONT') else {})}
    try:
        r = urllib.request.urlopen(urllib.request.Request(COMFY + '/prompt', json.dumps(body).encode(), {'Content-Type': 'application/json'}))
    except urllib.error.HTTPError as e:
        sys.exit('ComfyUI refused the job: ' + e.read().decode()[:1500])
    return json.loads(r.read())['prompt_id']


def wait(pid):
    while True:
        h = json.loads(urllib.request.urlopen(f'{COMFY}/history/{pid}').read().decode(), strict=False)
        if pid in h and h[pid].get('status', {}).get('completed') is not None:
            if h[pid]['status'].get('status_str') == 'error':
                sys.exit(f'ComfyUI job {pid} failed: ' + json.dumps(h[pid]['status']['messages'])[-800:])
            return h[pid]['outputs']
        time.sleep(2)


def fetch(filename, subfolder, kind='output'):
    q = urllib.parse.urlencode({'filename': filename, 'subfolder': subfolder, 'type': kind})
    return urllib.request.urlopen(f'{COMFY}/view?{q}').read()


def upload(path, name):
    """Upload a file into ComfyUI/input (the image upload endpoint takes any file)."""
    boundary = uuid.uuid4().hex
    data = open(path, 'rb').read()
    body = (f'--{boundary}\r\nContent-Disposition: form-data; name="image"; filename="{name}"\r\n'
            f'Content-Type: application/octet-stream\r\n\r\n').encode() + data + \
           f'\r\n--{boundary}\r\nContent-Disposition: form-data; name="overwrite"\r\n\r\ntrue\r\n--{boundary}--\r\n'.encode()
    urllib.request.urlopen(urllib.request.Request(COMFY + '/upload/image', body, {'Content-Type': f'multipart/form-data; boundary={boundary}'}))


def ffmpeg(*args):
    subprocess.run(['ffmpeg', '-v', 'error', '-y', *args], check=True)


def duration(path):
    return float(subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', path],
                                capture_output=True, text=True, check=True).stdout)


def dialogue_name(project, video_part):
    return f'{project}_part_{video_part:03d}_dialogue'


def make_dialogue(st, project, part, video_part, tmp):
    """Speak each line, assemble the part's audio track, upload it with its timings."""
    new, _, _, _, lines = st['PARTS'][part]
    voices = st['VOICES']
    files = []
    for i, (spk, text, *_) in enumerate(lines):
        voice = voices[spk][0]
        q = {'1': {'class_type': 'ChatterBoxEngineNode', 'inputs': {'language': 'local:English', 'device': 'auto', 'exaggeration': 0.5,
                                                                    'temperature': 0.8, 'cfg_weight': 0.5, 'crash_protection_template': 'hmm ,, {seg} hmm ,,'}},
             '2': {'class_type': 'UnifiedTTSTextNode', 'inputs': {'TTS_engine': ['1', 0], 'text': text, 'narrator_voice': voice, 'seed': 1 + i}},
             '3': {'class_type': 'SaveAudio', 'inputs': {'audio': ['2', 0], 'filename_prefix': f'dialogue/{project}/part_{video_part:03d}_line{i + 1}'}}}
        out = wait(post(q))['3']['audio'][0]
        f = os.path.join(tmp, f'line{i}.wav')
        open(f + '.flac', 'wb').write(fetch(out['filename'], out['subfolder']))
        ffmpeg('-i', f + '.flac', '-ar', '48000', '-ac', '1', f)
        files.append(f)
    cont = not (new or video_part == 1)
    t = CONTEXT / FPS + 0.3 if cont else LEAD
    pieces, timing = [], []
    if cont:      # the frozen context frames keep their own audio: start with the previous part's last 39 frames
        prev = os.path.join(tmp, 'prev.mkv')
        open(prev, 'wb').write(fetch(f'part_{video_part - 1:03d}.mkv', f'long_video/{project}/segments'))
        tail = os.path.join(tmp, 'tail.wav')
        ffmpeg('-sseof', f'-{CONTEXT / FPS:.4f}', '-i', prev, '-vn', '-ar', '48000', '-ac', '1', tail)
        pieces.append((tail, 0.0))
    for (spk, text, *_), f in zip(lines, files):
        d = duration(f)
        timing.append({'speaker': spk, 'text': text, 'start': round(t, 2), 'end': round(t + d, 2)})
        pieces.append((f, t))
        t += d + GAP
    total = float(st.get('SECONDS', 10.0)) + 0.2
    if timing[-1]['end'] > total - 0.3:
        print(f'  warning: part {video_part} dialogue ends at {timing[-1]["end"]:.1f}s, longer than the part ({total - 0.2:.0f}s); shorten the lines')
    inputs, filt = [], []
    for k, (f, start) in enumerate(pieces):
        inputs += ['-i', f]
        filt.append(f'[{k}]adelay={int(start * 1000)}|{int(start * 1000)}[a{k}]')
    filt.append(''.join(f'[a{k}]' for k in range(len(pieces))) + f'amix=inputs={len(pieces)}:normalize=0,apad=whole_dur={total}[out]')
    wav = os.path.join(tmp, dialogue_name(project, video_part) + '.wav')
    ffmpeg(*inputs, '-filter_complex', ';'.join(filt), '-map', '[out]', '-t', f'{total}', '-ar', '48000', '-ac', '1', wav)
    js = wav[:-4] + '.json'
    json.dump(timing, open(js, 'w'), indent=1)
    upload(wav, os.path.basename(wav)); upload(js, os.path.basename(js))
    return timing


def dialogue_text(st, timing):
    out = []
    for i, ln in enumerate(timing):
        pron = st['VOICES'][ln['speaker']][1]
        out.append(f'{ln["start"]:.1f}-{ln["end"]:.1f}s: {ln["speaker"]} says, {pron} lips moving clearly: "{ln["text"]}"')
    return ' '.join(out) + ' Whoever is not speaking listens with a closed mouth.'


def build(st, project, part, video_part, seed=None, timing=None):
    """API prompt for one part. Node ids are those of templates/generate_api.json (= example workflow 1)."""
    entry = st['PARTS'][part]
    new, loc, loras, prompt = entry[:4]
    lines = entry[4] if len(entry) > 4 else None
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
    new_shot = bool(new or video_part == 1)
    q['79']['inputs']['value'] = new_shot
    if lines and st.get('DIALOGUE_MODE', 'h3') == 'h3':
        speakers = [k for k in st['VOICES'] if any(ln[0] == k for ln in lines)]   # stable <Audio n> order: VOICES order
        for i, spk in enumerate(speakers):
            q[str(36 + i)] = {'class_type': 'LoadAudio', 'inputs': {'audio': st['VOICES'][spk][0]}}
        q['40a'] = {'class_type': 'H3LongVideoReferenceAudios', 'inputs': {'max_seconds': 10.0, **{f'audio_{i + 1}': [str(36 + i), 0] for i in range(len(speakers))}}}
        refs['references'] = ['40a', 0]
        said = []
        for k, ln in enumerate(lines):
            spk, text = ln[0], ln[1]
            how = f', {ln[2]}' if len(ln) > 2 and ln[2] else ''
            verb = 'says' if k == 0 else ('answers' if lines[k - 1][0] != spk else 'adds')
            said.append(f'{"Then " if k else ""}{spk} {verb} in the voice from <Audio {speakers.index(spk) + 1}>{how}, '
                        f'{st["VOICES"][spk][1]} lips moving clearly: "{text}"')
        if re.search(r'(^|[ ,.])(DY|camera motion,|bullet-time)([ ,.]|$)', prompt):
            print(f'  warning: part {video_part} has dialogue and a LoRA trigger word in its prompt; H3 may speak it ("D.Y."). Remove the word, keep the LoRA.')
        prompt = prompt.replace('{DIALOGUE}', ' '.join(said) + (' They speak naturally, like a real conversation, and react to each other. ' + st.get('DIALOGUE_SOUND', DIALOGUE_SOUND)).rstrip())
    elif lines:
        if timing is None:
            sys.exit(f'part {video_part} has dialogue: run `run_story.py dialogue` first')
        prompt = prompt.replace('{DIALOGUE}', dialogue_text(st, timing))
        # freeze the dialogue track instead of letting H3 invent the speech; replaces the Continue node
        q['34'] = {'class_type': 'LoadAudio', 'inputs': {'audio': dialogue_name(project, video_part) + '.wav'}}
        q['33'] = {'class_type': 'MiniMaxH3SongMaskedAVContext', 'inputs': {
            'latent': ['23', 1], 'audio_vae': ['4', 0], 'master_audio': ['34', 0], 'clip_start_seconds': 0.0,
            'context_length': 0 if new_shot else CONTEXT, 'source_fps': float(FPS), 'crop': 'disabled'}}
        if not new_shot:
            q['35'] = {'class_type': 'H3LongVideoLoadPart', 'inputs': {'project': project, 'part': video_part - 1}}
            q['33']['inputs']['source_latent'] = ['35', 0]
        q['44']['inputs']['latent_image'] = ['33', 0]
        q['52']['inputs']['trim_frames'] = ['33', 1]
        del q['32']
    q['22']['inputs']['value'] = prompt
    q['30']['inputs']['value'] = project
    q['31']['inputs']['value'] = video_part
    refs.update(width=st.get('WIDTH', 1280), height=st.get('HEIGHT', 704))
    q['20']['inputs']['value'] = float(st.get('SECONDS', 10.0))
    q['40']['inputs']['noise_seed'] = seed or random.randrange(2 ** 48)
    return q


def load_timing(project, video_part):
    try:
        return json.loads(fetch(dialogue_name(project, video_part) + '.json', '', 'input'))
    except Exception:
        return None


def words(text):
    return re.findall(r"[a-z0-9']+", text.lower())


_WHISPER = None


def speech_match(project, video_part, lines):
    """Transcribe the new frames of a part and compare them with the script (0..1)."""
    global _WHISPER
    import whisper
    if _WHISPER is None:
        _WHISPER = whisper.load_model(os.environ.get('WHISPER_MODEL', 'small'),
                                      download_root=os.environ.get('WHISPER_DIR') or None)
    with tempfile.TemporaryDirectory() as tmp:
        f = os.path.join(tmp, 'part.mkv')
        open(f, 'wb').write(fetch(f'part_{video_part:03d}.mkv', f'long_video/{project}/segments'))
        heard = _WHISPER.transcribe(f, language=os.environ.get('WHISPER_LANG', 'en'))['text'].strip()
    want = words(' '.join(ln[1] for ln in lines))
    return difflib.SequenceMatcher(None, want, words(heard)).ratio(), heard


def parse(st, specs):
    order = st.get('STORY') or sorted(st['PARTS'])
    if not specs:
        return [(s, v) for v, s in enumerate(order, 1)]
    out = []
    for spec in specs:
        a, _, b = spec.partition(':')
        out.append((int(a), int(b)) if b else (order[int(a) - 1], int(a)))
    return out


def has_lines(st, s):
    return len(st['PARTS'][s]) > 4 and st['PARTS'][s][4]


def main(argv):
    global CHECK
    CHECK = '--check' in argv
    argv = [a for a in argv if a != '--check']
    if len(argv) < 2 or argv[0] not in ('gen', 'upscale', 'prompts', 'dialogue'):
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
        project = argv[2] if len(argv) > 2 else None
        for s, v in parse(st, argv[3:]):
            timing = load_timing(project, v) if project and has_lines(st, s) else None
            if has_lines(st, s) and timing is None:
                timing = [{'speaker': ln[0], 'text': ln[1], 'start': 0, 'end': 0} for ln in st['PARTS'][s][4]]
            print(f'--- video part {v} (story part {s})\n' + build(st, project or 'x', s, v, timing=timing)['22']['inputs']['value'])
        return
    project = argv[2]
    parts = parse(st, argv[3:])
    check = cmd == 'gen' and CHECK
    if cmd == 'dialogue':
        with tempfile.TemporaryDirectory() as tmp:
            for s, v in parts:
                if has_lines(st, s):
                    for ln in make_dialogue(st, project, s, v, tmp):
                        print(f'part {v}: {ln["start"]:5.2f}-{ln["end"]:5.2f}s {ln["speaker"]}: {ln["text"]}')
        return
    if check:
        tries, need = int(os.environ.get('CHECK_TRIES', 3)), float(os.environ.get('CHECK_MIN', 0.8))
        for s, v in parts:
            for attempt in range(1, tries + 1):
                wait(post(build(st, project, s, v, timing=load_timing(project, v) if has_lines(st, s) else None)))
                if not has_lines(st, s):
                    print(f'part {v}: done (no dialogue)'); break
                score, heard = speech_match(project, v, st['PARTS'][s][4])
                print(f'part {v} take {attempt}: match {score:.2f}  heard: {heard}')
                if score >= need:
                    break
            else:
                print(f'part {v}: no take reached {need}; kept the last one')
        return
    ids = []
    for s, v in parts:
        timing = load_timing(project, v) if has_lines(st, s) else None
        ids.append(post(build(st, project, s, v, timing=timing)))
    print(len(ids), 'parts queued')


if __name__ == '__main__':
    main(sys.argv[1:])
