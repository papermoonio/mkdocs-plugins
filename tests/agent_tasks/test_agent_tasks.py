import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from plugins.agent_tasks.plugin import AgentTasksPlugin

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_plugin(**overrides):
    """Return a plugin instance with a minimal config dict."""
    plugin = AgentTasksPlugin()
    plugin.config = {"agent_tasks_config": "agent_tasks_config.json", **overrides}
    return plugin


def _minimal_task(**overrides):
    """Return a task dict with only the required fields."""
    task = {
        "id": "test-task",
        "title": "Test Task",
        "objective": "Verify the plugin works",
    }
    task.update(overrides)
    return task


REFERENCE_REPOS = {
    "demo-repo": {
        "url": "https://github.com/org/demo-repo",
        "raw_base_url": "https://raw.githubusercontent.com/org/demo-repo/main",
    }
}

PROJECT = {"id": "test-project", "name": "Test Project"}


# ---------------------------------------------------------------------------
# TestBuildRawUrl
# ---------------------------------------------------------------------------


class TestBuildRawUrl:
    """Tests for _build_raw_url URL construction."""

    def setup_method(self):
        self.plugin = _make_plugin()

    def test_basic_url(self):
        ref_code = {"repo": "demo-repo", "base_path": "src"}
        result = self.plugin._build_raw_url(REFERENCE_REPOS, ref_code, "index.ts")
        assert (
            result
            == "https://raw.githubusercontent.com/org/demo-repo/main/src/index.ts"
        )

    def test_nested_file_path(self):
        ref_code = {"repo": "demo-repo", "base_path": "packages/core"}
        result = self.plugin._build_raw_url(REFERENCE_REPOS, ref_code, "lib/utils.ts")
        assert result == (
            "https://raw.githubusercontent.com/org/demo-repo/main"
            "/packages/core/lib/utils.ts"
        )

    def test_unknown_repo_returns_partial_url(self):
        ref_code = {"repo": "missing-repo", "base_path": "src"}
        result = self.plugin._build_raw_url(REFERENCE_REPOS, ref_code, "app.py")
        assert result == "/src/app.py"

    def test_empty_base_path(self):
        ref_code = {"repo": "demo-repo", "base_path": ""}
        result = self.plugin._build_raw_url(REFERENCE_REPOS, ref_code, "README.md")
        assert result == (
            "https://raw.githubusercontent.com/org/demo-repo/main//README.md"
        )


# ---------------------------------------------------------------------------
# TestRenderTaskFrontmatter
# ---------------------------------------------------------------------------


class TestRenderTaskFrontmatter:
    """Tests for YAML frontmatter in rendered task output."""

    def setup_method(self):
        self.plugin = _make_plugin()

    def _frontmatter(self, content):
        """Extract the YAML frontmatter block from rendered content."""
        parts = content.split("---")
        return parts[1] if len(parts) >= 3 else ""

    def test_contains_required_fields(self):
        task = _minimal_task()
        content = self.plugin._render_task(task, PROJECT, {})
        fm = self._frontmatter(content)
        assert "task_id: test-task" in fm
        assert 'title: "Test Task"' in fm
        assert 'objective: "Verify the plugin works"' in fm
        assert "estimated_steps: 0" in fm
        assert "generated:" in fm

    def test_includes_reference_repo_when_present(self):
        task = _minimal_task(reference_code={"repo": "demo-repo", "base_path": "src"})
        content = self.plugin._render_task(task, PROJECT, REFERENCE_REPOS)
        fm = self._frontmatter(content)
        assert "reference_repo: https://github.com/org/demo-repo" in fm

    def test_omits_reference_repo_when_missing(self):
        task = _minimal_task()
        content = self.plugin._render_task(task, PROJECT, {})
        fm = self._frontmatter(content)
        assert "reference_repo" not in fm

    def test_prerequisites_not_in_frontmatter(self):
        task = _minimal_task(prerequisites={"tools": ["Node.js >= 18", "npm"]})
        content = self.plugin._render_task(task, PROJECT, {})
        fm = self._frontmatter(content)
        assert "prerequisites" not in fm

    def test_estimated_steps_matches_step_count(self):
        steps = [
            {"order": 1, "action": "Init"},
            {"order": 2, "action": "Build"},
        ]
        task = _minimal_task(steps=steps)
        content = self.plugin._render_task(task, PROJECT, {})
        fm = self._frontmatter(content)
        assert "estimated_steps: 2" in fm


# ---------------------------------------------------------------------------
# TestRenderTaskPrerequisites
# ---------------------------------------------------------------------------


