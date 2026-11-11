#!/usr/bin/env python3
"""Free AI images through Cloudflare Workers AI. CLI + library (used by api.py).

genimage "prompt" [-o file] [--model flux|sdxl|klein|dreamshaper] [--style NAME] [--ratio 16:9]
         [--size WxH] [--steps N] [--seed N] [-n COUNT] [--from image --strength 0.6] [--x2]
genimage --upscale image.jpg        2x Lanczos + sharpen (ImageMagick)
genimage --quota | --styles | --config
Keys (Settings -> Keys): CLOUDFLARE_ACCOUNT_ID, CLOUDFLARE_API_TOKEN.
"""
import argparse, base64, json, os, subprocess, sys, time, urllib.error, urllib.request, uuid, zipfile
from pathlib import Path


def _workspace():
    for c in (os.environ.get("MAXXING_WORKSPACE"), "/root/maxxing", str(Path.home() / "maxxing")):
        if c and Path(c).is_dir():
            return Path(c)
    return Path.home()


def _state_dir():
    d = Path("/var/lib/claude-maxxing/extensions/images")
    return d if d.parent.is_dir() and os.access(d.parent, os.W_OK) else Path.home() / ".local/share/genimage"


STATE = Path(os.environ.get("GENIMAGE_STATE") or _state_dir())  # api.py sets it from ctx["state_dir"]
OUT_ROOT = Path(os.environ.get("GENIMAGE_OUT") or _workspace() / "images")
DAILY_NEURONS = 10000  # Workers AI free plan, reset 00:00 UTC

MODELS = {
    "flux": {"id": "@cf/black-forest-labs/flux-1-schnell", "label": "FLUX.1 schnell (quality, 1024²)", "sized": False, "seed": False, "steps": 4, "fmt": "json"},
    "sdxl": {"id": "@cf/bytedance/stable-diffusion-xl-lightning", "label": "SDXL Lightning (fast, free sizes)", "sized": True, "seed": True, "steps": 4, "fmt": "json"},
    "klein": {"id": "@cf/black-forest-labs/flux-2-klein-4b", "label": "FLUX.2 klein 4B (finer, ~95/day)", "sized": True, "seed": False, "steps": 4, "fmt": "multipart"},
    "dreamshaper": {"id": "@cf/lykon/dreamshaper-8-lcm", "label": "DreamShaper (image to image, free sizes)", "sized": True, "seed": True, "steps": 4, "fmt": "json", "img2img": True},
}
RATIOS = {"1:1": (1024, 1024), "16:9": (1024, 576), "9:16": (576, 1024), "3:2": (1024, 688), "2:3": (688, 1024), "4:3": (1024, 768), "3:4": (768, 1024)}
STYLES = {  # suffix appended to the prompt
    "photo": "photorealistic, shot on 85mm lens, f/1.8, shallow depth of field, natural soft light, sharp focus, fine detail",
    "portrait": "studio portrait, 85mm, softbox lighting, soft catchlights, neutral background, skin texture visible",
    "cinematic": "cinematic film still, anamorphic lens, dramatic rim lighting, teal and orange grading, 35mm film grain",
    "flat": "flat vector illustration, clean shapes, limited color palette, no gradients, minimal, white background",
    "watercolor": "soft watercolor painting, wet-on-wet washes, visible paper texture, pastel tones, loose brush strokes",
    "oil": "oil painting, thick impasto brush strokes, rich colors, canvas texture, warm gallery lighting",
    "3d": "3D render, soft clay material, smooth rounded shapes, studio lighting, pastel colors, octane render",
    "isometric": "isometric 3D illustration, tiny diorama, clean geometry, soft shadows, light background",
    "logo": "minimalist logo design, simple bold geometric shape, centered, flat vector, solid background, high contrast",
    "icon": "app icon, single centered object, rounded shape, subtle gradient, clean edges, plain background",
    "banner": "wide banner composition, subject on the right, large empty space on the left for text, soft gradient background",
    "pixel": "pixel art, 16-bit style, crisp pixels, limited palette, retro game sprite, dithering",
    "anime": "anime illustration, clean line art, cel shading, vibrant colors, detailed background",
    "sketch": "pencil sketch, graphite hatching, white paper, fine linework, monochrome",
    "product": "product photo on seamless white background, softbox lighting, soft shadow, ultra sharp, e-commerce style",
    "cyberpunk": "cyberpunk night city, neon reflections on wet streets, volumetric fog, magenta and cyan lights",
}
CONFIG_DEFAULT = {
    "caller_daily_max": 40,   # images a day for each caller other than the page (agent, session)
    "human_reserve_pct": 20,  # share of the daily budget kept for the page
    "max_per_minute": 10,     # anti-loop
    "fallback": False,        # AI Horde when Cloudflare fails: prompts go to volunteers' machines
}


