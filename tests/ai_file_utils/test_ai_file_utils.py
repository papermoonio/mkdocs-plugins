import base64
import html
import json
import urllib.parse

from helper_lib.ai_file_utils.ai_file_utils import AIFileUtils


class TestAIFileUtils:
    def test_resolve_actions_usage(self):
        """
        Demonstrates how to use the AIFileUtils to resolve actions.
        """
        # 1. Instantiate the utility class
        utils = AIFileUtils()

        # 2. Define the context for a specific page
        site_url = "https://docs.polkadot.com"
        page_url = "/directory/page.md"
        filename = "page.md"
        content = "# Polkadot Basics\n\nPolkadot is a sharded protocol."

        # 3. Build the fully-qualified prompt URL and call the public API
        prompt_page_url = site_url.rstrip("/") + "/" + page_url.lstrip("/")
        actions = utils.resolve_actions(page_url, filename, content, prompt_page_url=prompt_page_url)

        # Usage Verification:
        # Check that we got a list back
        assert isinstance(actions, list)
        assert len(actions) > 0

        # Inspect the "View Markdown" action
        view_action = next(a for a in actions if a["id"] == "view-markdown")
        assert view_action["href"] == "/directory/page.md"

        # Inspect the "Download Markdown" action (check download attribute interpolation)
        download_action = next(a for a in actions if a["id"] == "download-markdown")
        assert download_action["download"] == "page.md"

        # Inspect the "Copy Markdown" (primary) action
        copy_action = next(a for a in actions if a["id"] == "copy-markdown")
        assert copy_action["clipboardContent"] == content
        assert copy_action.get("primary") is True

        # Inspect the "ChatGPT" action (check prompt encoding)
        chatgpt_action = next(a for a in actions if a["id"] == "open-chat-gpt")
        # The prompt should be encoded in the URL
        assert "chatgpt.com" in chatgpt_action["href"]
        # Should contain encoded full URL (site_url + page_url) in the prompt
        assert "docs.polkadot.com" in chatgpt_action["href"]

        # Inspect the "Claude" action
        claude_action = next(a for a in actions if a["id"] == "open-claude")
        assert "claude.ai" in claude_action["href"]
        # Should contain encoded full URL (site_url + page_url) in the prompt
        assert "docs.polkadot.com" in claude_action["href"]

    def test_prompt_page_url_interpolation(self):
        """prompt_page_url should be interpolated into prompt templates without double slashes."""
        utils = AIFileUtils()

        site_url = "https://docs.example.com/"
        page_url = "/directory/page.md"
        prompt_page_url = site_url.rstrip("/") + "/" + page_url.lstrip("/")

        actions = utils.resolve_actions(
            page_url=page_url,
            filename="test-page.md",
            content="test",
            prompt_page_url=prompt_page_url,
        )

        chatgpt_action = next(a for a in actions if a["id"] == "open-chat-gpt")
        # The encoded href should contain the clean URL without double slashes
        # https://docs.example.com/directory/page.md (no double slash)
        assert "docs.example.com" in chatgpt_action["href"]
        # Double slash between site_url and page_url should NOT appear
        assert "docs.example.com%2F%2Fdirectory" not in chatgpt_action["href"]

    def test_site_url_defaults_to_empty(self):
        """When site_url is omitted, prompt templates still work with just page_url."""
        utils = AIFileUtils()

        actions = utils.resolve_actions(
            page_url="/directory/page.md",
            filename="test-page.md",
            content="test",
        )

        chatgpt_action = next(a for a in actions if a["id"] == "open-chat-gpt")
        assert "chatgpt.com" in chatgpt_action["href"]

    def test_missing_schema_file(self, tmp_path, caplog):
        """Test behavior when schema file is missing."""
        import logging

        caplog.set_level(logging.WARNING)

        utils = AIFileUtils()
        # Override path to non-existent file
        utils._actions_config_path = tmp_path / "non_existent.json"

        # Should return empty list, not crash. Logs warning internally.
        actions = utils.resolve_actions("url", "file", "content")

        # Verify warning log
        assert "Actions schema file not found" in caplog.text
        assert actions == []

    def test_malformed_json_schema(self, tmp_path, caplog):
        """Test behavior when schema file contains invalid JSON."""
        utils = AIFileUtils()
        # Create bad JSON file
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("{ not valid json ", encoding="utf-8")
        utils._actions_config_path = bad_file

        # Should return empty list. Logs error internally.
        actions = utils.resolve_actions("url", "file", "content")

        # Verify error log
        assert "Failed to parse actions schema JSON" in caplog.text
        assert actions == []

    def test_action_resolution_failure(self, caplog):
        """Test that one bad action doesn't crash the whole list."""
        utils = AIFileUtils()
        # Manually set schema with one good and one bad action (bad promptTemplate type)
        utils._actions_schema = {
            "actions": [
                {"id": "good-action", "type": "link", "href": "{{ page_url }}"},
                {
                    "id": "bad-action",
                    "type": "link",
                    "promptTemplate": 123,  # This will cause AttributeError on replace()
                },
            ]
        }

        actions = utils.resolve_actions("http://example.com", "page.md", "content")

        # We should get the good action
        assert len(actions) == 1
        assert actions[0]["id"] == "good-action"

        # We should see a warning for the bad action
        assert "Failed to resolve action bad-action" in caplog.text


