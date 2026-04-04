"""Tests for state management — project state, journal, git."""

import tempfile
from pathlib import Path

import yaml

from autolab.state.project import ProjectState
from autolab.state.journal import Journal
from autolab.state.git import GitOps


class TestProjectState:
    def test_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = ProjectState(tmp)
            s = state.load()
            assert s["iteration"] == 0
            assert s["total_experiments_run"] == 0

    def test_save_and_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = ProjectState(tmp)
            state.save({"iteration": 5, "total_experiments_run": 100})
            s = state.load()
            assert s["iteration"] == 5
            assert s["total_experiments_run"] == 100

    def test_update(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = ProjectState(tmp)
            state.save({"iteration": 1, "foo": "bar"})
            s = state.update(iteration=2, new_key="hello")
            assert s["iteration"] == 2
            assert s["foo"] == "bar"
            assert s["new_key"] == "hello"

    def test_increment(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = ProjectState(tmp)
            state.save({"counter": 5})
            val = state.increment("counter", 3)
            assert val == 8
            s = state.load()
            assert s["counter"] == 8

    def test_increment_new_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = ProjectState(tmp)
            state.save({})
            val = state.increment("new_counter")
            assert val == 1

    def test_check_targets(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            config = {
                "targets": {"min_campaigns": 10, "min_experiments": 100},
            }
            (tmp / "autolab.yaml").write_text(yaml.dump(config))

            state = ProjectState(tmp)
            state.save({"total_campaigns_created": 5, "total_experiments_run": 50})

            targets = state.check_targets()
            assert targets["campaigns_met"] is False
            assert targets["experiments_met"] is False
            assert targets["all_met"] is False

            state.save({"total_campaigns_created": 10, "total_experiments_run": 100})
            targets = state.check_targets()
            assert targets["all_met"] is True


class TestJournal:
    def test_append_and_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "JOURNAL.md").write_text("# Research Journal\n\n---\n")

            j = Journal(tmp)
            j.append_iteration(
                iteration=1,
                summary="First iteration",
                hypothesis="Testing that things work",
                campaigns=[{"name": "test_camp", "experiments": 5, "best": "42"}],
                learnings=["Things work"],
                next_steps=["Try more things"],
            )
            text = j.read()
            assert "## Iteration 1" in text
            assert "First iteration" in text
            assert "test_camp" in text
            assert "Things work" in text

    def test_count_iterations(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "JOURNAL.md").write_text("# Journal\n")

            j = Journal(tmp)
            assert j.count_iterations() == 0

            j.append_iteration(1, "First")
            j.append_iteration(2, "Second")
            assert j.count_iterations() == 2

    def test_read_latest_iteration(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "JOURNAL.md").write_text("# Journal\n")

            j = Journal(tmp)
            j.append_iteration(1, "First")
            j.append_iteration(2, "Latest")

            latest = j.read_latest_iteration()
            assert "Iteration 2" in latest
            assert "Latest" in latest

    def test_nonexistent_journal(self):
        with tempfile.TemporaryDirectory() as tmp:
            j = Journal(tmp)
            assert not j.exists()
            assert j.read() == ""
            assert j.count_iterations() == 0
            assert j.read_latest_iteration() is None


class TestGitOps:
    def test_is_git_repo(self):
        with tempfile.TemporaryDirectory() as tmp:
            git = GitOps(tmp)
            assert not git.is_git_repo()

    def test_init_and_commit(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            git = GitOps(tmp)
            created = git.init()
            assert created is True
            assert git.is_git_repo()

            # No changes yet
            assert not git.has_changes()
            assert git.commit_iteration(1, "test") is None

            # Create a file and commit
            (tmp / "test.txt").write_text("hello")
            assert git.has_changes()
            sha = git.commit_iteration(1, "initial")
            assert sha is not None
            assert len(sha) >= 7

            # No more changes
            assert not git.has_changes()

    def test_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            git = GitOps(tmp)
            git.init()
            (tmp / "a.txt").write_text("a")
            git.commit_iteration(1, "first")
            log = git.log(5)
            assert "research: iteration 1" in log
