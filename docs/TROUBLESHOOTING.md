# Troubleshooting: the ways this breaks

Every one of these happened on a real install. Each one is fast to find once you know the shape.

## 1. Worked for a week, then stopped

The Google app was left in Testing. Google expires the login after seven days with no error. Go to the OAuth consent screen, press **Publish**, run `gsend auth` again. Then `gsend test`.

## 1b. The login says "can only be used within its organization"

Error 403 `org_internal`. The Google Cloud project is owned by a Workspace organization and its consent screen is Internal, so only that company's own addresses can authorize it. Either make a fresh project while signed in as the address the agent will use, or switch that project's audience to External and publish. See docs/GOOGLE-OAUTH.md.

## 2. Works while you are logged in, dies when you disconnect

`loginctl enable-linger YOURUSER` was never run. A systemd user service only lives while that user has a session unless linger is on. Same shape on WSL.

## 3. The bot runs but every draft fails, and edits say "claude unavailable"

The service cannot find `claude` or its token. systemd and launchd do not read your shell profile. Check the unit has `EnvironmentFile=` and `Environment=PATH=` (Linux) or the `EnvironmentVariables` block (Mac). Then `journalctl --user -u inbox-agent -f` and look for `claude rc=`.

## 4. Quiet for days, no errors, then a message about authentication

The Claude login expired. Use `claude setup-token` for anything unattended, not `claude /login`. The bot freezes inbound during an outage rather than dropping mail, and resumes on its own when Claude answers again. Nothing is lost, but you were not reading email for however long it took you to notice. Put a reminder on the digest hour.

## 5. Sent from the wrong address

Impossible with this code, by design: gsend refuses to run if the token's address does not match `gmail_address` in config. If you are seeing it, you are not sending through gsend. Check that nothing else has that token.

## 6. A tap did nothing, or a tap sent twice

It cannot send twice: a draft is marked done before the send fires, and the buttons are replaced with a dead one. A tap that did nothing was probably a tap Telegram replayed after the bot restarted. Those are refused because they cannot be acknowledged. Tap again.

## 7. The same email got two drafts

Should not happen: the bot retires the older draft when a new email lands on the thread. If it does, look for `retire` lines in `bot.log`. Usually it means two different threads from the same sender, which is two conversations, and both drafts are correct.

## 8. Everything stopped and there is no error

```
ls ~/.config/inbox-agent/PAUSED
```

The stop file exists. Delete it, or `/resume` in Telegram.

## 9. The bot ignored something important

Look for `ignored` lines in `bot.log`. The noise filter in `bot/bot.py` and the triage prompt in `bot/prompts/triage.md` decide this. Add a sender to a deal-word list, or loosen the prompt. Then reply to any message in Telegram with `chain` to inspect.

## 10. Rewrite timed out

Long threads on a slow backend. The original draft is untouched. Try a shorter instruction, or switch `claude_backend` to `api` for faster turnarounds.

## Reading the log

```
tail -50 ~/.config/inbox-agent/bot.log
grep -c '\tsent ' ~/.config/inbox-agent/bot.log       # how many went out
grep -c 'rewrote' ~/.config/inbox-agent/bot.log       # how many you edited
```

The ratio of those two numbers is the only honest measure of whether your playbook is done.
