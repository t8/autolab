---
description: "Show Autolab research status — experiments, campaigns, progress toward targets, moonshot ratio."
allowed-tools: ["Bash(*)", "Read(*)"]
---

Show the current Autolab research status.

Run these commands and summarize the output:

1. `PYTHONPATH=src python3 -m autolab.cli status` — experiment and campaign counts
2. `cat .autolab/state.json` — iteration count, moonshot ratio, consecutive no-improvement
3. `cat research_plan.yaml` — active questions and their status
4. Check moonshot ratio against target in autolab.yaml

Present a concise summary with:
- Total experiments and campaigns
- Current iteration number
- Active research questions
- Moonshot ratio (current vs target)
- Whether targets are met

$ARGUMENTS
