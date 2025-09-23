# Test Suite for papermoon-mkdocs-plugins

This directory contains tests for the PaperMoon MkDocs Plugins collection.

## Running Tests

### Run All Tests
```bash
pytest
```

### Run Tests for a Specific Plugin

```bash
# Run only Minify plugin tests
pytest tests/minify/
```

### Run Tests with Verbose Output

```bash
pytest -v
```

## Dependencies

The test suite requires:
- pytest
- pytest-cov
- pytest-mock
- mkdocs
- mkdocs-material
- pymdown-extensions
- htmlmin
- jsmin
- csscompressor
- packaging

These are listed in `requirements.txt` and `requirements-dev.txt`.