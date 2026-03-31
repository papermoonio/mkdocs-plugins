# Link Processor Plugin

The Link Processor plugin automatically post-processes the HTML of every built page to enforce consistent link behaviour across your site. It opens external links in a new tab and adds trailing slashes to internal paths so URLs match MkDocs' default clean-URL structure.

It handles two categories of links:

- **External links** — any `<a>` whose `href` starts with `http://` or `https://` receives `target="_blank"` and `rel="noopener noreferrer"`. If the element already has a `rel` attribute the new values are merged with the existing ones rather than replacing them.
- **Internal links** — any `<a>` whose `href` does not start with `http`, `#`, or `mailto:` gets a trailing slash appended to its path component, unless the path already ends with `/`, the final segment looks like a file (contains a `.`), or the path starts with a configured skip prefix.

Fragment and query strings are preserved correctly — e.g. `/learn/build#some-section` becomes `/learn/build/#some-section`.

## 🔹 Usage

Enable the plugin in your `mkdocs.yml`:

```yaml
plugins:
  - link_processor
```

With optional configuration:

```yaml
plugins:
  - link_processor:
      skip_internal_path_prefixes:
        - /api/
        - /static/
```

## 🔹 Configuration

- **`skip_internal_path_prefixes`**:
  - Defaults to `[]`.
  - A list of path prefixes. Internal links whose path starts with any of these prefixes are left untouched — no trailing slash is added.
  - Useful for paths that intentionally lack trailing slashes, such as API endpoints, static asset directories, or versioned URL schemes.
  - Prefix matching is exact and case-sensitive (e.g. `/api/` matches `/api/v1/endpoint` but not `/docs/api/page`).

## 🔹 Notes

- Links with fragment-only hrefs (e.g. `#section`) and `mailto:` links are never modified.
- Paths whose final segment contains a `.` (e.g. `/images/photo.png`, `/downloads/guide.pdf`) are treated as file references and left without a trailing slash.
- The plugin runs on the `on_page_content` event, so it processes the rendered HTML of each page rather than the Markdown source.
