import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from plugins.ai_docs.plugin import AIDocsPlugin

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_plugin(**overrides):
    """Return an AIDocsPlugin instance with agent skills config set up."""
    plugin = AIDocsPlugin()
    plugin.config = {
        "llms_config": "llms_config.json",
        "ai_resources_page": True,
        "ai_page_actions": True,
        "agent_skills_config": "agent_skills_config.json",
        "agent_skills": True,
        **overrides,
    }
    return plugin


def _minimal_skill(**overrides):
    """Return a skill dict with only the required fields."""
    skill = {
        "id": "test-skill",
        "title": "Test Skill",
        "objective": "Verify the plugin works",
    }
    skill.update(overrides)
    return skill


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
# TestRenderSkillFrontmatter
# ---------------------------------------------------------------------------


class TestRenderSkillFrontmatter:
    """Tests for YAML frontmatter in rendered skill output."""

    def setup_method(self):
        self.plugin = _make_plugin()

    def _frontmatter(self, content):
        """Extract the YAML frontmatter block from rendered content."""
        parts = content.split("---")
        return parts[1] if len(parts) >= 3 else ""

    def test_contains_required_fields(self):
        task = _minimal_skill()
        content = self.plugin._render_skill(task, PROJECT, {})
        fm = self._frontmatter(content)
        assert "name: test-skill" in fm
        assert "description: Verify the plugin works" in fm
        assert "title: Test Skill" in fm
        assert "estimated_steps: 0" in fm
        assert "generated:" in fm

    def test_includes_reference_repo_when_present(self):
        task = _minimal_skill(reference_code={"repo": "demo-repo", "base_path": "src"})
        content = self.plugin._render_skill(task, PROJECT, REFERENCE_REPOS)
        fm = self._frontmatter(content)
        assert "  reference_repo: https://github.com/org/demo-repo" in fm

    def test_omits_reference_repo_when_missing(self):
        task = _minimal_skill()
        content = self.plugin._render_skill(task, PROJECT, {})
        fm = self._frontmatter(content)
        assert "reference_repo" not in fm

    def test_prerequisites_not_in_frontmatter(self):
        task = _minimal_skill(prerequisites={"tools": ["Node.js >= 18", "npm"]})
        content = self.plugin._render_skill(task, PROJECT, {})
        fm = self._frontmatter(content)
        assert "prerequisites" not in fm

    def test_estimated_steps_matches_step_count(self):
        steps = [
            {"order": 1, "action": "Init"},
            {"order": 2, "action": "Build"},
        ]
        task = _minimal_skill(steps=steps)
        content = self.plugin._render_skill(task, PROJECT, {})
        fm = self._frontmatter(content)
        assert "estimated_steps: 2" in fm

    def test_metadata_block_present(self):
        task = _minimal_skill()
        content = self.plugin._render_skill(task, PROJECT, {})
        fm = self._frontmatter(content)
        assert "metadata:" in fm

    def test_includes_license_when_present(self):
        task = _minimal_skill(license="BSD-2-Clause")
        content = self.plugin._render_skill(task, PROJECT, {})
        fm = self._frontmatter(content)
        assert "license: BSD-2-Clause" in fm

    def test_omits_license_when_absent(self):
        task = _minimal_skill()
        content = self.plugin._render_skill(task, PROJECT, {})
        fm = self._frontmatter(content)
        assert "license" not in fm

    def test_includes_compatibility_when_present(self):
        task = _minimal_skill(compatibility="Requires Node.js >= 18")
        content = self.plugin._render_skill(task, PROJECT, {})
        fm = self._frontmatter(content)
        assert "compatibility: Requires Node.js >= 18" in fm

    def test_omits_compatibility_when_absent(self):
        task = _minimal_skill()
        content = self.plugin._render_skill(task, PROJECT, {})
        fm = self._frontmatter(content)
        assert "compatibility" not in fm


# ---------------------------------------------------------------------------
# TestRenderSkillPrerequisites
# ---------------------------------------------------------------------------


