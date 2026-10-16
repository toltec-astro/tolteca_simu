See the [Scientific Python Developer Guide][spc-dev-intro] for a detailed
description of best practices for developing scientific packages.

[spc-dev-intro]: https://learn.scientific-python.org/development/

# Quick development

The fastest way to start with development is to use
[just](https://just.systems). If you don't have just, you can use
`uvx --from rust-just just` to run it without installing, or
`uv tool install rust-just`. If you don't have uv, you can
[install it a variety of ways](https://docs.astral.sh/uv/getting-started/installation/),
including with pip, pipx, brew, and just downloading the binary (single file).

To use, run `just` to list the recipes. The main ones are:

```console
$ just install  # Create the development environment, activate the commit hook
$ just qa  # Lint and test
$ just test  # Python tests
$ just coverage  # Python tests with a coverage report
$ just doc  # Build and serve the docs
$ just build  # Make an SDist and wheel
```

The recipes run through uv in the project's own environment.

# Setting up a development environment manually

You can set up a development environment by running:

```bash
uv sync
```

# Pre-commit

`just install` points git at the tracked hook in `.githooks/`, which runs
[prek](https://github.com/j178/prek) on every commit to check that it passes the
required checks.

You can also run `uvx prek run` (changes only) or `uvx prek run --all-files` to
check without committing.

# Testing

Use pytest to run the unit checks:

```bash
uv run pytest
```

# Coverage

Use pytest-cov to generate coverage reports:

```bash
uv run pytest --cov=tolteca_simu
```

# Building docs

You can build and serve the docs using:

```bash
just doc
```

You can build the docs only with:

```bash
just doc-build
```
