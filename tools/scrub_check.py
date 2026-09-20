#!/usr/bin/env python3
"""
Refuse to publish personal data.

    python3 tools/scrub_check.py            scan the repo, exit 1 on any hit
    python3 tools/scrub_check.py --staged   scan only files staged in git (use as a pre-commit hook)

Built-in patterns catch secrets and identifiers of any kind. A private
denylist adds YOUR names, addresses, brands and numbers. It lives OUTSIDE
the repo so it is never published itself:

    ~/.config/inbox-agent/denylist.txt      one term per line, case-insensitive
    or  SCRUB_DENYLIST=/path/to/file

Install as a hook:
    printf '#!/bin/sh\\nexec python3 tools/scrub_check.py --staged\\n' > .git/hooks/pre-commit
    chmod +x .git/hooks/pre-commit
"""

import os
import re
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DENY = os.path.expanduser(os.environ.get("SCRUB_DENYLIST", "~/.config/inbox-agent/denylist.txt"))
SKIP_DIRS = {".git", "venv", "__pycache__", "node_modules"}
TEXT_EXT = {".py", ".md", ".json", ".sh", ".txt", ".service", ".plist", ".example", ".yml", ".yaml", ""}
ALLOW = ("example.com", "brodyautomates/inbox-agent", "github.com/brodyautomates")

BUILTIN = [
    ("telegram bot token", re.compile(r"\b\d{8,10}:[A-Za-z0-9_-]{35}\b")),
    ("anthropic key", re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}")),
    ("openai-style key", re.compile(r"\bsk-[A-Za-z0-9]{32,}\b")),
    ("google oauth token", re.compile(r"\bya29\.[A-Za-z0-9_-]{30,}")),
    ("google client secret", re.compile(r"GOCSPX-[A-Za-z0-9_-]{20,}")),
    ("github token", re.compile(r"\b(gh[pousr]_[A-Za-z0-9]{30,})\b")),
    ("claude oauth token", re.compile(r"sk-ant-oat[A-Za-z0-9_-]{10,}")),
    ("private key block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("tailscale / private ip", re.compile(r"\b(100\.(6[4-9]|[7-9]\d|1[01]\d|12[0-7])\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3}|10\.\d{1,3}\.\d{1,3}\.\d{1,3})\b")),
    ("public ipv4", re.compile(r"\b(?!0\.)(?!127\.)(?!255\.)\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b")),
    ("real email address", re.compile(r"\b[A-Za-z0-9._%+-]+@(?![A-Za-z0-9.-]*(?:example\.(?:com|org|net)|\.example|\.test|\.invalid)\b)[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    ("home path with username", re.compile(r"/(?:Users|home)/(?!YOU\b|agent\b|user\b)[A-Za-z0-9_.-]+")),
    ("telegram numeric id", re.compile(r"\b(?<![:\d])[1-9]\d{8,9}\b(?!:)")),
]


def files_to_scan(staged):
    if staged:
        out = subprocess.run(["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
                             capture_output=True, text=True, cwd=REPO).stdout.split()
        return [os.path.join(REPO, p) for p in out]
    paths = []
    for root, dirs, files in os.walk(REPO):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in files:
            if os.path.splitext(f)[1] in TEXT_EXT:
                paths.append(os.path.join(root, f))
    return paths


def load_denylist():
    terms = []
    if os.path.exists(DENY):
        with open(DENY) as f:
            for ln in f:
                ln = ln.strip()
                if ln and not ln.startswith("#"):
                    terms.append(ln)
    return terms


def main():
    staged = "--staged" in sys.argv
    deny = load_denylist()
    if not deny:
        print(f"note: no private denylist at {DENY}; only built-in patterns will run")
    hits = 0
    for path in files_to_scan(staged):
        rel = os.path.relpath(path, REPO)
        if rel == os.path.relpath(__file__, REPO):
            continue
        try:
            text = open(path, errors="replace").read()
        except (OSError, UnicodeDecodeError):
            continue
        for n, line in enumerate(text.splitlines(), 1):
            probe = line
            for a in ALLOW:
                probe = probe.replace(a, "")
            for label, rx in BUILTIN:
                if rx.search(probe):
                    # allow the documented placeholder ids in examples
                    if label == "telegram numeric id" and "123456789" in probe:
                        continue
                    print(f"{rel}:{n}: [{label}] {line.strip()[:110]}")
                    hits += 1
            low = probe.lower()
            for term in deny:
                if term.lower() in low:
                    print(f"{rel}:{n}: [denylist: {term}] {line.strip()[:110]}")
                    hits += 1
    if hits:
        print(f"\n{hits} hit(s). Nothing was published. Fix and re-run.")
        sys.exit(1)
    print("clean")


if __name__ == "__main__":
    main()
