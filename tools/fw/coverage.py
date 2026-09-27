#!/usr/bin/env python3
"""Line coverage of the model modules from the gcov data of the host tests.

Runs after `host_tests.sh coverage` (a build with --coverage and the tests
executed): for every object of the code under test it calls `gcov`, reads
the `.gcov` files it writes and sums the lines executed against the lines
that could execute. Fails (exit code 1) when any module of
zephyr_app/src/model stays below the threshold, which is what CLAUDE.md
asks for: the tests are not done while a module is below it.

    python tools/fw/coverage.py [--build DIR] [--min 95]
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BUILD = ROOT / "zephyr_app" / "tests" / "host" / "build" / "host-cov"
MODEL_DIR = (ROOT / "zephyr_app" / "src" / "model").resolve()


def find_gcov() -> str:
    for cand in ("gcov", r"C:\ProgramData\mingw64\mingw64\bin\gcov.exe"):
        path = shutil.which(cand) or (cand if Path(cand).is_file() else None)
        if path:
            return path
    sys.exit("gcov not found: install the MinGW-w64 GCC of the host tests")


def parse_gcov(text: str) -> tuple[int, int, list[int]]:
    """(executed, executable, missed line numbers) of one .gcov file."""
    executed = executable = 0
    missed = []
    for line in text.splitlines():
        parts = line.split(":", 2)
        if len(parts) < 3:
            continue
        count, lineno = parts[0].strip(), parts[1].strip()
        if count in ("-",) or not lineno.isdigit():
            continue
        if count.startswith("#####") or count.startswith("====="):
            executable += 1
            missed.append(int(lineno))
        elif count.rstrip("*").isdigit():
            executable += 1
            executed += 1
    return executed, executable, missed


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--build", type=Path, default=DEFAULT_BUILD)
    ap.add_argument("--min", type=float, default=95.0)
    args = ap.parse_args()

    build = args.build.resolve()
    if not build.is_dir():
        sys.exit(f"build directory not found: {build}")
    gcov = find_gcov()

    per_file: dict[Path, tuple[int, int, set[int]]] = {}
    seen_objects = 0
    for gcda in build.rglob("*.gcda"):
        obj_dir = gcda.parent
        seen_objects += 1
        out_dir = build / "_gcov" / gcda.stem
        out_dir.mkdir(parents=True, exist_ok=True)
        subprocess.run([gcov, "-b", "-o", str(obj_dir), str(gcda)], cwd=out_dir,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        for gc in out_dir.glob("*.gcov"):
            text = gc.read_text(encoding="utf-8", errors="replace")
            m = re.search(r"^\s*-:\s*0:Source:(.*)$", text, re.M)
            if not m:
                continue
            src = Path(m.group(1).strip()).resolve()
            try:
                src.relative_to(MODEL_DIR)
            except ValueError:
                continue
            executed, executable, missed = parse_gcov(text)
            # the same source may be compiled into several test binaries:
            # a line counts as covered when any of them executed it
            prev = per_file.get(src)
            if prev is None:
                per_file[src] = (executed, executable, set(missed))
            else:
                per_file[src] = (max(prev[0], executed), max(prev[1], executable),
                                 prev[2] & set(missed))
    if seen_objects == 0:
        sys.exit("no .gcda in the build: run the tests of the coverage build first")
    if not per_file:
        sys.exit("no model module found in the gcov data")

    total_exec = total_lines = 0
    failed = []
    print(f"{'module':<32} {'lines':>6} {'run':>6} {'cover':>7}")
    for src in sorted(per_file):
        executed, executable, missed = per_file[src]
        covered = executable - len(missed)
        pct = 100.0 * covered / executable if executable else 100.0
        total_exec += covered
        total_lines += executable
        flag = "" if pct >= args.min else f"  <- below {args.min:g} %: lines {sorted(missed)[:12]}"
        print(f"{src.name:<32} {executable:>6} {covered:>6} {pct:>6.1f} %{flag}")
        if pct < args.min:
            failed.append(src.name)
    total = 100.0 * total_exec / total_lines if total_lines else 100.0
    print(f"{'total':<32} {total_lines:>6} {total_exec:>6} {total:>6.1f} %")
    if failed:
        print(f"below {args.min:g} %: {', '.join(failed)}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
