#!/usr/bin/env bash
# Replace the home-server site's database with a backup from deploy/backup.sh.
#
#   bash deploy/restore.sh ~/backups/florida/florida-2027-01-15_0330.dump
#
# Asks for confirmation, saves the current database first
# (before-restore-….dump in BACKUP_DIR), stops the site, recreates the
# database from the file and starts the site again.
set -euo pipefail

if [ $# -ne 1 ] || [ ! -f "$1" ]; then
    echo "usage: bash deploy/restore.sh <backup file .dump>" >&2
    exit 2
fi
# Absolute path before changing directory.
file="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"
cd "$(dirname "$0")/.."

BACKUP_DIR="${BACKUP_DIR:-$HOME/backups/florida}"

if ! docker compose exec -T db pg_restore --list < "$file" > /dev/null; then
    echo "Not a readable pg_dump archive: $file" >&2
    exit 1
fi

echo "This REPLACES the site's database with:"
echo "  $file"
read -r -p "Type yes to continue: " answer
if [ "$answer" != "yes" ]; then
    echo "Cancelled; nothing changed."
    exit 1
fi

mkdir -p "$BACKUP_DIR"
safety="$BACKUP_DIR/before-restore-$(date +%Y-%m-%d_%H%M%S).dump"
docker compose exec -T db sh -c \
    'pg_dump --username="$POSTGRES_USER" --dbname="$POSTGRES_DB" --format=custom' \
    > "$safety"
echo "Current database saved to $safety"

trap 'echo "Restore FAILED. The site is stopped. To go back to the database as it was:" >&2
      echo "  bash deploy/restore.sh $safety" >&2
      echo "or, to start the site as it is now:  docker compose start web" >&2' ERR

docker compose stop web
docker compose exec -T db sh -c \
    'dropdb --username="$POSTGRES_USER" --force --if-exists "$POSTGRES_DB" &&
     createdb --username="$POSTGRES_USER" "$POSTGRES_DB"'
docker compose exec -T db sh -c \
    'pg_restore --username="$POSTGRES_USER" --dbname="$POSTGRES_DB" --no-owner --no-acl' \
    < "$file"
docker compose start web

trap - ERR
echo "Restored from $file; the site is starting (docker compose ps shows when it is healthy)."
