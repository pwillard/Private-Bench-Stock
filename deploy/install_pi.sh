#!/usr/bin/env bash
# ecDB installer / updater for Raspberry Pi OS (or any Debian/Ubuntu with systemd).
#
# Run from the unpacked app folder:
#   sudo ./deploy/install_pi.sh [--dump /path/to/ecdb.sql] [--files /var/www/html] [--port 8080]
#
#   --dump   import the old MySQL dump into a NEW database (refuses if one already exists)
#   --files  old PHP web root: copies sheets/, appnotes/ and img/parts/ (existing files are kept)
#   --port   port to listen on (default 8080)
#
# Safe to re-run for updates: code is replaced, instance/ (database, files, secret key) is kept.
set -euo pipefail

DEST=/opt/ecdb
SRC="$(cd "$(dirname "$0")/.." && pwd)"
DUMP="" ; FILES="" ; PORT=8080
while [ $# -gt 0 ]; do
  case "$1" in
    --dump)  DUMP="$2"; shift 2 ;;
    --files) FILES="$2"; shift 2 ;;
    --port)  PORT="$2"; shift 2 ;;
    *) echo "Unknown option $1"; exit 1 ;;
  esac
done
[ "$(id -u)" -eq 0 ] || { echo "Run with sudo."; exit 1; }

echo "== Packages"
apt-get install -y python3 python3-venv rsync sqlite3 >/dev/null

echo "== Service user"
id ecdb >/dev/null 2>&1 || useradd --system --home "$DEST" --shell /usr/sbin/nologin ecdb

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
  if [ -f "$DEST/instance/ecdb.sqlite3" ]; then
    echo "!! $DEST/instance/ecdb.sqlite3 already exists - not importing (delete it first to re-import)."
  else
    echo "== Importing $DUMP"
    (cd "$DEST" && .venv/bin/python manage.py import-mysql "$DUMP")
  fi
fi

if [ -n "$FILES" ]; then
  echo "== Copying reference files from $FILES"
  for d in sheets appnotes img/parts; do
    [ -d "$FILES/$d" ] && rsync -a --ignore-existing "$FILES/$d"/ "$DEST/instance/media/$d"/ && \
      echo "   $d: $(ls "$DEST/instance/media/$d" | wc -l) files"
  done
fi

chown -R ecdb:ecdb "$DEST/instance"
chmod 750 "$DEST/instance"

echo "== systemd"
sed "s/--port 8080/--port $PORT/" "$DEST/deploy/ecdb.service" > /etc/systemd/system/ecdb.service
if [ "$PORT" -lt 1024 ]; then
  sed -i 's/^#AmbientCapabilities/AmbientCapabilities/' /etc/systemd/system/ecdb.service
fi
cp "$DEST/deploy/ecdb-backup.service" "$DEST/deploy/ecdb-backup.timer" /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now ecdb-backup.timer >/dev/null
systemctl enable ecdb >/dev/null
systemctl restart ecdb
sleep 2
systemctl --no-pager --lines=3 status ecdb || true

echo
echo "ecDB is running: http://$(hostname -I | awk '{print $1}'):$PORT/"
echo "Backup now:     cd $DEST && sudo -u ecdb .venv/bin/python manage.py backup"
