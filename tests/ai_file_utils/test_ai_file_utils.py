import html

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
        page_url = "/ai/pages/basics.md"
        filename = "basics.md"
        content = "# Polkadot Basics\n\nPolkadot is a sharded protocol."

        # 3. Call the public API: resolve_actions
        actions = utils.resolve_actions(page_url, filename, content, site_url=site_url)

        # Usage Verification:
        # Check that we got a list back
        assert isinstance(actions, list)
        assert len(actions) > 0

        # Inspect the "View Markdown" action
        view_action = next(a for a in actions if a["id"] == "view-markdown")
        assert view_action["href"] == "/ai/pages/basics.md"

        # Inspect the "Download Markdown" action (check download attribute interpolation)
        download_action = next(a for a in actions if a["id"] == "download-markdown")
        assert download_action["download"] == "basics.md"

        # Inspect the "Copy Markdown" (primary) action
        copy_action = next(a for a in actions if a["id"] == "copy-markdown")
        assert copy_action["clipboardContent"] == content
        assert copy_action.get("primary") is True

        # Inspect the "ChatGPT" action (check prompt encoding)
        chatgpt_action = next(a for a in actions if a["id"] == "open-chat-gpt")
        # The prompt should be encoded in the URL
        assert "chatgpt.com" in chatgpt_action["href"]
        # Should contain encoded reference to jina.ai with full site URL
        assert "r.jina.ai" in chatgpt_action["href"]
        assert "docs.polkadot.com" in chatgpt_action["href"]

        # Inspect the "Claude" action
        claude_action = next(a for a in actions if a["id"] == "open-claude")
        assert "claude.ai" in claude_action["href"]
        # Should contain encoded full URL (site_url + page_url) in the prompt
        assert "docs.polkadot.com" in claude_action["href"]

    def test_site_url_interpolation(self):
        """site_url should be interpolated into prompt templates without double slashes."""
        utils = AIFileUtils()

        actions = utils.resolve_actions(
            page_url="/ai/pages/test-page.md",
            filename="test-page.md",
            content="test",
            site_url="https://docs.example.com/",  # trailing slash should be stripped
        )

        chatgpt_action = next(a for a in actions if a["id"] == "open-chat-gpt")
        # The encoded href should contain the clean URL without double slashes
        # r.jina.ai/https://docs.example.com/ai/pages/test-page.md (no double slash)
        assert "docs.example.com" in chatgpt_action["href"]
        # Double slash between site_url and page_url should NOT appear
        assert "docs.example.com%2F%2Fai" not in chatgpt_action["href"]

    def test_site_url_defaults_to_empty(self):
        """When site_url is omitted, prompt templates still work with just page_url."""
        utils = AIFileUtils()

        actions = utils.resolve_actions(
            page_url="/ai/pages/test-page.md",
            filename="test-page.md",
            content="test",
        )

        chatgpt_action = next(a for a in actions if a["id"] == "open-chat-gpt")
        assert "chatgpt.com" in chatgpt_action["href"]
        assert "r.jina.ai" in chatgpt_action["href"]

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

        actions = utils.resolve_actions("http://example.com", "test.md", "content")

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
            url="/ai/pages/test.md", filename="test.md"
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
            url="/ai/pages/test.md", filename="test.md"
        )
        assert 'data-action-id="copy-markdown"' not in result

    def test_primary_button_driven_by_json(self):
        """The primary button should use label and icon from the JSON."""
        result = self.utils.generate_dropdown_html(
            url="/ai/pages/test.md", filename="test.md"
        )
        assert 'data-action="copy-markdown"' in result
        assert 'class="ai-file-actions-btn ai-file-actions-copy"' in result
        assert "Copy file" in result
        assert "M16 1H4c-1.1" in result

    def test_exclude_filters_actions(self):
        """Excluded action IDs should not appear in the output."""
        result = self.utils.generate_dropdown_html(
            url="/ai/pages/test.md",
            filename="test.md",
            exclude=["view-markdown", "open-claude"],
        )
        assert 'data-action-id="view-markdown"' not in result
        assert 'data-action-id="open-claude"' not in result
        assert 'data-action-id="download-markdown"' in result
        assert 'data-action-id="open-chat-gpt"' in result

    def test_primary_button_always_present(self):
        """The primary button should appear regardless of exclude list."""
        result = self.utils.generate_dropdown_html(
            url="/ai/pages/test.md",
            filename="test.md",
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
            url="/ai/pages/test.md", filename="test.md"
        )
        assert 'class="ai-file-actions-container"' in result
        assert 'class="ai-file-actions-btn ai-file-actions-trigger"' in result
        assert 'class="ai-file-actions-menu"' in result

    def test_html_escaping_for_special_urls(self):
        """URLs with special characters should be properly HTML-escaped."""
        url = '/ai/pages/test.md?foo=1&bar=2"<script>'
        result = self.utils.generate_dropdown_html(url=url, filename="test.md")
        assert '&bar=2"<script>' not in result
        safe = html.escape(url, quote=True)
        # Primary button still uses data-url
        assert f'data-url="{safe}"' in result
        # Link actions use href
        assert f'href="{safe}"' in result

    def test_exclude_none_same_as_no_exclude(self):
        """Passing exclude=None should show all actions."""
        result_default = self.utils.generate_dropdown_html(
            url="/ai/pages/test.md", filename="test.md"
        )
        result_none = self.utils.generate_dropdown_html(
            url="/ai/pages/test.md", filename="test.md", exclude=None
        )
        assert result_default == result_none
