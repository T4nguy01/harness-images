import importlib.util
from pathlib import Path

_F = Path(__file__).with_name("genimage.py")
_mods = {}


def _lib():
    """Load genimage.py again whenever the file changes (the server keeps modules in memory)."""
    key = _F.stat().st_mtime_ns
    if key not in _mods:
        spec = importlib.util.spec_from_file_location(f"genimage_{key}", _F)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        _mods.clear()
        _mods[key] = m
    return _mods[key]


def _status(g, query=None):
    q = query or {}
    return {"quota": g.quota(), "config": g.config(), "styles": list(g.STYLES), "ratios": list(g.RATIOS),
            "models": {k: {"label": v["label"], "sized": v["sized"], "seed": v["seed"], "img2img": bool(v.get("img2img"))} for k, v in g.MODELS.items()},
            "items": g.history(80, str(q.get("q", "")), str(q.get("fav", "")) == "1")}


def handle(ctx, method, path, query, body):
    g = _lib()
    g.STATE = Path(ctx["state_dir"])
    g.OUT_ROOT = Path(ctx["workspace"]) / "images"
    g.VAULT = ctx["secret"]
    b = body or {}
    if path == "status" and method == "GET":
        return _status(g, query)
    if path == "generate" and method == "POST":
        src = None
        if b.get("source"):
            src = next((i["path"] for i in g._read() if i["id"] == b["source"]), None)
        items = []
        try:
            for k in range(max(1, min(4, int(b.get("n") or 1)))):
                seed = b.get("seed")
                seed = None if seed in (None, "") else int(seed) + k
                items.append(g.generate(b.get("prompt"), b.get("model", "flux"), b.get("steps") or None, seed,
                                        b.get("width") or 1024, b.get("height") or 1024, topic="page", style=b.get("style") or None,
                                        ratio=b.get("ratio") or None, source=src, strength=float(b.get("strength") or 0.6), x2=bool(b.get("x2"))))
        except (ValueError, RuntimeError, OSError) as e:
            return 400, {"error": "failed", "message": str(e), "done": len(items)}
        return {"items": items, "quota": g.quota()}
    if path.split("/")[0] in ("thumb", "fav", "item", "upscale") and not g.valid_id(path.partition("/")[2]):
        return 400, {"error": "bad_id"}
    if path.startswith("thumb/") and method == "GET":
        t = g.thumb(path[6:])
        return {"src": t} if t else (404, {"error": "not_found"})
    if path.startswith("fav/") and method == "POST":
        g.set_fav(path[4:], b.get("fav", True))
        return {"ok": True}
    if path.startswith("item/") and method == "DELETE":
        g.delete(path[5:], force=str(query.get("force", "")) == "1")
        return _status(g)
    if path == "zip" and method == "POST":
        try:
            return {"path": g.make_zip(b.get("ids") or [])}
        except ValueError as e:
            return 400, {"error": "failed", "message": str(e)}
    if path.startswith("upscale/") and method == "POST":
        it = next((i for i in g._read() if i["id"] == path[8:]), None)
        if not it:
            return 404, {"error": "not_found"}
        return {"path": g.upscale(it["path"])}
    if path == "config" and method == "PUT":
        return {"config": g.set_config(b)}
    return 404, {"error": "not_found", "message": f"{method} {path}"}
