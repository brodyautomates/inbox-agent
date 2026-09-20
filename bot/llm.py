"""
One function, two backends.

    ask(prompt) -> str | None

backend "code"  runs Claude Code headless:  claude -p "<prompt>" --max-turns 1
                auth: CLAUDE_CODE_OAUTH_TOKEN in ~/.config/inbox-agent/env
                (make it with `claude setup-token` on a machine with a browser)

backend "api"   calls the Anthropic Messages API directly with urllib.
                auth: ANTHROPIC_API_KEY in the same env file

A global outage (auth expired, usage limit, rate limit) freezes the pipeline
for ten minutes instead of burning retries. Nothing is marked as seen while
that holds, so no email is lost during an outage.
"""

import json
import os
import shutil
import subprocess
import time
import urllib.request

from . import config as C

OUTAGE = {"at": 0.0, "why": "", "recovered": False}
OUTAGE_HOLD = 600


def down():
    return time.time() - OUTAGE["at"] < OUTAGE_HOLD


def _mark_outage(err):
    low = err.lower()
    if any(k in low for k in ("authenticate", "oauth", "login", "usage limit",
                              "rate limit", "401", "429", "overloaded", "credit")):
        OUTAGE["at"] = time.time()
        OUTAGE["why"] = err[:200]


def _claude_binary():
    cfg = C.load()
    explicit = cfg.get("claude_binary")
    if explicit and os.path.exists(os.path.expanduser(explicit)):
        return os.path.expanduser(explicit)
    for p in ("~/.local/bin/claude", "/usr/local/bin/claude", "/opt/homebrew/bin/claude"):
        if os.path.exists(os.path.expanduser(p)):
            return os.path.expanduser(p)
    return shutil.which("claude")


def _ask_code(prompt, timeout):
    binary = _claude_binary()
    if not binary:
        C.log("claude binary not found; set claude_binary in config.json")
        _mark_outage("login: claude not installed")
        return None
    try:
        r = subprocess.run([binary, "-p", prompt, "--max-turns", "1"],
                           capture_output=True, text=True, timeout=timeout,
                           env={**os.environ, **C.env_file()})
    except subprocess.TimeoutExpired:
        C.log(f"claude timeout after {timeout}s")
        return None
    if r.returncode != 0:
        err = (r.stderr or r.stdout or "").strip()
        C.log(f"claude rc={r.returncode} err={err[:300]}")
        _mark_outage(err)
        return None
    if OUTAGE["at"]:
        OUTAGE["recovered"] = True
    return r.stdout.strip()


def _ask_api(prompt, timeout):
    cfg = C.load()
    key = C.env_file().get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        C.log("ANTHROPIC_API_KEY missing from env file")
        _mark_outage("authenticate: no api key")
        return None
    body = json.dumps({
        "model": cfg.get("api_model", "claude-sonnet-5"),
        "max_tokens": 1500,
        "messages": [{"role": "user", "content": prompt}],
    }).encode()
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages", data=body, method="POST",
        headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                 "content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.load(r)
    except urllib.error.HTTPError as e:
        err = f"{e.code} {e.read().decode(errors='replace')[:200]}"
        C.log(f"api error {err}")
        _mark_outage(err)
        return None
    except Exception as e:
        C.log(f"api error {e!r}")
        return None
    if OUTAGE["at"]:
        OUTAGE["recovered"] = True
    return "".join(b.get("text", "") for b in data.get("content", [])).strip()


def ask(prompt, timeout=180):
    """Send one prompt, get one text answer. None on failure."""
    if down():
        return None
    backend = C.load().get("claude_backend", "code")
    if backend == "api":
        return _ask_api(prompt, timeout)
    return _ask_code(prompt, timeout)


def healthy():
    """A one-word round trip. Used by the doctor and the startup check."""
    out = ask("Reply with the single word OK and nothing else.", timeout=90)
    return bool(out) and "OK" in out.upper()
