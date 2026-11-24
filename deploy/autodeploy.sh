#!/usr/bin/env bash
# Automatic update of the home-server site from GitHub, the way Render
# deployed on every push. cron runs it every 3 minutes (deploy/crontab.example):
#
#   bash /home/deploy/florida/deploy/autodeploy.sh
#
# Each run:
#   1. git fetch origin main; the same commit as the last good one → ends
#      without a word;
#   2. refuses a commit without docker-compose.yml and Dockerfile (the old,
#      pre-Docker main), or one that tracks mimi's own deploy/.env.prod or
#      docker-compose.override.yml; the site stays as it is;
#   3. git reset --hard to the new commit, docker compose up -d --build (at
#      most BUILD_TIMEOUT), waits until the web container reports "healthy";
#   4. success → that commit becomes the last good one. Failure → back to the
#      last good commit, built and started again. The failed commit is not
#      tried again; the next commit on main is.
# A run cut short (reboot, kill, full disk) leaves the checkout away from the
# last good commit: the next run finishes the update or goes back.
#
# Files, all in the home directory of the user running it:
#   florida-deploy.log        the journal: one or two lines per event
#   florida-deploy-build.log  git and docker output of the latest update
#   florida-deploy.ok         the last commit that ran healthy
#   florida-deploy.failed     the commit that failed; rm to retry it
#   florida-deploy.paused     exists → updates are paused (touch / rm)
#
# Untracked files in the checkout — deploy/.env.prod (secrets) and
# docker-compose.override.yml — are never touched: git reset --hard leaves
# untracked files alone, and nothing here runs git clean.
#
# Settings, from the environment (the defaults are mimi's):
#   APP_DIR         the git checkout                        /home/deploy/florida
#   BRANCH          the branch to follow                    main
#   BUILD_TIMEOUT   seconds for docker compose up --build   900
#   HEALTH_TIMEOUT  seconds to wait for "healthy" after it  300
#   HEALTH_POLL     seconds between health checks           5
#
# How-to (journal, pause, manual rollback, first setup): README.md →
# "Automatic updates on mimi".
set -euo pipefail

APP_DIR="${APP_DIR:-/home/deploy/florida}"
BRANCH="${BRANCH:-main}"
REMOTE=origin
BUILD_TIMEOUT="${BUILD_TIMEOUT:-900}"
HEALTH_TIMEOUT="${HEALTH_TIMEOUT:-300}"
HEALTH_POLL="${HEALTH_POLL:-5}"
COMPOSE_PROJECT=florida   # `name:` in docker-compose.yml

LOG_FILE="$HOME/florida-deploy.log"
BUILD_LOG="$HOME/florida-deploy-build.log"
OK_FILE="$HOME/florida-deploy.ok"
FAILED_FILE="$HOME/florida-deploy.failed"
PAUSE_FILE="$HOME/florida-deploy.paused"
LOCK_FILE="$HOME/.florida-deploy.lock"

# cron has no terminal: fail at once instead of waiting forever for a
# passphrase prompt or a dead connection (a stuck run would hold the lock).
export GIT_TERMINAL_PROMPT=0
export GIT_SSH_COMMAND="${GIT_SSH_COMMAND:-ssh -o BatchMode=yes -o ConnectTimeout=30 -o ServerAliveInterval=15 -o ServerAliveCountMax=4}"

# --- journal ---------------------------------------------------------------

# Shown only to a person running the script by hand, never written anywhere.
say() {
    if [ -t 1 ]; then echo "$*"; fi
}

log() {
    local line
    line="$(date '+%Y-%m-%d %H:%M:%S') $*"
    echo "$line" >> "$LOG_FILE"
    say "$line"
}

# Like log, but skipped when the journal already ends with the same message:
# a lasting state (paused, a refused commit, GitHub unreachable) is written
# once, not every 3 minutes.
log_once() {
    local last=""
    if [ -f "$LOG_FILE" ]; then
        last=$(tail -n 1 "$LOG_FILE" | cut -d' ' -f3-)   # without date and time
    fi
    if [ "$last" = "$*" ]; then
        say "$*"
    else
        log "$*"
    fi
}

# --- git -------------------------------------------------------------------

short() { git rev-parse --short "$1"; }

# Short hash and subject, e.g.: 5d6e7f8 "Ticket 14: forms"
describe() { echo "$(short "$1") \"$(git log -1 --format=%s "$1")\""; }

is_clone() {
    [ -d .git ] && git rev-parse --verify --quiet HEAD > /dev/null
}

