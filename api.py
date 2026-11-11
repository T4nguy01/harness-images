import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import genimage as g


def handle(ctx, method, path, query, body):
    g.STATE = Path(ctx["state_dir"])
    g.OUT_ROOT = Path(ctx["workspace"]) / "images"
    if path == "status" and method == "GET":
        return {"quota": g.quota(), "models": {k: {"label": v["label"], "sized": v["sized"], "seed": v["seed"], "steps": v["steps"], "max_steps": v["max_steps"]} for k, v in g.MODELS.items()},
                "items": g.history()}
    if path == "generate" and method == "POST":
        b = body or {}
        try:
            it = g.generate(b.get("prompt"), b.get("model", "flux"), b.get("steps") or None, b.get("seed") if b.get("seed") not in (None, "") else None,
                            b.get("width") or 1024, b.get("height") or 1024, topic="page")
        except (ValueError, RuntimeError) as e:
            return 400, {"error": "failed", "message": str(e)}
        return {"item": it, "quota": g.quota()}
    if path.startswith("thumb/") and method == "GET":
        t = g.thumb(path[6:])
        return {"src": t} if t else (404, {"error": "not_found"})
    if path.startswith("item/") and method == "DELETE":
        g.delete(path[5:])
        return {"quota": g.quota(), "items": g.history()}
    return 404, {"error": "not_found", "message": f"{method} {path}"}
