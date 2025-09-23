# Minify Plugin

This fork of the [mkdocs-minify-plugin](https://github.com/byrnereese/mkdocs-minify-plugin) allows you to minify HTML, JS, and CSS files before they are written to disk. It also adds support for scoped CSS injection, allowing styles to be loaded only on specific pages or templates, rather than globally.

It supports:

- HTML minification using [htmlmin2](https://github.com/wilhelmer/htmlmin)
- JavaScript minification using [jsmin](https://github.com/tikitu/jsmin/)
- CSS minification using [csscompressor](https://github.com/sprymix/csscompressor)

## 🔹 Usage

Enable the plugin in your `mkdocs.yml` with with any of the available options as needed:

```yaml
plugins:
  - search
  - minify:
      minify_html: true
      minify_js: true
      minify_css: true
      htmlmin_opts:
          remove_comments: true
      cache_safe: true
      js_files:
          - my/javascript/dir/file1.js
          - my/javascript/dir/file2.js
      css_files:
          - my/css/dir/file1.css
          - my/css/dir/file2.css
      scoped_css:
        docs/index.md:
          - assets/css/landing.css
      scoped_css_templates:
        home.html:
          - assets/css/homepage.css
```

## 🔹 Configuration

### Basic Options

- `minify_html`:
  - Defaults to `False`.
  - Sets whether HTML files should be minified.

- `minify_js`:
  - Defaults to `False`.
  - Sets whether JS files should be minified.
  - If set to `True`, you must specify the JS files using `js_files`.

- `minify_css`:
  - Defaults to `False`.
  - Sets whether CSS files should be minified.
  - If set to `True`, you must specify the CSS files using `css_files`.

### Advanced Options

- `htmlmin_opts`:
  - Defaults to `None`.
  - Sets runtime htmlmin API options using the [config parameters of htmlmin](https://htmlmin.readthedocs.io/en/latest/reference.html#main-functions)

- `cache_safe`:
  - Defaults to `False`.
  - Sets whether a hash should be added to the JS and CSS file names.
  - This ensures that the browser always loads the latest version of the files instead of loading them from the cache.
  - If set to `True`, you must specify the files using `js_files` or `css_files`.

### File Specification

- `js_files`:
  - Defaults to `None`.
  - List of JS files to be minified.
  - The plugin will generate minified versions of these files and save them as `.min.js` in the output directory.

- `css_files`:
  - Defaults to `None`.
  - List of CSS files to be minified.
  - The plugin will generate minified versions of these files and save them as `.min.css` in the output directory.

### Scoped Injection

- `scoped_css`:
  - Defaults to `None`.
  - A mapping of Markdown page paths or glob patterns to lists of CSS files.
  - These CSS files will be minified, hashed, and injected only into the matching pages instead of globally.

- `scoped_css_templates`:
  - Defaults to `None`.
  - A mapping of template names or glob patterns (e.g., `home.html`, `index-page.html`) to lists of CSS files.
  - These CSS files will be minified, hashed, and injected only into the matching templates instead of globally.

## 🔹 Notes

- Both `js_files` and `css_files` support the use of **globs** (e.g. `**/*.css`, `**/*.js`) for file specification.
- Scoped CSS injection provides fine-grained control over where additional CSS is applied in your site.

## Credits

This plugin is based on the excellent work by the original authors:

- **[Byrne Reese](https://github.com/byrnereese)** - Original author
- **[Lars Wilhelmer](https://github.com/wilhelmer)** - Co-author

**Fork Maintainer:**
- **[Lucas Malizia](https://github.com/0xlukem)** - Current maintainer of this fork

## Original Repository

The original plugin can be found at: https://github.com/byrnereese/mkdocs-minify-plugin