# ---------------------------------------------------------------- state
def config():
    c = dict(CONFIG_DEFAULT)
    try:
        c.update(json.loads((STATE / "config.json").read_text()))
    except (OSError, ValueError):
        pass
    return c


def set_config(patch):
    c = config()
    for k, v in (patch or {}).items():
        if k in CONFIG_DEFAULT and type(v) is type(CONFIG_DEFAULT[k]) and (type(v) is bool or v >= 0):
            c[k] = v
    STATE.mkdir(parents=True, exist_ok=True)
    (STATE / "config.json").write_text(json.dumps(c))
    return c


def _read():
    f = STATE / "history.jsonl"
    if not f.exists():
        return []
    out = []
    for line in f.read_text().splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:
            pass
    return out


def _write(items):
    STATE.mkdir(parents=True, exist_ok=True)
    tmp = STATE / "history.tmp"
    tmp.write_text("".join(json.dumps(i, ensure_ascii=False) + "\n" for i in items))
    tmp.replace(STATE / "history.jsonl")


def history(limit=80, q="", fav=False):
    items = list(reversed(_read()))
    if q:
        items = [i for i in items if q.lower() in i["prompt"].lower()]
    if fav:
        items = [i for i in items if i.get("fav")]
    return items[:limit]


def _today():
    day = time.strftime("%Y-%m-%d", time.gmtime())
    return [i for i in _read() if time.strftime("%Y-%m-%d", time.gmtime(i["at"])) == day]


def neurons(model, steps, w, h):
    if model == "flux":  # published: 4.8 per 512x512 tile + 9.6 per step
        return round(max(1, round(w * h / (512 * 512))) * 4.8 + steps * 9.6, 1)
    if model == "klein":  # estimate from the pricing page (~105 at 1024x1024)
        return round(105 * (w * h) / (1024 * 1024), 1)
    return round(max(1, w * h / (512 * 512)) * 4.8 + steps * 2, 1)  # estimate


def quota():
    used = sum(i.get("neurons", 0) for i in _today())
    left = max(0, DAILY_NEURONS - used)
    callers = {}
    for i in _today():
        callers[i.get("topic") or "?"] = callers.get(i.get("topic") or "?", 0) + 1
    return {"used": round(used, 1), "limit": DAILY_NEURONS, "left": round(left, 1),
            "approx_images_left": int(left // neurons("flux", 4, 1024, 1024)), "by_caller": callers}


def _check_limits(caller, cost):
    c, items = config(), _read()
    now = time.time()
    if sum(1 for i in items if i["at"] > now - 60) >= c["max_per_minute"]:
        raise RuntimeError(f"anti-boucle : {c['max_per_minute']} images par minute au maximum")
    if caller != "page":
        n = sum(1 for i in _today() if i.get("topic") == caller)
        if n >= c["caller_daily_max"]:
            raise RuntimeError(f"plafond de {c['caller_daily_max']} images par jour atteint pour « {caller} »")
        if quota()["used"] + cost > DAILY_NEURONS * (100 - c["human_reserve_pct"]) / 100:
            raise RuntimeError(f"il reste {c['human_reserve_pct']} % du quota gratuit réservés à la page")


# ---------------------------------------------------------------- files
def _secret(name):
    v = os.environ.get(name)
    if v:
        return v
    return subprocess.run(["maxxing", "keys", "get", name], capture_output=True, text=True).stdout.strip()


def delete(item_id, force=False):
    items = _read()
    keep = []
    for i in items:
        if i["id"] == item_id and (force or not i.get("fav")):
            for p in (i["path"], str(STATE / "thumbs" / f"{item_id}.jpg")):
                try:
                    Path(p).unlink()
                except OSError:
                    pass
        else:
            keep.append(i)
    _write(keep)


def set_fav(item_id, value):
    items = _read()
    for i in items:
        if i["id"] == item_id:
            i["fav"] = bool(value)
    _write(items)


def thumb(item_id):
    t = STATE / "thumbs" / f"{item_id}.jpg"
    if not t.exists():
        src = next((i["path"] for i in _read() if i["id"] == item_id), None)
        if not src or not Path(src).exists():
            return None
        t.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["convert", src, "-resize", "384x384>", "-quality", "75", str(t)], check=True)
    return "data:image/jpeg;base64," + base64.b64encode(t.read_bytes()).decode()


def make_zip(ids):
    items = [i for i in _read() if i["id"] in set(ids) and Path(i["path"]).exists()]
    if not items:
        raise ValueError("aucune image")
    out = OUT_ROOT / "zips" / f"images-{time.strftime('%Y%m%d-%H%M%S')}.zip"
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_STORED) as z:
        for i in items:
            z.write(i["path"], Path(i["path"]).name)
    return str(out)