class TestRenderTaskPrerequisites:
    """Tests for the Prerequisites body section."""

    def setup_method(self):
        self.plugin = _make_plugin()

    def test_renders_grouped_prerequisites(self):
        task = _minimal_task(
            prerequisites={
                "tools": ["Node.js >= 18", "npm"],
                "accounts": ["GitHub account"],
            }
        )
        content = self.plugin._render_task(task, PROJECT, {})
        assert "## Prerequisites" in content
        assert "**Tools:**" in content
        assert "- Node.js >= 18" in content
        assert "- npm" in content
        assert "**Accounts:**" in content
        assert "- GitHub account" in content

    def test_omits_section_when_no_prerequisites(self):
        task = _minimal_task()
        content = self.plugin._render_task(task, PROJECT, {})
        assert "## Prerequisites" not in content

    def test_omits_section_when_prerequisites_empty(self):
        task = _minimal_task(prerequisites={})
        content = self.plugin._render_task(task, PROJECT, {})
        assert "## Prerequisites" not in content


# ---------------------------------------------------------------------------
# TestRenderTaskEnvVars
# ---------------------------------------------------------------------------


class TestRenderTaskEnvVars:
    """Tests for the Environment Variables section."""

    def setup_method(self):
        self.plugin = _make_plugin()

    def test_renders_env_vars(self):
        task = _minimal_task(
            env_vars=[
                {"name": "API_KEY", "description": "Your API key", "required": True},
                {
                    "name": "DEBUG",
                    "description": "Enable debug mode",
                    "required": False,
                },
            ]
        )
        content = self.plugin._render_task(task, PROJECT, {})
        assert "## Environment Variables" in content
        assert "```env" in content
        assert "# Your API key (required)" in content
        assert "API_KEY=" in content
        assert "# Enable debug mode (optional)" in content
        assert "DEBUG=" in content

    def test_omits_section_when_no_env_vars(self):
        task = _minimal_task()
        content = self.plugin._render_task(task, PROJECT, {})
        assert "## Environment Variables" not in content


# ---------------------------------------------------------------------------
# TestRenderTaskSteps
# ---------------------------------------------------------------------------


class TestRenderTaskSteps:
    """Tests for the Execution Steps section."""

    def setup_method(self):
        self.plugin = _make_plugin()

    def test_renders_step_with_all_fields(self):
        task = _minimal_task(
            reference_code={
                "repo": "demo-repo",
                "base_path": "src",
                "files": [],
            },
            steps=[
                {
                    "order": 1,
                    "action": "Initialize project",
                    "description": "Set up the project directory.",
                    "commands": ["mkdir my-project", "cd my-project"],
                    "reference_file": "setup.ts",
                    "expected_output": "Directory created",
                },
            ],
        )
        content = self.plugin._render_task(task, PROJECT, REFERENCE_REPOS)
        assert "### Step 1: Initialize project" in content
        assert "Set up the project directory." in content
        assert "```bash" in content
        assert "mkdir my-project" in content
        assert "cd my-project" in content
        assert "**Reference file:** [`setup.ts`]" in content
        assert "**Expected output:** Directory created" in content

    def test_renders_step_without_optional_fields(self):
        task = _minimal_task(steps=[{"order": 1, "action": "Do something"}])
        content = self.plugin._render_task(task, PROJECT, {})
        assert "### Step 1: Do something" in content
        assert "```bash" not in content
        assert "**Reference file:**" not in content
        assert "**Expected output:**" not in content

    def test_omits_section_when_no_steps(self):
        task = _minimal_task()
        content = self.plugin._render_task(task, PROJECT, {})
        assert "## Execution Steps" not in content


# ---------------------------------------------------------------------------
# TestRenderTaskReferenceCodeIndex
# ---------------------------------------------------------------------------


class TestRenderTaskReferenceCodeIndex:
    """Tests for the Reference Code Index table."""

    def setup_method(self):
        self.plugin = _make_plugin()

    def test_renders_reference_code_table(self):
        task = _minimal_task(
            reference_code={
                "repo": "demo-repo",
                "base_path": "src",
                "files": [
                    {"path": "index.ts", "description": "Entry point"},
                    {"path": "utils.ts", "description": "Helpers"},
                ],
            }
        )
        content = self.plugin._render_task(task, PROJECT, REFERENCE_REPOS)
        assert "## Reference Code Index" in content
        assert "| File | Description | Raw URL |" in content
        assert "| `index.ts` | Entry point |" in content
        assert "| `utils.ts` | Helpers |" in content
        assert "[Fetch](" in content

    def test_includes_repo_description(self):
        task = _minimal_task(
            reference_code={
                "repo": "demo-repo",
                "base_path": "src",
                "files": [{"path": "app.ts", "description": "App"}],
            }
        )
        content = self.plugin._render_task(task, PROJECT, REFERENCE_REPOS)
        assert "These files are from [demo-repo]" in content
        assert "`src` directory" in content

    def test_omits_section_when_no_files(self):
        task = _minimal_task()
        content = self.plugin._render_task(task, PROJECT, {})
        assert "## Reference Code Index" not in content


# ---------------------------------------------------------------------------
# TestRenderTaskErrorRecovery
# ---------------------------------------------------------------------------


