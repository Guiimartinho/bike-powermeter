#!/usr/bin/env python3
"""Checks the Mermaid diagrams of the project documentation.

Extracts every ```mermaid block of the Markdown files to OUT as
<path>__L<line>.mmd, flags fenced code blocks that look like plain-text
diagrams (box drawing characters, ASCII boxes and arrows), which the
documentation standard does not allow, and renders each diagram with
mermaid-cli (mmdc) to prove that it parses.

mermaid-cli is looked up in this order: the MMDC environment variable (path to
cli.js or to an mmdc executable), `mmdc` on PATH, then the npx cache
(%LOCALAPPDATA%/npm-cache/_npx/*/node_modules/@mermaid-js/mermaid-cli).
Nothing is installed by this script. PUPPETEER_CONFIG, when set, is passed to
mmdc as its puppeteer configuration file (-p).

Usage: python tools/docs/mermaid_check.py [--no-render] [ROOT] [OUT]
       (defaults: the repository root and build/docs/mermaid)
Exit status is 1 when a diagram fails to render or a plain-text diagram is
suspected.
"""

import concurrent.futures
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys

# Upstream stravaV10 material (legacy/, libraries/, tools/) keeps its own docs;
# docs/historico/ holds superseded documents kept as written.
SKIP_DIRS = {".git", "node_modules", "Lib", "Scripts", "legacy", "libraries", "tools", "hardware", "historico"}
# Project files that live inside skipped folders.
OWN_FILES = {"legacy/README.md", "docs/historico/README.md"}
FENCE = re.compile(r"^\s*(`{3,}|~{3,})\s*([\w+-]*)")
PLAIN_DIAGRAM = re.compile(r"[─-╿]|[←-⇿]|-->|<--|\+--|--\+|\+=+\+|^\s*\|.*\|\s*$")
WORKERS = 4


def markdown_files(root: pathlib.Path):
    for path in sorted(root.rglob("*.md")):
        parts = path.relative_to(root).parts
        if path.relative_to(root).as_posix() not in OWN_FILES and (
                SKIP_DIRS.intersection(parts) or any(p.startswith("build") for p in parts[:-1])):
            continue
        yield path


def find_mmdc():
    """Returns the command prefix that runs mermaid-cli, or None."""
    env = os.environ.get("MMDC")
    if env:
        return ["node", env] if env.endswith(".js") else [env]
    on_path = shutil.which("mmdc")
    if on_path:
        return [on_path]
    cache = pathlib.Path(os.environ.get("LOCALAPPDATA", "")) / "npm-cache" / "_npx"
    candidates = []
    for package in cache.glob("*/node_modules/@mermaid-js/mermaid-cli/package.json"):
        try:
            meta = json.loads(package.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        version = tuple(int(n) for n in re.findall(r"\d+", meta.get("version", "0"))[:3])
        candidates.append((version, package.parent / "src" / "cli.js"))
    if candidates and shutil.which("node"):
        return ["node", str(max(candidates)[1])]
    return None


def extract(root: pathlib.Path, out: pathlib.Path):
    diagrams, suspects = [], []
    for md in markdown_files(root):
        rel = md.relative_to(root).as_posix()
        lines = md.read_text(encoding="utf-8").splitlines()
        i = 0
        while i < len(lines):
            opening = FENCE.match(lines[i])
            if not opening:
                i += 1
                continue
            marker, lang = opening.group(1), opening.group(2).lower()
            end = i + 1
            while end < len(lines) and not lines[end].strip().startswith(marker):
                end += 1
            body = lines[i + 1:end]
            if lang == "mermaid":
                # No leading dot: shell globs skip hidden files (.claude/skills).
                name = rel.replace("/", "__").replace(" ", "_").lstrip(".") + f"__L{i + 2}.mmd"
                target = out / name
                target.write_text("\n".join(body) + "\n", encoding="utf-8")
                diagrams.append((f"{rel}:{i + 2}", target))
            elif lang in ("", "text", "txt", "plain") and sum(bool(PLAIN_DIAGRAM.search(l)) for l in body) >= 2:
                suspects.append(f"{rel}:{i + 1}")
            i = end + 1
    return diagrams, suspects


def render(mmdc, source: pathlib.Path):
    target = source.with_suffix(".svg")
    extra = []
    # CI runners need Chrome flags such as --no-sandbox: PUPPETEER_CONFIG
    # points to a puppeteer JSON config handed to mmdc with -p.
    if os.environ.get("PUPPETEER_CONFIG"):
        extra = ["-p", os.environ["PUPPETEER_CONFIG"]]
    result = subprocess.run(mmdc + extra + ["-q", "-i", str(source), "-o", str(target)],
                            capture_output=True, text=True, encoding="utf-8", errors="replace")
    ok = result.returncode == 0 and target.exists() and "Error" not in result.stderr
    detail = [l for l in (result.stderr + result.stdout).splitlines() if l.strip() and not l.lstrip().startswith("at ")]
    return ok, detail[:8]


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    no_render = "--no-render" in sys.argv
    root = pathlib.Path(args[0] if args else pathlib.Path(__file__).resolve().parents[2]).resolve()
    out = pathlib.Path(args[1] if len(args) > 1 else root / "build" / "docs" / "mermaid")
    out.mkdir(parents=True, exist_ok=True)
    for old in list(out.glob("*.mmd")) + list(out.glob("*.svg")):
        old.unlink()

    diagrams, suspects = extract(root, out)
    print(f"{len(diagrams)} Mermaid diagrams extracted to {out}")
    for suspect in suspects:
        print(f"plain-text diagram suspected: {suspect}")

    failed = 0
    if not no_render and diagrams:
        mmdc = find_mmdc()
        if mmdc is None:
            print("mermaid-cli not found: set MMDC or run once `npx -y @mermaid-js/mermaid-cli -V`")
            return 1
        with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as pool:
            results = list(pool.map(lambda d: render(mmdc, d[1]), diagrams))
        for (where, _), (ok, detail) in zip(diagrams, results):
            if not ok:
                failed += 1
                print(f"FAIL {where}")
                for line in detail:
                    print(f"    {line}")
        print(f"rendered {len(diagrams) - failed} of {len(diagrams)}")
    return 1 if failed or suspects else 0


if __name__ == "__main__":
    sys.exit(main())
