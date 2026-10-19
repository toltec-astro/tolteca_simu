"""Sky and coverage views drawn by a Firefly server.

The page loads Firefly's API from the server; `assets/firefly_views.js` draws
each view in its own Firefly viewer: the HiPS view with the overlays as DS9
regions, and the uploaded coverage FITS file.
"""

from __future__ import annotations

from itertools import pairwise
from typing import TYPE_CHECKING, Any

from dash import ClientsideFunction, Input, Output, State, dcc, html

from .views import ViewsPanel

if TYPE_CHECKING:
    from dash import Dash
    from dash_component_template import LazyComponent

__all__ = ["FireflyViewsPanel"]

_HIPS = "CDS/P/DSS2/color"


class FireflyViewsPanel(ViewsPanel):
    """Sky and coverage views drawn by Firefly.

    Parameters
    ----------
    firefly_url : str
        Base URL of the Firefly server, as browsers reach it.
    downloads : dash_component_template.LazyComponent
        Store holding the files of the current result.
    sky_parent, coverage_parent : dash_component_template.LazyComponent
        Containers of the sky and coverage views.
    """

    def __init__(
        self,
        firefly_url: str,
        downloads: LazyComponent,
        sky_parent: LazyComponent,
        coverage_parent: LazyComponent,
    ) -> None:
        super().__init__(downloads, sky_parent, coverage_parent)
        # One Firefly viewer per view.
        self._sky = sky_parent.child[html.Div](style={"height": "480px"})
        self._coverage = coverage_parent.child[html.Div](style={"height": "420px"})
        self._firefly_url = self.child[dcc.Store](data=firefly_url)

    @staticmethod
    def make_views(description: dict[str, Any]) -> dict[str, Any]:
        """Return Firefly's view settings and DS9 regions.

        Parameters
        ----------
        description : dict
            A `make_view_description` result.

        Returns
        -------
        dict
            ``hips`` (survey), ``world_pt`` and ``size_deg`` (center and size
            of the views), ``sky_title`` and ``coverage_title``, and
            ``regions``: DS9 region strings for the ``trajectory`` (line
            segments), the coverage ``outline`` (a polygon) and the
            ``detectors`` (circles of the beam radius, hidden at first).
        """
        ra, dec = description["center"]
        outline = description["outline"]
        detectors = description["detectors"]
        radius = detectors["radius_deg"] * 3600
        return {
            "hips": _HIPS,
            "world_pt": f"{ra};{dec};EQ_J2000",
            "size_deg": description["size_deg"],
            "sky_title": description["sky_title"],
            "coverage_title": description["coverage_title"],
            "regions": {
                "trajectory": [
                    f"icrs;line({a[0]:.6f},{a[1]:.6f},{b[0]:.6f},{b[1]:.6f})"
                    " # color=red"
                    for a, b in pairwise(description["trajectory"])
                ],
                "outline": [
                    "icrs;polygon("
                    + ",".join(f"{v[0]:.6f},{v[1]:.6f}" for v in outline)
                    + ") # color=#66cccc width=2"
                ]
                if outline
                else [],
                "detectors": [
                    f'icrs;circle({p[0]:.6f},{p[1]:.6f},{radius:.2f}") # color=#4dabf7'
                    for p in detectors["positions"]
                ],
            },
        }

    def setup_callbacks(self, app: Dash) -> None:
        """Draw both views in the browser for each planning result.

        Parameters
        ----------
        app : dash.Dash
            Application receiving the callbacks.
        """
        app.clientside_callback(
            ClientsideFunction(
                namespace="toltec_obs_planner", function_name="render_firefly_views"
            ),
            Output(self._status(), "children"),
            Input(self.views(), "data"),
            State(self._downloads(), "data"),
            State(self._firefly_url(), "data"),
            State(self._status(), "id"),
            State(self._sky(), "id"),
            State(self._coverage(), "id"),
        )
