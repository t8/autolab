---
name: Autolab Research Loop
description: This skill should be used when the user asks to "run research", "start research loop", "autolab loop", "autonomous research", "research marathon", "run experiments autonomously". It provides the protocol for autonomous research iteration using Autolab.
version: 0.1.0
---

Execute the Autolab autonomous research loop. Each iteration follows this exact cycle:

## Step 0: Orient

Read the current state before doing anything:
- Read `JOURNAL.md` for past iterations' learnings
- Read `DISCOVERIES.md` for verified novel findings
- Run `PYTHONPATH=src python3 -m autolab.cli status` for experiment counts
- Read `research_plan.yaml` for current question decomposition
- Read `.autolab/state.json` for machine-readable progress
- Run `git log --oneline -20` for recent commits

## Step 1: Hypothesize

- Review `research_plan.yaml` for active questions
- If no active questions, decompose the research directive (from `autolab.yaml`) into 3-5 testable questions and write them to `research_plan.yaml`
- Form a testable hypothesis targeting the highest-priority runnable question
- Write the hypothesis in `JOURNAL.md` BEFORE proceeding to design

## Step 2: Design Campaign

Choose a path:
- **Path A**: New campaign YAML in `campaigns/` (parameter exploration)
- **Path B**: Code change in `experiments/` + campaign (algorithmic exploration)
- **Path C**: Fundamentally different approach (moonshot)

Check the moonshot ratio in `.autolab/state.json`. If below the target in `autolab.yaml` (default 50%), design a moonshot campaign.

Campaign YAML format:
```yaml
version: 1
name: descriptive_name
hypothesis: "What I expect to find"
question: q1
moonshot: false
runner:
  backend: local
  command: "python experiments/script.py --param {param}"
  working_dir: .
  timeout_seconds: 3600
defaults:
  fixed_param: value
grid:
  variable_param: [val1, val2, val3]
metrics:
  primary: metric_name
  direction: maximize
  collect:
    - name: metric_name
      pattern: "Metric: ([\\d.]+)"
stopping:
  window: 3
  threshold: 0.05
  max_failures: 3
```

## Step 3: Execute

```bash
PYTHONPATH=src python3 -m autolab.cli run campaigns/<name>.yaml
```

If a campaign fails twice, skip it and try a different approach.

## Step 4: Analyze & Record

Query results:
```bash
PYTHONPATH=src python3 -m autolab.cli results --campaign <name> --metric <primary> --top 5
```

- Confirm or refute the hypothesis
- Update `JOURNAL.md` with iteration number, hypothesis, results, key learnings
- If a novel finding: add to `DISCOVERIES.md` using the template (include prior art search)
- Update `research_plan.yaml` — answer questions, spawn sub-questions
- Update `.autolab/state.json` — increment iteration, update moonshot counts
- Commit: `git add -A && git commit -m "research: <description>"`

## Escape Protocol

If `consecutive_no_improvement` in `.autolab/state.json` reaches 3:
1. Search the web for alternative approaches
2. Write a "devil's advocate" journal entry
3. Add a new research question to `research_plan.yaml`
4. Design a moonshot campaign testing the opposite assumption

## Completion

Continue iterating until the targets in `autolab.yaml` are met (check with `cat .autolab/state.json`).
