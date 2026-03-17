from collections import defaultdict
from html import escape
from pathlib import Path
from typing import List, Any
from mkdocs.plugins import BasePlugin
from mkdocs.structure.pages import Page
from mkdocs.structure.files import Files
from mkdocs.config.defaults import MkDocsConfig
from bs4 import BeautifulSoup


class TogglePagesPlugin(BasePlugin):
    def __init__(self):
        # group -> { canonical: str, variants: {variant_name: {page, label, html, toc_html}} }
        self.toggle_groups = defaultdict(lambda: {"canonical": None, "variants": {}})

    # ------------------------------------------------------------
    # Capture content and TOC from all pages in toggle groups
    # ------------------------------------------------------------
    def on_page_content(self, html: str, page: Page, config: MkDocsConfig, files: Files) -> str:
        toggle = page.meta.get("toggle")
        if not toggle:
            return html

        # Extract toggle metadata
        group = toggle.get("group")
        is_canonical = toggle.get("canonical", False)

        if not group:
            return html

        variant = toggle.get("variant")
        if not variant:
            return html

        label = toggle.get("label", variant)

        # Prepare and store data to be accessed by other hooks
        group_data = self.toggle_groups.setdefault(
            group, {"canonical": None, "variants": {}}
        )

        # Store content + pre-rendered TOC HTML
        toc_html = self.render_toc_html(
            getattr(page, "toc", []),
            variant=variant,
            is_canonical=is_canonical,
        )

        soup = BeautifulSoup(html, "html.parser")

        h1 = soup.find("h1")
        h1_html = None
        if h1:
            h1_html = str(h1)
            h1.extract()

        # Fix tabbed elements for non-canonical pages
        if not is_canonical:
            for tabbed in soup.select(".tabbed-set"):
                labels = tabbed.select(".tabbed-labels label")
                inputs = tabbed.select("input[type='radio']")
                if not inputs or not labels:
                    continue

                # Build a lookup of input IDs for validation against labels.
                input_ids = {inp.get("id") for inp in inputs if inp.get("id")}

                # Use same name for all inputs in this tabbed set
                group_name = f"{variant}{inputs[0].get('name', '__tabbed')}"

                # Update input IDs and names
                for inp in inputs:
                    input_id = inp.get("id")
                    new_id = f"{variant}{input_id}"
                    inp["id"] = new_id
                    inp["name"] = group_name
                    inp.attrs.pop("checked", None)

                # Update labels AFTER inputs IDs are updated
                for label_tag in labels:
                    if label_tag.find("a"):
                        continue
                    input_id = label_tag.get("for")
                    if input_id not in input_ids:
                        continue
                    text = label_tag.text.strip()
                    label_tag.clear()
                    label_tag["for"] = f"{variant}{input_id}"
                    a_tag = soup.new_tag("a", href=f"#{variant}{input_id}", tabindex="-1")
                    a_tag.string = text
                    label_tag.append(a_tag)

                # Check the first input
                first_input = inputs[0]
                first_input.attrs["checked"] = "checked"

                # Set indicator CSS
                first_label = labels[0]
                indicator_width = str(len(first_label.text.strip()) * 8) + "px"
                tabbed["style"] = f"--md-indicator-x: 0px; --md-indicator-width: {indicator_width};"


        html = str(soup)

        group_data["variants"][variant] = {
            "page": page,
            "label": label,
            "html": html,
            "h1_html": h1_html,
            "toc_html": toc_html,
        }

        if is_canonical:
            group_data["canonical"] = variant
            # Render immediately with whatever variants are available.
            # If variants processed later were missed, on_post_build will
            # re-render with the complete set.
            group_data["rendered_variants"] = set(group_data["variants"].keys())
            return self.render_toggle_page(group)

        # Non-canonical variants render nothing
        return ""

    # ------------------------------------------------------------
    # Fix up any toggle groups that had late variants, then clean up
    # ------------------------------------------------------------
    def on_post_build(self, config: MkDocsConfig) -> None:
        for group, group_data in self.toggle_groups.items():
            canonical_variant = group_data["canonical"]
            if not canonical_variant:
                continue

            # Check if any variants were processed after the canonical page
            rendered = group_data.get("rendered_variants", set())
            all_variants = set(group_data["variants"].keys())
            missing = all_variants - rendered

            if missing:
                # Re-render with all variants and update the output file.
                rendered_html = self.render_toggle_page(group)
                canonical_page = group_data["variants"][canonical_variant]["page"]
                canonical_path = Path(canonical_page.file.abs_dest_path)
                if canonical_path.exists():
                    full_html = canonical_path.read_text(encoding="utf-8")
                    soup = BeautifulSoup(full_html, "html.parser")
                    esc_group = escape(group, quote=True)
                    container = soup.select_one(
                        f'.toggle-container[data-toggle-group="{esc_group}"]'
                    )
                    if container:
                        new_container = BeautifulSoup(rendered_html, "html.parser")
                        container.replace_with(new_container)
                        full_html = str(soup)

                    # Re-inject AI page action widgets for the updated toggle
                    ai_plugin = config.get("plugins", {}).get("ai_page_actions")
                    if ai_plugin and hasattr(ai_plugin, "on_post_page"):
                        updated = ai_plugin.on_post_page(
                            full_html, page=canonical_page, config=config
                        )
                        if updated:
                            full_html = updated

                    canonical_path.write_text(full_html, encoding="utf-8")

            # Remove non-canonical variant output files.
            for variant, data in group_data["variants"].items():
                page = data["page"]
                toggle = page.meta.get("toggle", {})
                if toggle.get("canonical"):
                    continue

                output_path = Path(page.file.abs_dest_path)
                if output_path.exists():
                    output_path.unlink()

    # ------------------------------------------------------------
    # Render canonical page with toggle
    # ------------------------------------------------------------
    def render_toggle_page(self, group: str) -> str:
        group_data = self.toggle_groups[group]
        canonical = group_data["canonical"]
        variants = group_data["variants"]

        buttons_html = []
        content_html = []
        headers_html = []

        # Ensure canonical variant is first
        ordered_variants = [canonical] + [
            v for v in variants.keys() if v != canonical
        ]
        for variant in ordered_variants:
            data = variants[variant]
            active_class = "active" if variant == canonical else ""
            data_filename = (
                ""
                if variant == canonical
                else f"{data['page'].url.rstrip('/').split('/')[-1]}"
            )

            esc_variant = escape(variant, quote=True)
            esc_label = escape(data["label"], quote=True)
            esc_filename = escape(data_filename, quote=True)

            # Header
            headers_html.append(
                f'<span data-variant="{esc_variant}">{data["h1_html"] or ""}</span>'
            )

            # Buttons
            buttons_html.append(
                f'<button class="toggle-btn {active_class}" data-variant="{esc_variant}"'
                f' data-canonical="{str(variant == canonical).lower()}" data-filename="{esc_filename}">{esc_label}</button>'
            )

            # Content panels
            toc_html_attr = escape(data["toc_html"], quote=True)
            content_html.append(
                f'<div class="toggle-panel {active_class}" '
                f'data-variant="{esc_variant}" '
                f'data-toc-html="{toc_html_attr}">'
                f'{data["html"]}'
                f"</div>"
            )

        esc_group = escape(group, quote=True)
        return f"""
<div class="toggle-container" data-toggle-group="{esc_group}">
  <div class="toggle-header">
   {''.join(headers_html)}
    <div class="toggle-buttons">
        {''.join(buttons_html)}
    </div>
  </div>
  <div class="toggle-content">
    {''.join(content_html)}
  </div>
</div>
"""

    # ------------------------------------------------------------
    # Render page TOC in MkDocs sidebar format
    # ------------------------------------------------------------
    def render_toc_html(self, items: List[Any], variant: str, is_canonical: bool) -> str:
        """
        Render page.toc into MkDocs sidebar HTML format.
        For non-canonical variants, prefix IDs with `{variant}-`.
        Only includes h2+ headers (skip h1).
        """

        def rewrite_id(id_):
            if is_canonical or not id_:
                return id_
            return f"{variant}-{id_}"

        def render_items(items, top_level=False):
            html = ""
            if not top_level:
                html += "<ul class='md-nav__list' data-md-component='toc'>"

            for item in items:
                if getattr(item, "level", 2) == 1:
                    # skip h1, but still render children
                    if getattr(item, "children", None):
                        html += render_items(item.children)
                    continue

                rewritten_id = rewrite_id(item.id)
                html += "<li class='md-nav__item'>"
                html += (
                    f"<a href='#{rewritten_id}' class='md-nav__link'>"
                    f"<span class='md-ellipsis'>{item.title}</span>"
                    "</a>"
                )
                if getattr(item, "children", None):
                    html += render_items(item.children)
                html += "</li>"

            if not top_level:
                html += "</ul>"
            return html

        return (
            "<nav class='md-nav md-nav--secondary' aria-label='On this page'>"
            "<label class='md-nav__title' for='__toc'>"
            "<span class='md-nav__icon md-icon'></span> On this page"
            "</label>"
            f"{render_items(items, top_level=True)}"
            "</nav>"
        )
