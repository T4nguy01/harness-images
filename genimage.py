#!/usr/bin/env python3
"""Free AI images through Cloudflare Workers AI. CLI + library (used by api.py).

genimage "prompt" [-o file] [--model flux|sdxl] [--steps N] [--seed N] [--size 1024x1024] [--quota]
Keys (Settings -> Keys): CLOUDFLARE_ACCOUNT_ID, CLOUDFLARE_API_TOKEN.
"""
import argparse, base64, json, os, subprocess, sys, time, urllib.error, urllib.request
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
    "flux": {"id": "@cf/black-forest-labs/flux-1-schnell", "label": "FLUX.1 schnell (qualité)", "sized": False, "seed": False, "max_steps": 8, "steps": 4},
    "sdxl": {"id": "@cf/bytedance/stable-diffusion-xl-lightning", "label": "SDXL Lightning (rapide, tailles libres)", "sized": True, "seed": True, "max_steps": 8, "steps": 4},
}


def neurons(model, steps, w, h):
    if model == "flux":  # published: 4.8 / 512x512 tile + 9.6 / step
        tiles = max(1, round(w * h / (512 * 512))) if w and h else 4
        return round(tiles * 4.8 + steps * 9.6, 1)
    return round(max(1, w * h / (512 * 512)) * 4.8 + steps * 2, 1)  # estimate


def _secret(name):
    v = os.environ.get(name)
    if v:
        return v
    r = subprocess.run(["maxxing", "keys", "get", name], capture_output=True, text=True)
    return r.stdout.strip()


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


def history(limit=60):
    return list(reversed(_read()))[:limit]


def quota():
    day = time.strftime("%Y-%m-%d", time.gmtime())
    used = sum(i.get("neurons", 0) for i in _read() if time.strftime("%Y-%m-%d", time.gmtime(i["at"])) == day)
    left = max(0, DAILY_NEURONS - used)
    return {"used": round(used, 1), "limit": DAILY_NEURONS, "left": round(left, 1), "approx_images_left": int(left // neurons("flux", 4, 1024, 1024))}


def delete(item_id):
    items = _read()
    keep = [i for i in items if i["id"] != item_id]
    for i in items:
        if i["id"] == item_id:
            try:
                Path(i["path"]).unlink()
            except OSError:
                pass
            (STATE / "thumbs" / f"{item_id}.jpg").unlink(missing_ok=True)
    _write(keep)


def thumb(item_id):
    t = STATE / "thumbs" / f"{item_id}.jpg"
    if not t.exists():
        src = next((i["path"] for i in _read() if i["id"] == item_id), None)
        if not src or not Path(src).exists():
            return None
        t.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["convert", src, "-resize", "384x384>", "-quality", "75", str(t)], check=True)
    return "data:image/jpeg;base64," + base64.b64encode(t.read_bytes()).decode()


def generate(prompt, model="flux", steps=None, seed=None, width=1024, height=1024, out=None, topic=""):
    prompt = (prompt or "").strip()
    if not prompt:
        raise ValueError("prompt vide")
    m = MODELS.get(model)
    if not m:
        raise ValueError(f"modèle inconnu: {model} ({', '.join(MODELS)})")
    steps = max(1, min(m["max_steps"], int(steps or m["steps"])))
    width, height = (max(256, min(1024, int(width) // 8 * 8)), max(256, min(1024, int(height) // 8 * 8))) if m["sized"] else (1024, 1024)
    cost = neurons(model, steps, width, height)
    if quota()["left"] < cost:
        raise RuntimeError(f"quota gratuit du jour atteint (remise à zéro 00:00 UTC) : {quota()}")
    acc, tok = _secret("CLOUDFLARE_ACCOUNT_ID"), _secret("CLOUDFLARE_API_TOKEN")
    if not acc or not tok:
        raise RuntimeError("clés CLOUDFLARE_ACCOUNT_ID / CLOUDFLARE_API_TOKEN absentes (Settings -> Keys)")
    body = {"prompt": prompt}
    if m["sized"]:
        body.update(num_steps=steps, width=width, height=height)
    else:
        body["steps"] = steps
    if not m["seed"]:
        seed = None  # FLUX schnell on Workers AI refuses a seed
    if seed is not None:
        body["seed"] = int(seed)
    req = urllib.request.Request(f"https://api.cloudflare.com/client/v4/accounts/{acc}/ai/run/{m['id']}",
                                 json.dumps(body).encode(), {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"})
    data = None
    for attempt in range(3):
        try:
            resp = urllib.request.urlopen(req, timeout=100)
            raw = resp.read()
            if resp.headers.get_content_type().startswith("image/"):
                data = raw
            else:
                d = json.loads(raw)
                if not d.get("success"):
                    raise RuntimeError(str(d.get("errors"))[:300])
                data = base64.b64decode(d["result"]["image"])
            break
        except urllib.error.HTTPError as e:
            msg = e.read()[:200].decode(errors="replace")
            if e.code in (429, 500, 502, 503) and attempt < 2:
                time.sleep(3 * (attempt + 1))
                continue
            raise RuntimeError(f"Cloudflare {e.code}: {msg}")
    ext = "png" if data[:4] == b"\x89PNG" else "jpg"
    item_id = f"{int(time.time())}-{os.urandom(2).hex()}"
    if out:
        path = Path(out).expanduser().resolve()
    else:
        path = OUT_ROOT / time.strftime("%Y-%m") / f"{item_id}.{ext}"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    item = {"id": item_id, "at": time.time(), "prompt": prompt, "model": model, "steps": steps, "seed": seed,
            "w": width, "h": height, "path": str(path), "neurons": cost, "topic": topic}
    _write(_read() + [item])
    return item


def main():
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("prompt", nargs="?")
    a.add_argument("-o", "--out")
    a.add_argument("--model", default="flux", choices=list(MODELS))
    a.add_argument("--steps", type=int)
    a.add_argument("--seed", type=int)
    a.add_argument("--size", default="1024x1024", help="WxH, SDXL only (FLUX: always 1024x1024, no seed)")
    a.add_argument("--quota", action="store_true")
    a = a.parse_args()
    if a.quota or not a.prompt:
        print(json.dumps(quota()))
        return
    try:
        w, h = (int(x) for x in a.size.lower().split("x"))
        it = generate(a.prompt, a.model, a.steps, a.seed, w, h, a.out, os.path.basename(os.getcwd()))
    except Exception as e:
        sys.exit(f"Erreur: {e}")
    print(it["path"])
    print(f"({it['neurons']} neurons, reste ~{quota()['approx_images_left']} images aujourd'hui)", file=sys.stderr)


if __name__ == "__main__":
    main()
