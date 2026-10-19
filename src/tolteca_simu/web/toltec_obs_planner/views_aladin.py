"""Sky and coverage views drawn by Aladin Lite, in the page itself.

The sky view has the overlays as `dash_aladin_lite` layers; for the coverage
view, `assets/aladin_views.js` decompresses the result's coverage FITS file in
the browser and shows it as the base image, without a survey.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from dash import ClientsideFunction, Input, Output, State
from dash_aladin_lite import AladinLite, Circle, GraphicLayer, Polygon, Polyline

from .views import ViewsPanel

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
        name="Coverage outline",
        color="#66cccc",
        line_width=2,
        shapes=[Polygon(vertices=outline)] if outline else [],
    )


class AladinViewsPanel(ViewsPanel):
    """Sky and coverage views drawn by Aladin Lite.

    Parameters
    ----------
    downloads : dash_component_template.LazyComponent
        Store holding the files of the current result.
    sky_parent, coverage_parent : dash_component_template.LazyComponent
        Containers of the sky and coverage views.
    """

    def __init__(
        self,
        downloads: LazyComponent,
        sky_parent: LazyComponent,
        coverage_parent: LazyComponent,
    ) -> None:
        super().__init__(downloads, sky_parent, coverage_parent)
        self._sky = sky_parent.child[AladinLite](
            survey=_SURVEY,
            options=_OPTIONS | {"showSimbadPointerControl": True},
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
            ``sky`` and ``coverage``, each with the view ``target`` and ``fov``
            and its ``layers``: the trajectory, outline and detectors (hidden at
            first) for the sky view, the outline for the coverage view; and the
            ``coverage_title`` naming the coverage image.
        """
        ra, dec = description["center"]
        detectors = description["detectors"]
        outline = _outline_layer(description["outline"]).to_plotly_json()
        view = {"target": f"{ra} {dec}", "fov": description["size_deg"]}
        sky_layers = [
            GraphicLayer(
                id="trajectory",
                name="Trajectory",
                color="red",
                line_width=1,
                shapes=[Polyline(vertices=description["trajectory"])],
            ),
            # Many detectors clutter the view; they are a layer to switch on.
            GraphicLayer(
                id="detectors",
                name="Detectors",
                color="#4dabf7",
                line_width=1,
                shapes=[
                    Circle(center=p, radius=detectors["radius_deg"])
                    for p in detectors["positions"]
                ],
                visible=False,
            ),
        ]
        return {
            "sky": view
            | {"layers": [layer.to_plotly_json() for layer in sky_layers] + [outline]},
            "coverage": view | {"layers": [outline]},
            "coverage_title": description["coverage_title"],
        }

    def setup_callbacks(self, app: Dash) -> None:
        """Set both views in the browser for each planning result.

        Parameters
        ----------
        app : dash.Dash
            Application receiving the callbacks.
        """
        app.clientside_callback(
            ClientsideFunction(
                namespace="toltec_obs_planner", function_name="render_aladin_views"
            ),
            Output(self._sky(), "target"),
            Output(self._sky(), "fov"),
            Output(self._sky(), "layers"),
            Output(self._coverage(), "target"),
            Output(self._coverage(), "fov"),
            Output(self._coverage(), "layers"),
            Output(self._status(), "children"),
            Input(self.views(), "data"),
            State(self._downloads(), "data"),
        )
