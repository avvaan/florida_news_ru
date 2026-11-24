#!/usr/bin/env bash
# Nightly database backup of the home-server site (deploy/crontab.example).
#
#   bash deploy/backup.sh
#
# pg_dump runs inside the db container and writes a compressed custom-format
# file (restore it with deploy/restore.sh, or pg_restore for Render) named
# florida-YYYY-MM-DD_HHMM.dump. The newest BACKUP_KEEP files are kept.
#
# Settings, from the environment (crontab.example sets them):
#   BACKUP_DIR     where the files go          default: ~/backups/florida
#   BACKUP_KEEP    how many files to keep      default: 14
#   RCLONE_REMOTE  off-site copy, e.g. "gdrive:florida-backups" —
#                  an rclone remote set up with `rclone config`. Empty → skipped.
set -euo pipefail
cd "$(dirname "$0")/.."

BACKUP_DIR="${BACKUP_DIR:-$HOME/backups/florida}"
BACKUP_KEEP="${BACKUP_KEEP:-14}"
RCLONE_REMOTE="${RCLONE_REMOTE:-}"

mkdir -p "$BACKUP_DIR"
file="$BACKUP_DIR/florida-$(date +%Y-%m-%d_%H%M).dump"
partial="$file.partial"
trap 'rm -f "$partial"' EXIT

# -T: no terminal, so the binary dump passes through untouched.
docker compose exec -T db sh -c \
    'pg_dump --username="$POSTGRES_USER" --dbname="$POSTGRES_DB" --format=custom' \
    > "$partial"

# An empty or unreadable file is not a backup.
if [ ! -s "$partial" ] || ! docker compose exec -T db pg_restore --list < "$partial" > /dev/null; then
    echo "backup FAILED: the dump is empty or unreadable" >&2
    exit 1
fi
mv "$partial" "$file"
echo "backup saved: $file ($(du -h "$file" | cut -f1))"

# Keep the newest BACKUP_KEEP files (names sort by date).
ls -1 "$BACKUP_DIR"/florida-*.dump | sort -r | tail -n +"$((BACKUP_KEEP + 1))" |
while IFS= read -r old; do
    rm -f -- "$old"
    echo "removed old backup: $old"
done

# Optional copy outside the house.
if [ -z "$RCLONE_REMOTE" ]; then
    echo "off-site copy skipped: RCLONE_REMOTE is not set"
elif ! command -v rclone > /dev/null; then
    echo "off-site copy skipped: rclone is not installed"
elif rclone copy "$file" "$RCLONE_REMOTE"; then
    echo "off-site copy: $RCLONE_REMOTE/$(basename "$file")"
else
    echo "off-site copy FAILED (the local backup is fine): rclone copy to $RCLONE_REMOTE" >&2
    exit 1
fi
