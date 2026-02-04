import pytest
from plugins.ai_file_utils.plugin import AIFileUtilsPlugin

class TestAIFileUtilsPlugin:
    def test_resolve_actions_usage(self):
        """
        Demonstrates how to use the AIFileUtilsPlugin to resolve actions.
        """
        # 1. Instantiate the plugin
        # In a real MkDocs run, this happens automatically via entry points, 
        # but here we do it manually.
        plugin = AIFileUtilsPlugin()
        
        # 2. Initialize configuration (loading the JSON schema)
        # We simulate the on_config lifecycle event
        plugin.on_config({})

        # 3. Define the context for a specific page
        # This data usually comes from the processing loop in resolve_md
        page_url = "https://docs.polkadot.com/ai/pages/basics.md"
        filename = "basics.md"
        content = "# Polkadot Basics\n\nPolkadot is a sharded protocol."

        # 4. Call the public API: resolve_actions
        actions = plugin.resolve_actions(page_url, filename, content)

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

        # Inspect the "ChatGPT" action (check prompt encoding)
        chatgpt_action = next(a for a in actions if a["id"] == "open-chat-gpt")
        # The prompt should be encoded in the URL
        assert "chatgpt.com" in chatgpt_action["href"]
        assert "%23+Polkadot+Basics" in chatgpt_action["href"]  # Encoded '# Polkadot Basics'

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
