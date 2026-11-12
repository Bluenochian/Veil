#!/usr/bin/env python3
"""Check repository-local Markdown links and embedded image assets."""

from pathlib import Path
from urllib.parse import unquote
import re
import sys

ROOT = Path(__file__).resolve().parent.parent
MARKDOWN_LINK = re.compile(r"!?\[[^\]\n]+\]\(([^)\n]+)\)")
HTML_LINK = re.compile(r"(?:href|src)=['\"]([^'\"]+)['\"]")
REMOTE = ("http://", "https://", "mailto:", "data:")


def links_in(text):
    for match in MARKDOWN_LINK.finditer(text):
        yield match.group(1).strip('<>').split(' "', 1)[0]
    for match in HTML_LINK.finditer(text):
        yield match.group(1)


def check():
    markdown = [ROOT / "README.md", *sorted((ROOT / "docs").glob("*.md"))]
    problems = []
    count = 0
    for source in markdown:
        body = source.read_text(encoding="utf-8")
        if body.count("```") % 2:
            problems.append(f"{source.relative_to(ROOT)}: unpaired fenced code block")
        for link in links_in(body):
            if not link or link.startswith(REMOTE):
                continue
            file_part = unquote(link.split("#", 1)[0])
            if not file_part:
                continue
            count += 1
            target = (source.parent / file_part).resolve()
            if not target.is_relative_to(ROOT):
                problems.append(f"{source.relative_to(ROOT)}: outside repository: {link}")
            elif not target.is_file():
                problems.append(f"{source.relative_to(ROOT)}: missing target: {link}")
    if problems:
        for problem in problems:
            print(problem, file=sys.stderr)
        return 1
    print(f"Documentation links OK: {count} local targets across {len(markdown)} Markdown files")
    return 0


if __name__ == "__main__":
    raise SystemExit(check())
