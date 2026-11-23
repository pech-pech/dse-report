#!/bin/bash
# Keep the desktop apps' price store (~/.dse_pnf/prices.sqlite3) current while they are closed: the DSE P&F Desk
# app refreshes only while it is open. Runs the engine's own refresh job through dsereport (launchd:
# scripts/com.pech-pech.dse-report.store.plist). The engine logs the run in app_refresh_log, so an app that is
# open waits for it; this script likewise skips when an app started a refresh in the last 20 minutes.
set -uo pipefail
DB="${DSE_STORE:-$HOME/.dse_pnf/prices.sqlite3}"
HERE="$(cd "$(dirname "$0")/.." && pwd)"
stamp() { date '+%F %T'; }
case "$(date +%u)" in 5|6) echo "$(stamp) Fri/Sat: no session"; exit 0;; esac
[ -f "$DB" ] || { echo "$(stamp) no store at $DB"; exit 1; }
busy=$(/usr/bin/sqlite3 "$DB" "SELECT COUNT(*) FROM app_refresh_log WHERE finished IS NULL AND kind IN ('refresh','backfill') AND started > strftime('%Y-%m-%dT%H:%M:%S', 'now', '-20 minutes')" 2>&1)
if [ "$busy" != "0" ]; then echo "$(stamp) an app is refreshing ($busy); skipped"; exit 0; fi
echo "$(stamp) $("$HERE/.venv/bin/dsereport" refresh --db "$DB" 2>&1 | tail -1)"
