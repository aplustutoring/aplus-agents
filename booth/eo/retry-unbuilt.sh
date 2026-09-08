#!/usr/bin/env bash
# Retry the nine "your ideas are still sitting there" emails until Resend's
# daily cap clears. Quiet while blocked; one line per person once it works.
#
# send-unbuilt.py records each success to .unbuilt-sent and skips anyone
# already recorded, so a cap that clears mid-batch cannot double-send.
# Exit code 3 from that script means "quota", not "broken".
set -u
cd "$(dirname "$0")/../.." || exit 1

TOTAL=9
say() { echo "[$(date +%H:%M:%S)] $*"; }

say "waiting on Resend quota — will send the 9 unbuilt-agent emails as soon as it clears"

while :; do
  OUT=$(HUBSPOT_PRIVATE_APP_TOKEN=$(grep '^HUBSPOT_PRIVATE_APP_TOKEN=' /Users/romanslavinsky/code/aplus-agents/.env | cut -d= -f2- | tr -d '"') \
        RESEND_API_KEY=$(grep '^RESEND_API_KEY=' /Users/romanslavinsky/code/aplus-agents/.env | cut -d= -f2- | tr -d '"') \
        python3 booth/eo/send-unbuilt.py --live 2>&1)
  CODE=$?

  SENT=$(printf '%s\n' "$OUT" | grep -c '^  LIVE ')
  # Test for the file first: `wc -l < missing` is a SHELL redirect failure,
  # which 2>/dev/null on the command does not suppress — it printed an error
  # every pass until the first send created the file.
  if [ -f booth/eo/.unbuilt-sent ]; then
    DONE=$(wc -l < booth/eo/.unbuilt-sent | tr -d ' ')
  else
    DONE=0
  fi

  if [ "$SENT" -gt 0 ]; then
    say "quota cleared — sent $SENT this pass ($DONE/$TOTAL done)"
    printf '%s\n' "$OUT" | grep '^  LIVE ' | sed 's/^/    /'
  fi

  if [ "$DONE" -ge "$TOTAL" ]; then
    say "all $TOTAL sent — done"
    exit 0
  fi

  if [ "$CODE" -ne 3 ] && [ "$SENT" -eq 0 ]; then
    say "unexpected failure (exit $CODE) — stopping so it can be looked at"
    printf '%s\n' "$OUT" | tail -4 | sed 's/^/    /'
    exit 1
  fi

  sleep 1800
done
