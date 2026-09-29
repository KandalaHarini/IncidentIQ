"""Retain incidents into memory (Hindsight, or local fallback).

Usage:
  python -m scripts.seed_memory                     # seed data/seed_incidents.json (once)
  python -m scripts.seed_memory data/more.json       # seed a different file
  python -m scripts.seed_memory --force               # re-seed even if already done

Idempotent: after a file is seeded once, a marker is written to
data/.seeded so re-running the same command does not retain duplicates.
Pass --force to override that.
"""
import json, sys
from pathlib import Path
from core.agent import memory

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
MARKER = DATA_DIR / ".seeded"

args = [a for a in sys.argv[1:] if a != "--force"]
force = "--force" in sys.argv
path = Path(args[0]) if args else DATA_DIR / "seed_incidents.json"

done = json.loads(MARKER.read_text()) if MARKER.exists() else []
key = str(path)

if key in done and not force:
    print(f"{path} was already seeded into '{memory.backend}'. Skipping to avoid duplicates.")
    print("Use --force to re-seed anyway.")
    sys.exit(0)

for inc in json.loads(path.read_text()):
    ok = memory.retain({**inc, "status": "resolved"})
    print("retained", inc["id"], "->", memory.backend, "(hindsight)" if ok else "(local fallback)")

if key not in done:
    done.append(key)
MARKER.write_text(json.dumps(done, indent=2))
print(f"Done. Marked {path} as seeded.")