class TestRenderSkillPrerequisites:
    """Tests for the Prerequisites body section."""

    def setup_method(self):
        self.plugin = _make_plugin()

    def test_renders_grouped_prerequisites(self):
        task = _minimal_skill(
            prerequisites={
                "tools": ["Node.js >= 18", "npm"],
                "accounts": ["GitHub account"],
            }
        )
        content = self.plugin._render_skill(task, PROJECT, {})
        assert "## Prerequisites" in content
        assert "**Tools:**" in content
        assert "- Node.js >= 18" in content
        assert "- npm" in content
        assert "**Accounts:**" in content
        assert "- GitHub account" in content

    def test_omits_section_when_no_prerequisites(self):
        task = _minimal_skill()
        content = self.plugin._render_skill(task, PROJECT, {})
        assert "## Prerequisites" not in content

    def test_omits_section_when_prerequisites_empty(self):
        task = _minimal_skill(prerequisites={})
        content = self.plugin._render_skill(task, PROJECT, {})
        assert "## Prerequisites" not in content


# ---------------------------------------------------------------------------
# TestRenderSkillEnvVars
# ---------------------------------------------------------------------------


class TestRenderSkillEnvVars:
    """Tests for the Environment Variables section."""

    def setup_method(self):
        self.plugin = _make_plugin()

    def test_renders_env_vars(self):
        task = _minimal_skill(
            env_vars=[
                {"name": "API_KEY", "description": "Your API key", "required": True},
                {
                    "name": "DEBUG",
                    "description": "Enable debug mode",
                    "required": False,
                },
            ]
        )
        content = self.plugin._render_skill(task, PROJECT, {})
        assert "## Environment Variables" in content
        assert "```env" in content
        assert "# Your API key (required)" in content
        assert "API_KEY=" in content
        assert "# Enable debug mode (optional)" in content
        assert "DEBUG=" in content

    def test_omits_section_when_no_env_vars(self):
        task = _minimal_skill()
        content = self.plugin._render_skill(task, PROJECT, {})
        assert "## Environment Variables" not in content


# ---------------------------------------------------------------------------
# TestRenderSkillSteps
# ---------------------------------------------------------------------------


