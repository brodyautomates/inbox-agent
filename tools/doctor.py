#!/usr/bin/env python3
"""
Pre-flight. Run after install and before you trust the service.

    venv/bin/python3 tools/doctor.py

Every line is PASS, WARN or FAIL with the fix next to it.
"""

import json
import os
import re
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
os.chdir(REPO)

from bot import config as C  # noqa: E402

FAILS = 0


def report(ok, label, fix="", warn=False):
    global FAILS
    tag = "PASS" if ok else ("WARN" if warn else "FAIL")
    if not ok and not warn:
        FAILS += 1
    line = f"[{tag}] {label}"
    if not ok and fix:
        line += f"\n       fix: {fix}"
    print(line)


def main():
    print(f"config folder: {C.HOME}\n")

    # config
    try:
        cfg = C.load()
    except SystemExit as e:
        report(False, "config.json present", str(e))
        return finish()
    report(bool(cfg["gmail_address"]) and not cfg["gmail_address"].endswith("@example.com"),
           "gmail_address set", "edit config.json")
    report(bool(cfg["telegram_token"]) and not cfg["telegram_token"].startswith("123456789:"),
           "telegram_token set", "message @BotFather, /newbot, paste the token")
    report(isinstance(cfg["allowed_user"], int) and cfg["allowed_user"] not in (0, 123456789),
           "allowed_user set to your own Telegram id",
           "message your bot once, then: curl -s https://api.telegram.org/bot<TOKEN>/getUpdates | grep -o '\"id\":[0-9]*' | head -1")
    report(bool(cfg.get("signoff_name")) and cfg["signoff_name"] != "Your Name",
           "signoff_name set", "edit config.json")
    report(cfg["mode"] in ("manual", "assisted", "autopilot"), "mode valid")
    report(C.mode() == "manual", "mode is manual for a first run", "echo manual > ~/.config/inbox-agent/mode", warn=True)

    # secrets
    env = C.env_file()
    if cfg["claude_backend"] == "api":
        report(bool(env.get("ANTHROPIC_API_KEY")), "ANTHROPIC_API_KEY in env file", "edit ~/.config/inbox-agent/env")
    else:
        report(bool(env.get("CLAUDE_CODE_OAUTH_TOKEN")), "CLAUDE_CODE_OAUTH_TOKEN in env file",
               "run `claude setup-token` on a machine with a browser, paste into ~/.config/inbox-agent/env")
    for f in ("env", "token.json", "client_secret.json"):
        p = os.path.join(C.HOME, f)
        if os.path.exists(p):
            mode = oct(os.stat(p).st_mode)[-3:]
            report(mode == "600", f"{f} is chmod 600 (is {mode})", f"chmod 600 {p}")
        else:
            report(False, f"{f} present", "see docs/GOOGLE-OAUTH.md" if f != "env" else "cp env.example ~/.config/inbox-agent/env")

    # playbook
    try:
        pb = open(cfg["playbook_path"]).read()
        left = re.findall(r"\[[A-Za-z][^\]]{1,40}\]", pb)
        left = [x for x in left if x not in ("[date]", "[First name]", "[Your name]", "[Creator]", "[Creator/company]")]
        report(not left, f"playbook has no unfilled brackets ({len(left)} left)",
               "edit playbook/SKILL.md: " + ", ".join(sorted(set(left))[:6]), warn=True)
    except FileNotFoundError:
        report(False, "playbook file found", f"check playbook_path in config.json ({cfg['playbook_path']})")

    # gmail
    gs = [sys.executable, os.path.join(REPO, "gsend", "gsend.py")]
    r = subprocess.run(gs + ["whoami"], capture_output=True, text=True)
    who = (r.stdout.strip().splitlines() or ["?"])[0][:60]
    report(r.returncode == 0 and who.lower() == cfg["gmail_address"].lower(),
           f"gmail token belongs to the configured address ({who})",
           "gsend auth, logging in as the configured address")

    # telegram
    try:
        import urllib.request
        with urllib.request.urlopen(f"https://api.telegram.org/bot{cfg['telegram_token']}/getMe", timeout=15) as resp:
            me = json.load(resp)
        report(me.get("ok"), f"telegram bot reachable (@{me.get('result', {}).get('username', '?')})")
    except Exception as e:
        report(False, "telegram bot reachable", f"check telegram_token ({e!r})")

    # claude
    from bot import llm
    report(llm.healthy(), f"Claude answers via backend '{cfg['claude_backend']}'",
           "backend code: token in env + claude installed on this machine. backend api: key in env.")

    # linger (linux only)
    if sys.platform.startswith("linux"):
        r = subprocess.run(["loginctl", "show-user", os.environ.get("USER", ""), "-p", "Linger"],
                           capture_output=True, text=True)
        report("Linger=yes" in r.stdout, "loginctl linger enabled",
               f"loginctl enable-linger {os.environ.get('USER', '')}", warn=True)

    # stop file
    report(not C.paused(), "stop file absent", f"rm {C.PAUSE_FILE}", warn=True)
    finish()


def finish():
    print()
    if FAILS:
        print(f"{FAILS} failing check(s). Fix them before installing the service.")
        sys.exit(1)
    print("Ready. Install the service (docs/SETUP-*.md) and send yourself a test email.")


if __name__ == "__main__":
    main()
