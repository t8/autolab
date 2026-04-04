---
description: "Start an autonomous research loop using the Ralph Wiggum technique. The agent reads RESEARCH_PROMPT.md and iterates: orient → hypothesize → design → execute → analyze → document → commit."
allowed-tools: ["Bash(*)", "Read(*)", "Write(*)", "Edit(*)", "Glob(*)", "Grep(*)"]
---

Start an autonomous Autolab research loop.

1. Read RESEARCH_PROMPT.md and follow its instructions exactly.
2. You are running an autonomous research marathon using Autolab.
3. Each iteration follows the cycle: Orient → Hypothesize → Design Campaign → Execute → Analyze → Document → Commit.

Pass any arguments after the command as the research directive override. If no arguments provided, use the directive from autolab.yaml.

Execute: Read the file "RESEARCH_PROMPT.md" and begin following its research cycle. If RESEARCH_PROMPT.md does not exist, read autolab.yaml for the research directive and begin the cycle from Step 0 (Orient).

$ARGUMENTS