is_commit() {
    [ -n "$1" ] && git cat-file -e "$1^{commit}" 2> /dev/null
}

# A commit without these is the old main from before the move to Docker:
# deploying it would leave nothing to run the site with.
has_docker_files() {
    git cat-file -e "$1:docker-compose.yml" 2> /dev/null &&
        git cat-file -e "$1:Dockerfile" 2> /dev/null
}

# mimi's own files must stay untracked: a commit that tracks them (git add -f)
# would overwrite them on reset, and a rollback would then delete them.
tracks_server_files() {
    git cat-file -e "$1:deploy/.env.prod" 2> /dev/null ||
        git cat-file -e "$1:docker-compose.override.yml" 2> /dev/null
}

# The commit kept in a state file ($OK_FILE, $FAILED_FILE), or nothing.
read_commit() {
    if [ -f "$1" ]; then cat "$1"; fi
}

# Through a temporary file, so a crash never leaves half a hash behind.
write_commit() {
    echo "$2" > "$1.tmp"
    mv "$1.tmp" "$1"
}

# git reset --hard throws away edits made on mimi to tracked files. Name them
# in the journal, so such an edit does not vanish without a trace.
log_local_edits() {
    local edited
    edited=$(git status --porcelain --untracked-files=no | cut -c4- | paste -sd ' ' -)
    if [ -n "$edited" ]; then
        log "discarding edits made on this server to: $edited"
    fi
}

# --- docker ----------------------------------------------------------------

# Health of the web container as Docker reports it: starting, healthy or
# unhealthy — "missing" while no web container is running.
web_health() {
    local id
    id=$(docker compose ps -q web 2> /dev/null | head -n 1) || true
    if [ -z "$id" ]; then
        echo missing
    else
        docker inspect --format '{{.State.Health.Status}}' "$id" 2> /dev/null || echo unknown
    fi
}

# Builds and starts the checked-out commit. True once web is healthy; on
# failure FAILURE says why. The docker output goes to the build log.
start_site() {
    local deadline status rc=0
    # `up` has a time limit: cloudflared waits for web to be healthy, so a web
    # that keeps crashing can keep `up` waiting forever, and a build can hang
    # on the network. Past the limit it counts as a failure, like any other.
    timeout --kill-after=30 "$BUILD_TIMEOUT" docker compose up -d --build >> "$BUILD_LOG" 2>&1 || rc=$?
    case "$rc" in
        0) ;;
        124 | 137) FAILURE="docker compose up --build still busy after ${BUILD_TIMEOUT}s"; return 1 ;;
        *) FAILURE="docker compose up --build failed"; return 1 ;;
    esac
    deadline=$((SECONDS + HEALTH_TIMEOUT))
    while :; do
        status=$(web_health)
        case "$status" in
            healthy) return 0 ;;
            unhealthy) FAILURE="web is unhealthy"; return 1 ;;
        esac
        if [ "$SECONDS" -ge "$deadline" ]; then
            FAILURE="web not healthy after ${HEALTH_TIMEOUT}s (still: $status)"
            return 1
        fi
        sleep "$HEALTH_POLL"
    done
}

# Every update leaves the previous web image behind, untagged. Remove the
# untagged images of this project only (Compose labels the images it builds),
# so they do not fill the disk over the months. Never fatal.
prune_old_images() {
    docker image prune --force --filter "label=com.docker.compose.project=$COMPOSE_PROJECT" \
        >> "$BUILD_LOG" 2>&1 || true
}

# --- the update ------------------------------------------------------------

# The first run after First setup (README) finds no $OK_FILE: the checked-out
# commit becomes the last good one, provided web is healthy right now.
ensure_ok_file() {
    local good
    good=$(read_commit "$OK_FILE")
    if [ -n "$good" ]; then
        if is_commit "$good"; then return 0; fi
        log_once "$OK_FILE holds \"$good\", not a commit of this clone: write the running, healthy commit there (README: Automatic updates on mimi)"
        return 1
    fi
    if [ "$(web_health)" != healthy ]; then
        log_once "no $OK_FILE yet and web is not healthy: start the site, then write the running commit there (README: First setup)"
        return 1
    fi
    write_commit "$OK_FILE" "$(git rev-parse HEAD)"
    log "recorded $(short HEAD) as the last good commit (web is healthy)"
}

