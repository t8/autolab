"""Agent harness — tool-use loop that drives research iterations for API backends."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from .base import AgentBackend, AgentMessage, ToolCall, ToolResult, RESEARCH_TOOLS
from ..core.loop import ResearchLoop
from ..metrics.db import ResultsDB
from ..state.project import ProjectState


class ToolExecutor:
    """Executes tool calls from the agent in the project directory."""

    def __init__(self, project_dir: Path, db: ResultsDB):
        self.project_dir = project_dir
        self.db = db
        self.loop = ResearchLoop(db.db_path)
        self.state = ProjectState(project_dir)
        self._iteration_complete = False

    @property
    def iteration_complete(self) -> bool:
        return self._iteration_complete

    def execute(self, tool_call: ToolCall) -> ToolResult:
        """Execute a single tool call and return the result."""
        try:
            handler = getattr(self, f"_tool_{tool_call.name}", None)
            if handler is None:
                return ToolResult(
                    tool_call_id=tool_call.id,
                    output=f"Unknown tool: {tool_call.name}",
                    is_error=True,
                )
            output = handler(**tool_call.arguments)
            return ToolResult(
                tool_call_id=tool_call.id,
                output=str(output),
            )
        except Exception as e:
            return ToolResult(
                tool_call_id=tool_call.id,
                output=f"Error: {e}",
                is_error=True,
            )

    def _tool_run_campaign(self, campaign_path: str) -> str:
        full_path = self.project_dir / campaign_path
        if not full_path.exists():
            return f"Campaign file not found: {campaign_path}"
        results = self.loop.run_campaign(str(full_path))
        completed = sum(1 for r in results if r.status == "completed")
        failed = sum(1 for r in results if r.status == "failed")
        summary_lines = [f"Campaign complete: {completed} completed, {failed} failed"]
        for r in results:
            metrics_str = ", ".join(f"{k}={v}" for k, v in r.metrics.items())
            summary_lines.append(f"  [{r.status}] {r.experiment_name}: {metrics_str}")
        return "\n".join(summary_lines)

    def _tool_query_results(
        self,
        campaign_name: str | None = None,
        metric: str | None = None,
        direction: str = "maximize",
        limit: int = 10,
    ) -> str:
        if metric:
            rows = self.db.best_by_metric(metric, direction, campaign_name, limit)
            lines = [f"Top {len(rows)} by {metric} ({direction}):"]
            for r in rows:
                lines.append(f"  {r['experiment_name']}: {metric}={r.get('metric_value', 'N/A')}")
            return "\n".join(lines)
        else:
            history = self.db.load_history(campaign_name)
            lines = [f"Total: {len(history)} experiments"]
            for r in history[-limit:]:
                metrics_str = ", ".join(f"{k}={v}" for k, v in r.get("metrics", {}).items())
                lines.append(f"  [{r['status']}] {r['experiment_name']}: {metrics_str}")
            return "\n".join(lines)

    def _tool_read_file(self, path: str) -> str:
        full_path = self.project_dir / path
        if not full_path.exists():
            return f"File not found: {path}"
        try:
            return full_path.read_text()
        except Exception as e:
            return f"Error reading {path}: {e}"

    def _tool_write_file(self, path: str, content: str) -> str:
        full_path = self.project_dir / path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content)
        return f"Written {len(content)} bytes to {path}"

    def _tool_run_shell(self, command: str, working_dir: str | None = None) -> str:
        cwd = self.project_dir / working_dir if working_dir else self.project_dir
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                cwd=str(cwd),
                timeout=120,
            )
            output = result.stdout
            if result.stderr:
                output += f"\nSTDERR:\n{result.stderr}"
            if result.returncode != 0:
                output += f"\n(exit code {result.returncode})"
            return output or "(no output)"
        except subprocess.TimeoutExpired:
            return "Command timed out after 120s"

    def _tool_get_status(self) -> str:
        state = self.state.load()
        total = self.db.count_experiments()
        history = self.db.load_history()
        campaigns = set(r.get("campaign_name") for r in history)

        lines = [
            f"Iteration: {state.get('iteration', 0)}",
            f"Total experiments: {total}",
            f"Total campaigns: {len(campaigns)}",
            f"Discoveries: {state.get('total_discoveries', 0)}",
            f"Consecutive no improvement: {state.get('consecutive_no_improvement', 0)}",
            f"Moonshot ratio: {state.get('moonshot_count', 0)} / "
            f"{state.get('moonshot_count', 0) + state.get('non_moonshot_count', 0)}",
        ]
        return "\n".join(lines)

    def _tool_complete_iteration(self, summary: str) -> str:
        self._iteration_complete = True
        state = self.state.load()
        state["iteration"] = state.get("iteration", 0) + 1
        state["total_experiments_run"] = self.db.count_experiments()
        self.state.save(state)
        return f"Iteration {state['iteration']} complete: {summary}"


class AgentHarness:
    """Drives the research loop by sending prompts to an LLM and executing tool calls.

    This is the main entry point for API-based agent backends (Anthropic, OpenAI).
    The Claude Code plugin path uses Ralph Wiggum loops instead.
    """

    def __init__(
        self,
        agent: AgentBackend,
        project_dir: str | Path,
        db_path: str | Path | None = None,
        max_tool_rounds: int = 50,
    ):
        self.agent = agent
        self.project_dir = Path(project_dir).resolve()
        self.db = ResultsDB(db_path or self.project_dir / "results.db")
        self.executor = ToolExecutor(self.project_dir, self.db)
        self.max_tool_rounds = max_tool_rounds

    def run_iteration(self, system_prompt: str, user_prompt: str) -> str:
        """Run a single research iteration.

        Sends the prompt to the agent, then loops executing tool calls
        until the agent calls complete_iteration or runs out of rounds.

        Returns the agent's final text response.
        """
        messages: list[AgentMessage] = [
            AgentMessage(role="system", content=system_prompt),
            AgentMessage(role="user", content=user_prompt),
        ]

        tools = RESEARCH_TOOLS
        final_text = ""

        for round_num in range(self.max_tool_rounds):
            response = self.agent.send(messages, tools)
            messages.append(response)

            if response.content:
                final_text = response.content
                print(f"\n[Agent] {response.content[:200]}...")

            if not response.tool_calls:
                break

            for tc in response.tool_calls:
                print(f"  [Tool] {tc.name}({json.dumps(tc.arguments)[:100]})")
                result = self.executor.execute(tc)
                print(f"  [Result] {result.output[:200]}...")
                messages.append(AgentMessage(
                    role="tool",
                    tool_result=result,
                ))

            if self.executor.iteration_complete:
                break

        return final_text

    def run_loop(
        self,
        max_iterations: int = 10,
        system_prompt: str | None = None,
        user_prompt: str | None = None,
    ) -> None:
        """Run multiple research iterations in a loop.

        If no prompts provided, reads RESEARCH_PROMPT.md from the project.
        """
        if system_prompt is None:
            prompt_path = self.project_dir / "RESEARCH_PROMPT.md"
            if prompt_path.exists():
                system_prompt = prompt_path.read_text()
            else:
                system_prompt = "You are an autonomous research agent. Follow the research cycle."

        if user_prompt is None:
            config_path = self.project_dir / "autolab.yaml"
            if config_path.exists():
                import yaml
                config = yaml.safe_load(config_path.read_text())
                directive = config.get("directive", "Conduct research")
            else:
                directive = "Conduct research"
            user_prompt = (
                f"Research directive: {directive}\n\n"
                "Begin a new research iteration. Follow the cycle in the system prompt exactly."
            )

        print(f"\nAutolab research loop — {self.agent.model_name()}")
        print(f"Project: {self.project_dir}")
        print(f"Max iterations: {max_iterations}\n")

        for i in range(max_iterations):
            print(f"\n{'=' * 60}")
            print(f"ITERATION {i + 1}/{max_iterations}")
            print(f"{'=' * 60}")

            self.executor._iteration_complete = False
            self.run_iteration(system_prompt, user_prompt)

            if not self.executor.iteration_complete:
                print("\nAgent did not call complete_iteration. Stopping loop.")
                break

        print(f"\nResearch loop finished after {i + 1} iterations.")
        print(f"Total experiments: {self.db.count_experiments()}")
