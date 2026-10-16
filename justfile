# Show the available recipes
default:
    @just --list

# Create or update the development environment and activate the commit hook
install:
    uv sync
    git config core.hooksPath .githooks

# Run every check: the pre-commit hooks on all files, the tests, the doc examples
qa:
    uvx prek run --all-files --show-diff-on-failure
    uv run pytest
    just doc-test

# Run the tests; extra arguments are passed to pytest
test *ARGS:
    uv run pytest {{ARGS}}

# Run the tests and report coverage, in the terminal and as HTML in htmlcov/
coverage:
    uv run pytest --cov --cov-report=term-missing --cov-report=html

# The generated API stubs are removed first: one left over from a renamed or
# deleted object would fail the build. Every page is read again (-E): Sphinx
# reports a broken reference only for a page it rebuilds, so a build that
# reuses its saved state can pass with broken references on unchanged pages.
#
# Build the docs; any warning, including a broken reference, fails the build
doc-build:
    rm -rf docs/api
    uv run --group docs sphinx-build -W --keep-going -n -T -E -b html -d docs/_build/doctrees docs docs/_build/html

# Cross-project links are not needed to run examples, so intersphinx is off
# and the run stays offline. Every page is read again (-E), as in doc-build:
# state saved before an API page existed makes the run fail on its stubs.
#
# Run the testcode examples in the docs
doc-test:
    rm -rf docs/api
    uv run --group docs sphinx-build -W --keep-going -T -E -b doctest -D disable_intersphinx=1 docs docs/_build/doctest

# Serve the docs locally, rebuilding on change
doc:
    uv run --group docs --with sphinx-autobuild sphinx-autobuild --open-browser -n -T -b html -d docs/_build/doctrees docs docs/_build/html

# Publish the built docs to GitHub Pages (the gh-pages branch of origin)
doc-deploy: doc-build
    uvx ghp-import --no-jekyll --push docs/_build/html

# Build the sdist and wheel
build:
    uv build

# Remove the built docs and the generated API stubs
clean-doc:
    rm -rf docs/_build docs/api

# Remove the built distributions
clean-build:
    rm -rf dist src/*.egg-info

# Remove the test, coverage and lint caches
clean-test:
    rm -rf .pytest_cache .ruff_cache .coverage htmlcov

# Remove everything the recipes generate
clean: clean-doc clean-build clean-test