class TestAIFileUtilsDropdownHtml:
    """Tests for generate_dropdown_html on the shared AIFileUtils class."""

    def setup_method(self):
        self.utils = AIFileUtils()

    def test_all_dropdown_actions_render_by_default(self):
        """All 4 non-primary action IDs should appear in the dropdown."""
        result = self.utils.generate_dropdown_html(
            url="/directory/page.md", filename="page.md"
        )
        expected_ids = [
            "view-markdown",
            "download-markdown",
            "open-chat-gpt",
            "open-claude",
        ]
        for action_id in expected_ids:
            assert f'data-action-id="{action_id}"' in result

    def test_primary_action_not_in_dropdown(self):
        """The primary action should NOT appear as a dropdown item."""
        result = self.utils.generate_dropdown_html(
            url="/directory/page.md", filename="page.md"
        )
        assert 'data-action-id="copy-markdown"' not in result

    def test_primary_button_driven_by_json(self):
        """The primary button should use label and icon from the JSON."""
        result = self.utils.generate_dropdown_html(
            url="/directory/page.md", filename="page.md"
        )
        assert 'data-action="copy-markdown"' in result
        assert 'class="ai-file-actions-btn ai-file-actions-copy"' in result
        assert "Copy file" in result
        assert "M16 1H4c-1.1" in result

    def test_exclude_filters_actions(self):
        """Excluded action IDs should not appear in the output."""
        result = self.utils.generate_dropdown_html(
            url="/directory/page.md",
            filename="page.md",
            exclude=["view-markdown", "open-claude"],
        )
        assert 'data-action-id="view-markdown"' not in result
        assert 'data-action-id="open-claude"' not in result
        assert 'data-action-id="download-markdown"' in result
        assert 'data-action-id="open-chat-gpt"' in result

    def test_primary_button_always_present(self):
        """The primary button should appear regardless of exclude list."""
        result = self.utils.generate_dropdown_html(
            url="/directory/page.md",
            filename="page.md",
            exclude=[
                "view-markdown",
                "download-markdown",
                "open-chat-gpt",
                "open-claude",
            ],
        )
        assert 'class="ai-file-actions-btn ai-file-actions-copy"' in result
        assert 'data-action="copy-markdown"' in result

    def test_container_structure(self):
        """The output should have the correct container structure."""
        result = self.utils.generate_dropdown_html(
            url="/directory/page.md", filename="page.md"
        )
        assert 'class="ai-file-actions-container"' in result
        assert 'class="ai-file-actions-btn ai-file-actions-trigger"' in result
        assert 'class="ai-file-actions-menu"' in result

    def test_html_escaping_for_special_urls(self):
        """URLs with special characters should be properly HTML-escaped."""
        url = '/directory/page.md?foo=1&bar=2"<script>'
        result = self.utils.generate_dropdown_html(url=url, filename="page.md")
        assert '&bar=2"<script>' not in result
        safe = html.escape(url, quote=True)
        # Primary button still uses data-url
        assert f'data-url="{safe}"' in result
        # Link actions use href
        assert f'href="{safe}"' in result

    def test_exclude_none_same_as_no_exclude(self):
        """Passing exclude=None should show all actions."""
        result_default = self.utils.generate_dropdown_html(
            url="/directory/page.md", filename="page.md"
        )
        result_none = self.utils.generate_dropdown_html(
            url="/directory/page.md", filename="page.md", exclude=None
        )
        assert result_default == result_none


