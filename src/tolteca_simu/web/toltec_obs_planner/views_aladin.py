"""Sky and coverage views drawn by Aladin Lite, in the page itself.

The sky view follows the target and has the overlays as `dash_aladin_lite`
layers; for the coverage view, `assets/aladin_views.js` decompresses the
result's coverage FITS file in the browser and shows it as the base image,
without a survey.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from dash import ClientsideFunction, Input, Output, State
from dash_aladin_lite import AladinLite, Circle, GraphicLayer, Polygon, Polyline

from .views import SKY_FOV_DEFAULT, SKY_TARGET_DEFAULT, ViewsPanel

if TYPE_CHECKING:
    from dash import Dash
    from dash_component_template import LazyComponent

__all__ = ["AladinViewsPanel"]

_SURVEY = "P/DSS2/color"
_OPTIONS = {
    "cooFrame": "icrs",
    "showLayersControl": True,
    "showCooGridControl": True,
    "showFullscreenControl": True,
}


def _outline_layer(outline: list[list[float]]) -> GraphicLayer:
    return GraphicLayer(
        id="outline",
        name="Coverage Outline",
        color="#66cccc",
        line_width=4,
        shapes=[Polygon(vertices=outline)] if outline else [],
    )


class AladinViewsPanel(ViewsPanel):
    """Sky and coverage views drawn by Aladin Lite.

    Parameters
    ----------
    sky_target : dash_component_template.LazyComponent
        Store holding the RA and Dec of the target, in degrees, or None.
    downloads : dash_component_template.LazyComponent
        Store holding the files of the current result.
    sky_parent, coverage_parent : dash_component_template.LazyComponent
        Containers of the sky and coverage views.
    """

    def __init__(
        self,
        sky_target: LazyComponent,
        downloads: LazyComponent,
        sky_parent: LazyComponent,
        coverage_parent: LazyComponent,
    ) -> None:
        super().__init__(sky_target, downloads, sky_parent, coverage_parent)
        self._sky = sky_parent.child[AladinLite](
            survey=_SURVEY,
            target=SKY_TARGET_DEFAULT,
            fov=SKY_FOV_DEFAULT,
            options=_OPTIONS | {"showSimbadPointerControl": True, "showReticle": False},
            style={"width": "100%", "height": "480px"},
        )
        self._coverage = coverage_parent.child[AladinLite](
            options=_OPTIONS, style={"width": "100%", "height": "420px"}
        )

    @staticmethod
    def make_views(description: dict[str, Any]) -> dict[str, Any]:
        """Return the properties of the two Aladin Lite views.

        Parameters
        ----------
        description : dict
            A `make_view_description` result.

        Returns
        -------
        dict
            ``sky``, with the ``fov`` and ``layers`` of the sky view, whose
            center stays on the target: the mapping trajectory, the detectors
            (hidden at first), the array's field of view and the coverage
            outline, named and styled as in v1; ``coverage``, with the
            ``target``, ``fov`` and outline ``layers`` of the coverage view;
            and the ``coverage_title`` naming the coverage image.
        """
        ra, dec = description["center"]
        detectors = description["detectors"]
        name_long = description["array_name_long"]
        outline = _outline_layer(description["outline"]).to_plotly_json()
        fov = description["size_deg"]
        sky_layers = [
            GraphicLayer(
                id="trajectory",
                name="Mapping Trajectory",
                color="red",
                line_width=1,
                shapes=[Polyline(vertices=description["trajectory"])],
            ),
            # Many detectors clutter the view; they are a layer to switch on.
            GraphicLayer(
                id="detectors",
                name=f"Detectors: {name_long}",
                color="blue",
                line_width=1,
                shapes=[
                    Circle(center=p, radius=detectors["radius_deg"])
                    for p in detectors["positions"]
                ],
                visible=False,
            ),
            GraphicLayer(
                id="fov",
                name=f"FOV: {name_long}",
                color="#cc66cc",
                line_width=8,
                shapes=[Polygon(vertices=description["fov_outline"])],
            ),
        ]
        return {
            "sky": {
                "fov": fov,
                "layers": [layer.to_plotly_json() for layer in sky_layers] + [outline],
            },
            "coverage": {"target": f"{ra} {dec}", "fov": fov, "layers": [outline]},
            "coverage_title": description["coverage_title"],
        }

    def setup_callbacks(self, app: Dash) -> None:
        """Center the sky view on the target; set both views for each result.

        Parameters
        ----------
        app : dash.Dash
            Application receiving the callbacks.
        """
        app.clientside_callback(
            """
            function(radec) {
                if (!radec) {
                    return window.dash_clientside.no_update;
                }
                return radec[0] + " " + radec[1];
            }
            """,
            Output(self._sky(), "target"),
            Input(self._sky_target(), "data"),
        )
        app.clientside_callback(
            ClientsideFunction(
                namespace="toltec_obs_planner", function_name="render_aladin_views"
            ),
            Output(self._sky(), "fov"),
            Output(self._sky(), "layers"),
            Output(self._coverage(), "target"),
            Output(self._coverage(), "fov"),
            Output(self._coverage(), "layers"),
            Output(self._status(), "children"),
            Input(self.views(), "data"),
            State(self._downloads(), "data"),
        )
