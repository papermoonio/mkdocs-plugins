from mkdocs.plugins import BasePlugin

from plugins.ai_file_utils.ai_file_utils import AIFileUtils


class AiFileActionsPlugin(BasePlugin):
    """MkDocs plugin registered as ``ai_file_actions``.

    Delegates to :class:`AIFileUtils` for action resolution and
    HTML generation.  Kept as a thin wrapper so MkDocs can
    discover the plugin via entry points and so future per-page
    hooks have a natural home.
    """

    def __init__(self):
        super().__init__()
        self._file_utils = AIFileUtils()

    def generate_dropdown_html(
        self,
        url: str,
        filename: str,
        exclude: list | None = None,
        site_url: str = "",
    ) -> str:
        """Delegate to :meth:`AIFileUtils.generate_dropdown_html`."""
        return self._file_utils.generate_dropdown_html(
            url=url, filename=filename, exclude=exclude, site_url=site_url
        )
