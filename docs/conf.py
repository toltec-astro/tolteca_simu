"""Sphinx configuration, built on the Astropy defaults.

Everything in ``sphinx_astropy.conf.v2`` applies unless it is overridden below,
and each override says why.
"""

from __future__ import annotations

import importlib.metadata
import os
import warnings
from typing import TYPE_CHECKING

from sphinx.addnodes import pending_xref
from sphinx_astropy.conf.v2 import *  # noqa: F403
from sphinx_astropy.conf.v2 import extensions, intersphinx_mapping

if TYPE_CHECKING:
    from docutils.nodes import document
    from sphinx.application import Sphinx

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
intersphinx_mapping["astroplan"] = ("https://astroplan.readthedocs.io/en/stable/", None)
# The published Tollan and TolTECA inventories predate APIs used here. Set these
# variables to the objects.inv of local builds to link the unpublished APIs.
intersphinx_mapping["tollan"] = (
    "https://toltec-astro.github.io/tollan/",
    os.environ.get("TOLLAN_DOCS_INVENTORY"),
)
intersphinx_mapping["tolteca"] = (
    "https://toltec-astro.github.io/tolteca/",
    os.environ.get("TOLTECA_DOCS_INVENTORY"),
)

# Annotations that name imports made only for type checking stay unresolved
# strings in signatures, as do the private paths of some public names. Qualify
# them before lookup; "obj" also matches type aliases and data.
_REFERENCE_ALIASES = {
    "Observer": "astroplan.Observer",
    "QTable": "astropy.table.QTable",
    "SkyCoord": "astropy.coordinates.SkyCoord",
    "datetime": "datetime.datetime",
    "fits.HDUList": "astropy.io.fits.HDUList",
    "np.ndarray": "numpy.ndarray",
    "numpy._typing._array_like.ArrayLike": "numpy.typing.ArrayLike",
    "u.Quantity": "astropy.units.Quantity",
    "LmtTelAccessor": "tolteca_datamodels.lmt.tel.LmtTelAccessor",
    "RuntimeContext": "tollan.config.RuntimeContext",
    "LmtAtmModelName": "tolteca_simu.lmt.LmtAtmModelName",
    "MappingPattern": "tolteca_simu.mapping.MappingPattern",
    "ToltecArrayName": "tolteca_simu.toltec.info.ToltecArrayName",
}


def _qualify_references(app: Sphinx, doctree: document) -> None:  # noqa: ARG001
    for node in doctree.findall(pending_xref):
        if node.get("refdomain") == "py" and (
            target := _REFERENCE_ALIASES.get(node.get("reftarget"))
        ):
            node["reftarget"] = target
            node["reftype"] = "obj"


def setup(app: Sphinx) -> None:
    """Qualify the aliased reference targets of each document Sphinx reads.

    Parameters
    ----------
    app : sphinx.application.Sphinx
        The application building the docs.
    """
    app.connect("doctree-read", _qualify_references)


nitpick_ignore = [
    ("py:class", "_io.StringIO"),
    ("py:class", "_io.BytesIO"),
    # Pydantic renders this name in every model, and it has no inventory entry.
    ("py:class", "ConfigDict"),
    # Dash publishes no Sphinx inventory.
    ("py:class", "Dash"),
    # Sphinx's legacy renderer links a generic base's type parameter as a class.
    ("py:class", "RuntimeContextT"),
    # Tollan's inventory has no entries for its field types, which are type
    # aliases; it lists UnitField under a doubled module path.
    ("py:class", "tollan.config.types.path.AbsDirectoryPath"),
    ("py:class", "tollan.config.types.path.AbsFilePath"),
    ("py:class", "tollan.config.types.quantity.AngleQuantityField"),
    ("py:class", "tollan.config.types.quantity.LengthQuantityField"),
    ("py:class", "tollan.config.types.quantity.TimeQuantityField"),
    ("py:class", "tollan.config.types.skycoord.SkyCoordField"),
    ("py:class", "tollan.config.types.time.TimeField"),
    ("py:class", "tollan.config.types.unit.UnitField"),
    # Module-private field types; each field's description states the quantity.
    ("py:class", "tolteca_simu.mapping.AngularSpeedQuantityField"),
    ("py:class", "tolteca_simu.planning.description.FluxDensityQuantityField"),
]
# Fields inherited from a base model name the same field types unqualified.
nitpick_ignore += [
    ("py:class", name)
    for name in (
        "AngleQuantityField",
        "AngularSpeedQuantityField",
        "TimeQuantityField",
    )
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
