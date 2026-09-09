#!/bin/zsh
# Run 2 launcher: waits for the run-1 evaluation process to exit, then re-inventories CONTROL/PLANTED for every
# completed run-1 scene under project charade-r2, re-verifies with the v2 candidates, rescores, summarises, backs up.
set -u
cd ~/Projects/scripty
set -a; . ./.env; set +a
export CLICKHOUSE_MAX_MEMORY=1500000000
echo "run2: waiting for run 1 to finish ($(date +%H:%M:%S))"
while pgrep -f "scripty.eval_cli" >/dev/null; do sleep 60; done
echo "run2: run 1 finished, starting rerun ($(date +%H:%M:%S))"
.venv/bin/python -c "from scripty import db; db.purge_project('charade-r2')" 2>/dev/null
rm -f docs/eval/charade-r2.progress.jsonl
.venv/bin/python -m scripty.rerun charade charade-r2 --verify-top 90 2>&1 | grep -vE "UserWarning|warnings.warn|AFC|socks"
echo "run2: rerun done ($(date +%H:%M:%S)); rescoring"
.venv/bin/python scripts/rescore.py charade-r2 >/dev/null 2>&1
.venv/bin/python scripts/summarise.py charade-r2 2
.venv/bin/python scripts/rescore.py charade >/dev/null 2>&1
echo "run2: DONE ($(date +%H:%M:%S))"
