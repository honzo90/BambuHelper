#!/usr/bin/env python3
"""Measure how much of the fork is written by LLM agents (see AGENTS.md "Attribution").

Every non-merge commit is classified from its message:
  llm      - trailer `AI-Assisted: <model>` or `Co-Authored-By:` naming an AI model
  human    - trailer `AI-Assisted: none`
  upstream - cherry-pick of a commit from upstream (origin/main = Keralots); cherry-picks
             of fork commits are classified by the original commit
  unknown  - no attribution (commits before the rule, or made outside the hook)

Usage:
  python3 -B scripts/ai_share.py                  # report since the 4.3B fork base
  python3 -B scripts/ai_share.py --since 2026-11-01
  python3 -B scripts/ai_share.py --list           # one line per commit
  python3 -B scripts/ai_share.py --check-msg FILE # used by .githooks/commit-msg
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FORK_BASE = "23347fb"  # upstream v3.9.0, start of the 4.3B port (docs/UPSTREAM.md)
CATEGORIES = ("llm", "human", "upstream", "unknown")

AI_NAMES = re.compile(
    r"claude|anthropic|gpt|openai|codex|copilot|gemini|gemma|qwen|llama|mistral|devstral|deepseek",
    re.I,
)
AI_ASSISTED = re.compile(r"^AI-Assisted:[ \t]*(.+?)[ \t]*$", re.I | re.M)
CO_AUTHOR = re.compile(r"^Co-Authored-By:[ \t]*(.+?)[ \t]*$", re.I | re.M)
CHERRY_PICK = re.compile(r"^\(cherry picked from commit ([0-9a-f]{7,40})\)$", re.M)
UPSTREAM_REF = "origin/main"  # Keralots/BambuHelper


def is_upstream(sha):
    try:
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", sha, UPSTREAM_REF],
            cwd=ROOT,
            capture_output=True,
            check=True,
        )
        return True
    except (subprocess.CalledProcessError, OSError):
        return False


def original_message(sha):
    try:
        return git("log", "-1", "--format=%B", sha)
    except subprocess.CalledProcessError:
        return None


def classify(message):
    """Return (category, model) for a commit message."""
    pick = CHERRY_PICK.search(message)
    if pick:
        if is_upstream(pick.group(1)):
            return "upstream", ""
        original = original_message(pick.group(1))
        if original is not None and not CHERRY_PICK.search(original):
            return classify(original)
    m = AI_ASSISTED.search(message)
    if m:
        value = m.group(1)
        return ("human", "") if value.lower() == "none" else ("llm", value)
    for co_author in CO_AUTHOR.findall(message):
        if AI_NAMES.search(co_author):
            return "llm", re.sub(r"\s*<[^>]*>", "", co_author)
    return "unknown", ""


def git(*args):
    return subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout


def commits(since):
    """Yield (sha, date, message, added, deleted) for non-merge commits after FORK_BASE."""
    args = ["log", "--no-merges", "--format=%x00%h%x01%cs%x01%B%x02", "--numstat"]
    if since:
        # A bare date makes git count from the current time of day; start at midnight.
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", since):
            since += " 00:00"
        args.append(f"--since={since}")
    out = git(*args, f"{FORK_BASE}..HEAD")
    for record in out.split("\x00")[1:]:
        head, _, stats = record.partition("\x02")
        sha, date, message = head.split("\x01", 2)
        added = deleted = 0
        for line in stats.strip().splitlines():
            a, d, _ = line.split("\t", 2)
            if a != "-":
                added, deleted = added + int(a), deleted + int(d)
        yield sha, date, message, added, deleted


def report(since, listing):
    totals = {c: [0, 0] for c in CATEGORIES}
    models = {}
    for sha, date, message, added, _ in commits(since):
        category, model = classify(message)
        totals[category][0] += 1
        totals[category][1] += added
        if model:
            models[model] = models.get(model, 0) + 1
        if listing:
            subject = message.strip().splitlines()[0][:70]
            print(f"{sha} {date} {category:8} {model[:24]:24} {subject}")
    if listing:
        print()

    fork = {c: totals[c] for c in ("llm", "human", "unknown")}
    n = sum(v[0] for v in fork.values()) or 1
    lines = sum(v[1] for v in fork.values()) or 1
    print(f"Fork commits since {since or FORK_BASE} (merges excluded):")
    print(f"{'category':10} {'commits':>8} {'share':>7} {'added lines':>12} {'share':>7}")
    for c, (count, added) in fork.items():
        print(f"{c:10} {count:8} {count / n:7.0%} {added:12} {added / lines:7.0%}")
    print(f"{'upstream':10} {totals['upstream'][0]:8}   (cherry-picks, not counted above)")
    if models:
        print("LLM commits by model: " + ", ".join(f"{m} {k}" for m, k in sorted(models.items())))


def check_message(path):
    """commit-msg hook: refuse commits without attribution."""
    message = Path(path).read_text()
    message = "\n".join(l for l in message.splitlines() if not l.startswith("#"))
    if (ROOT / ".git" / "MERGE_HEAD").exists() or classify(message)[0] != "unknown":
        return 0
    print(
        "commit refused: add an attribution trailer (AGENTS.md, Attribution):\n"
        "  AI-Assisted: <model>   (e.g. Claude Opus 5.5, qwen3.6:35b)\n"
        "  AI-Assisted: none      (written by a human only)",
        file=sys.stderr,
    )
    return 1


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--since", help="only commits after this date (YYYY-MM-DD)")
    parser.add_argument("--list", action="store_true", help="print every commit")
    parser.add_argument("--check-msg", metavar="FILE", help="validate a commit message file")
    args = parser.parse_args()
    if args.check_msg:
        return check_message(args.check_msg)
    report(args.since, args.list)
    return 0


if __name__ == "__main__":
    sys.exit(main())
