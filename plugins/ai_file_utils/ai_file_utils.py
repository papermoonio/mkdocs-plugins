import copy
import html
import json
import urllib.parse
from pathlib import Path
from typing import Any, Dict, List

from mkdocs.utils import log


class AIFileUtils:
    """
    A utility class for resolving AI file actions and generating
    the HTML UI components (split-button dropdown) for those actions.
    This acts as a shared library for plugins to resolve links,
    clipboard content, LLM prompts, and render action HTML based
    on a defined schema.
    """

    def __init__(self):
        self._actions_schema = None
        self._actions_config_path = Path(__file__).parent / "ai_file_actions.json"

    def _load_actions_schema(self):
        """
        Loads the actions definition from the JSON file.
        """
        try:
            if self._actions_config_path.exists():
                text = self._actions_config_path.read_text(encoding="utf-8")
                self._actions_schema = json.loads(text)
                log.info(
                    f"[ai_file_utils] Loaded actions schema from {self._actions_config_path}"
                )
            else:
                log.warning(
                    f"[ai_file_utils] Actions schema file not found at {self._actions_config_path}"
                )
                self._actions_schema = {"actions": []}
        except json.JSONDecodeError as e:
            log.error(f"[ai_file_utils] Failed to parse actions schema JSON: {e}")
            self._actions_schema = {"actions": []}
        except Exception as e:
            log.error(
                f"[ai_file_utils] Unexpected error loading actions schema: {e}",
                exc_info=True,
            )
            self._actions_schema = {"actions": []}

    def get_page_widget_config(self) -> Dict[str, Any]:
        """Return the ``pageWidget`` configuration from the JSON schema."""
        if not self._actions_schema:
            self._load_actions_schema()
        return self._actions_schema.get("pageWidget", {})

    def is_page_excluded(self, src_path: str, page_meta: Dict[str, Any]) -> bool:
        """Check whether a page should be excluded from widget injection."""
        config = self.get_page_widget_config()
        exclude_pages = config.get("excludePages", [])
        fm_key = config.get("frontMatterKey", "hide_ai_actions")

        for pattern in exclude_pages:
            if src_path == pattern or src_path.endswith(pattern):
                return True

        if page_meta.get(fm_key):
            return True

        return False

    def resolve_actions(
        self, page_url: str, filename: str, content: str, site_url: str = ""
    ) -> List[Dict[str, Any]]:
        """
        Resolves the list of actions for a given page context.

        Args:
            page_url: The absolute URL to the markdown file (ai artifact).
            filename: The name of the file (e.g., 'page.md').
            content: The actual text content of the markdown file.
            site_url: The site base URL (e.g., 'https://example.com').
                      Trailing slashes are stripped automatically.

        Returns:
            A list of action dictionaries with all placeholders resolved.
        """
        if not self._actions_schema:
            self._load_actions_schema()

        resolved_actions = []
        raw_actions = self._actions_schema.get("actions", [])

        for action_def in raw_actions:
            try:
                resolved_action = self._resolve_single_action(
                    action_def, page_url, filename, content, site_url
                )
                resolved_actions.append(resolved_action)
            except Exception as e:
                log.warning(
                    f"[ai_file_utils] Failed to resolve action {action_def.get('id')}: {e}",
                    exc_info=True,
                )

        return resolved_actions

    def _resolve_single_action(
        self,
        action_def: Dict[str, Any],
        page_url: str,
        filename: str,
        content: str,
        site_url: str = "",
    ) -> Dict[str, Any]:
        """
        Resolves a single action definition by replacing placeholders.
        """
        # Create a deep copy to avoid modifying the schema if it has nested structures
        action = copy.deepcopy(action_def)

        # Strip trailing slash from site_url so {{ site_url }}{{ page_url }}
        # produces clean URLs (page_url already starts with /).
        clean_site_url = site_url.rstrip("/")

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
                "{{ filename }}": filename,
                "{{ site_url }}": clean_site_url,
            }
            for placeholder, replacement in prompt_replacements.items():
                if placeholder in tpl:
                    tpl = tpl.replace(placeholder, replacement)
            prompt_text = tpl

            # Remove the template from the output as it's processed
            action.pop("promptTemplate")

        # 2. Prepare Context Variables
        # URL encode the prompt for use in query parameters
        encoded_prompt = urllib.parse.quote_plus(prompt_text)

        replacements = {
            "{{ page_url }}": page_url,
            "{{ filename }}": filename,
            "{{ content }}": content,  # Be careful with large content in attributes, but for clipboard it's needed
            "{{ prompt }}": encoded_prompt,
            "{{ site_url }}": clean_site_url,
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

    # ------------------------------------------------------------------
    # URL / slug resolution
    # ------------------------------------------------------------------

    @staticmethod
    def build_slug(page_url: str) -> str:
        """Convert a page URL to the slug used by resolve_md.

        Mirrors ``resolve_md.compute_slug_and_url`` and the client-side
        ``buildSlugFromPath`` in copy-to-llm.js.
        """
        route = page_url.strip("/")
        if not route:
            return "index"
        return route.replace("/", "-")

    @staticmethod
    def build_toggle_slug(page_url: str, data_filename: str) -> str:
        """Build a slug for a toggle-page variant.

        For the canonical variant (empty ``data_filename``), uses the
        base slug.  For non-canonical variants, drops the last path
        segment and appends the variant filename.
        """
        route = page_url.strip("/")
        if not data_filename:
            return route.replace("/", "-") if route else "index"
        segments = route.split("/")
        base = "-".join(segments[:-1]) if len(segments) > 1 else ""
        return f"{base}-{data_filename}" if base else data_filename

    @staticmethod
    def build_ai_page_url(slug: str) -> str:
        """Build the ``/ai/pages/{slug}.md`` URL from a slug."""
        return f"/ai/pages/{slug}.md"

    # ------------------------------------------------------------------
    # HTML generation
    # ------------------------------------------------------------------

    def _render_primary_button(
        self, action: dict, url: str, primary_label: str | None = None
    ) -> str:
        """Render the primary (left-side) button from a JSON action."""
        safe_url = html.escape(url, quote=True)
        raw_label = primary_label if primary_label else action.get("label", "Copy file")
        label = html.escape(raw_label, quote=True)
        icon_svg = action.get("icon", "")
        action_id = html.escape(action.get("id", ""), quote=True)

        spinner_svg = (
            '<svg class="ai-file-actions-icon'
            ' loading-spinner"'
            ' xmlns="http://www.w3.org/2000/svg"'
            ' viewBox="0 0 24 24"'
            ' width="24" height="24">'
            '<circle cx="12" cy="12" r="10"'
            ' stroke="currentColor"'
            ' stroke-width="2" fill="none"'
            ' stroke-dasharray="31.4"'
            ' stroke-dashoffset="0">'
            '<animate attributeName="stroke-dashoffset"'
            ' dur="1s" repeatCount="indefinite"'
            ' from="0" to="62.8"/>'
            "</circle></svg>"
        )
        success_svg = (
            '<svg class="ai-file-actions-icon'
            ' copy-success-icon"'
            ' xmlns="http://www.w3.org/2000/svg"'
            ' viewBox="0 0 24 24">'
            '<path fill="currentColor"'
            ' d="M9 16.17L4.83 12l-1.42 1.41L9'
            ' 19 21 7l-1.41-1.41z"/>'
            "</svg>"
        )

        loading_attr = html.escape(spinner_svg, quote=True)
        success_attr = html.escape(success_svg, quote=True)

        return (
            '<button class="ai-file-actions-btn'
            ' ai-file-actions-copy"'
            f' title="{label}"'
            f' aria-label="{label}"'
            ' role="button"'
            f' data-action="{action_id}"'
            f' data-url="{safe_url}"'
            f' data-loading-html="{loading_attr}"'
            f' data-success-html="{success_attr}">'
            f"{icon_svg}"
            f'<span class="button-text">{label}</span>'
            "</button>"
        )

    def _render_action_item(self, action: dict, url: str) -> str:
        """Render a single dropdown item from a resolved action.

        Link-type actions render as ``<a>`` so the browser handles
        navigation natively.  Clipboard actions render as ``<button>``
        since copying requires JavaScript.
        """
        action_type = action.get("type", "link")
        action_id = action.get("id", "")
        label = html.escape(action.get("label", ""), quote=True)
        icon_svg = action.get("icon", "")
        trailing_svg = action.get("trailingIcon", "")

        safe_id = html.escape(action_id, quote=True)
        inner = f"{icon_svg}" f"<span>{label}</span>" f"{trailing_svg}"

        if action_type == "link":
            href = action.get("href", "")
            safe_href = html.escape(href, quote=True)
            dl_attr = ""
            if "download" in action:
                safe_dl = html.escape(action["download"], quote=True)
                dl_attr = f' download="{safe_dl}"'
            else:
                dl_attr = ' target="_blank" rel="noopener noreferrer"'
            return (
                f'<a class="ai-file-actions-item"'
                f' href="{safe_href}"'
                f"{dl_attr}"
                f' data-action-id="{safe_id}"'
                f' role="menuitem" tabindex="-1">'
                f"{inner}"
                f"</a>"
            )

        # clipboard (or any non-link type)
        safe_url = html.escape(url, quote=True)
        return (
            f'<button class="ai-file-actions-item"'
            f' data-action-type="clipboard"'
            f' data-action-id="{safe_id}"'
            f' data-url="{safe_url}"'
            f' role="menuitem" tabindex="-1">'
            f"{inner}"
            f"</button>"
        )

    def generate_dropdown_html(
        self,
        url: str,
        filename: str,
        exclude: list | None = None,
        primary_label: str | None = None,
        site_url: str = "",
    ) -> str:
        """
        Generate the HTML for the AI file actions split-button.

        The action marked ``primary: true`` in the JSON renders
        as the left-side button; all other actions render as
        dropdown items.  The primary action is automatically
        excluded from the dropdown.

        Args:
            url: The URL of the file to act upon.
            filename: The filename for the download action.
            exclude: Optional list of action IDs to exclude
                     from the dropdown.
            primary_label: Optional label override for the primary
                     button (e.g., "Copy page" vs default "Copy file").
            site_url: The site base URL (e.g., 'https://example.com').

        Returns:
            The HTML string for the component.
        """
        actions = self.resolve_actions(
            page_url=url, filename=filename, content="", site_url=site_url
        )

        # Separate primary action from dropdown actions
        primary_action = None
        dropdown_actions = []
        exclude_set = set(exclude) if exclude else set()

        for action in actions:
            if action.get("primary"):
                primary_action = action
            elif action.get("id") not in exclude_set:
                dropdown_actions.append(action)

        # Primary copy button (left side of split button)
        copy_btn = self._render_primary_button(
            primary_action or {}, url, primary_label=primary_label
        )

        # Dropdown trigger (right side of split button)
        chevron = (
            '<svg xmlns="http://www.w3.org/2000/svg"'
            ' width="24px" height="24px"'
            ' viewBox="0 0 24 24"'
            ' class="ai-file-actions-icon'
            ' ai-file-actions-chevron"'
            ' aria-hidden="true">'
            '<path d="M7 10l5 5 5-5z"/></svg>'
        )
        dropdown_btn = (
            '<button class="ai-file-actions-btn'
            ' ai-file-actions-trigger"'
            ' title="More options"'
            ' type="button"'
            ' aria-label="More options"'
            ' aria-haspopup="true"'
            ' aria-expanded="false"'
            ' role="button">'
            f"{chevron}"
            "</button>"
        )

        # Dropdown menu items
        menu_items = ""
        for action in dropdown_actions:
            menu_items += self._render_action_item(action, url)

        dropdown_menu = (
            '<div class="ai-file-actions-menu"' ' role="menu">' f"{menu_items}" "</div>"
        )

        return (
            '<div class="ai-file-actions-container">'
            f"{copy_btn}"
            f"{dropdown_btn}"
            f"{dropdown_menu}"
            "</div>"
        )
