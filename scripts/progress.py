"""Stub burn-down by layer. Run it whenever you want to know where you are.

    python scripts/progress.py             # summary
    python scripts/progress.py --detail    # every remaining function, by file

A function counts as DONE when its body no longer raises NotImplementedError.
That is a crude measure and deliberately so: it cannot be gamed by writing a
docstring, and it needs no bookkeeping you have to remember to update.

The layer order below is the build order in docs/ROADMAP.md, because the
dependency chain is real -- features cannot be correct before ingestion is, and
no model means anything before the splits are temporal.
"""

from __future__ import annotations

import argparse
import ast
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# (label, path prefix, roadmap phase)
LAYERS: list[tuple[str, str, str]] = [
    ("L1  ingest", "src/cvm/ingest/", "1"),
    ("L2  synthesis", "src/cvm/synthesis/", "2"),
    ("L3  features", "src/cvm/features/", "3"),
    ("L4  M1 churn", "src/cvm/models/m1_churn/", "4"),
    ("L4  M2 value", "src/cvm/models/m2_value/", "5"),
    ("L4  M3 uplift", "src/cvm/models/m3_uplift/", "6"),
    ("L4  M4 advance", "src/cvm/models/m4_advance/", "7"),
    ("L4  registry", "src/cvm/models/registry.py", "8"),
    ("L5  decision", "src/cvm/decision/", "8"),
    ("L6  api", "src/cvm/api/", "done"),
    ("    utils", "src/cvm/utils/", "any"),
    ("    config + cli", "src/cvm/c", "done"),
]


def is_stub(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    return any(
        isinstance(node, ast.Raise)
        and isinstance(node.exc, ast.Call)
        and getattr(node.exc.func, "id", "") == "NotImplementedError"
        for node in ast.walk(fn)
    )


def tracked_python() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", "src/cvm"], cwd=ROOT, capture_output=True, text=True, check=True
    )
    return [f for f in out.stdout.splitlines() if f.endswith(".py")]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--detail", action="store_true", help="List every remaining function.")
    args = ap.parse_args()

    files = tracked_python()
    remaining: dict[str, list[str]] = {}
    totals = {"stub": 0, "done": 0}

    print(f"\n{'LAYER':<18}{'LEFT':>5}{'DONE':>6}  {'':<22}PHASE")
    print("-" * 60)

    # Only the FIRST incomplete layer in build order gets the arrow. The chain
    # is serial, so more than one "next" is a lie about what you can work on.
    flagged = False
    for label, prefix, phase in LAYERS:
        stub = done = 0
        for f in files:
            if not f.startswith(prefix):
                continue
            tree = ast.parse((ROOT / f).read_text(encoding="utf-8"))
            for fn in ast.walk(tree):
                if not isinstance(fn, ast.FunctionDef | ast.AsyncFunctionDef):
                    continue
                if is_stub(fn):
                    stub += 1
                    remaining.setdefault(f, []).append(fn.name)
                else:
                    done += 1

        totals["stub"] += stub
        totals["done"] += done
        pct = 100 * done // max(1, stub + done)
        filled = round(20 * done / max(1, stub + done))
        bar = "#" * filled + "." * (20 - filled)
        flag = ""
        if stub and phase not in {"done", "any"} and not flagged:
            flag, flagged = "  <-- next", True
        print(f"{label:<18}{stub:>5}{done:>6}  {bar} {pct:>3}%  {phase}{flag}")

    total = totals["stub"] + totals["done"]
    pct = 100 * totals["done"] // max(1, total)
    print("-" * 60)
    print(f"{'TOTAL':<18}{totals['stub']:>5}{totals['done']:>6}  {pct}% implemented\n")

    if args.detail:
        for f in sorted(remaining):
            print(f"{f}")
            for name in remaining[f]:
                print(f"    {name}")
        print()

    # The "next" layer is the first incomplete one in build order. Printing it
    # is the whole point: the chain is serial, so there is only ever one right
    # answer to "what should I do now".
    for label, prefix, phase in LAYERS:
        if phase in {"done", "any"}:
            continue
        if any(f.startswith(prefix) and f in remaining for f in files):
            print(f"Next: phase {phase} -- {label.strip()}.  See docs/ROADMAP.md#phase-{phase}")
            break
    else:
        print("Every layer is implemented. Run the full pipeline and the demo dry-run.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
