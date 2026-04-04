#!/usr/bin/env bash
# Check Autolab research progress against targets.
#
# Reads .autolab/state.json and autolab.yaml, reports whether
# campaign and experiment targets are met.

set -euo pipefail

STATE_FILE=".autolab/state.json"
CONFIG_FILE="autolab.yaml"

if [ ! -f "$STATE_FILE" ]; then
    echo "No state file found. Run some research iterations first."
    exit 0
fi

if [ ! -f "$CONFIG_FILE" ]; then
    echo "No autolab.yaml found."
    exit 0
fi

# Extract values (portable: no jq dependency)
ITERATION=$(python3 -c "import json; print(json.load(open('$STATE_FILE')).get('iteration', 0))" 2>/dev/null || echo "?")
EXPERIMENTS=$(python3 -c "import json; print(json.load(open('$STATE_FILE')).get('total_experiments_run', 0))" 2>/dev/null || echo "?")
CAMPAIGNS=$(python3 -c "import json; print(json.load(open('$STATE_FILE')).get('total_campaigns_created', 0))" 2>/dev/null || echo "?")
DISCOVERIES=$(python3 -c "import json; print(json.load(open('$STATE_FILE')).get('total_discoveries', 0))" 2>/dev/null || echo "?")
MOONSHOTS=$(python3 -c "import json; print(json.load(open('$STATE_FILE')).get('moonshot_count', 0))" 2>/dev/null || echo "?")
NON_MOONSHOTS=$(python3 -c "import json; print(json.load(open('$STATE_FILE')).get('non_moonshot_count', 0))" 2>/dev/null || echo "?")
NO_IMPROVE=$(python3 -c "import json; print(json.load(open('$STATE_FILE')).get('consecutive_no_improvement', 0))" 2>/dev/null || echo "?")

# Extract targets from config
TARGET_CAMPAIGNS=$(python3 -c "import yaml; print(yaml.safe_load(open('$CONFIG_FILE')).get('targets',{}).get('min_campaigns', 0))" 2>/dev/null || echo "?")
TARGET_EXPERIMENTS=$(python3 -c "import yaml; print(yaml.safe_load(open('$CONFIG_FILE')).get('targets',{}).get('min_experiments', 0))" 2>/dev/null || echo "?")
TARGET_MOONSHOT=$(python3 -c "import yaml; print(yaml.safe_load(open('$CONFIG_FILE')).get('strategy',{}).get('moonshot_ratio', 0.5))" 2>/dev/null || echo "?")

echo "=== Autolab Research Progress ==="
echo ""
echo "Iteration:     $ITERATION"
echo "Experiments:   $EXPERIMENTS / $TARGET_EXPERIMENTS"
echo "Campaigns:     $CAMPAIGNS / $TARGET_CAMPAIGNS"
echo "Discoveries:   $DISCOVERIES"
echo "Moonshots:     $MOONSHOTS / $(($MOONSHOTS + $NON_MOONSHOTS)) (target: ${TARGET_MOONSHOT})"
echo "No-improvement streak: $NO_IMPROVE"
echo ""

# Check targets
if [ "$EXPERIMENTS" != "?" ] && [ "$TARGET_EXPERIMENTS" != "?" ]; then
    if [ "$EXPERIMENTS" -ge "$TARGET_EXPERIMENTS" ] 2>/dev/null; then
        echo "[OK] Experiment target met"
    else
        echo "[..] Experiments: $((TARGET_EXPERIMENTS - EXPERIMENTS)) remaining"
    fi
fi

if [ "$CAMPAIGNS" != "?" ] && [ "$TARGET_CAMPAIGNS" != "?" ]; then
    if [ "$CAMPAIGNS" -ge "$TARGET_CAMPAIGNS" ] 2>/dev/null; then
        echo "[OK] Campaign target met"
    else
        echo "[..] Campaigns: $((TARGET_CAMPAIGNS - CAMPAIGNS)) remaining"
    fi
fi