def upscale(path, out=None):
    src = Path(path).expanduser().resolve()
    dst = Path(out) if out else src.with_name(src.stem + "-x2" + src.suffix)
    subprocess.run(["convert", str(src), "-filter", "Lanczos", "-resize", "200%", "-unsharp", "0x1", "-quality", "92", str(dst)], check=True)
    return str(dst)


def _crop(path, ratio):
    w, h = RATIOS[ratio]
    subprocess.run(["convert", path, "-gravity", "center", "-crop", f"{w}x{h}+0+0", "+repage", path], check=True)


# ---------------------------------------------------------------- providers
def _multipart(fields):
    b = uuid.uuid4().hex
    body = b"".join(f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode() for k, v in fields.items()) + f"--{b}--\r\n".encode()
    return body, f"multipart/form-data; boundary={b}"


def _cloudflare(m, body, acc, tok):
    url = f"https://api.cloudflare.com/client/v4/accounts/{acc}/ai/run/{m['id']}"
    if m["fmt"] == "multipart":
        raw_body, ctype = _multipart(body)
    else:
        raw_body, ctype = json.dumps(body).encode(), "application/json"
    req = urllib.request.Request(url, raw_body, {"Authorization": f"Bearer {tok}", "Content-Type": ctype})
    for attempt in range(3):
        try:
            resp = urllib.request.urlopen(req, timeout=100)
            raw = resp.read()
            if resp.headers.get_content_type().startswith("image/"):
                return raw
            d = json.loads(raw)
            if not d.get("success", True):
                raise RuntimeError(str(d.get("errors"))[:300])
            return base64.b64decode(d["result"]["image"])
        except urllib.error.HTTPError as e:
            msg = e.read()[:200].decode(errors="replace")
            if e.code in (429, 500, 502, 503) and attempt < 2:
                time.sleep(3 * (attempt + 1))
                continue
            raise RuntimeError(f"Cloudflare {e.code}: {msg}")


