# A Mac you leave on

A Mac mini, or a laptop that stays plugged in. The lid can be shut.

## 1. Stop it sleeping

```
sudo pmset -a sleep 0
sudo pmset -a disksleep 0
pmset -g | grep sleep       # check
```

## 2. Claude

Install Claude Code if it is not there, then log in once on this machine. Because the Mac has a screen you can use the normal login, but a setup token is still safer for anything unattended:

```
claude setup-token
mkdir -p ~/.config/inbox-agent
echo 'CLAUDE_CODE_OAUTH_TOKEN=paste_here' > ~/.config/inbox-agent/env
chmod 600 ~/.config/inbox-agent/env
```

## 3. Install the agent

```
git clone https://github.com/brodyautomates/inbox-agent
cd inbox-agent
./install.sh
```

Fill in the config, do the Google login here (docs/GOOGLE-OAUTH.md), edit the playbook, run the doctor.

## 4. Hand it to launchd

```
cp service/local.inbox-agent.plist ~/Library/LaunchAgents/
# open it and replace every /Users/YOU with your real home folder,
# and paste your token into the EnvironmentVariables block
chmod 600 ~/Library/LaunchAgents/local.inbox-agent.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/local.inbox-agent.plist
```

launchd does not read your shell profile, so the token has to be in the plist. That is why it is chmod 600 and why you keep it out of any screenshot.

Stop and start:

```
launchctl bootout gui/$(id -u)/local.inbox-agent
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/local.inbox-agent.plist
```

Logs: `~/.config/inbox-agent/bot.log`, `out.log`, `err.log`.

## 5. Prove it

Restart the Mac. Do not log in. Send yourself an email from another account. It should reach your phone within two minutes.

## Note on macOS permissions

The first time launchd runs `claude` it may trigger a permissions prompt you cannot see. If the bot logs Claude failures right after a fresh install, run `claude -p "say ok"` once in Terminal, approve whatever it asks, then restart the service.
