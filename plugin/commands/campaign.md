---
description: "Create or run an Autolab campaign. Usage: /campaign create <name> or /campaign run <path>"
allowed-tools: ["Bash(*)", "Read(*)", "Write(*)", "Edit(*)", "Glob(*)", "Grep(*)"]
---

Handle Autolab campaign operations.

If the first argument is "create":
- Create a new campaign YAML file in campaigns/ with the given name
- Ask what hypothesis to test and what parameters to sweep
- Generate the YAML following the campaign schema in CLAUDE.md

If the first argument is "run":
- Run the campaign: `PYTHONPATH=src python3 -m autolab.cli run <campaign_path>`
- Report results afterward

If the first argument is "list":
- List all campaigns in campaigns/ and their status from results.db

$ARGUMENTS
