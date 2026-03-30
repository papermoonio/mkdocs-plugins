import json
from pathlib import Path
from unittest.mock import MagicMock

from plugins.ai_resources_page.plugin import AiResourcesPagePlugin


def _make_config(tmp_path, site_url="https://docs.example.com/"):
    """Create a minimal llms_config.json and return a mock MkDocs config."""
    llms_config = {
        "project": {"name": "TestProject"},
        "content": {
            "categories_info": {
                "basics": {
                    "name": "Basics",
                    "description": "Basic docs.",
                }
            }
        },
        "outputs": {"public_root": "/ai/"},
    }
    config_file = tmp_path / "llms_config.json"
    config_file.write_text(json.dumps(llms_config), encoding="utf-8")

    # MkDocs config mock
    mkdocs_yml = tmp_path / "mkdocs.yml"
    mkdocs_yml.write_text("", encoding="utf-8")

    config = {
        "config_file_path": str(mkdocs_yml),
        "site_url": site_url,
    }
    return config


class TestAiResourcesPageSubpath:
    """Tests that artifact URLs include the site subpath."""

    def test_root_site_url(self, tmp_path):
        """Root deploy should produce URLs without a prefix."""
        plugin = AiResourcesPagePlugin()
        config = _make_config(tmp_path, site_url="https://docs.polkadot.com/")
        page = MagicMock()
        page.file.src_path = "ai-resources.md"

        result = plugin.on_page_markdown("", page, config, [])

        assert "/ai/site-index.json" in result
        assert "/ai/llms-full.jsonl" in result
        assert "/ai/categories/basics.md" in result
        assert "/llms.txt" in result
        # Should NOT have a double path like /docs/ai/
        assert '"/docs/' not in result

    def test_subpath_site_url(self, tmp_path):
        """Subpath deploy should prepend /docs/ to all URLs."""
        plugin = AiResourcesPagePlugin()
        config = _make_config(tmp_path, site_url="https://wormhole.com/docs/")
        page = MagicMock()
        page.file.src_path = "ai-resources.md"

        result = plugin.on_page_markdown("", page, config, [])

        assert "/docs/ai/site-index.json" in result
        assert "/docs/ai/llms-full.jsonl" in result
        assert "/docs/ai/categories/basics.md" in result
        assert "/docs/llms.txt" in result

    def test_empty_site_url(self, tmp_path):
        """Empty site_url should produce URLs without a prefix."""
        plugin = AiResourcesPagePlugin()
        config = _make_config(tmp_path, site_url="")
        page = MagicMock()
        page.file.src_path = "ai-resources.md"

        result = plugin.on_page_markdown("", page, config, [])

        assert "/ai/site-index.json" in result
        assert "/ai/categories/basics.md" in result
        assert "/llms.txt" in result


class TestMCPSection:
    """Tests for MCP install section on the AI Resources page."""

    def test_mcp_section_present_when_configured(self, tmp_path):
        """MCP section should appear when mcp_name and mcp_url are set."""
        llms_config = {
            "project": {
                "name": "TestProject",
                "mcp_name": "test-mcp",
                "mcp_url": "https://mcp.example.com/sse",
            },
            "content": {
                "categories_info": {
                    "basics": {"name": "Basics", "description": "Basic docs."}
                }
            },
            "outputs": {"public_root": "/ai/"},
        }
        config_file = tmp_path / "llms_config.json"
        config_file.write_text(json.dumps(llms_config), encoding="utf-8")
        mkdocs_yml = tmp_path / "mkdocs.yml"
        mkdocs_yml.write_text("", encoding="utf-8")
        config = {"config_file_path": str(mkdocs_yml), "site_url": "https://docs.example.com/"}

        plugin = AiResourcesPagePlugin()
        page = MagicMock()
        page.file.src_path = "ai-resources.md"

        result = plugin.on_page_markdown("", page, config, [])

        assert "## Connect via MCP" in result
        assert "https://mcp.example.com/sse" in result
        assert "Cursor" in result
        assert "VS Code" in result
        assert "Claude Code CLI" in result
        assert "Codex CLI" in result
        assert "Claude Desktop" in result
        assert "cursor://anysphere.cursor-deeplink" in result
        assert "vscode:mcp/install?" in result

    def test_mcp_section_absent_when_not_configured(self, tmp_path):
        """MCP section should not appear when mcp_name/mcp_url are missing."""
        config = _make_config(tmp_path)

        plugin = AiResourcesPagePlugin()
        page = MagicMock()
        page.file.src_path = "ai-resources.md"

        result = plugin.on_page_markdown("", page, config, [])

        assert "## Connect via MCP" not in result
