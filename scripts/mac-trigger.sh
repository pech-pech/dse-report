#!/bin/bash
# Start the daily-report workflow from the owner's Mac (launchd: scripts/com.pech-pech.dse-report.trigger.plist),
# because GitHub's own schedule can run hours late. Uses the gh login; no token is stored here.
#   mac-trigger.sh         normal run: publishes only a session newer than the site's (--if-newer)
#   mac-trigger.sh final   rebuild=true: republishes today's session with the later, complete end-of-day data
set -euo pipefail
GH=/opt/homebrew/bin/gh
REPO=pech-pech/dse-report
dow=$(date +%u)                      # 1=Mon .. 7=Sun; DSE trades Sun-Thu
case "$dow" in 5|6) echo "$(date '+%F %T') Fri/Sat: no session, not started"; exit 0;; esac
args=()
[ "${1:-}" = final ] && args=(-f rebuild=true)
"$GH" workflow run daily-report -R "$REPO" "${args[@]+"${args[@]}"}"
echo "$(date '+%F %T') started daily-report ${1:-normal}"
