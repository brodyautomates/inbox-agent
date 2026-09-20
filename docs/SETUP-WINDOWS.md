# A Windows PC you leave on

Works, and it is the fussiest of the three. If you do not want to fight it, rent a server (docs/SETUP-HETZNER.md). Five dollars, twenty minutes.

## 1. Turn on the Linux layer

PowerShell as administrator:

```
wsl --install
```

Restart. Open Ubuntu from the Start menu and set a username and password.

## 2. Turn on background services

They are off by default in WSL, and without them nothing survives you closing the window.

```
sudo tee /etc/wsl.conf <<'EOF'
[boot]
systemd=true
EOF
```

Back in PowerShell:

```
wsl --shutdown
```

Open Ubuntu again.

## 3. Stop the PC sleeping

Settings → System → Power → Screen and sleep → set sleep to Never while plugged in.

## 4. From here it is Linux

Follow docs/SETUP-HETZNER.md from step 4 onward, inside the Ubuntu window. Skip the `adduser` step and use your own username wherever it says `agent`.

Your Gmail login can happen inside WSL because the browser will open on Windows.

## Two things that bite

- WSL stops if no Windows session is open. Stay logged in to Windows, lock the screen instead of signing out.
- `loginctl enable-linger` still applies inside WSL. Run it.
