from mkdocs.plugins import BasePlugin
import html

class AiFileActionsPlugin(BasePlugin):
    def generate_dropdown_html(self, url: str, filename: str, view: bool = True) -> str:
        """
        Generates the HTML structure for the AI file actions dropdown.
        Replicates the structure of the copy-to-llm split button.
        
        Args:
            url (str): The URL of the file to act upon.
            filename (str): The filename for the download action.
            view (bool): Whether to include the "View" action. Defaults to True.
            
        Returns:
            str: The HTML string for the component.
        """
        # Define SVG assets
        # We use single quotes for attributes inside the SVG to make it easier to embed in double-quoted HTML attributes,
        # but we will also HTML-escape the entire string to be safe.
        spinner_svg = (
            '<svg class="ai-file-actions-icon loading-spinner" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24">'
            '<circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="2" fill="none" stroke-dasharray="31.4" stroke-dashoffset="0">'
            '<animate attributeName="stroke-dashoffset" dur="1s" repeatCount="indefinite" from="0" to="62.8"/>'
            '</circle>'
            '</svg>'
        )

        success_svg = (
            '<svg class="ai-file-actions-icon copy-success-icon" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
            '<path fill="currentColor" d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/>'
            '</svg>'
        )

        # HTML Escape the SVG strings so they can be safely put into data attributes
        loading_html_attr = html.escape(spinner_svg, quote=True)
        success_html_attr = html.escape(success_svg, quote=True)

        # HTML Escape the URL and filename to prevent attribute injection
        safe_url = html.escape(url, quote=True)
        safe_filename = html.escape(filename, quote=True)

        # Copy Button (Left side of split button)
        copy_btn = (
            f'<button class="ai-file-actions-btn ai-file-actions-copy"'
            f' title="Copy file content"'
            f' aria-label="Copy file content"'
            f' role="button"'
            f' data-action="copy-file"'
            f' data-url="{safe_url}"'
            f' data-loading-html="{loading_html_attr}"'
            f' data-success-html="{success_html_attr}">'
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" class="ai-file-actions-icon" aria-hidden="true">'
            f'<path d="M16 1H4c-1.1 0-2 .9-2 2v14h2V3h12V1zm3 4H8c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h11c1.1 0 2-.9 2-2V7c0-1.1-.9-2-2-2zm0 16H8V7h11v14z"/>'
            f'</svg>'
            f'<span class="button-text">Copy file</span>'
            f'</button>'
        )

        # Dropdown Button (Right side of split button)
        dropdown_btn = (
            f'<button class="ai-file-actions-btn ai-file-actions-trigger"'
            f' title="More options"'
            f' type="button"'
            f' aria-label="More options"'
            f' aria-haspopup="true"'
            f' aria-expanded="false"'
            f' role="button">'
            f'<svg xmlns="http://www.w3.org/2000/svg" width="24px" height="24px" viewBox="0 0 24 24" class="ai-file-actions-icon ai-file-actions-chevron" aria-hidden="true"><path d="M7 10l5 5 5-5z"/></svg>'
            f'</button>'
        )

        # Dropdown Items
        
        # View Item
        view_item = (
            f'<button class="ai-file-actions-item"'
            f' data-action="view-file"'
            f' data-url="{safe_url}"'
            f' role="menuitem" tabindex="-1">'
            f'<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16" class="ai-file-actions-icon">'
            f'<path d="M8 2c1.981 0 3.671.992 4.933 2.078 1.27 1.091 2.187 2.345 2.637 3.023a1.62 1.62 0 0 1 0 1.798c-.45.678-1.367 1.932-2.637 3.023C11.67 13.008 9.981 14 8 14c-1.981 0-3.671-.992-4.933-2.078C1.797 10.83.88 9.576.43 8.898a1.62 1.62 0 0 1 0-1.798c.45-.677 1.367-1.931 2.637-3.022C4.33 2.992 6.019 2 8 2ZM1.679 7.932a.12.12 0 0 0 0 .136c.411.622 1.241 1.75 2.366 2.717C5.176 11.758 6.527 12.5 8 12.5c1.473 0 2.825-.742 3.955-1.715 1.124-.967 1.954-2.096 2.366-2.717a.12.12 0 0 0 0-.136c-.412-.621-1.242-1.75-2.366-2.717C10.824 4.242 9.473 3.5 8 3.5c-1.473 0-2.825.742-3.955 1.715-1.124.967-1.954 2.096-2.366 2.717ZM8 10a2 2 0 1 1-.001-3.999A2 2 0 0 1 8 10Z"/>'
            f'</svg>'
            f'<span>View file in Markdown</span>'
            f'</button>'
        )

        # Download Item
        download_item = (
            f'<button class="ai-file-actions-item"'
            f' data-action="download-file"'
            f' data-url="{safe_url}"'
            f' data-filename="{safe_filename}"'
            f' role="menuitem" tabindex="-1">'
            f'<svg class="octicon ai-file-actions-icon" aria-hidden="true" width="16" height="16" viewBox="0 0 16 16">'
            f'<path d="M2.75 14A1.75 1.75 0 0 1 1 12.25v-2.5a.75.75 0 0 1 1.5 0v2.5c0 .138.112.25.25.25h10.5a.25.25 0 0 0 .25-.25v-2.5a.75.75 0 0 1 1.5 0v2.5A1.75 1.75 0 0 1 13.25 14Z"/>'
            f'<path d="M7.25 7.689V2a.75.75 0 0 1 1.5 0v5.689l1.97-1.969a.749.749 0 1 1 1.06 1.06l-3.25 3.25a.75.75 0 0 1-1.06 0L4.22 6.78a.749.749 0 1 1 1.06-1.06z"/>'
            f'</svg>'
            f'<span>Download file in Markdown</span>'
            f'</button>'
        )

        # Construct dropdown menu content
        menu_items = ""
        if view:
            menu_items += view_item
        menu_items += download_item

        dropdown_menu = (
             f'<div class="ai-file-actions-menu" role="menu">'
             f'{menu_items}'
             f'</div>'
        )

        return (
            f'<div class="ai-file-actions-container">'
            f'{copy_btn}'
            f'{dropdown_btn}'
            f'{dropdown_menu}'
            f'</div>'
        )
