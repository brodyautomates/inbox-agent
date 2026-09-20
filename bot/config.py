"""
Paths, config, env file, logging. Everything lives under one folder:

    ~/.config/inbox-agent/
        config.json         your settings (copy config.example.json)
        env                 CLAUDE_CODE_OAUTH_TOKEN or ANTHROPIC_API_KEY, chmod 600
        client_secret.json  Google OAuth client, chmod 600
        token.json          Gmail login, chmod 600
        state.json          the bot's memory. Never edit while the bot runs.
        mode                one word: manual | assisted | autopilot
        PAUSED              stop switch. Make the file, nothing sends. Delete it, it carries on.
        bot.log, send.log

Override the folder with INBOX_AGENT_HOME.
"""

import json
import os
import time

HOME = os.path.expanduser(os.environ.get("INBOX_AGENT_HOME", "~/.config/inbox-agent"))
CONFIG = os.path.join(HOME, "config.json")
ENV = os.path.join(HOME, "env")
STATE = os.path.join(HOME, "state.json")
MODE_FILE = os.path.join(HOME, "mode")
PAUSE_FILE = os.path.join(HOME, "PAUSED")
LOG = os.path.join(HOME, "bot.log")

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROMPTS = os.path.join(REPO, "bot", "prompts")

DEFAULTS = {
    "gmail_address": "",
    "telegram_token": "",
    "allowed_user": 0,
    "mode": "manual",
    "autopilot_delay_minutes": 10,
    "poll_seconds": 120,
    "ceiling_amount": 5000,
    "currency_symbols": "$£€",
    "assisted_max_words": 40,
    "digest_hour": 8,
    "claude_backend": "code",
    "api_model": "claude-sonnet-5",
    "claude_binary": "",
    "playbook_path": os.path.join(REPO, "playbook", "SKILL.md"),
    "assisted_templates_path": os.path.join(REPO, "playbook", "assisted-templates.md"),
    "never_answer_keywords": [],
    "ignore_senders": [],
    "signoff_name": "",
}

_cache = {"mtime": None, "cfg": None}


def load():
    """Config with defaults filled in. Re-read when the file changes."""
    try:
        mtime = os.path.getmtime(CONFIG)
    except FileNotFoundError:
        raise SystemExit(f"Missing {CONFIG}. Run install.sh, or copy config.example.json there.")
    if _cache["mtime"] != mtime:
        with open(CONFIG) as f:
            user = json.load(f)
        cfg = dict(DEFAULTS)
        cfg.update({k: v for k, v in user.items() if v not in ("", None)})
        cfg["playbook_path"] = os.path.expanduser(cfg["playbook_path"])
        cfg["assisted_templates_path"] = os.path.expanduser(cfg["assisted_templates_path"])
        _cache.update(mtime=mtime, cfg=cfg)
    return _cache["cfg"]


def env_file():
    """KEY=VALUE lines from the env file, as a dict."""
    out = {}
    try:
        with open(ENV) as f:
            for ln in f:
                ln = ln.strip()
                if not ln or ln.startswith("#") or "=" not in ln:
                    continue
                k, v = ln.split("=", 1)
                out[k.strip()] = v.strip().strip('"').strip("'")
    except FileNotFoundError:
        pass
    return out


def paused():
    return os.path.exists(PAUSE_FILE)


def mode():
    """The mode file wins over config.json so you can switch from your phone."""
    try:
        with open(MODE_FILE) as f:
            m = f.read().strip().lower()
        if m in ("manual", "assisted", "autopilot"):
            return m
    except FileNotFoundError:
        pass
    return load().get("mode", "manual")


def set_mode(m):
    with open(MODE_FILE, "w") as f:
        f.write(m + "\n")


def prompt(name, **kw):
    """Load bot/prompts/<name>.md and fill {{placeholders}}."""
    with open(os.path.join(PROMPTS, f"{name}.md")) as f:
        text = f.read()
    for k, v in kw.items():
        text = text.replace("{{" + k + "}}", str(v))
    return text


def playbook():
    with open(load()["playbook_path"]) as f:
        return f.read()


def log(msg):
    os.makedirs(HOME, exist_ok=True)
    stamp = time.strftime("%Y-%m-%dT%H:%M:%S")
    with open(LOG, "a") as f:
        f.write(f"{stamp}\t{msg}\n")
