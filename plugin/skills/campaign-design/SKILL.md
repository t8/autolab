---
name: Autolab Campaign Design
description: This skill should be used when the user asks to "design a campaign", "create experiment campaign", "plan experiments", "set up parameter sweep", "design parameter grid". It guides designing effective Autolab campaign YAML files.
version: 0.1.0
---

Design an effective Autolab experiment campaign.

## Campaign Design Principles

1. **Hypothesis-first**: Every campaign starts with a testable hypothesis. Write it before choosing parameters.

2. **Isolate variables**: Each campaign should test one primary variable. Use defaults to hold everything else constant.

3. **Grid sizing**: Aim for 5-20 experiments per campaign. Fewer is too sparse to draw conclusions. More wastes time before analysis.

4. **Moonshot ratio**: Check if the project needs more moonshots (`.autolab/state.json` vs `autolab.yaml` target). If so, design a campaign that challenges fundamental assumptions rather than incrementally tweaking parameters.

5. **Metric selection**: Choose a primary metric that directly measures what the hypothesis predicts. Add secondary metrics for context.

## Campaign YAML Schema

```yaml
version: 1
name: descriptive_snake_case_name       # Unique, describes what's tested
hypothesis: "Clear testable prediction"  # What you expect to find and why
question: q1                             # Links to research_plan.yaml
moonshot: false                          # true = fundamentally different approach

runner:
  backend: local                         # local | ssh
  command: "python experiment.py --param {grid_param}"
  working_dir: ./experiments
  timeout_seconds: 3600

defaults:                                # Fixed across all experiments
  seed: 42
  epochs: 10

grid:                                    # Cartesian product of values
  learning_rate: [0.1, 0.01, 0.001]
  batch_size: [16, 32, 64]
  # -> 9 experiments

metrics:
  primary: throughput                    # For early stopping + best result
  direction: maximize                    # maximize | minimize
  collect:
    - name: throughput
      source: stdout
      pattern: "Throughput: ([\\d.]+)"
      type: float
    - name: loss
      source: stdout
      pattern: "Loss: ([\\d.]+)"
      type: float

stopping:
  window: 3                              # Check last N experiments
  threshold: 0.05                        # Stop if <5% improvement
  max_failures: 3                        # Stop after N consecutive failures
```

## SSH Runner Configuration

For remote experiments:
```yaml
runner:
  backend: ssh
  host: gpu-server.lab
  user: researcher
  key_path: ~/.ssh/lab_key
  command: "python train.py --lr {learning_rate}"
  working_dir: /home/researcher/experiments
  deploy_files:
    - local: experiments/train.py
      remote: /home/researcher/train.py
  cleanup_command: "rm -f /tmp/experiment_lock"
  timeout_seconds: 7200
```

## Metric Extraction

The experiment command writes to stdout. Autolab parses metrics using regex:
- Pattern must have exactly one capture group `(...)` for the value
- Type can be `float`, `int`, or `str`
- Source is `stdout` (default) or `stderr`

For structured output, write a JSON file and use the file collector pattern.

## Naming Convention

Name campaigns as `NNN_description.yaml` where NNN is a sequential number:
- `000_example.yaml`
- `001_baseline_throughput.yaml`
- `002_batch_size_sweep.yaml`
- `050_moonshot_sparse_attention.yaml`

## After Creating

1. Link the campaign to a question: update `research_plan.yaml`
2. Run it: `PYTHONPATH=src python3 -m autolab.cli run campaigns/<name>.yaml`
3. Analyze results: `PYTHONPATH=src python3 -m autolab.cli results --campaign <name> --metric <primary>`
