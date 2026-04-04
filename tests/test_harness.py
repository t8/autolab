"""Tests for the agent harness — tool execution and iteration loop."""

import tempfile
from pathlib import Path

import yaml

from autolab.agents.base import AgentMessage, ToolCall
from autolab.agents.harness import ToolExecutor, AgentHarness
from autolab.metrics.db import ResultsDB
from tests.test_agents import MockAgent


class TestToolExecutor:
    def _make_executor(self, tmp: Path) -> ToolExecutor:
        db = ResultsDB(tmp / "results.db")
        return ToolExecutor(tmp, db)

    def test_read_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "test.txt").write_text("hello world")
            executor = self._make_executor(tmp)
            result = executor.execute(ToolCall(id="t1", name="read_file", arguments={"path": "test.txt"}))
            assert result.output == "hello world"
            assert not result.is_error

    def test_read_file_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            executor = self._make_executor(Path(tmp))
            result = executor.execute(ToolCall(id="t1", name="read_file", arguments={"path": "nope.txt"}))
            assert "not found" in result.output

    def test_write_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            executor = self._make_executor(tmp)
            result = executor.execute(ToolCall(
                id="t1", name="write_file",
                arguments={"path": "out.txt", "content": "data"},
            ))
            assert "Written" in result.output
            assert (tmp / "out.txt").read_text() == "data"

    def test_write_file_nested(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            executor = self._make_executor(tmp)
            executor.execute(ToolCall(
                id="t1", name="write_file",
                arguments={"path": "sub/dir/file.txt", "content": "nested"},
            ))
            assert (tmp / "sub" / "dir" / "file.txt").read_text() == "nested"

    def test_run_shell(self):
        with tempfile.TemporaryDirectory() as tmp:
            executor = self._make_executor(Path(tmp))
            result = executor.execute(ToolCall(
                id="t1", name="run_shell",
                arguments={"command": "echo 'hello from shell'"},
            ))
            assert "hello from shell" in result.output

    def test_get_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / ".autolab").mkdir()
            executor = self._make_executor(tmp)
            result = executor.execute(ToolCall(id="t1", name="get_status", arguments={}))
            assert "Iteration:" in result.output
            assert "Total experiments:" in result.output

    def test_complete_iteration(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / ".autolab").mkdir()
            executor = self._make_executor(tmp)
            assert not executor.iteration_complete
            result = executor.execute(ToolCall(
                id="t1", name="complete_iteration",
                arguments={"summary": "tested things"},
            ))
            assert executor.iteration_complete
            assert "complete" in result.output.lower()

    def test_unknown_tool(self):
        with tempfile.TemporaryDirectory() as tmp:
            executor = self._make_executor(Path(tmp))
            result = executor.execute(ToolCall(id="t1", name="nonexistent", arguments={}))
            assert result.is_error
            assert "Unknown tool" in result.output

    def test_run_campaign(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            campaign = {
                "name": "harness_test",
                "grid": {"x": [1, 2]},
                "runner": {"backend": "local", "command": "echo 'Score: {x}'"},
                "metrics": {
                    "primary": "score",
                    "direction": "maximize",
                    "collect": [{"name": "score", "pattern": r"Score: (\d+)", "type": "int"}],
                },
            }
            (tmp / "campaigns").mkdir()
            (tmp / "campaigns" / "test.yaml").write_text(yaml.dump(campaign))

            executor = self._make_executor(tmp)
            result = executor.execute(ToolCall(
                id="t1", name="run_campaign",
                arguments={"campaign_path": "campaigns/test.yaml"},
            ))
            assert "complete" in result.output.lower()
            assert "2 completed" in result.output


class TestAgentHarness:
    def test_single_iteration_no_tools(self):
        """Agent responds without tool calls — iteration ends."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            agent = MockAgent([
                AgentMessage(role="assistant", content="Nothing to do."),
            ])
            harness = AgentHarness(agent, tmp)
            result = harness.run_iteration("system prompt", "user prompt")
            assert result == "Nothing to do."

    def test_iteration_with_tool_call(self):
        """Agent calls a tool, gets result, then completes."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "data.txt").write_text("file contents")

            agent = MockAgent([
                AgentMessage(
                    role="assistant",
                    content="Reading file...",
                    tool_calls=[ToolCall(id="t1", name="read_file", arguments={"path": "data.txt"})],
                ),
                AgentMessage(role="assistant", content="Got the file."),
            ])
            harness = AgentHarness(agent, tmp)
            result = harness.run_iteration("sys", "usr")
            assert result == "Got the file."

    def test_iteration_completes_on_complete_iteration_tool(self):
        """Harness stops looping when complete_iteration is called."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / ".autolab").mkdir()

            agent = MockAgent([
                AgentMessage(
                    role="assistant",
                    content="Finishing up",
                    tool_calls=[ToolCall(
                        id="t1", name="complete_iteration",
                        arguments={"summary": "done"},
                    )],
                ),
                # This should NOT be reached
                AgentMessage(role="assistant", content="SHOULD NOT SEE THIS"),
            ])
            harness = AgentHarness(agent, tmp)
            harness.run_iteration("sys", "usr")
            assert harness.executor.iteration_complete
