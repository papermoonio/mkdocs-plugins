import json
import logging
import re
import urllib.parse
from pathlib import Path
from typing import Any, Dict, List, Optional
from mkdocs.plugins import BasePlugin

# Configure Logger
log = logging.getLogger("mkdocs.plugins.ai_file_utils")

class AIFileUtilsPlugin(BasePlugin):
    """
    A MkDocs plugin that provides utilities for resolving AI file actions.
    This plugin acts as a library/service for other plugins to resolve
    links, clipboard content, and LLM prompts based on a defined schema.
    """

    def __init__(self):
        self._actions_schema = None
        self._actions_config_path = Path(__file__).parent / "ai_file_actions.json"

    def on_config(self, config, **kwargs):
        """
        Load the actions schema when the configuration is loaded.
        """
        self._load_actions_schema()
        return config

    def _load_actions_schema(self):
        """
        Loads the actions definition from the JSON file.
        """
        try:
            if self._actions_config_path.exists():
                text = self._actions_config_path.read_text(encoding="utf-8")
                self._actions_schema = json.loads(text)
                log.info(f"[ai_file_utils] Loaded actions schema from {self._actions_config_path}")
            else:
                log.warning(f"[ai_file_utils] Actions schema file not found at {self._actions_config_path}")
                self._actions_schema = {"actions": []}
        except Exception as e:
            log.error(f"[ai_file_utils] Failed to load actions schema: {e}")
            self._actions_schema = {"actions": []}

    def resolve_actions(self, page_url: str, filename: str, content: str) -> List[Dict[str, Any]]:
        """
        Resolves the list of actions for a given page context.

        Args:
            page_url: The absolute URL to the markdown file (ai artifact).
            filename: The name of the file (e.g., 'page.md').
            content: The actual text content of the markdown file.

        Returns:
            A list of action dictionaries with all placeholders resolved.
        """
        if not self._actions_schema:
            self._load_actions_schema()

        resolved_actions = []
        raw_actions = self._actions_schema.get("actions", [])

        for action_def in raw_actions:
            try:
                resolved_action = self._resolve_single_action(action_def, page_url, filename, content)
                resolved_actions.append(resolved_action)
            except Exception as e:
                log.warning(f"[ai_file_utils] Failed to resolve action {action_def.get('id')}: {e}")

        return resolved_actions

    def _resolve_single_action(self, action_def: Dict[str, Any], page_url: str, filename: str, content: str) -> Dict[str, Any]:
        """
        Resolves a single action definition by replacing placeholders.
        """
        # Create a copy to avoid modifying the schema
        action = action_def.copy()
        
        # 1. Resolve Prompt if a template exists
        prompt_text = ""
        if "promptTemplate" in action:
            tpl = action["promptTemplate"]
            # Apply replacements to the prompt template first
            # We construct a specific dict for prompt replacements to avoid circular dependency with "{{ prompt }}"
            # and to handle content/url availability
            prompt_replacements = {
                "{{ content }}": content,
                "{{ page_url }}": page_url,
                "{{ filename }}": filename
            }
            for placeholder, replacement in prompt_replacements.items():
                if placeholder in tpl:
                    tpl = tpl.replace(placeholder, replacement)
            prompt_text = tpl
            
            # Remove the template from the output as it's processed
            # action.pop("promptTemplate") 
        
        # 2. Prepare Context Variables
        # URL encode the prompt for use in query parameters
        encoded_prompt = urllib.parse.quote_plus(prompt_text)
        
        replacements = {
            "{{ page_url }}": page_url,
            "{{ filename }}": filename,
            "{{ content }}": content, # Be careful with large content in attributes, but for clipboard it's needed
            "{{ prompt }}": encoded_prompt
        }

        # 3. Interpolate values into specific fields
        # Fields that support interpolation
        target_fields = ["href", "download", "clipboardContent"]

        for field in target_fields:
            if field in action and isinstance(action[field], str):
                val = action[field]
                for placeholder, replacement in replacements.items():
                    if placeholder in val:
                        val = val.replace(placeholder, replacement)
                action[field] = val

        return action
