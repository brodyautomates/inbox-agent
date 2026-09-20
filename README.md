# inbox-agent

An AI that reads one inbox, writes every reply against a playbook you own, and puts each one on your phone with a send button. Runs 24/7 on a five dollar server, a Mac you leave on, or a Windows PC. About an hour to set up. Nothing to buy except the Claude subscription you probably already have.

Start with a manual send gate: nothing goes without your tap. Move to assisted, then autopilot, once it has earned it. The gate is in code, not in a prompt.

```
Inbox  →  Playbook  →  Draft in Gmail  →  Your phone (Telegram)  →  [gate]  →  Sent
```

## What it does

- Polls the inbox every two minutes. New email, it decides whether it is worth a reply.
- Writes the reply against `playbook/SKILL.md`: your prices, your rules, your stages, your voice. Creates it as a Gmail draft, threaded, to the sender only.
- Posts the draft to Telegram with **SEND**, **SKIP**, **CHAIN**. Reply to it in plain text ("make it 9k", "warmer opener") and it rewrites.
- One live draft per thread. A follow-up from them retires the old draft and writes a fresh one.
- Three modes: manual, assisted, autopilot. Hard stops that hold in every mode. A stop file that beats everything.
- Works with Claude Code headless (your Claude subscription) or the Anthropic API. One config flag.

## What it never does

- Sends to anyone who did not email you first. There is no cold email path in this code.
- Lets the model choose a recipient. It is copied from the original message.
- Sends from the wrong address. The Gmail token is checked against your config on every command.
- Sends twice. A draft is marked done before the send fires.
- Sends anything while `~/.config/inbox-agent/PAUSED` exists.

## Sixty minute path

1. **Telegram bot.** Message @BotFather, `/newbot`, keep the token. Message your new bot once. Get your own id:
   ```
   curl -s "https://api.telegram.org/bot<TOKEN>/getUpdates" | grep -o '"id":[0-9]*' | head -1
   ```
2. **Google.** Four minutes of clicks, and press Publish. [docs/GOOGLE-OAUTH.md](docs/GOOGLE-OAUTH.md)
3. **Install.**
   ```
   git clone https://github.com/brodyautomates/inbox-agent
   cd inbox-agent
   ./install.sh
   ```
   Fill in `~/.config/inbox-agent/config.json` and put your Claude token in `~/.config/inbox-agent/env`.
4. **Prove the sender.**
   ```
   gsend auth && gsend whoami && gsend test     # has to print VERIFIED
   ```
5. **Playbook.** Open `playbook/SKILL.md` and replace every bracket. This is the file that makes it yours.
6. **Doctor.**
   ```
   venv/bin/python3 tools/doctor.py
   ```
7. **Keep it alive.** Pick one: [Hetzner / any Linux server](docs/SETUP-HETZNER.md), [Mac](docs/SETUP-MAC.md), [Windows](docs/SETUP-WINDOWS.md).
8. **Prove it.** Reboot the machine, do not log in, email yourself from another account. Two minutes later it is on your phone.

## Customize it

Everything a viewer would want to change is a text file, not code.

| Want to change | Edit |
|---|---|
| Prices, rules, stages, voice, sign-off | `playbook/SKILL.md` |
| What gets a reply, what gets ignored, what escalates | `bot/prompts/triage.md` |
| How replies are written | `bot/prompts/draft.md` |
| How edits are applied | `bot/prompts/rewrite.md` |
| Which short replies may go without you in assisted mode | `playbook/assisted-templates.md` |
| Ceiling, word limit, delay, digest hour, ignored senders, keywords | `~/.config/inbox-agent/config.json` |
| Claude Code vs API, model | `claude_backend`, `api_model` in config |
| Mode | `/mode` in Telegram, or `~/.config/inbox-agent/mode` |

Deeper changes: the noise word lists at the top of `bot/bot.py`, the filters in `bot/modes.py`, the card layout in `bot.py card_text`.

## Files

```
gsend/gsend.py         the only thing that touches Gmail. auth, test, search, reply, send.
bot/bot.py             the daemon: poll, triage, draft, announce, taps, edits, modes
bot/modes.py           the gate: hard stops and the assisted filter
bot/llm.py             one ask() with two backends: claude -p, or the API
bot/prompts/           triage, draft, rewrite, template_match. Edit freely.
playbook/SKILL.md      your prices, rules, stages, voice. The bot reads it on every draft.
rules/                 inbound, negotiation, modes, outbound: the reasoning behind the defaults
service/               systemd unit and launchd plist
docs/                  setup per machine, Google OAuth, troubleshooting, security
tools/doctor.py        pre-flight checks
tools/scrub_check.py   refuses to commit secrets or personal data
tests/                 the gate logic, no network needed
```

## Telegram commands

`/status` mode, pause state, what is waiting. `/mode manual|assisted|autopilot`. `/pause` and `/resume`. Reply to any draft card to rewrite it. Tap CHAIN to see the whole thread.

## Cost

Claude Pro at around twenty dollars a month covers this comfortably with the `code` backend. Gmail and Telegram are free. A rented server is around five dollars a month. Check both prices; they move.

## Run the tests

```
venv/bin/python3 -m unittest tests/test_modes.py
```

## License

MIT. Fork it, change it, ship it. If you build the outbound path, read [rules/outbound.md](rules/outbound.md) first. The penalties are per email.
