#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python_bin="$(command -v python3)"
unit_dir="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
mkdir -p "$unit_dir"

cat > "$unit_dir/wakeboard.service" <<EOF
[Unit]
Description=Wakeboard local Wake-on-LAN dashboard
After=network-online.target

[Service]
Type=simple
WorkingDirectory=$project_dir
ExecStart="$python_bin" "$project_dir/app.py"
Restart=on-failure

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now wakeboard.service
echo "Wakeboard uruchamia się teraz po zalogowaniu. Strona: http://127.0.0.1:8000"
