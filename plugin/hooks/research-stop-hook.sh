#!/usr/bin/env bash
# Autolab research stop hook — Ralph Wiggum-style loop continuation.
#
# When the agent tries to exit, this hook checks if a research loop is active.
# If so, it increments the iteration counter and re-feeds the research prompt,
# preventing the session from ending until completion criteria are met.

set -euo pipefail

STATE_FILE=".claude/autolab-loop.local.md"

# If no loop state file, allow exit
if [ ! -f "$STATE_FILE" ]; then
    exit 0
fi

# Read state from frontmatter
ACTIVE=$(sed -n 's/^active: *//p' "$STATE_FILE" | head -1)
ITERATION=$(sed -n 's/^iteration: *//p' "$STATE_FILE" | head -1)
MAX_ITERATIONS=$(sed -n 's/^max_iterations: *//p' "$STATE_FILE" | head -1)
COMPLETION_PROMISE=$(sed -n 's/^completion_promise: *//p' "$STATE_FILE" | head -1)

# If not active, allow exit
if [ "$ACTIVE" != "true" ]; then
    exit 0
fi

# Check if max iterations reached
if [ -n "$MAX_ITERATIONS" ] && [ "$MAX_ITERATIONS" != "0" ] && [ "$ITERATION" -ge "$MAX_ITERATIONS" ]; then
    rm -f "$STATE_FILE"
    exit 0
fi

# Check for completion promise in the last assistant message
if [ -n "$COMPLETION_PROMISE" ]; then
    # Read the transcript to check for the promise
    LAST_OUTPUT=$(cat /dev/stdin 2>/dev/null || true)
    if echo "$LAST_OUTPUT" | grep -qF "$COMPLETION_PROMISE"; then
        rm -f "$STATE_FILE"
        exit 0
    fi
fi

# Increment iteration
NEW_ITERATION=$((ITERATION + 1))
sed -i.bak "s/^iteration: .*/iteration: $NEW_ITERATION/" "$STATE_FILE"
rm -f "${STATE_FILE}.bak"

# Extract the prompt (everything after the frontmatter closing ---)
PROMPT=$(sed '1,/^---$/d; 1,/^---$/d' "$STATE_FILE")

# Output JSON to block exit and re-feed the prompt
cat <<EOF
{
  "action": "block",
  "message": "$PROMPT"
}
EOF
