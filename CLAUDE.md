# inbox-agent: instructions for Claude Code

You are helping a person, who may not be technical, set this agent up on their own machine. Go one step at a time. Do the terminal work yourself. Ask them for the things only they can do, and wait.

## The order

1. `./install.sh` if `~/.config/inbox-agent/config.json` does not exist yet.
2. **Telegram.** They make the bot in BotFather on their phone and message it once. You ask for the token, then run the getUpdates curl from README to find their id, then write `telegram_token`, `allowed_user`, `gmail_address` and `signoff_name` into `~/.config/inbox-agent/config.json`. Ask for the address and the sign-off name; do not guess them.
3. **Google.** Walk them through `docs/GOOGLE-OAUTH.md` in the browser. Tell them to press Publish and why. They download the JSON; you move it to `~/.config/inbox-agent/client_secret.json` and `chmod 600` it. Then run `gsend auth` (a browser opens for them), `gsend whoami`, `gsend test`. Do not continue until `test` prints VERIFIED.
4. **Claude.** Ask which backend. For `code`: they run `claude setup-token` in their own terminal and paste the result to you; you write it into `~/.config/inbox-agent/env` as `CLAUDE_CODE_OAUTH_TOKEN=...` and `chmod 600` it. For `api`: same with `ANTHROPIC_API_KEY` and set `claude_backend` to `api` in config.
5. **Playbook.** Interview them: what they sell, prices, floors, payment terms, what they never answer, how they sign off. Write their answers into `playbook/SKILL.md`, replacing every bracket. Read the voice section back to them and adjust. Suggest they invent numbers if they are recording.
6. `venv/bin/python3 tools/doctor.py`. Fix every FAIL before going on.
7. **First run by hand.** `venv/bin/python3 -m bot.bot --once` does one inbox pass and handles any taps already waiting, then exits. Have them email the configured address from another account, run it again, and the card reaches their phone.

   For the demo, taps are nicer live: run `venv/bin/python3 -m bot.bot` with no flag in a terminal they can leave open. It polls the inbox and listens to Telegram at the same time, so SEND, CHAIN, replies and `/status` all work instantly. Ctrl-C stops it. Without a running loop, nothing in Telegram does anything.
8. **Keep it alive.** Mac: `docs/SETUP-MAC.md` (pmset, then the plist with their real paths and token). Linux or WSL: `docs/SETUP-HETZNER.md` step 6. Then reboot and prove it comes back.

## Rules

- Never print a token, key or the contents of `env`, `token.json` or `client_secret.json` into the conversation. Write them to the file and say you did.
- Never commit. `.gitignore` covers the secrets, but do not stage anything in `~/.config/inbox-agent/` under any circumstances.
- `gsend` is the only way to touch Gmail. Do not write ad-hoc Gmail API calls.
- The mode stays `manual` until they have watched several drafts go through. Do not switch to assisted or autopilot for them.
- If a check fails, read `docs/TROUBLESHOOTING.md` before improvising.
- Keep explanations short and plain. One idea per message.
