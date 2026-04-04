#!/usr/bin/env bash
# Set up an Autolab research loop state file for the Ralph Wiggum hook.
#
# Usage: setup-research-loop.sh [--max-iterations N] [--completion-promise TEXT] PROMPT
#
# Creates .claude/autolab-loop.local.md with frontmatter that the stop hook reads.

set -euo pipefail

MAX_ITERATIONS=0
COMPLETION_PROMISE="RESEARCH COMPLETE"
PROMPT=""

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --max-iterations)
            MAX_ITERATIONS="$2"
            shift 2
            ;;
        --completion-promise)
            COMPLETION_PROMISE="$2"
            shift 2
            ;;
        *)
            PROMPT="$*"
            break
            ;;
    esac
done

if [ -z "$PROMPT" ]; then
    # Default prompt: read RESEARCH_PROMPT.md
    if [ -f "RESEARCH_PROMPT.md" ]; then
        PROMPT="Read RESEARCH_PROMPT.md and follow its instructions exactly. You are running an autonomous research marathon using Autolab."
    else
        PROMPT="Begin an autonomous research loop. Read autolab.yaml for the research directive and follow the research cycle."
    fi
fi

# Create state directory
mkdir -p .claude

# Write state file
cat > .claude/autolab-loop.local.md << ENDOFSTATE
---
active: true
iteration: 1
max_iterations: $MAX_ITERATIONS
completion_promise: $COMPLETION_PROMISE
started_at: $(date -u +"%Y-%m-%dT%H:%M:%SZ")
---

$PROMPT
ENDOFSTATE

echo "Autolab research loop initialized."
echo "  Max iterations: $MAX_ITERATIONS (0 = unlimited)"
echo "  Completion promise: $COMPLETION_PROMISE"
echo "  State file: .claude/autolab-loop.local.md"
