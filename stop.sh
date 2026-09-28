#!/usr/bin/env bash
# Stop the Recruiter Mail Harvester and close its Chrome window.
# Usage: ./stop.sh
set -uo pipefail
cd "$(dirname "$0")"

# Match the real processes only: a pattern like "bin/harvest" alone also matches any
# shell or editor whose command line happens to contain that text, and kills it.
HARVEST='^[^ ]*/python[0-9.]* ([^ ]*/)?\.venv/bin/harvest( |$)'
CHROME='^[^ ]*/chrom[^ ]* .*--user-data-dir=[^ ]*recruiter-mail-harvester/profile'

stopped=0

# 1) The process we started, by its saved PID.
if [ -f .harvest.pid ]; then
  pid="$(cat .harvest.pid 2>/dev/null || true)"
  # A stale file can name a PID that now belongs to something else: check it first.
  if [ -n "${pid:-}" ] && ps -o args= -p "$pid" 2>/dev/null | grep -Eq "$HARVEST" \
     && kill "$pid" 2>/dev/null; then stopped=1; fi
  rm -f .harvest.pid
fi

# 2) Any other harvest process (e.g. started by hand).
for p in $(pgrep -f "$HARVEST" 2>/dev/null || true); do
  kill "$p" 2>/dev/null && stopped=1 || true
done

# 3) The Chrome window using the tool's own profile (leaves your normal Chrome alone).
for p in $(pgrep -f "$CHROME" 2>/dev/null || true); do
  kill "$p" 2>/dev/null && stopped=1 || true
done

sleep 1
if [ "$stopped" = 1 ]; then
  echo "Recruiter Mail Harvester stopped."
else
  echo "Nothing was running."
fi