class TestRenderSkillSteps:
    """Tests for the Execution Steps section."""

    def setup_method(self):
        self.plugin = _make_plugin()

    def test_renders_step_with_all_fields(self):
        task = _minimal_skill(
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
        content = self.plugin._render_skill(task, PROJECT, REFERENCE_REPOS)
        assert "### Step 1: Initialize project" in content
        assert "Set up the project directory." in content
        assert "```bash" in content
        assert "mkdir my-project" in content
        assert "cd my-project" in content
        assert "**Reference file:** [`setup.ts`]" in content
        assert "**Expected output:** Directory created" in content

    def test_renders_step_without_optional_fields(self):
        task = _minimal_skill(steps=[{"order": 1, "action": "Do something"}])
        content = self.plugin._render_skill(task, PROJECT, {})
        assert "### Step 1: Do something" in content
        assert "```bash" not in content
        assert "**Reference file:**" not in content
        assert "**Expected output:**" not in content

    def test_omits_section_when_no_steps(self):
        task = _minimal_skill()
        content = self.plugin._render_skill(task, PROJECT, {})
        assert "## Execution Steps" not in content


# ---------------------------------------------------------------------------
# TestRenderSkillReferenceCodeIndex
# ---------------------------------------------------------------------------


class TestRenderSkillReferenceCodeIndex:
    """Tests for the Reference Code Index table."""

    def setup_method(self):
        self.plugin = _make_plugin()

    def test_renders_reference_code_table(self):
        task = _minimal_skill(
            reference_code={
                "repo": "demo-repo",
                "base_path": "src",
                "files": [
                    {"path": "index.ts", "description": "Entry point"},
                    {"path": "utils.ts", "description": "Helpers"},
                ],
            }
        )
        content = self.plugin._render_skill(task, PROJECT, REFERENCE_REPOS)
        assert "## Reference Code Index" in content
        assert "| File | Description | Raw URL |" in content
        assert "| `index.ts` | Entry point |" in content
        assert "| `utils.ts` | Helpers |" in content
        assert "[Fetch](" in content

    def test_includes_repo_description(self):
        task = _minimal_skill(
            reference_code={
                "repo": "demo-repo",
                "base_path": "src",
                "files": [{"path": "app.ts", "description": "App"}],
            }
        )
        content = self.plugin._render_skill(task, PROJECT, REFERENCE_REPOS)
        assert "These files are from [demo-repo]" in content
        assert "`src` directory" in content

    def test_omits_section_when_no_files(self):
        task = _minimal_skill()
        content = self.plugin._render_skill(task, PROJECT, {})
        assert "## Reference Code Index" not in content


# ---------------------------------------------------------------------------
# TestRenderSkillErrorRecovery
# ---------------------------------------------------------------------------


class TestRenderSkillErrorRecovery:
    """Tests for the Error Recovery section."""

    def setup_method(self):
        self.plugin = _make_plugin()

    def test_renders_error_patterns(self):
        task = _minimal_skill(
            error_patterns=[
                {
                    "pattern": "ECONNREFUSED",
                    "cause": "Server not running",
                    "resolution": "Start the dev server first",
                },
            ]
        )
        content = self.plugin._render_skill(task, PROJECT, {})
        assert "## Error Recovery" in content
        assert "**`ECONNREFUSED`**" in content
        assert "- **Cause:** Server not running" in content
        assert "- **Resolution:** Start the dev server first" in content

    def test_omits_section_when_no_error_patterns(self):
        task = _minimal_skill()
        content = self.plugin._render_skill(task, PROJECT, {})
        assert "## Error Recovery" not in content


# ---------------------------------------------------------------------------
# TestRenderSkillSupplementaryContext
# ---------------------------------------------------------------------------


class TestRenderSkillSupplementaryContext:
    """Tests for the Supplementary Context section."""

    def setup_method(self):
        self.plugin = _make_plugin()

    def test_renders_supplementary_context(self):
        task = _minimal_skill(
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
        content = self.plugin._render_skill(task, PROJECT, {})
        assert "## Supplementary Context" in content
        assert "Related documentation pages." in content
        assert (
            "- [getting-started](https://docs.example.com/start) — Setup instructions"
            in content
        )

    def test_omits_section_when_no_supplementary_context(self):
        task = _minimal_skill()
        content = self.plugin._render_skill(task, PROJECT, {})
        assert "## Supplementary Context" not in content


# ---------------------------------------------------------------------------
# TestRenderSkillMinimal
# ---------------------------------------------------------------------------


class TestRenderSkillMinimal:
    """Tests that a skill with only required fields renders cleanly."""

    def setup_method(self):
        self.plugin = _make_plugin()

    def test_minimal_skill_renders(self):
        task = _minimal_skill()
        content = self.plugin._render_skill(task, PROJECT, {})
        assert content.startswith("---")
        assert "# Test Skill" in content
        assert "**Objective:** Verify the plugin works" in content

    def test_minimal_skill_omits_all_optional_sections(self):
        task = _minimal_skill()
        content = self.plugin._render_skill(task, PROJECT, {})
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
# TestWriteSkillsIndex
# ---------------------------------------------------------------------------


class TestWriteSkillsIndex:
    """Tests for _write_skills_index JSON generation."""

    def setup_method(self):
        self.plugin = _make_plugin()

    def test_writes_valid_index(self, tmp_path):
        skills = [
            _minimal_skill(),
            _minimal_skill(
                id="second-skill",
                title="Second Skill",
                objective="Another skill",
                steps=[{"order": 1, "action": "Go"}],
            ),
        ]
        self.plugin._write_skills_index(skills, PROJECT, tmp_path)
        index_path = tmp_path / "index.json"
        assert index_path.exists()

        data = json.loads(index_path.read_text(encoding="utf-8"))
        assert data["project"] == PROJECT
        assert "generated" in data
        assert len(data["skills"]) == 2

        first = data["skills"][0]
        assert first["id"] == "test-skill"
        assert first["title"] == "Test Skill"
        assert first["description"] == "Verify the plugin works"
        assert first["file"] == "test-skill.md"
        assert first["steps"] == 0

        second = data["skills"][1]
        assert second["id"] == "second-skill"
        assert second["steps"] == 1


# ---------------------------------------------------------------------------
# TestOnConfigSkillsOutputsValidation
# ---------------------------------------------------------------------------


class TestOnConfigSkillsOutputsValidation:
    """Tests for on_config validation of outputs.public_root and outputs.skills_dir."""

    def _write_skills_config(self, tmp_path, data):
        """Write agent_skills_config.json and return a minimal MkDocs config dict."""
        config_path = tmp_path / "agent_skills_config.json"
        config_path.write_text(json.dumps(data), encoding="utf-8")
        return {"config_file_path": str(tmp_path / "mkdocs.yml")}

    def _base_config(self, **output_overrides):
        """Return a minimal skills config dict with the given outputs values."""
        outputs = {"public_root": "/ai/", "skills_dir": "skills"}
        outputs.update(output_overrides)
        return {
            "project": {"id": "test"},
            "outputs": outputs,
            "skills": [_minimal_skill(source_pages=["docs/page.md"])],
        }

    def test_valid_outputs_sets_instance_vars(self, tmp_path):
        plugin = _make_plugin()
        data = self._base_config(public_root="/custom/root/", skills_dir="my-skills")
        mkdocs_config = self._write_skills_config(tmp_path, data)
        plugin.on_config(mkdocs_config)
        assert plugin._skills_public_root == "custom/root"
        assert plugin._skills_dir_name == "my-skills"

    def test_defaults_applied_when_outputs_key_absent(self, tmp_path):
        plugin = _make_plugin()
        data = {"project": {"id": "test"}, "skills": [_minimal_skill()]}
        mkdocs_config = self._write_skills_config(tmp_path, data)
        plugin.on_config(mkdocs_config)
        assert plugin._skills_public_root == "ai"
        assert plugin._skills_dir_name == "skills"

    def test_page_skill_map_populated_for_valid_config(self, tmp_path):
        plugin = _make_plugin()
        mkdocs_config = self._write_skills_config(tmp_path, self._base_config())
        plugin.on_config(mkdocs_config)
        assert "docs/page.md" in plugin._page_skill_map

    def test_empty_public_root_clears_skills_config(self, tmp_path):
        plugin = _make_plugin()
        mkdocs_config = self._write_skills_config(
            tmp_path, self._base_config(public_root="")
        )
        plugin.on_config(mkdocs_config)
        assert not plugin._skills_config

    def test_slash_only_public_root_clears_skills_config(self, tmp_path):
        # "/" strips to "" — must be treated as empty
        plugin = _make_plugin()
        mkdocs_config = self._write_skills_config(
            tmp_path, self._base_config(public_root="/")
        )
        plugin.on_config(mkdocs_config)
        assert not plugin._skills_config

    def test_empty_skills_dir_clears_skills_config(self, tmp_path):
        plugin = _make_plugin()
        mkdocs_config = self._write_skills_config(
            tmp_path, self._base_config(skills_dir="")
        )
        plugin.on_config(mkdocs_config)
        assert not plugin._skills_config

    def test_both_empty_clears_skills_config(self, tmp_path):
        plugin = _make_plugin()
        mkdocs_config = self._write_skills_config(
            tmp_path, self._base_config(public_root="", skills_dir="")
        )
        plugin.on_config(mkdocs_config)
        assert not plugin._skills_config

    def test_invalid_outputs_do_not_modify_instance_vars(self, tmp_path):
        # Core invariant: bad values must never be written to _skills_public_root
        # or _skills_dir_name — they must stay at their __init__ defaults.
        plugin = _make_plugin()
        mkdocs_config = self._write_skills_config(
            tmp_path, self._base_config(public_root="", skills_dir="")
        )
        plugin.on_config(mkdocs_config)
        assert plugin._skills_public_root == "ai"
        assert plugin._skills_dir_name == "skills"

    def test_page_skill_map_empty_when_validation_fails(self, tmp_path):
        # source_pages must not be mapped if outputs validation fails
        plugin = _make_plugin()
        mkdocs_config = self._write_skills_config(
            tmp_path, self._base_config(public_root="")
        )
        plugin.on_config(mkdocs_config)
        assert plugin._page_skill_map == {}


# ---------------------------------------------------------------------------
# TestLoadSkillsConfig
# ---------------------------------------------------------------------------


class TestLoadSkillsConfig:
    """Tests for _load_skills_config file loading and error handling."""

    def setup_method(self):
        self.plugin = _make_plugin()

    def test_loads_valid_config(self, tmp_path):
        config_data = {"project": {"id": "p1"}, "skills": []}
        config_path = tmp_path / "agent_skills_config.json"
        config_path.write_text(json.dumps(config_data), encoding="utf-8")

        result = self.plugin._load_skills_config(tmp_path)
        assert result == config_data

    def test_returns_empty_for_missing_file(self, tmp_path):
        result = self.plugin._load_skills_config(tmp_path)
        assert not result

    def test_returns_empty_for_invalid_json(self, tmp_path):
        config_path = tmp_path / "agent_skills_config.json"
        config_path.write_text("not valid json {{{", encoding="utf-8")

        result = self.plugin._load_skills_config(tmp_path)
        assert not result

    def test_returns_empty_when_config_filename_not_set(self, tmp_path):
        plugin = _make_plugin(agent_skills_config="")
        result = plugin._load_skills_config(tmp_path)
        assert not result


# ---------------------------------------------------------------------------
# TestOnPostPageSkillWidgetInjection
# ---------------------------------------------------------------------------

# Minimal rendered page HTML — matches the structure MkDocs produces.
_PAGE_HTML = '<div class="md-content"><h1>Test Page</h1></div>'
_PAGE_HTML_WITH_CHIPS = (
    '<div class="md-content">'
    "<h1>Test Page</h1>"
    '<div class="page-meta-chips"><span>existing</span></div>'
    "</div>"
)


def _make_page(src_path="docs/page.md", url="docs/page"):
    page = MagicMock()
    page.file.src_path = src_path
    page.url = url
    page.is_homepage = False
    page.meta = {}
    return page


class TestOnPostPageSkillWidgetInjection:
    """Integration tests for agent skill widget injection in on_post_page."""

    def setup_method(self):
        # Disable ai_page_actions so inject_widget is always False — isolates
        # the skills widget path and avoids any _ensure_config_loaded calls.
        self.plugin = _make_plugin(ai_page_actions=False)
        self.plugin._skills_config = {"skills": [_minimal_skill()]}
        self.plugin._page_skill_map = {
            "docs/page.md": [{"id": "test-skill", "title": "Test Skill"}]
        }
        self.mkdocs_config = {"site_url": "https://docs.example.com"}

    def test_injects_widget_for_mapped_page(self):
        result = self.plugin.on_post_page(
            _PAGE_HTML, page=_make_page(), config=self.mkdocs_config
        )
        assert "agent-skill-widget" in result

    def test_widget_contains_skill_title_in_tooltip(self):
        result = self.plugin.on_post_page(
            _PAGE_HTML, page=_make_page(), config=self.mkdocs_config
        )
        assert 'title="Test Skill"' in result

    def test_widget_view_and_download_links_carry_aria_labels(self):
        result = self.plugin.on_post_page(
            _PAGE_HTML, page=_make_page(), config=self.mkdocs_config
        )
        assert 'aria-label="View Test Skill"' in result
        assert 'aria-label="Download Test Skill"' in result

    def test_creates_chips_div_when_absent(self):
        result = self.plugin.on_post_page(
            _PAGE_HTML, page=_make_page(), config=self.mkdocs_config
        )
        assert "page-meta-chips" in result

    def test_prepends_to_existing_chips_div(self):
        result = self.plugin.on_post_page(
            _PAGE_HTML_WITH_CHIPS, page=_make_page(), config=self.mkdocs_config
        )
        # Widget must appear before the pre-existing chip content
        assert result.index("agent-skill-widget") < result.index("existing")

    def test_no_injection_for_unmapped_page(self):
        result = self.plugin.on_post_page(
            _PAGE_HTML,
            page=_make_page(src_path="docs/other.md"),
            config=self.mkdocs_config,
        )
        assert result == _PAGE_HTML

    def test_no_injection_when_md_content_absent(self):
        bare_html = "<html><body><h1>No wrapper</h1></body></html>"
        result = self.plugin.on_post_page(
            bare_html, page=_make_page(), config=self.mkdocs_config
        )
        assert result == bare_html

    def test_no_injection_when_agent_skills_disabled(self):
        plugin = _make_plugin(ai_page_actions=False, agent_skills=False)
        result = plugin.on_post_page(
            _PAGE_HTML, page=_make_page(), config=self.mkdocs_config
        )
        assert result == _PAGE_HTML


# ---------------------------------------------------------------------------
# TestOnPostBuildAgentSkills
# ---------------------------------------------------------------------------


def _make_on_post_build_config(tmp_path):
    """Return a minimal MkDocs config dict with real docs/site dirs in tmp_path."""
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir(exist_ok=True)
    site_dir = tmp_path / "site"
    site_dir.mkdir(exist_ok=True)
    return {"docs_dir": str(docs_dir), "site_dir": str(site_dir), "site_url": ""}


class TestOnPostBuildAgentSkills:
    """Integration tests for agent skill file generation in on_post_build.

    Non-skills methods are patched out so tests focus on the skills block.
    subprocess.run is patched to report no git repo, keeping tests hermetic.
    """

    _PATCH_TARGETS = [
        "_ensure_config_loaded",
        "get_all_markdown_files",
        "build_category_bundles",
        "build_category_light",
        "build_llms_txt",
        "load_yaml",
    ]

    def _run_build(self, plugin, tmp_path):
        """Patch all non-skills on_post_build machinery and run the hook."""
        mkdocs_config = _make_on_post_build_config(tmp_path)
        patches = [
            patch.object(
                plugin, t, return_value=([] if "files" in t or "index" in t else None)
            )
            for t in self._PATCH_TARGETS
        ]
        patches.append(patch.object(plugin, "build_site_index", return_value=[]))
        patches.append(patch("subprocess.run", return_value=MagicMock(returncode=1)))
        plugin.config["ai_resources_page"] = False
        plugin._llms_config = {}

        ctx = __import__("contextlib").ExitStack()
        for p in patches:
            ctx.enter_context(p)
        with ctx:
            plugin.on_post_build(mkdocs_config)
        return Path(mkdocs_config["site_dir"])

    def test_writes_skill_file(self, tmp_path):
        plugin = _make_plugin()
        plugin._skills_config = {
            "project": PROJECT,
            "skills": [_minimal_skill()],
            "reference_repos": {},
        }
        site_dir = self._run_build(plugin, tmp_path)
        assert (site_dir / "ai" / "skills" / "test-skill.md").exists()

    def test_writes_index_json(self, tmp_path):
        plugin = _make_plugin()
        plugin._skills_config = {
            "project": PROJECT,
            "skills": [_minimal_skill()],
            "reference_repos": {},
        }
        site_dir = self._run_build(plugin, tmp_path)
        index_path = site_dir / "ai" / "skills" / "index.json"
        assert index_path.exists()
        data = json.loads(index_path.read_text(encoding="utf-8"))
        assert len(data["skills"]) == 1
        assert data["skills"][0]["id"] == "test-skill"

    def test_cleans_output_dir_before_writing(self, tmp_path):
        plugin = _make_plugin()
        plugin._skills_config = {
            "project": PROJECT,
            "skills": [_minimal_skill()],
            "reference_repos": {},
        }
        # Pre-populate the output dir with a stale file
        stale_dir = tmp_path / "site" / "ai" / "skills"
        stale_dir.mkdir(parents=True)
        stale_file = stale_dir / "stale-skill.md"
        stale_file.write_text("stale", encoding="utf-8")

        self._run_build(plugin, tmp_path)
        assert not stale_file.exists()

    def test_index_excludes_failed_skills(self, tmp_path):
        # A malformed skill (missing objective) should not appear in index.json
        plugin = _make_plugin()
        plugin._skills_config = {
            "project": PROJECT,
            "skills": [
                _minimal_skill(),
                {"id": "broken-skill", "title": "Broken"},  # missing objective
            ],
            "reference_repos": {},
        }
        site_dir = self._run_build(plugin, tmp_path)
        index_path = site_dir / "ai" / "skills" / "index.json"
        data = json.loads(index_path.read_text(encoding="utf-8"))
        ids = [s["id"] for s in data["skills"]]
        assert "test-skill" in ids
        assert "broken-skill" not in ids

    def test_skips_generation_when_skills_list_empty(self, tmp_path):
        plugin = _make_plugin()
        plugin._skills_config = {
            "project": PROJECT,
            "skills": [],
            "reference_repos": {},
        }
        site_dir = self._run_build(plugin, tmp_path)
        assert not (site_dir / "ai" / "skills").exists()

    def test_skips_generation_when_skills_config_absent(self, tmp_path):
        plugin = _make_plugin()
        plugin._skills_config = {}
        site_dir = self._run_build(plugin, tmp_path)
        assert not (site_dir / "ai" / "skills").exists()
