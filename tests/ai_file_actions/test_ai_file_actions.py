import html

from helper_lib.ai_file_actions.plugin import AiFileActionsPlugin
from helper_lib.ai_file_utils.ai_file_utils import AIFileUtils


class TestAiFileActionsPlugin:
    def setup_method(self):
        self.plugin = AiFileActionsPlugin()

    def test_all_dropdown_actions_render_by_default(self):
        """All 4 non-primary action IDs should appear in the dropdown."""
        result = self.plugin.generate_dropdown_html(
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
        result = self.plugin.generate_dropdown_html(
            url="/ai/pages/test.md", filename="test.md"
        )
        assert 'data-action-id="copy-markdown"' not in result

    def test_primary_button_driven_by_json(self):
        """The primary button should use label and icon from the JSON."""
        result = self.plugin.generate_dropdown_html(
            url="/ai/pages/test.md", filename="test.md"
        )
        assert 'data-action="copy-markdown"' in result
        assert 'class="ai-file-actions-btn ai-file-actions-copy"' in result
        # Label from JSON
        assert "Copy file" in result
        # Icon SVG from JSON (the copy icon path)
        assert "M16 1H4c-1.1" in result

    def test_exclude_filters_actions(self):
        """Excluded action IDs should not appear in the output."""
        result = self.plugin.generate_dropdown_html(
            url="/ai/pages/test.md",
            filename="test.md",
            exclude=["view-markdown", "open-claude"],
        )
        assert 'data-action-id="view-markdown"' not in result
        assert 'data-action-id="open-claude"' not in result
        # Others should still be present
        assert 'data-action-id="download-markdown"' in result
        assert 'data-action-id="open-chat-gpt"' in result

    def test_primary_button_always_present(self):
        """The primary button should appear regardless of exclude list."""
        result = self.plugin.generate_dropdown_html(
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

    def test_link_actions_render_as_anchor_tags(self):
        """Link-type actions should render as <a> tags with href."""
        result = self.plugin.generate_dropdown_html(
            url="/ai/pages/test.md", filename="test.md"
        )
        assert '<a class="ai-file-actions-item"' in result
        assert 'href="/ai/pages/test.md"' in result
        assert 'target="_blank"' in result

    def test_download_actions_have_download_attribute(self):
        """Download actions should be <a> tags with a download attribute."""
        result = self.plugin.generate_dropdown_html(
            url="/ai/pages/test.md", filename="test.md"
        )
        assert 'download="test.md"' in result

    def test_svg_icons_in_dropdown(self):
        """Each dropdown item should contain an SVG icon."""
        result = self.plugin.generate_dropdown_html(
            url="/ai/pages/test.md", filename="test.md"
        )
        menu_start = result.index('role="menu"')
        menu_html = result[menu_start:]
        # 4 leading icons + 2 trailing icons (ChatGPT, Claude)
        assert menu_html.count("<svg") == 6

    def test_html_escaping_for_special_urls(self):
        """URLs with special characters should be properly HTML-escaped."""
        url = '/ai/pages/test.md?foo=1&bar=2"<script>'
        result = self.plugin.generate_dropdown_html(url=url, filename="test.md")
        assert '&bar=2"<script>' not in result
        safe = html.escape(url, quote=True)
        assert f'data-url="{safe}"' in result

    def test_container_structure(self):
        """The output should have the correct container structure."""
        result = self.plugin.generate_dropdown_html(
            url="/ai/pages/test.md", filename="test.md"
        )
        assert 'class="ai-file-actions-container"' in result
        assert 'class="ai-file-actions-btn ai-file-actions-trigger"' in result
        assert 'class="ai-file-actions-menu"' in result

    def test_exclude_none_same_as_no_exclude(self):
        """Passing exclude=None should show all actions (same as default)."""
        result_default = self.plugin.generate_dropdown_html(
            url="/ai/pages/test.md", filename="test.md"
        )
        result_none = self.plugin.generate_dropdown_html(
            url="/ai/pages/test.md", filename="test.md", exclude=None
        )
        assert result_default == result_none

    def test_exclude_empty_list_shows_all(self):
        """Passing an empty exclude list should show all actions."""
        result_default = self.plugin.generate_dropdown_html(
            url="/ai/pages/test.md", filename="test.md"
        )
        result_empty = self.plugin.generate_dropdown_html(
            url="/ai/pages/test.md", filename="test.md", exclude=[]
        )
        assert result_default == result_empty

    def test_delegation_matches_ai_file_utils(self):
        """Plugin output should match AIFileUtils output exactly."""
        utils = AIFileUtils()
        url = "/ai/pages/test.md"
        filename = "test.md"
        exclude = ["view-markdown"]

        plugin_result = self.plugin.generate_dropdown_html(
            url=url, filename=filename, exclude=exclude
        )
        utils_result = utils.generate_dropdown_html(
            url=url, filename=filename, exclude=exclude
        )
        assert plugin_result == utils_result
