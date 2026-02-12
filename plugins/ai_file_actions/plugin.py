import html

from mkdocs.plugins import BasePlugin

from plugins.ai_file_utils.ai_file_utils import AIFileUtils


class AiFileActionsPlugin(BasePlugin):
    def __init__(self):
        super().__init__()
        self._file_utils = AIFileUtils()

    def _render_primary_button(
        self, action: dict, url: str
    ) -> str:
        """Render the primary (left-side) button from a JSON action."""
        safe_url = html.escape(url, quote=True)
        label = html.escape(
            action.get("label", "Copy file"), quote=True
        )
        icon_svg = action.get("icon", "")
        action_id = html.escape(
            action.get("id", ""), quote=True
        )

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

    def _render_action_item(
        self, action: dict, url: str
    ) -> str:
        """Render a single dropdown item from a resolved action."""
        action_type = action.get("type", "link")
        action_id = action.get("id", "")
        label = html.escape(
            action.get("label", ""), quote=True
        )
        icon_svg = action.get("icon", "")
        trailing_svg = action.get("trailingIcon", "")

        safe_type = html.escape(action_type, quote=True)
        safe_id = html.escape(action_id, quote=True)
        attrs = (
            f' data-action-type="{safe_type}"'
            f' data-action-id="{safe_id}"'
        )

        if action_type == "link":
            href = action.get("href", "")
            safe_href = html.escape(href, quote=True)
            attrs += f' data-href="{safe_href}"'
            if "download" in action:
                safe_dl = html.escape(
                    action["download"], quote=True
                )
                attrs += f' data-download="{safe_dl}"'
        elif action_type == "clipboard":
            safe_url = html.escape(url, quote=True)
            attrs += f' data-url="{safe_url}"'

        return (
            f'<button class="ai-file-actions-item"'
            f"{attrs}"
            f' role="menuitem" tabindex="-1">'
            f"{icon_svg}"
            f"<span>{label}</span>"
            f"{trailing_svg}"
            f"</button>"
        )

    def generate_dropdown_html(
        self,
        url: str,
        filename: str,
        exclude: list | None = None,
    ) -> str:
        """
        Generates the HTML for the AI file actions split-button.

        The action marked ``primary: true`` in the JSON renders
        as the left-side button; all other actions render as
        dropdown items.  The primary action is automatically
        excluded from the dropdown.

        Args:
            url: The URL of the file to act upon.
            filename: The filename for the download action.
            exclude: Optional list of action IDs to exclude
                     from the dropdown.

        Returns:
            The HTML string for the component.
        """
        actions = self._file_utils.resolve_actions(
            page_url=url, filename=filename, content=""
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
            primary_action or {}, url
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
            menu_items += self._render_action_item(
                action, url
            )

        dropdown_menu = (
            '<div class="ai-file-actions-menu"'
            ' role="menu">'
            f"{menu_items}"
            "</div>"
        )

        return (
            '<div class="ai-file-actions-container">'
            f"{copy_btn}"
            f"{dropdown_btn}"
            f"{dropdown_menu}"
            "</div>"
        )
