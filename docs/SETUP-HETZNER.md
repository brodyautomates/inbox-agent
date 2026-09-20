# A rented server: the five dollar computer that never sleeps

For anyone who only has a laptop. The bot runs on a machine in a data centre that is already on, never sleeps, nobody unplugs, and is not your problem when it dies. About twenty minutes.

Hetzner is used here because it is cheap and boring. Any provider that gives you an Ubuntu box with SSH works the same way.

## 1. Make a key on your laptop

```
ssh-keygen -t ed25519
# press enter three times

cat ~/.ssh/id_ed25519.pub
# copy the whole line. It is a lock, not a secret.
```

## 2. Rent the box

At [console.hetzner.cloud](https://console.hetzner.cloud):

1. Sign up, add a card. New accounts are sometimes held for identity checks for a day, so do this ahead of time.
2. New project. Name it anything.
3. **Add Server.**
4. Location: the one nearest you.
5. Image: **Ubuntu 24.04**.
6. Type: **Shared vCPU**, the cheapest one. Two cores and four gigabytes is far more than this needs.
7. SSH keys: **Add SSH key**, paste the line from step 1.
8. Leave everything else. **Create.**
9. Copy the IP address from the server page.

## 3. First commands on the new box

```
ssh root@YOUR_SERVER_IP
# type yes the first time

apt update && apt install -y python3-venv python3-pip curl git

# a normal user for the agent, with your key
adduser --disabled-password --gecos "" agent
mkdir -p /home/agent/.ssh
cp ~/.ssh/authorized_keys /home/agent/.ssh/
chown -R agent:agent /home/agent/.ssh
exit

# from now on, always:
ssh agent@YOUR_SERVER_IP
```

## 4. Install Claude on the server (backend "code")

```
curl -fsSL https://claude.ai/install.sh | bash
exit
ssh agent@YOUR_SERVER_IP
claude --version
```

Then the token. A server has no browser, so make the token on your laptop and carry it over:

```
# laptop:
claude setup-token          # opens a browser, prints a token

# server:
mkdir -p ~/.config/inbox-agent
echo 'CLAUDE_CODE_OAUTH_TOKEN=paste_here' > ~/.config/inbox-agent/env
chmod 600 ~/.config/inbox-agent/env
```

Use `setup-token`, not `claude /login`. A login session expires after a while and the bot then fails silently. A setup token is made for unattended use.

If you would rather use an API key, skip the install and put `ANTHROPIC_API_KEY=...` in the env file instead, with `"claude_backend": "api"` in config.

## 5. Install the agent

```
git clone https://github.com/brodyautomates/inbox-agent
cd inbox-agent
./install.sh
```

Fill in `~/.config/inbox-agent/config.json`. Do the Google login on your laptop (docs/GOOGLE-OAUTH.md) and push the two files up. Edit the playbook. Then:

```
venv/bin/python3 tools/doctor.py
```

## 6. Hand it to the system

```
mkdir -p ~/.config/systemd/user
cp service/inbox-agent.service ~/.config/systemd/user/
sed -i "s#/home/YOU#/home/agent#g" ~/.config/systemd/user/inbox-agent.service
systemctl --user daemon-reload
systemctl --user enable --now inbox-agent
loginctl enable-linger agent

systemctl --user status inbox-agent
journalctl --user -u inbox-agent -f
```

Two lines in that unit are not optional and nobody tells you:

- `loginctl enable-linger`. Without it the bot dies the moment you close the SSH connection, which looks exactly like it worked when you tested it and then quietly did not.
- `EnvironmentFile` and `PATH`. systemd does not read your profile. Without those the bot cannot find `claude` or its token, and the first edit from your phone fails with nothing on screen.

## 7. Prove it

```
sudo reboot
```

Close the terminal. Do not reopen it. Send yourself an email from another account. Wait two minutes. It should arrive on your phone with a SEND button. That is the whole point of renting a computer.

## The stop switch

```
touch ~/.config/inbox-agent/PAUSED     # nothing sends
rm ~/.config/inbox-agent/PAUSED        # carries on
```

Or `/pause` and `/resume` in Telegram.