# Moves the checkout from the last good commit $1 to $2 and starts it; on
# failure goes back to $1. Returns 0 deployed, 1 rolled back, 2 the rollback
# failed as well.
deploy() {
    local good="$1" target="$2" why
    log "updating $(short "$good") -> $(describe "$target")"
    echo "=== $(date '+%Y-%m-%d %H:%M:%S') updating $good -> $target" > "$BUILD_LOG"

    log_local_edits
    git reset --hard --quiet "$target"
    if start_site; then
        write_commit "$OK_FILE" "$target"
        rm -f "$FAILED_FILE"
        log "deployed $(short "$target")"
        prune_old_images
        return 0
    fi

    why="$FAILURE"
    echo "=== $(date '+%Y-%m-%d %H:%M:%S') $why; rolling back to $good" >> "$BUILD_LOG"
    git reset --hard --quiet "$good"
    # The failed commit is written down only now: a run cut short before this
    # point leaves it to the next run, which tries it again.
    if start_site; then
        write_commit "$FAILED_FILE" "$target"
        log "FAILED $(short "$target"): $why. Rolled back to $(short "$good"), which runs again. Output: $BUILD_LOG"
        return 1
    fi
    write_commit "$FAILED_FILE" "$target"
    log "FAILED $(short "$target"): $why. The rollback to $(short "$good") failed too ($FAILURE): the site may be down (README: Automatic updates on mimi, If the rollback fails). Output: $BUILD_LOG"
    return 2
}

# The checkout is not at the last good commit $1 but at $2: an update was cut
# short (reboot, kill, full disk), and there is nothing to deploy instead.
# Put the last good commit back and start it.
restore() {
    local good="$1" head="$2"
    log "the checkout is at $(short "$head"), not at the last good $(short "$good"): an update was cut short. Going back to $(short "$good")"
    echo "=== $(date '+%Y-%m-%d %H:%M:%S') restoring $good (the checkout was at $head)" > "$BUILD_LOG"
    git reset --hard --quiet "$good"
    if start_site; then
        log "restored $(short "$good")"
        return 0
    fi
    log "restoring $(short "$good") FAILED ($FAILURE): the site may be down (README: Automatic updates on mimi, If the rollback fails). Output: $BUILD_LOG"
    return 2
}

main() {
    local fetch_output good target head reason=""

    if [ -e "$PAUSE_FILE" ]; then
        log_once "paused: $PAUSE_FILE exists (delete it to resume)"
        return 0
    fi

    if ! cd "$APP_DIR" 2> /dev/null || ! is_clone; then
        log_once "not a git clone yet: $APP_DIR (README: Automatic updates on mimi, First setup); nothing done"
        return 0
    fi

    # One run at a time: an update can take longer than the 3 minutes between
    # runs. A run that finds the lock taken leaves the busy one alone.
    exec 9> "$LOCK_FILE"
    if ! flock -n 9; then
        say "another update is running; leaving it alone"
        return 0
    fi

    if ! ensure_ok_file; then
        return 1
    fi

    # The remote is reached over SSH (a deploy key), so git's message names
    # no password or token.
    if ! fetch_output=$(git fetch --quiet "$REMOTE" "$BRANCH" 2>&1); then
        log_once "cannot fetch $REMOTE/$BRANCH: $(echo "$fetch_output" | head -n 1)"
        return 1
    fi

    # "New" means: not the last good commit. The checkout alone can't tell —
    # it moves to the new commit before the build succeeds.
    good=$(read_commit "$OK_FILE")
    target=$(git rev-parse "refs/remotes/$REMOTE/$BRANCH")
    head=$(git rev-parse HEAD)

    if [ "$target" = "$good" ]; then
        :   # nothing new
    elif ! has_docker_files "$target"; then
        reason="REFUSED $(short "$target"): no docker-compose.yml or Dockerfile in it (the old $BRANCH?); the site stays on $(short "$good")"
    elif tracks_server_files "$target"; then
        reason="REFUSED $(short "$target"): it tracks deploy/.env.prod or docker-compose.override.yml, which belong to this server only (git rm --cached them on $BRANCH); the site stays on $(short "$good")"
    elif [ "$(read_commit "$FAILED_FILE")" = "$target" ]; then
        reason="waiting for a commit newer than $(short "$target"), which failed (to try it again: rm $FAILED_FILE)"
    else
        deploy "$good" "$target"
        return
    fi

    if [ -n "$reason" ]; then
        log_once "$reason"
    fi
    if [ "$head" != "$good" ]; then
        restore "$good" "$head"
        return
    fi
    if [ -n "$reason" ]; then
        return 1
    fi
    say "up to date: $(describe "$good")"
}

# The whole script is read before anything runs (main and exit are on one
# line): git reset in deploy rewrites this very file.
main "$@"; exit
