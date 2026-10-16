"""Sphinx configuration, built on the Astropy defaults.

Everything in ``sphinx_astropy.conf.v2`` applies unless it is overridden below,
and each override says why.
"""

from __future__ import annotations

import importlib.metadata
import warnings

from sphinx_astropy.conf.v2 import *  # noqa: F403
from sphinx_astropy.conf.v2 import extensions, intersphinx_mapping

project = "tolteca_simu"
copyright = "2026, Zhiyuan Ma"
author = "Zhiyuan Ma"
version = release = importlib.metadata.version("tolteca_simu")

# The Astropy defaults already load autodoc, numpydoc, automodapi, intersphinx,
# mathjax, viewcode and copybutton.
extensions += [
    "myst_parser",
    "sphinx.ext.doctest",
    "sphinxcontrib.autodoc_pydantic",
    "sphinxcontrib.typer",
]

# autodoc-pydantic 2.2 is written against autodoc's class-based documenters.
# With the new implementation Sphinx 9 uses by default, the methods and
# properties of models are left out. Remove this when the extension supports it.
autodoc_use_legacy_class_based = True

source_suffix = [".rst", ".md"]
exclude_patterns = [
    "_build",
    "**.ipynb_checkpoints",
    "Thumbs.db",
    ".DS_Store",
    ".env",
    ".venv",
]

# Our chosen look. It builds on the pydata theme the Astropy defaults use, so
# their theme options still apply.
html_theme = "sphinx_book_theme"
# The icon browsers show for the site. The template ships a placeholder;
# replace the file with the project's own.
html_favicon = "_static/favicon.ico"

myst_enable_extensions = [
    "colon_fence",
]
# MyST gives a heading a link target only down to this level. Without it a
# Markdown link to a heading, such as ``guide.md#some-heading``, fails the build.
myst_heading_anchors = 3

# Resolve references to Pydantic's own API.
intersphinx_mapping["pydantic"] = ("https://docs.pydantic.dev/latest/", None)

nitpick_ignore = [
    ("py:class", "_io.StringIO"),
    ("py:class", "_io.BytesIO"),
    # Pydantic renders this name in every model, and it has no inventory entry.
    ("py:class", "ConfigDict"),
]
# Field constraints such as ``gt=0`` render as annotated_types classes, which
# have no Sphinx inventory to link to.
nitpick_ignore_regex = [
    ("py:class", r"annotated_types\..*"),
    # autodoc-pydantic links a validator for the whole model to
    # "<Model>.all fields", which is not an object.
    ("py:obj", r".*\.all fields"),
]

# The Astropy default, "obj", turns every single-backtick word into an object
# reference. Docstrings in numpydoc style put parameter names in single
# backticks, so with nitpicky checking each of them would fail the build.
default_role = None

# numpydoc reports malformed docstring sections as Python warnings, which
# sphinx-build -W does not see. Turn them into errors so they fail the build
# instead of silently dropping content.
warnings.filterwarnings("error", category=UserWarning, module=r"numpydoc\.docscrape$")

# pytest runs the `>>>` examples (see pyproject.toml). The Sphinx doctest builder
# only runs explicit testcode blocks, which is how Markdown guides carry runnable
# examples, so every example is run by exactly one tool.
doctest_test_doctest_blocks = ""