class TestMCPHelpers:
    """Tests for the MCP deeplink and HTML helper static methods."""

    def test_build_cursor_deeplink_format(self):
        """Cursor deeplink should have correct scheme, path, and base64-encoded config."""
        result = AIFileUtils.build_cursor_deeplink("my-server", "https://mcp.example.com/sse")

        assert result.startswith("cursor://anysphere.cursor-deeplink/mcp/install?")
        assert "name=my-server" in result
        assert "&config=" in result

        # Extract and decode the config parameter
        config_b64 = result.split("&config=")[1]
        config_json = base64.urlsafe_b64decode(config_b64).decode()
        config = json.loads(config_json)
        assert config == {"url": "https://mcp.example.com/sse"}

    def test_build_cursor_deeplink_encodes_server_name(self):
        """Server names with special URL characters should be percent-encoded."""
        result = AIFileUtils.build_cursor_deeplink("my&server=bad", "https://mcp.example.com/sse")

        # The raw ampersand/equals must not appear unencoded in the query string
        assert "name=my&server" not in result
        assert f"name={urllib.parse.quote('my&server=bad', safe='')}" in result

    def test_build_vscode_deeplink_format(self):
        """VS Code deeplink should encode name and url as JSON in the query string."""
        result = AIFileUtils.build_vscode_deeplink("my-server", "https://mcp.example.com/sse")

        assert result.startswith("vscode:mcp/install?")

        # Decode the query string back to JSON
        encoded_json = result[len("vscode:mcp/install?"):]
        decoded = json.loads(urllib.parse.unquote(encoded_json))
        assert decoded == {"name": "my-server", "url": "https://mcp.example.com/sse"}

    def test_mcp_install_button_html(self):
        """Install button should be an <a> with correct class and default label."""
        result = AIFileUtils.mcp_install_button("cursor://install")

        assert 'href="cursor://install"' in result
        assert 'class="ai-file-actions-btn single-action-btn"' in result
        assert ">Install</a>" in result

    def test_mcp_install_button_custom_label(self):
        """Custom label should appear in the button text."""
        result = AIFileUtils.mcp_install_button("cursor://install", label="Add to Cursor")
        assert ">Add to Cursor</a>" in result

    def test_mcp_install_button_escapes_href(self):
        """href with special HTML characters should be escaped."""
        result = AIFileUtils.mcp_install_button('bad"onclick="alert(1)')
        assert 'href="bad&quot;onclick=&quot;alert(1)"' in result

    def test_mcp_copy_code_html(self):
        """Copy code should wrap command in <pre><code> tags with inline style."""
        result = AIFileUtils.mcp_copy_code("claude mcp add my-server https://example.com")
        assert "<pre><code" in result
        assert "white-space: pre-wrap" in result
        assert "claude mcp add my-server https://example.com</code></pre>" in result

    def test_mcp_copy_code_escapes_html(self):
        """HTML characters in commands should be escaped."""
        result = AIFileUtils.mcp_copy_code("echo <script>alert(1)</script>")
        assert "<script>" not in result
        assert "&lt;script&gt;" in result


