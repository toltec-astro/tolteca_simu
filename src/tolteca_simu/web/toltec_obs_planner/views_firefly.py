"""Sky and coverage views drawn by a Firefly server.

The page loads Firefly's API from the server; `assets/firefly_views.js` draws
each view in its own Firefly viewer: the HiPS view, which follows the target
and takes the overlays of each result as DS9 region layers, and the uploaded
coverage FITS file.
"""

from __future__ import annotations

from itertools import pairwise
from typing import TYPE_CHECKING, Any

from dash import ClientsideFunction, Input, Output, State, dcc, html

from .views import SKY_FOV_DEFAULT, SKY_OVERLAYS, ViewsPanel

if TYPE_CHECKING:
    from dash import Dash
    from dash_component_template import LazyComponent

__all__ = ["FireflyViewsPanel"]

_HIPS = "CDS/P/DSS2/color"


def _region_layer(
    layer_id: str, array_name_long: str, regions: list[str]
) -> dict[str, Any]:
    overlay = SKY_OVERLAYS[layer_id]
    return {
        "id": layer_id,
        "title": overlay.name.format(array=array_name_long),
        "regions": regions,
        "visible": overlay.visible,
    }


def _style(layer_id: str) -> str:
    overlay = SKY_OVERLAYS[layer_id]
    return f"color={overlay.color} width={overlay.line_width}"


class FireflyViewsPanel(ViewsPanel):
    """Sky and coverage views drawn by Firefly.

    Parameters
    ----------
    firefly_url : str
        Base URL of the Firefly server, as browsers reach it.
    sky_target : dash_component_template.LazyComponent
        Store holding the RA and Dec of the target, in degrees, or None.
    result : dash_component_template.LazyComponent
        Store holding the current result.
    sky_parent, coverage_parent : dash_component_template.LazyComponent
        Containers of the sky and coverage views.
    """

    def __init__(
        self,
        firefly_url: str,
        sky_target: LazyComponent,
        result: LazyComponent,
        sky_parent: LazyComponent,
        coverage_parent: LazyComponent,
    ) -> None:
        super().__init__(sky_target, result, sky_parent, coverage_parent)
        # One Firefly viewer per view.
        self._sky = sky_parent.child[html.Div](style={"height": "480px"})
        self._coverage = coverage_parent.child[html.Div](style={"height": "420px"})
        self._settings = self.child[dcc.Store](
            data={"url": firefly_url, "hips": _HIPS, "fov_default": SKY_FOV_DEFAULT}
        )
        # The sky view's center, as Firefly drew it.
        self._sky_center = self.child[dcc.Store](data=None)

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
            ``size_deg`` (field of view of the views), ``coverage_title``, and
            the region layers (``id``, ``title``, DS9 ``regions``,
            ``visible``) of the ``sky_layers`` and ``coverage_layers``: the
            mapping trajectory (line segments), the detectors (circles of the
            beam radius, hidden at first), the array's field of view and the
            coverage outline (polygons), named and styled by `SKY_OVERLAYS`.
        """
        name_long = description["array_name_long"]
        detectors = description["detectors"]
        radius = detectors["radius_deg"] * 3600
        detector_color = SKY_OVERLAYS["detectors"].color

        def polygon(layer_id: str, vertices: list[list[float]]) -> list[str]:
            if not vertices:
                return []
            points = ",".join(f"{v[0]:.6f},{v[1]:.6f}" for v in vertices)
            return [f"icrs;polygon({points}) # {_style(layer_id)}"]

        outline = _region_layer(
            "outline", name_long, polygon("outline", description["outline"])
        )
        return {
            "size_deg": description["size_deg"],
            "coverage_title": description["coverage_title"],
            "sky_layers": [
                _region_layer(
                    "trajectory",
                    name_long,
                    [
                        f"icrs;line({a[0]:.6f},{a[1]:.6f},{b[0]:.6f},{b[1]:.6f})"
                        f" # {_style('trajectory')}"
                        for a, b in pairwise(description["trajectory"])
                    ],
                ),
                _region_layer(
                    "detectors",
                    name_long,
                    [
                        f'icrs;circle({p[0]:.6f},{p[1]:.6f},{radius:.2f}")'
                        f" # color={detector_color}"
                        for p in detectors["positions"]
                    ],
                ),
                _region_layer(
                    "fov", name_long, polygon("fov", description["fov_outline"])
                ),
                outline,
            ],
            "coverage_layers": [outline],
        }

    def setup_callbacks(self, app: Dash) -> None:
        """Center the sky view on the target; draw both views for each result.

        Parameters
        ----------
        app : dash.Dash
            Application receiving the callbacks.
        """
        super().setup_callbacks(app)
        app.clientside_callback(
            ClientsideFunction(
                namespace="toltec_obs_planner", function_name="center_firefly_sky"
            ),
            Output(self._sky_center(), "data"),
            Input(self._sky_target(), "data"),
            State(self._settings(), "data"),
            State(self._status(), "id"),
            State(self._sky(), "id"),
        )
        app.clientside_callback(
            ClientsideFunction(
                namespace="toltec_obs_planner", function_name="render_firefly_views"
            ),
            Output(self._status(), "children"),
            Input(self._result(), "data"),
            State(self._settings(), "data"),
            State(self._sky_target(), "data"),
            State(self._status(), "id"),
            State(self._sky(), "id"),
            State(self._coverage(), "id"),
        )
