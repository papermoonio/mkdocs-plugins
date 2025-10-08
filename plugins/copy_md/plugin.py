import os
import shutil

from mkdocs.utils import log
from mkdocs.config.config_options import Type
from mkdocs.plugins import BasePlugin

class CopyMDPlugin(BasePlugin):
    config_scheme = (
        ("source_dir", Type(str, required=True)),
        ("target_dir", Type(str, required=True)),
    )

    def on_post_build(self, config):
        source = self.config["source_dir"]
        target = os.path.join(config["site_dir"], self.config["target_dir"])

        if not os.path.exists(source):
            log.warning(f"Source directory '{source}' not found; skipping copy-md operation.")
            return

        # Remove existing target if present to avoid stale files
        if os.path.exists(target):
            shutil.rmtree(target)
            log.debug(f"Removed existing target directory: {target}")

        try:
            shutil.copytree(source, target)
            log.info(f"Successfully copied raw Markdown from '{source}' to '{target}'")
        except Exception as e:
            log.error(f"Failed to copy Markdown files from '{source}' to '{target}': {e}")
