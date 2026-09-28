#!/usr/bin/env bash
# Start the Recruiter Mail Harvester setup screen (a Chrome window).
# Usage: ./run.sh
set -euo pipefail
cd "$(dirname "$0")"

# Match the real processes only: a pattern like "bin/harvest" alone also matches any
# shell or editor whose command line happens to contain that text, and kills it.
HARVEST='^[^ ]*/python[0-9.]* ([^ ]*/)?\.venv/bin/harvest( |$)'
CHROME='^[^ ]*/chrom[^ ]* .*--user-data-dir=[^ ]*recruiter-mail-harvester/profile'

export DISPLAY="${DISPLAY:-:0}"
export PYTHONUNBUFFERED=1

if [ ! -x .venv/bin/harvest ]; then
  echo "No virtualenv found. Set it up first:" >&2
  echo "  python3 -m venv .venv && .venv/bin/pip install -e ." >&2
  exit 1
fi

# Only one copy can run at a time (the browser profile is single-use).
if pgrep -f "$HARVEST" >/dev/null 2>&1; then
  echo "Already running. Stop it first with ./stop.sh"
  exit 0
fi

# Clear any Chrome left holding the profile lock after a crash or hard close.
for p in $(pgrep -f "$CHROME" 2>/dev/null || true); do
  kill "$p" 2>/dev/null || true
done
sleep 1

mkdir -p logs
nohup .venv/bin/harvest ui > logs/harvest.log 2>&1 &
echo $! > .harvest.pid

echo "Recruiter Mail Harvester started (PID $(cat .harvest.pid))."
echo "A Chrome window will open with the setup screen."
echo "Press 'Save & find emails' there to run a search."
echo "Log:  logs/harvest.log"
echo "Stop: ./stop.sh"
