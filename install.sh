#!/usr/bin/env bash
# One-shot install. Safe to re-run.
#   git clone https://github.com/brodyautomates/inbox-agent && cd inbox-agent && ./install.sh
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOME_DIR="${INBOX_AGENT_HOME:-$HOME/.config/inbox-agent}"

echo "== inbox-agent install"
echo "   repo:   $HERE"
echo "   config: $HOME_DIR"

command -v python3 >/dev/null || { echo "python3 is required"; exit 1; }

# venv + deps
if [ ! -x "$HERE/venv/bin/python3" ]; then
  python3 -m venv "$HERE/venv"
fi
"$HERE/venv/bin/pip" install --quiet --upgrade pip
"$HERE/venv/bin/pip" install --quiet -r "$HERE/requirements.txt"

# config folder
mkdir -p "$HOME_DIR"
chmod 700 "$HOME_DIR"
[ -f "$HOME_DIR/config.json" ] || { cp "$HERE/config.example.json" "$HOME_DIR/config.json"; echo "   wrote $HOME_DIR/config.json  <-- fill this in"; }
[ -f "$HOME_DIR/env" ] || { cp "$HERE/env.example" "$HOME_DIR/env"; chmod 600 "$HOME_DIR/env"; echo "   wrote $HOME_DIR/env          <-- put your token in"; }
[ -f "$HOME_DIR/mode" ] || echo manual > "$HOME_DIR/mode"

# gsend wrapper on PATH
mkdir -p "$HOME/.local/bin"
cat > "$HOME/.local/bin/gsend" <<EOF
#!/usr/bin/env bash
exec "$HERE/venv/bin/python3" "$HERE/gsend/gsend.py" "\$@"
EOF
chmod +x "$HOME/.local/bin/gsend"
case ":$PATH:" in *":$HOME/.local/bin:"*) ;; *) echo "   add ~/.local/bin to your PATH to use the gsend command";; esac

# make the playbook path absolute in config so the service can find it from anywhere
"$HERE/venv/bin/python3" - "$HOME_DIR/config.json" "$HERE" <<'PY'
import json, os, sys
p, repo = sys.argv[1], sys.argv[2]
cfg = json.load(open(p))
for k in ("playbook_path", "assisted_templates_path"):
    v = cfg.get(k, "")
    if v and not os.path.isabs(os.path.expanduser(v)):
        cfg[k] = os.path.join(repo, v)
json.dump(cfg, open(p, "w"), indent=2)
PY

echo
echo "== next"
echo "   1. edit $HOME_DIR/config.json   (gmail_address, telegram_token, allowed_user, signoff_name)"
echo "   2. put your Claude token in $HOME_DIR/env"
echo "   3. put client_secret.json from Google in $HOME_DIR/   (docs/GOOGLE-OAUTH.md)"
echo "   4. gsend auth && gsend whoami && gsend test     (on a machine with a browser)"
echo "   5. edit playbook/SKILL.md until every [bracket] is gone"
echo "   6. $HERE/venv/bin/python3 tools/doctor.py"
echo "   7. install the service: docs/SETUP-HETZNER.md, SETUP-MAC.md or SETUP-WINDOWS.md"
