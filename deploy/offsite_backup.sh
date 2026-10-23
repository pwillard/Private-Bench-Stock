#!/usr/bin/env bash
# Nightly off-device copy of /opt/benchstock/instance to another machine over SSH.
# Settings: /etc/benchstock-offsite.conf (written by install_pi.sh --offsite user@host:/path)
#
# Copies: database snapshots (backups/), sheets, appnotes, part images, secret key.
# Skips the live database file (it can change mid-copy); today's snapshot is made first instead.
# Nothing is ever deleted on the remote side: a file deleted (or lost) here stays safe there.
set -euo pipefail

CONF=/etc/benchstock-offsite.conf
[ -f "$CONF" ] || { echo "No $CONF - off-device backup not configured."; exit 1; }
# shellcheck source=/dev/null
. "$CONF"
: "${REMOTE:?REMOTE not set in $CONF}"
SSH_KEY="${SSH_KEY:-/root/.ssh/benchstock_offsite}"
APP=/opt/benchstock
INSTANCE="$APP/instance"

# 1. Make sure there is a database snapshot from today
if [ -z "$(find "$INSTANCE/backups" -name 'benchstock-*.sqlite3' -newermt 'today 00:00' 2>/dev/null | head -1)" ]; then
  (cd "$APP" && runuser -u benchstock -- .venv/bin/python manage.py backup --keep 30)
fi

HOST="${REMOTE%%:*}"
DIR="${REMOTE#*:}"
SSH=(ssh -i "$SSH_KEY" -o BatchMode=yes -o ConnectTimeout=20 -o StrictHostKeyChecking=accept-new)

# 2. Copy
"${SSH[@]}" "$HOST" "mkdir -p '$DIR'"
rsync -a --partial --human-readable --stats \
      --exclude 'benchstock.sqlite3' --exclude 'benchstock.sqlite3-*' \
      --exclude '*.importing' --exclude '*.sql' \
      -e "${SSH[*]}" \
      "$INSTANCE/" "$REMOTE/"

# 3. Leave a marker on the remote so you can see when the last good copy happened
"${SSH[@]}" "$HOST" "date '+%F %T' > '$DIR/LAST_BACKUP_OK'"
echo "Off-device backup to $REMOTE finished OK."
