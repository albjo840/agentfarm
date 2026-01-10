#!/bin/bash
# AgentFarm quick status
clear
echo "=== AGENTFARM STATUS ==="
echo ""

# Check if server running
if curl -s http://localhost:8080/ > /dev/null 2>&1; then
    echo "Server: ✅ Running on :8080"
else
    echo "Server: ❌ Not running"
    exit 1
fi

echo ""
echo "=== LLM Models ==="
curl -s http://localhost:8080/api/router 2>/dev/null | python3 -c "
import sys,json
try:
    d=json.load(sys.stdin)
    for name, info in d['models'].items():
        status = '✅' if info['healthy'] else '❌'
        load = f'{info[\"load\"]}/{info[\"max_load\"]}'
        print(f'  {status} {name:15} load:{load}  reqs:{info[\"requests\"]}')
except Exception as e:
    print(f'  Error: {e}')
"

echo ""
echo "=== Recent Events ==="
curl -s "http://localhost:8080/api/events?limit=5" 2>/dev/null | python3 -c "
import sys,json
try:
    d=json.load(sys.stdin)
    print(f'  Processed: {d[\"metrics\"][\"events_processed\"]}')
    for e in d['history'][:3]:
        print(f'  - {e[\"type\"]} from {e[\"source\"]}')
except: pass
"

echo ""
echo "=== Workflows ==="
curl -s http://localhost:8080/api/workflows 2>/dev/null | python3 -c "
import sys,json
try:
    d=json.load(sys.stdin)
    print(f'  Total: {len(d[\"workflows\"])}, Resumable: {d[\"resumable_count\"]}')
except: pass
"
