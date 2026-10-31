"""CLI entry point for a local dashboard or a reproducible headless run."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .engine import Engine
from .models import Config


def main():
    parser = argparse.ArgumentParser(description="GNSS-R / remote-sensing swarm laboratory")
    parser.add_argument("--nodes", type=int, choices=range(3, 41), metavar="3..40", default=6)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--dt", type=float, default=2)
    parser.add_argument("--no-auto", action="store_true")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--steps", type=int, default=120)
    parser.add_argument("--export", type=Path)
    args = parser.parse_args()
    if not .25 <= args.dt <= 5 or not 0 <= args.seed < 2**31 or not 1 <= args.steps <= 100000:
        parser.error("dt must be .25..5, seed 0..2^31-1, and steps 1..100000")
    c = Config(nodes=args.nodes, seed=args.seed, dt_s=args.dt, auto_tasks=not args.no_auto)
    if args.headless:
        engine = Engine(c)
        for _ in range(args.steps):
            engine.step()
            engine.validate()
        snapshot = engine.snapshot()
        print(json.dumps(snapshot["metrics"], indent=2))
        if args.export:
            args.export.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
        return
    import uvicorn
    from .api import create_app
    print(f"Open http://{args.host}:{args.port} (starts paused; press Run)")
    uvicorn.run(create_app(c), host=args.host, port=args.port, workers=1)


if __name__ == "__main__":
    main()
