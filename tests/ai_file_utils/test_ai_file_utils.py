import pytest
from plugins.ai_file_utils.ai_file_utils import AIFileUtils

class TestAIFileUtils:
    def test_resolve_actions_usage(self):
        """
        Demonstrates how to use the AIFileUtils to resolve actions.
        """
        # 1. Instantiate the utility class
        utils = AIFileUtils()
        
        # 2. (Optional) Initialize configuration - redundant here as it loads lazily
        # utils._load_actions_schema() 

        # 3. Define the context for a specific page
        # This data usually comes from the processing loop in resolve_md
        page_url = "https://docs.polkadot.com/ai/pages/basics.md"
        filename = "basics.md"
        content = "# Polkadot Basics\n\nPolkadot is a sharded protocol."

        # 4. Call the public API: resolve_actions
        actions = utils.resolve_actions(page_url, filename, content)

        # Usage Verification:
        # Check that we got a list back
        assert isinstance(actions, list)
        assert len(actions) > 0

        # Inspect the "View Markdown" action
        view_action = next(a for a in actions if a["id"] == "view-markdown")
        assert view_action["href"] == "https://docs.polkadot.com/ai/pages/basics.md"
        
        # Inspect the "Download Markdown" action (check download attribute interpolation)
        download_action = next(a for a in actions if a["id"] == "download-markdown")
        assert download_action["download"] == "basics.md"

        # Inspect the "Copy Markdown" action
        copy_action = next(a for a in actions if a["id"] == "copy-markdown")
        assert copy_action["clipboardContent"] == content

        # Inspect the "ChatGPT" action (check prompt encoding)
        chatgpt_action = next(a for a in actions if a["id"] == "open-chat-gpt")
        # The prompt should be encoded in the URL
        assert "chatgpt.com" in chatgpt_action["href"]
        # Should contain encoded reference to jina.ai (part of the prompt now)
        assert "r.jina.ai" in chatgpt_action["href"]

        # Inspect the "Claude" action
        claude_action = next(a for a in actions if a["id"] == "open-claude")
        assert "claude.ai" in claude_action["href"]
        # Should contain encoded page url as it's part of the prompt
        assert "docs.polkadot.com" in claude_action["href"]

        # This would be the structure consumed by the UI generator
        print("\n--- Resolved Actions Example ---")
        for action in actions:
            print(f"Action ID: {action['id']}")
            print(f"  Type: {action['type']}")
            print(f"  Label: {action['label']}")
            if "href" in action:
                print(f"  Href: {action['href'][:50]}...") # Truncated for display
            if "clipboardContent" in action:
                print(f"  Clipboard: {action['clipboardContent'][:20]}...")

    def test_missing_schema_file(self, tmp_path, caplog):
        """Test behavior when schema file is missing."""
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
                {
                    "id": "good-action",
                    "type": "link", 
                    "href": "{{ page_url }}"
                },
                {
                    "id": "bad-action",
                    "type": "link",
                    "promptTemplate": 123  # This will cause AttributeError on replace()
                }
            ]
        }
        
        actions = utils.resolve_actions("http://example.com", "test.md", "content")
        
        # We should get the good action
        assert len(actions) == 1
        assert actions[0]["id"] == "good-action"
        
        # We should see a warning for the bad action
        assert "Failed to resolve action bad-action" in caplog.text

