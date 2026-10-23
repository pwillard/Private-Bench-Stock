#!/usr/bin/env bash
# Private Bench Stock installer / updater for Raspberry Pi OS (or any Debian/Ubuntu with systemd).
#
# Run from the unpacked app folder:
#   sudo ./deploy/install_pi.sh [--dump /path/to/ecdb.sql] [--files /var/www/html] [--port 8080]
#                               [--offsite user@host:/path]
#
#   --dump     import the old MySQL dump (replaces an empty database; refuses one that has parts)
#   --files    old PHP web root: copies sheets/, appnotes/ and img/parts/ (existing files are kept)
#   --port     port to listen on (default 8080)
#   --offsite  nightly 03:30 copy of instance/ to another machine over SSH,
#              e.g. --offsite willard@benchpi.local:/home/willard/backups/benchstock
#
# Safe to re-run for updates: code is replaced, instance/ (database, files, secret key) is kept.
set -euo pipefail

DEST=/opt/benchstock
SRC="$(cd "$(dirname "$0")/.." && pwd)"
DUMP="" ; FILES="" ; PORT=8080 ; OFFSITE=""
while [ $# -gt 0 ]; do
  case "$1" in
    --dump)  DUMP="$2"; shift 2 ;;
    --files) FILES="$2"; shift 2 ;;
    --port)  PORT="$2"; shift 2 ;;
    --offsite) OFFSITE="$2"; shift 2 ;;
    *) echo "Unknown option $1"; exit 1 ;;
  esac
done
[ "$(id -u)" -eq 0 ] || { echo "Run with sudo."; exit 1; }

echo "== Packages"
apt-get install -y python3 python3-venv rsync sqlite3 openssh-client >/dev/null

echo "== Service user"
id benchstock >/dev/null 2>&1 || useradd --system --home "$DEST" --shell /usr/sbin/nologin benchstock

echo "== Code -> $DEST"
mkdir -p "$DEST"
rsync -a --delete --exclude .venv --exclude instance --exclude __pycache__ --exclude .pytest_cache \
      "$SRC"/ "$DEST"/
mkdir -p "$DEST/instance/media/sheets" "$DEST/instance/media/appnotes" "$DEST/instance/media/img/parts" \
         "$DEST/instance/backups"

echo "== Python environment"
[ -x "$DEST/.venv/bin/python" ] || python3 -m venv "$DEST/.venv"
"$DEST/.venv/bin/pip" install --quiet --upgrade pip
"$DEST/.venv/bin/pip" install --quiet -r "$DEST/requirements.txt"

if [ -n "$DUMP" ]; then
  echo "== Importing $DUMP"
  systemctl stop benchstock 2>/dev/null || true
  # import-mysql replaces an empty database, but refuses one that already has parts
  if ! (cd "$DEST" && .venv/bin/python manage.py import-mysql "$DUMP"); then
    echo "!! Import did not run - see the message above. The existing database was left as it was."
  fi
fi

if [ -n "$FILES" ]; then
  echo "== Copying reference files from $FILES"
  for d in sheets appnotes img/parts; do
    [ -d "$FILES/$d" ] && rsync -a --ignore-existing "$FILES/$d"/ "$DEST/instance/media/$d"/ && \
      echo "   $d: $(ls "$DEST/instance/media/$d" | wc -l) files"
  done
fi

chown -R benchstock:benchstock "$DEST/instance"
chmod 750 "$DEST/instance"

echo "== systemd"
sed "s/--port 8080/--port $PORT/" "$DEST/deploy/benchstock.service" > /etc/systemd/system/benchstock.service
if [ "$PORT" -lt 1024 ]; then
  sed -i 's/^#AmbientCapabilities/AmbientCapabilities/' /etc/systemd/system/benchstock.service
fi
cp "$DEST/deploy/benchstock-backup.service" "$DEST/deploy/benchstock-backup.timer" /etc/systemd/system/
cp "$DEST/deploy/benchstock-offsite.service" "$DEST/deploy/benchstock-offsite.timer" /etc/systemd/system/

KEY=/root/.ssh/benchstock_offsite
if [ -n "$OFFSITE" ]; then
  echo "== Off-device backup -> $OFFSITE"
  case "$OFFSITE" in *@*:/*) ;; *) echo "!! --offsite must look like user@host:/absolute/path"; exit 1 ;; esac
  printf 'REMOTE="%s"\nSSH_KEY="%s"\n' "$OFFSITE" "$KEY" > /etc/benchstock-offsite.conf
  mkdir -p /root/.ssh && chmod 700 /root/.ssh
  [ -f "$KEY" ] || ssh-keygen -q -t ed25519 -N "" -C "benchstock-offsite@$(hostname)" -f "$KEY"
fi
systemctl daemon-reload
systemctl enable --now benchstock-backup.timer >/dev/null
if [ -f /etc/benchstock-offsite.conf ]; then
  systemctl enable --now benchstock-offsite.timer >/dev/null
fi
systemctl enable benchstock >/dev/null
systemctl restart benchstock
sleep 2
systemctl --no-pager --lines=3 status benchstock || true

echo
echo "Private Bench Stock is running: http://$(hostname -I | awk '{print $1}'):$PORT/"
echo "Backup now:     cd $DEST && sudo -u benchstock .venv/bin/python manage.py backup"
if [ -n "$OFFSITE" ]; then
  echo
  echo "Off-device backup: one-time step - let this Pi log in to ${OFFSITE%%:*} with its backup key"
  echo "(asks for that account's password once):"
  echo
  echo "    sudo ssh-copy-id -i $KEY.pub ${OFFSITE%%:*}"
  echo
  echo "Then test it right away (normally runs nightly at 03:30):"
  echo
  echo "    sudo systemctl start benchstock-offsite && journalctl -u benchstock-offsite -n 20 --no-pager"
fi
