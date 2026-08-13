# CLAUDE.md

Project guide for agents working on autolab.

## What is autolab

Autonomous research orchestration framework. It takes a research goal and runs the full cycle: hypothesis formation, campaign design, experiment execution, result analysis, and discovery documentation. Built on Karpathy's autoresearch concept, extended to multi-question research programs.

## Quick orientation

```
src/autolab/
  cli.py              CLI entry point (init, run, status, results, tree, loop)
  core/               Campaign engine, research loop, plan, scheduler
  agents/             LLM backends (Anthropic, OpenAI, compatible APIs)
  runners/            Experiment execution (local, SSH)
  metrics/            Collectors, SQLite DB, trend analysis
  intelligence/       Escape strategies, discovery management, literature search
  state/              Project state, journal, git integration
  scaffold/           Project init templates (Jinja2)
  viz/                Tree visualization (DOT + PIL compositing)
plugin/               Claude Code plugin (commands, skills, hooks)
examples/             3 example projects (ml-optimization, distributed-inference, algorithm-design)
tests/                126 tests across 13 files
```

## How to run

```bash
pip install -e .                              # Install in dev mode (requires Python >=3.10)
autolab init "research goal"                  # Scaffold a project
autolab run campaigns/000_example.yaml        # Run a campaign
autolab status                                # Check progress
autolab results --metric throughput --top 5   # Query results
autolab tree --render tree.png                # Visualize research tree
autolab loop --backend anthropic              # Autonomous research loop
pytest tests/ -v                              # Run tests
```

## Architecture

### Campaign execution flow
1. Campaign YAML defines a parameter grid (Cartesian product of all values)
2. `ResearchLoop` iterates: picks next unrun experiment, runs it, collects metrics via regex on stdout, stores in SQLite
3. Early stopping via diminishing returns detection (configurable window + threshold)
4. Results stored in `results.db` with two tables: `experiments` (full data) and `metric_values` (fast queries)

### Parameter templating
Commands use `str.format(**experiment)` — grid params are injected directly:
```yaml
command: "python train.py --lr {lr} --batch-size {batch_size}"
grid:
  lr: [0.01, 0.001]
  batch_size: [32, 64]
```
This creates 4 experiments. Params also exported as `AUTOLAB_PARAM_*` env vars.

### Agent tool loop
The LLM agent gets 7 tools: `run_campaign`, `query_results`, `read_file`, `write_file`, `run_shell`, `get_status`, `complete_iteration`. The harness runs up to 50 tool rounds per iteration, breaking when the agent calls `complete_iteration`.

`AgentHarness.run_iteration` accumulates messages and replays the **entire history** on every round. Any per-message field a provider requires on replay must therefore survive the round trip — see `AgentMessage.reasoning_content`.

### Thinking-mode models (DeepSeek V4)
DeepSeek's V4 family defaults thinking ON when `extra_body.thinking` is unset, returns `reasoning_content`, and then enforces that later turns echo it back. Combined with full-history replay, a backend that drops the field hits HTTP 400 `reasoning_content must be passed back` right after the first tool call.

`OpenAIAgent` handles this by (a) always sending `extra_body.thinking` explicitly for V4+ models, (b) mapping `reasoning_effort` (`xhigh`/`max`/`ultra` → `max`), and (c) capturing `reasoning_content` off the response and echoing it back on replay. Detection is substring-based so routed ids (`deepseek/deepseek-v4-pro` via OpenRouter) behave like native ones; `deepseek-v3*` is excluded so the V3 wire format is untouched. This mirrors the profile in Hermes' `plugins/model-providers/deepseek` so both agents on the droplet speak the same wire format. Pinned by `tests/test_deepseek_wire.py` (fake client — no live API).

### Research state
Each autolab project has:
- `.autolab/state.json` — machine state (iteration counter, experiment counts)
- `research_plan.yaml` — questions with status, priority, dependencies
- `JOURNAL.md` — human-readable iteration log
- `DISCOVERIES.md` — verified novel findings with prior art
- `results.db` — SQLite experiment results
- `campaigns/*.yaml` — experiment designs

### Moonshot enforcement
50% of campaigns (configurable) must be moonshots — experiments that challenge assumptions rather than incrementally tweak parameters. The scheduler enforces this ratio via scoring bonuses/penalties.

### Escape detection
When stuck for 3+ iterations (no metric improvement), the system recommends: literature search, devil's advocate, random perturbation (2x/0.5x ranges), or pivot to a new question.

## Tree visualization

The `autolab tree` command and `viz/tree.py` module render a phylogenetic-style research tree. The rendering pipeline:
1. `build_tree()` — builds tree from research_plan.yaml + campaigns + results.db
2. `render_dot()` — generates Graphviz DOT with heatmap coloring (dark green=best, red=worst), translucent nodes, score-proportional alpha
3. `render_to_png()` — composites layers via PIL: dark background + separator lines (behind) + graphviz output (transparent bg) + stage titles + footer
4. Requires: `graphviz` (brew install graphviz) and `Pillow` (pip install Pillow)

The heatmap scores experiments 0-1 within each campaign. Best-path campaigns use score range 0.55-1.0, others use 0.0-0.7. Global best gets fully opaque darkest green with bright accent border.

## Campaign YAML schema

```yaml
version: 1
name: campaign_name
hypothesis: "Testable claim"
question: q1                    # Links to research_plan.yaml
moonshot: false

runner:
  backend: local|ssh
  command: "cmd {param}"
  working_dir: .
  timeout_seconds: 3600

defaults:
  seed: 42

grid:
  param_a: [1, 2, 3]
  param_b: [x, y]

metrics:
  primary: throughput
  direction: maximize|minimize
  collect:
    - name: throughput
      pattern: "Throughput: ([\\d.]+)"
      type: float|int|str
      source: stdout|stderr

stopping:
  window: 3
  threshold: 0.05
  max_failures: 3
```

## Dependencies

Core: pyyaml, jinja2, click. Optional: anthropic, openai (for agent backends). Dev: pytest, pytest-cov. Visualization: graphviz (system), Pillow (Python).

## Conventions

- Tests live in `tests/` and mirror the source structure
- Campaign files are numbered: `NNN_descriptive_name.yaml`
- Moonshot campaigns use numbers 050+
- Git commits after each research iteration: `research: description`
- Discoveries include prior art verification and Autolab attribution