class TestGenerateDropdownHtmlStyle:
    """Tests for the style parameter of generate_dropdown_html."""

    def setup_method(self):
        self.utils = AIFileUtils()

    # --- split style (default) ---

    def test_split_style_renders_copy_button(self):
        """Split style produces the primary copy button outside the menu."""
        result = self.utils.generate_dropdown_html(
            url="/page.md", filename="page.md", style="split"
        )
        assert "ai-file-actions-copy" in result

    def test_split_style_excludes_primary_from_menu(self):
        """Split style does not include the primary action as a menu item."""
        result = self.utils.generate_dropdown_html(
            url="/page.md", filename="page.md", style="split"
        )
        assert 'data-action-id="copy-markdown"' not in result

    def test_split_style_container_has_no_dropdown_modifier(self):
        """Split style container does not carry the --dropdown modifier class."""
        result = self.utils.generate_dropdown_html(
            url="/page.md", filename="page.md", style="split"
        )
        assert "ai-file-actions-container--dropdown" not in result

    # --- dropdown style ---

    def test_dropdown_style_has_no_copy_button(self):
        """Dropdown style does not render a standalone copy button."""
        result = self.utils.generate_dropdown_html(
            url="/page.md", filename="page.md", style="dropdown"
        )
        assert "ai-file-actions-copy" not in result

    def test_dropdown_style_primary_action_in_menu(self):
        """Dropdown style includes the primary action as a menu item."""
        result = self.utils.generate_dropdown_html(
            url="/page.md", filename="page.md", style="dropdown"
        )
        assert 'data-action-id="copy-markdown"' in result

    def test_dropdown_style_trigger_shows_label(self):
        """Dropdown style trigger button shows the dropdown_label text."""
        result = self.utils.generate_dropdown_html(
            url="/page.md", filename="page.md", style="dropdown",
            dropdown_label="Markdown for LLMs"
        )
        assert "Markdown for LLMs" in result

    def test_dropdown_style_custom_label(self):
        """dropdown_label is reflected in the trigger button."""
        result = self.utils.generate_dropdown_html(
            url="/page.md", filename="page.md", style="dropdown",
            dropdown_label="AI Tools"
        )
        assert "AI Tools" in result
        assert "Markdown for LLMs" not in result

    def test_dropdown_style_container_modifier_class(self):
        """Dropdown style container carries the --dropdown modifier class."""
        result = self.utils.generate_dropdown_html(
            url="/page.md", filename="page.md", style="dropdown"
        )
        assert "ai-file-actions-container--dropdown" in result

    def test_dropdown_style_trigger_carries_data_url(self):
        """Dropdown style trigger button carries data-url for JS."""
        result = self.utils.generate_dropdown_html(
            url="/page.md", filename="page.md", style="dropdown"
        )
        assert 'data-url="/page.md"' in result

    def test_dropdown_style_exclude_still_works(self):
        """Excluded action IDs are not present in dropdown style output."""
        result = self.utils.generate_dropdown_html(
            url="/page.md", filename="page.md", style="dropdown",
            exclude=["view-markdown"]
        )
        assert 'data-action-id="view-markdown"' not in result

    def test_default_style_is_split(self):
        """Omitting style produces the same output as style='split'."""
        default = self.utils.generate_dropdown_html(url="/page.md", filename="page.md")
        explicit = self.utils.generate_dropdown_html(
            url="/page.md", filename="page.md", style="split"
        )
        assert default == explicit

    def test_extra_classes_appended_to_split_container(self):
        """extra_classes are added to the container in split style."""
        result = self.utils.generate_dropdown_html(
            url="/page.md", filename="page.md", style="split",
            extra_classes="ai-file-actions-container--table",
        )
        assert "ai-file-actions-container--table" in result
        assert "ai-file-actions-container--dropdown" not in result

    def test_extra_classes_appended_to_dropdown_container(self):
        """extra_classes are added alongside --dropdown in dropdown style."""
        result = self.utils.generate_dropdown_html(
            url="/page.md", filename="page.md", style="dropdown",
            extra_classes="ai-file-actions-container--table",
        )
        assert "ai-file-actions-container--dropdown" in result
        assert "ai-file-actions-container--table" in result

    def test_no_extra_classes_by_default(self):
        """Without extra_classes, only the base class (and style modifier) appear."""
        result = self.utils.generate_dropdown_html(url="/page.md", filename="page.md")
        assert "ai-file-actions-container--table" not in result
