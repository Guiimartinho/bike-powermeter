#!/usr/bin/env python3
"""Checks the relative links of the project Markdown files.

For every [text](target) that is not an external URL, checks that the target
file or directory exists and, when the link has a #fragment pointing into a
Markdown file, that a heading with that GitHub anchor exists.

Usage: python tools/docs/links_check.py [ROOT]
Exit status is 1 when a link is broken.
"""

import pathlib
import re
import sys
import unicodedata
from urllib.parse import unquote

# Upstream stravaV10 material (legacy/, libraries/, tools/) keeps its own docs;
# docs/historico/ holds superseded documents kept as written.
SKIP_DIRS = {".git", "node_modules", "Lib", "Scripts", "legacy", "libraries", "tools", "hardware", "historico"}
# Project files that live inside skipped folders.
OWN_FILES = {"legacy/README.md", "docs/historico/README.md"}
LINK = re.compile(r"(?<!!)\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
IMAGE = re.compile(r"!\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(.*?)\s*#*\s*$")
FENCE = re.compile(r"^\s*(`{3,}|~{3,})")


def github_anchor(title: str) -> str:
    text = re.sub(r"`([^`]*)`", r"\1", title)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = text.strip().lower()
    kept = []
    for char in text:
        category = unicodedata.category(char)
        if char in " -_" or category[0] in ("L", "N"):
            kept.append(char)
    return "".join(kept).replace(" ", "-")


def anchors_of(path: pathlib.Path) -> set:
    anchors = set()
    seen = {}
    fenced = None
    for line in path.read_text(encoding="utf-8").splitlines():
        fence = FENCE.match(line)
        if fence:
            fenced = None if fenced and line.strip().startswith(fenced) else (fenced or fence.group(1))
            continue
        if fenced:
            continue
        heading = HEADING.match(line)
        if heading:
            base = github_anchor(heading.group(1))
            count = seen.get(base, 0)
            anchors.add(base if count == 0 else f"{base}-{count}")
            seen[base] = count + 1
    return anchors


def markdown_files(root: pathlib.Path):
    for path in sorted(root.rglob("*.md")):
        parts = path.relative_to(root).parts
        if path.relative_to(root).as_posix() not in OWN_FILES and (
                SKIP_DIRS.intersection(parts) or any(p.startswith("build") for p in parts[:-1])):
            continue
        yield path


def main() -> int:
    root = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else pathlib.Path(__file__).resolve().parents[2]).resolve()
    cache = {}
    broken = 0
    checked = 0
    for md in markdown_files(root):
        fenced = None
        for number, line in enumerate(md.read_text(encoding="utf-8").splitlines(), start=1):
            fence = FENCE.match(line)
            if fence:
                fenced = None if fenced and line.strip().startswith(fenced) else (fenced or fence.group(1))
                continue
            if fenced:
                continue
            line_without_code = re.sub(r"`[^`]*`", "", line)
            for target in LINK.findall(line_without_code) + IMAGE.findall(line_without_code):
                if re.match(r"^[a-z][a-z0-9+.-]*:", target) or target.startswith("//"):
                    continue
                checked += 1
                file_part, _, fragment = target.partition("#")
                destination = md if not file_part else (md.parent / unquote(file_part)).resolve()
                where = f"{md.relative_to(root).as_posix()}:{number}"
                if not destination.exists():
                    print(f"{where}: missing target {target}")
                    broken += 1
                    continue
                if fragment and destination.is_file() and destination.suffix == ".md":
                    if destination not in cache:
                        cache[destination] = anchors_of(destination)
                    if unquote(fragment).lower() not in cache[destination]:
                        print(f"{where}: missing anchor #{fragment} in {destination.relative_to(root).as_posix()}")
                        broken += 1
    print(f"links checked: {checked}, broken: {broken}")
    return 1 if broken else 0


if __name__ == "__main__":
    sys.exit(main())