def _horde(prompt, width, height):
    """Free fallback: AI Horde, anonymous key, queue-based (about a minute), 512x512 at most."""
    w, h = (max(64, min(512, x // 64 * 64)) for x in (width, height))
    hdr = {"apikey": "0000000000", "Content-Type": "application/json", "Client-Agent": "harness-images:1.0:unknown", "User-Agent": "harness-images/1.0"}
    req = urllib.request.Request("https://aihorde.net/api/v2/generate/async", json.dumps(
        {"prompt": prompt, "params": {"width": w, "height": h, "steps": 20, "n": 1}, "nsfw": False, "r2": True}).encode(), hdr)
    job = json.load(urllib.request.urlopen(req, timeout=30))["id"]
    deadline = time.time() + 240
    while time.time() < deadline:
        time.sleep(5)
        st = json.load(urllib.request.urlopen(urllib.request.Request(f"https://aihorde.net/api/v2/generate/status/{job}", headers=hdr), timeout=30))
        if st.get("done") and st.get("generations"):
            img = st["generations"][0]["img"]
            if img.startswith("http"):
                return urllib.request.urlopen(img, timeout=60).read()
            return base64.b64decode(img)
        if st.get("faulted"):
            break
    raise RuntimeError("AI Horde : pas de résultat (file d'attente trop longue)")


# ---------------------------------------------------------------- generate
def generate(prompt, model="flux", steps=None, seed=None, width=1024, height=1024, out=None, topic="",
             style=None, ratio=None, source=None, strength=0.6, x2=False):
    prompt = (prompt or "").strip()
    if not prompt:
        raise ValueError("prompt vide")
    m = MODELS.get(model)
    if not m:
        raise ValueError(f"modèle inconnu: {model} ({', '.join(MODELS)})")
    if style:
        if style not in STYLES:
            raise ValueError(f"style inconnu: {style} ({', '.join(STYLES)})")
        prompt = f"{prompt}, {STYLES[style]}"
    if source and not m.get("img2img"):
        raise ValueError("image → image : utiliser --model dreamshaper")
    if ratio:
        if ratio not in RATIOS:
            raise ValueError(f"ratio inconnu: {ratio} ({', '.join(RATIOS)})")
        width, height = RATIOS[ratio]
    steps = max(1, min(8, int(steps or m["steps"])))
    if m["sized"]:
        width, height = max(256, min(1024, int(width) // 8 * 8)), max(256, min(1024, int(height) // 8 * 8))
    else:
        width = height = 1024
    cost = neurons(model, steps, width, height)
    caller = topic or "cli"
    _check_limits(caller, cost)
    body = {"prompt": prompt}
    if m["fmt"] == "multipart":
        body.update(width=width, height=height)
    elif m["sized"]:
        body.update(num_steps=steps, width=width, height=height)
    else:
        body["steps"] = steps
    if not m["seed"]:
        seed = None  # FLUX refuses a seed on Workers AI
    if seed is not None:
        body["seed"] = int(seed)
    if source:
        body["image_b64"] = base64.b64encode(Path(source).read_bytes()).decode()
        body["strength"] = float(strength)
    provider, data = "cloudflare", None
    acc, tok = _secret("CLOUDFLARE_ACCOUNT_ID"), _secret("CLOUDFLARE_API_TOKEN")
    try:
        if not acc or not tok:
            raise RuntimeError("clés CLOUDFLARE_ACCOUNT_ID / CLOUDFLARE_API_TOKEN absentes (Settings -> Keys)")
        if quota()["left"] < cost:
            raise RuntimeError("quota gratuit du jour atteint (remise à zéro 00:00 UTC)")
        data = _cloudflare(m, body, acc, tok)
    except RuntimeError as e:
        if not config()["fallback"] or source or "clés" in str(e):
            raise
        try:
            data, provider, cost = _horde(prompt, width, height), "horde", 0
        except (OSError, ValueError, KeyError) as e2:
            raise RuntimeError(f"{e} ; secours AI Horde en échec : {e2}")
    ext = "png" if data[:4] == b"\x89PNG" else "webp" if data[:4] == b"RIFF" else "jpg"
    item_id = f"{int(time.time())}-{os.urandom(2).hex()}"
    path = Path(out).expanduser().resolve() if out else OUT_ROOT / time.strftime("%Y-%m") / f"{item_id}.{ext}"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    if ratio and not m["sized"] and provider == "cloudflare":
        _crop(str(path), ratio)
        width, height = RATIOS[ratio]
    if x2:
        path = Path(upscale(str(path), str(path.with_name(path.stem + "-x2" + path.suffix))))
        width, height = width * 2, height * 2
    item = {"id": item_id, "at": time.time(), "prompt": prompt, "model": model if provider == "cloudflare" else "horde",
            "provider": provider, "style": style, "steps": steps, "seed": seed, "w": width, "h": height,
            "path": str(path), "neurons": cost, "topic": caller}
    _write(_read() + [item])
    return item


def main():
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("prompt", nargs="?")
    a.add_argument("-o", "--out")
    a.add_argument("--model", default="flux", choices=list(MODELS))
    a.add_argument("--style", choices=list(STYLES))
    a.add_argument("--ratio", choices=list(RATIOS))
    a.add_argument("--size", help="WxH (sdxl, klein, dreamshaper; FLUX is always 1024x1024)")
    a.add_argument("--steps", type=int)
    a.add_argument("--seed", type=int)
    a.add_argument("-n", type=int, default=1, help="variants (1-4)")
    a.add_argument("--from", dest="source", help="source image (with --model dreamshaper)")
    a.add_argument("--strength", type=float, default=0.6)
    a.add_argument("--x2", action="store_true", help="2x upscale of the result")
    a.add_argument("--upscale", metavar="IMAGE")
    a.add_argument("--quota", action="store_true")
    a.add_argument("--styles", action="store_true")
    a.add_argument("--config", action="store_true")
    a = a.parse_args()
    if a.styles:
        print("\n".join(f"{k}: {v}" for k, v in STYLES.items()) + "\nratios: " + ", ".join(RATIOS))
        return
    if a.config:
        print(json.dumps(config()))
        return
    if a.upscale:
        print(upscale(a.upscale))
        return
    if a.quota or not a.prompt:
        print(json.dumps(quota()))
        return
    w, h = (int(x) for x in a.size.lower().split("x")) if a.size else (1024, 1024)
    caller = os.environ.get("GENIMAGE_CALLER") or os.path.basename(os.getcwd())
    n = max(1, min(4, a.n))
    for k in range(n):
        out = a.out
        if out and n > 1:
            p = Path(out)
            out = str(p.with_name(f"{p.stem}-{k + 1}{p.suffix}"))
        seed = a.seed + k if a.seed is not None else (int.from_bytes(os.urandom(3), "big") if n > 1 and MODELS[a.model]["seed"] else None)
        try:
            it = generate(a.prompt, a.model, a.steps, seed, w, h, out, caller, a.style, a.ratio, a.source, a.strength, a.x2)
        except Exception as e:
            sys.exit(f"Erreur: {e}")
        print(it["path"])
        extra = f", seed {it['seed']}" if it["seed"] is not None else ""
        print(f"({it['provider']}, {it['neurons']} neurons{extra}, reste ~{quota()['approx_images_left']} images FLUX aujourd'hui)", file=sys.stderr)


if __name__ == "__main__":
    main()
