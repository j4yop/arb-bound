#!/usr/bin/env bash
# Read MCX circular #766 (19 Nov 2024) via TinyFish Agent — the one in-window
# "spec-change?" candidate that could bear on the Nov-2024 GOLDGUINEA/GOLDPETAL
# break. Run in the background; writes /tmp/c766.json when it finishes.
set -u
cd /Users/jaygopal/arb-bound
source .env >/dev/null 2>&1

RID=$(curl -sS --max-time 120 -X POST \
  "https://agent.tinyfish.ai/v1/automation/run-async" \
  -H "X-API-Key: $TINYFISH_API_KEY" -H "Content-Type: application/json" -d '{
    "url": "https://www.mcxindia.com/circulars/all-circulars",
    "goal": "Find circular number 766, dated 19 November 2024, titled \"Acceptance Of MCX Good Delivery Norms For BIS - Standard Gold For Delivery In Gold Mini\". Open it and read it. Report: (1) exactly what the circular changes, (2) the effective date, (3) which commodity and contract specifications it applies to, (4) whether it affects GOLDGUINEA or GOLDPETAL at all, (5) whether it changes tender period, delivery period, lot size or purity. Quote the operative sentence if you find one.",
    "output_schema": {
      "type": "object",
      "properties": {
        "circular_no": {"type": "string"},
        "date": {"type": "string"},
        "opens_ok": {"type": "boolean"},
        "what_changes": {"type": "string"},
        "effective_date": {"type": "string", "nullable": true},
        "applies_to": {"type": "string"},
        "affects_guinea_or_petal": {"type": "string"},
        "changes_tender_lot_purity": {"type": "string"},
        "operative_quote": {"type": "string", "nullable": true}
      },
      "required": ["circular_no","what_changes","applies_to","affects_guinea_or_petal"]
    }
  }' | python3 -c "import json,sys;print(json.load(sys.stdin).get('run_id',''))")

if [ -z "$RID" ]; then echo "FAILED to submit" > /tmp/c766.err; exit 1; fi
echo "$RID" > /tmp/c766.rid
echo "submitted: $RID"

for i in $(seq 1 60); do
  sleep 20
  S=$(curl -sS --max-time 40 "https://agent.tinyfish.ai/v1/runs/$RID" \
        -H "X-API-Key: $TINYFISH_API_KEY" 2>/dev/null)
  ST=$(printf '%s' "$S" | python3 -c "import json,sys;print(json.load(sys.stdin).get('status',''))" 2>/dev/null)
  echo "poll $i: ${ST:-?}"
  if [ "$ST" = "COMPLETED" ] || [ "$ST" = "FAILED" ] || [ "$ST" = "CANCELLED" ]; then
    printf '%s' "$S" > /tmp/c766.json
    echo "DONE: $ST"
    exit 0
  fi
done
echo "TIMED OUT still RUNNING" > /tmp/c766.err
