import base64
import json
from pathlib import Path
from unittest.mock import MagicMock
from urllib.parse import unquote

from helper_lib.ai_file_utils.ai_file_utils import AIFileUtils
from plugins.ai_resources_page.plugin import AiResourcesPagePlugin


def _make_config(tmp_path, site_url="https://docs.example.com/", mcp_url=None, mcp_name=None):
    """Create a minimal llms_config.json and return a mock MkDocs config."""
    project = {"name": "TestProject"}
    if mcp_url is not None:
        project["mcp_url"] = mcp_url
    if mcp_name is not None:
        project["mcp_name"] = mcp_name

    llms_config = {
        "project": project,
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


class TestMcpSection:
    """Tests for the MCP install section."""

    MCP_URL = "https://mkdocs-mcp.papermoon.io/polkadot/mcp"
    MCP_NAME = "polkadot-docs"

    def test_mcp_section_rendered(self, tmp_path):
        """Section appears with all five clients when mcp_url is set."""
        plugin = AiResourcesPagePlugin()
        config = _make_config(
            tmp_path, mcp_url=self.MCP_URL, mcp_name=self.MCP_NAME
        )
        page = MagicMock()
        page.file.src_path = "ai-resources.md"

        result = plugin.on_page_markdown("", page, config, [])

        assert "## Connect via MCP" in result
        assert "cursor://anysphere.cursor-deeplink/mcp/install" in result
        assert "vscode:mcp/install?" in result
        assert f"claude mcp add --transport http {self.MCP_NAME} {self.MCP_URL}" in result
        assert f"codex mcp add {self.MCP_NAME} --url {self.MCP_URL}" in result
        assert "modelcontextprotocol.io" in result

    def test_mcp_section_absent_no_url(self, tmp_path):
        """Section is absent when mcp_url is not in config."""
        plugin = AiResourcesPagePlugin()
        config = _make_config(tmp_path)
        page = MagicMock()
        page.file.src_path = "ai-resources.md"

        result = plugin.on_page_markdown("", page, config, [])

        assert "## Connect via MCP" not in result

    def test_mcp_section_absent_empty_url(self, tmp_path):
        """Section is absent when mcp_url is an empty string."""
        plugin = AiResourcesPagePlugin()
        config = _make_config(tmp_path, mcp_url="", mcp_name=self.MCP_NAME)
        page = MagicMock()
        page.file.src_path = "ai-resources.md"

        result = plugin.on_page_markdown("", page, config, [])

        assert "## Connect via MCP" not in result

    def test_cursor_deeplink_format(self):
        """Cursor deeplink encodes the MCP URL as base64 config."""
        link = AIFileUtils.build_cursor_deeplink(
            self.MCP_NAME, self.MCP_URL
        )

        assert link.startswith("cursor://anysphere.cursor-deeplink/mcp/install?")
        assert f"name={self.MCP_NAME}" in link

        # Extract and decode the base64 config param
        b64_part = link.split("config=")[1]
        decoded = json.loads(base64.b64decode(b64_part).decode())
        assert decoded == {"url": self.MCP_URL}

    def test_vscode_deeplink_format(self):
        """VS Code deeplink URL-encodes a JSON config with name and url."""
        link = AIFileUtils.build_vscode_deeplink(
            self.MCP_NAME, self.MCP_URL
        )

        assert link.startswith("vscode:mcp/install?")

        encoded_part = link.split("?", 1)[1]
        decoded = json.loads(unquote(encoded_part))
        assert decoded == {"name": self.MCP_NAME, "url": self.MCP_URL}
