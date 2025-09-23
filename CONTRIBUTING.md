# Contributing to MkDocs Plugins Collection

Thank you for your interest in contributing! This repository houses multiple MkDocs plugins designed to extend [Material for MkDocs](https://squidfunk.github.io/mkdocs-material/).  

We welcome:

- Bug fixes
- New features
- New plugins
- Documentation improvements
- Examples and demos

## 🛠 Getting Started

1. Fork the repository and clone your fork locally:

    ```bash
    git clone https://github.com/your-username/mkdocs-plugins.git
    cd mkdocs-plugins
    ```

2. (Optional) Create a virtual environment:

    ```bash
    python -m venv .venv
    source .venv/bin/activate   # macOS/Linux
    .venv\Scripts\activate      # Windows
    ```

3. Install development dependencies:

    ```bash
    pip install -r requirements-dev.txt
    ```

4. Install pre-commit hooks:

    ```bash
    pre-commit install
    ```

    > **Note**: Now, every commit will automatically run Black, isort, and Flake8 to enforce consistent formatting and style.


## 📦 Adding a New Plugin

1. Create a new folder under `plugins/`:

    ```markdown
    plugins/
    └── your_plugin_name/
        ├── __init__.py
        └── plugin.py
    ```

2. Use this plugin template in `plugin.py`:

    ```python
    # plugins/your_plugin_name/plugin.py

    from mkdocs.plugins import BasePlugin

    class YourPluginName(BasePlugin):
        def on_page_markdown(self, markdown, page, config, files):
            # Your plugin logic here
            return markdown
    ```

3. Add documentation for your plugin under `/docs/your_plugin_name.md`

4. Update the [README](README.md) to link to your plugin docs

## 📄 Documentation

- Follow the style used in existing plugin docs (headings, code blocks, CSS notes, etc.).
- Clearly specify any CSS classes or HTML changes introduced by your plugin.
- Include examples for standard usage, optional features, and anything else to understand in order to use the plugin.

## 📝 Making Changes

1. Create a new branch for your changes:

    ```bash
    git checkout -b my-feature
    ```

2. Edit or add your plugin.

3. Commit and push your branch. Pre-commit hooks will enforce formatting automatically.

    Run formatting and linting manually if needed:

    ```bash
    black plugins/
    isort plugins/
    flake8 plugins/
    ```

4. Submit a pull request with a clear title and description.

## ⚠️ Guidelines

- Keep plugins self-contained.
- Maintain consistent naming conventions (snake_case for folders and files).
- Prefer minimal external dependencies — only include what is necessary.
- Use clear class and CSS naming consistent with existing plugins.

Thank you for helping make this collection better! 🤍