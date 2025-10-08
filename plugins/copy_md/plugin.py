import os
import shutil
from pathlib import Path

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
        target_rel = self.config["target_dir"]
        site_dir = config["site_dir"]
        
        # Validate and resolve the target path to prevent path traversal attacks
        try:
            # Resolve the target path relative to site_dir
            target = os.path.join(site_dir, target_rel)
            target_resolved = os.path.realpath(target)
            site_dir_resolved = os.path.realpath(site_dir)
            
            # Ensure the target is within the site directory bounds
            if not target_resolved.startswith(site_dir_resolved + os.sep) and target_resolved != site_dir_resolved:
                log.error(f"Security violation: target_dir '{target_rel}' resolves to path outside site directory")
                log.error(f"Resolved target: {target_resolved}")
                log.error(f"Site directory: {site_dir_resolved}")
                return
                
        except (OSError, ValueError) as e:
            log.error(f"Invalid target_dir '{target_rel}': {e}")
            return

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
