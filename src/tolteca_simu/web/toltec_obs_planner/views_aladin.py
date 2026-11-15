"""Sky and coverage views drawn by Aladin Lite, in the page itself.

The sky view follows the target and has the overlays as `dash_aladin_lite`
layers; for the coverage view, `assets/aladin_views.js` decompresses the
result's coverage FITS file in the browser and shows it as the base image,
without a survey.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from dash import ClientsideFunction, Input, Output
from dash_aladin_lite import AladinLite, Circle, GraphicLayer, Polygon, Polyline

from .views import SKY_FOV_DEFAULT, SKY_OVERLAYS, SKY_TARGET_DEFAULT, ViewsPanel

if TYPE_CHECKING:
    from dash import Dash
    from dash_component_template import LazyComponent

__all__ = ["AladinViewsPanel"]

# DSS colored (CDS/P/DSS2/color) from its ESA mirror, by URL. A survey ID
# needs CDS's MocServer to find the survey; when it does not answer, Aladin Lite
# requests the ID relative to the page, again and again (2026-11-02, 11-13).
_SURVEY = "https://skies.esac.esa.int/DSSColor"
_OPTIONS = {
    "cooFrame": "icrs",
    "showLayersControl": True,
    "showCooGridControl": True,
    "showFullscreenControl": True,
}


def _layer(layer_id: str, array_name_long: str, shapes: list) -> GraphicLayer:
    overlay = SKY_OVERLAYS[layer_id]
    return GraphicLayer(
        id=layer_id,
        name=overlay.name.format(array=array_name_long),
        color=overlay.color,
        line_width=overlay.line_width,
        shapes=shapes,
        visible=overlay.visible,
    )


class AladinViewsPanel(ViewsPanel):
    """Sky and coverage views drawn by Aladin Lite.

    Parameters
    ----------
    sky_target : dash_component_template.LazyComponent
        Store holding the RA and Dec of the target, in degrees, or None.
    result : dash_component_template.LazyComponent
        Store holding the current result.
    sky_parent, coverage_parent : dash_component_template.LazyComponent
        Containers of the sky and coverage views.
    """

    def __init__(
        self,
        sky_target: LazyComponent,
        result: LazyComponent,
        sky_parent: LazyComponent,
        coverage_parent: LazyComponent,
    ) -> None:
        super().__init__(sky_target, result, sky_parent, coverage_parent)
        self._sky = sky_parent.child[AladinLite](
            survey=_SURVEY,
            target=SKY_TARGET_DEFAULT,
            fov=SKY_FOV_DEFAULT,
            options=_OPTIONS | {"showSimbadPointerControl": True, "showReticle": False},
            style={"width": "100%", "height": "480px"},
        )
        # Aladin Lite always starts with a survey; the coverage FITS replaces
        # it as the base image, and a note covers the view until then.
        self._coverage = coverage_parent.child[AladinLite](
            survey=_SURVEY, options=_OPTIONS, style={"width": "100%", "height": "420px"}
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
            outline, named and styled by `SKY_OVERLAYS`; ``coverage``, with the
            ``target``, ``fov`` and outline ``layers`` of the coverage view;
            and the ``coverage_title`` naming the coverage image.
        """
        ra, dec = description["center"]
        detectors = description["detectors"]
        name_long = description["array_name_long"]
        outline = _layer(
            "outline",
            name_long,
            [Polygon(vertices=description["outline"])]
            if description["outline"]
            else [],
        ).to_plotly_json()
        fov = description["size_deg"]
        sky_layers = [
            _layer(
                "trajectory",
                name_long,
                [Polyline(vertices=description["trajectory"])],
            ),
            _layer(
                "detectors",
                name_long,
                [
                    Circle(center=p, radius=detectors["radius_deg"])
                    for p in detectors["positions"]
                ],
            ),
            _layer("fov", name_long, [Polygon(vertices=description["fov_outline"])]),
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
        super().setup_callbacks(app)
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
            Input(self._result(), "data"),
        )