class TestRenderTaskErrorRecovery:
    """Tests for the Error Recovery section."""

    def setup_method(self):
        self.plugin = _make_plugin()

    def test_renders_error_patterns(self):
        task = _minimal_task(
            error_patterns=[
                {
                    "pattern": "ECONNREFUSED",
                    "cause": "Server not running",
                    "resolution": "Start the dev server first",
                },
            ]
        )
        content = self.plugin._render_task(task, PROJECT, {})
        assert "## Error Recovery" in content
        assert "**`ECONNREFUSED`**" in content
        assert "- **Cause:** Server not running" in content
        assert "- **Resolution:** Start the dev server first" in content

    def test_omits_section_when_no_error_patterns(self):
        task = _minimal_task()
        content = self.plugin._render_task(task, PROJECT, {})
        assert "## Error Recovery" not in content


# ---------------------------------------------------------------------------
# TestRenderTaskSupplementaryContext
# ---------------------------------------------------------------------------


class TestRenderTaskSupplementaryContext:
    """Tests for the Supplementary Context section."""

    def setup_method(self):
        self.plugin = _make_plugin()

    def test_renders_supplementary_context(self):
        task = _minimal_task(
            supplementary_context={
                "description": "Related documentation pages.",
                "pages": [
                    {
                        "slug": "getting-started",
                        "url": "https://docs.example.com/start",
                        "relevance": "Setup instructions",
                    },
                ],
            }
        )
        content = self.plugin._render_task(task, PROJECT, {})
        assert "## Supplementary Context" in content
        assert "Related documentation pages." in content
        assert (
            "- [getting-started](https://docs.example.com/start) — Setup instructions"
            in content
        )

    def test_omits_section_when_no_supplementary_context(self):
        task = _minimal_task()
        content = self.plugin._render_task(task, PROJECT, {})
        assert "## Supplementary Context" not in content


# ---------------------------------------------------------------------------
# TestRenderTaskMinimal
# ---------------------------------------------------------------------------


class TestRenderTaskMinimal:
    """Tests that a task with only required fields renders cleanly."""

    def setup_method(self):
        self.plugin = _make_plugin()

    def test_minimal_task_renders(self):
        task = _minimal_task()
        content = self.plugin._render_task(task, PROJECT, {})
        assert content.startswith("---")
        assert "# Test Task" in content
        assert "**Objective:** Verify the plugin works" in content

    def test_minimal_task_omits_all_optional_sections(self):
        task = _minimal_task()
        content = self.plugin._render_task(task, PROJECT, {})
        for section in [
            "## Prerequisites",
            "## Environment Variables",
            "## Execution Steps",
            "## Reference Code Index",
            "## Error Recovery",
            "## Supplementary Context",
        ]:
            assert section not in content


# ---------------------------------------------------------------------------
# TestWriteIndex
# ---------------------------------------------------------------------------


class TestWriteIndex:
    """Tests for _write_index JSON generation."""

    def setup_method(self):
        self.plugin = _make_plugin()

    def test_writes_valid_index(self, tmp_path):
        tasks = [
            _minimal_task(),
            _minimal_task(
                id="second-task",
                title="Second Task",
                objective="Another task",
                steps=[{"order": 1, "action": "Go"}],
            ),
        ]
        self.plugin._write_index(tasks, PROJECT, tmp_path)
        index_path = tmp_path / "index.json"
        assert index_path.exists()

        data = json.loads(index_path.read_text(encoding="utf-8"))
        assert data["project"] == PROJECT
        assert "generated" in data
        assert len(data["tasks"]) == 2

        first = data["tasks"][0]
        assert first["id"] == "test-task"
        assert first["title"] == "Test Task"
        assert first["objective"] == "Verify the plugin works"
        assert first["file"] == "test-task.md"
        assert first["steps"] == 0

        second = data["tasks"][1]
        assert second["id"] == "second-task"
        assert second["steps"] == 1


# ---------------------------------------------------------------------------
# TestLoadConfig
# ---------------------------------------------------------------------------


class TestLoadConfig:
    """Tests for _load_config file loading and error handling."""

    def setup_method(self):
        self.plugin = _make_plugin()

    def test_loads_valid_config(self, tmp_path):
        config_data = {"project": {"id": "p1"}, "tasks": []}
        config_path = tmp_path / "agent_tasks_config.json"
        config_path.write_text(json.dumps(config_data), encoding="utf-8")

        result = self.plugin._load_config(tmp_path)
        assert result == config_data

    def test_returns_none_for_missing_file(self, tmp_path):
        result = self.plugin._load_config(tmp_path)
        assert result is None

    def test_returns_none_for_invalid_json(self, tmp_path):
        config_path = tmp_path / "agent_tasks_config.json"
        config_path.write_text("not valid json {{{", encoding="utf-8")

        result = self.plugin._load_config(tmp_path)
        assert result is None
