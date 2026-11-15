"""Sky and coverage views of the planner.

As in v1, the sky view shows a HiPS survey centered on the current target from
page load on; each planning result sets its field of view and its layers: the
trajectory, the detectors, the array's field of view and the coverage outline.
The coverage view shows the coverage FITS file of the result, the same file as
its download. A viewer backend draws both: Aladin Lite (`.views_aladin`) or a
Firefly server (`.views_firefly`). This module gives them the
backend-independent view description and the panel layout.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, NamedTuple

import astropy.units as u
import dash_mantine_components as dmc
import numpy as np
from astropy.coordinates import SkyCoord
from contourpy import contour_generator
from dash import Input, Output
from dash_component_template import Template

from tolteca_simu.sky import SkyBoundingBox
from tolteca_simu.toltec import TOLTEC_ARRAYS

if TYPE_CHECKING:
    from dash import Dash
    from dash_component_template import LazyComponent

    from tolteca_simu.planning import Trajectory
    from tolteca_simu.toltec.planning import ToltecPlanningResult

__all__ = [
    "SKY_FOV_DEFAULT",
    "SKY_OVERLAYS",
    "SKY_TARGET_DEFAULT",
    "SkyOverlay",
    "ViewsPanel",
    "make_view_description",
]

_TRAJECTORY_POINTS_MAX = 2000
_OUTLINE_POINTS_MAX = 500
# The outline follows the 10 % coverage level that defines the map area.
_OUTLINE_FRACTION = 0.1
# Show the map within this fraction of the view, as v1 did.
_FOV_FILL = 0.618
SKY_TARGET_DEFAULT = "M1"
"""Target of the sky view on page load, as in v1."""
SKY_FOV_DEFAULT = (10 << u.arcmin).to_value(u.deg)
"""Field of view of the sky view on page load, in degrees, as in v1."""
_EMPTY_TEXT = "Press Execute to plan the observation."
_HIDDEN_OVERLAY_TEXT = "Off at first: switch it on in the view's layer control."


class SkyOverlay(NamedTuple):
    """Style of a sky view overlay."""

    name: str
    """Name, in which ``{array}`` stands for the array's long name."""
    color: str
    """Line color, as a CSS color."""
    line_width: int
    """Line width, in screen pixels."""
    visible: bool
    """Whether the overlay is shown at first."""


SKY_OVERLAYS = {
    "trajectory": SkyOverlay(
        name="Mapping Trajectory", color="red", line_width=1, visible=True
    ),
    # Many detectors clutter the view; they are an overlay to switch on.
    "detectors": SkyOverlay(
        name="Detectors: {array}", color="blue", line_width=1, visible=False
    ),
    "fov": SkyOverlay(name="FOV: {array}", color="#cc66cc", line_width=8, visible=True),
    "outline": SkyOverlay(
        name="Coverage Outline", color="#66cccc", line_width=4, visible=True
    ),
}
"""Overlays of the sky view by layer id, named and styled as in v1. Both
viewer backends and the legend use them."""


def _decimate(values: np.ndarray, n_max: int) -> np.ndarray:
    step = max(1, int(np.ceil(len(values) / n_max)))
    return values[::step]


def _outline(result: ToltecPlanningResult) -> list[list[float]]:
    data = result.coverage.data_on_scan
    mask = (data > _OUTLINE_FRACTION * data.max()).astype(np.float64)
    lines = contour_generator(z=mask).lines(0.5)
    if not lines:
        return []
    longest = max(lines, key=len)
    xy = _decimate(np.asarray(longest), _OUTLINE_POINTS_MAX)
    ra, dec = result.coverage.wcs.pixel_to_world_values(xy[:, 0], xy[:, 1])
    return np.column_stack([ra, dec]).tolist()


def make_view_description(
    target: SkyCoord, trajectory: Trajectory, result: ToltecPlanningResult, unit: str
) -> dict[str, Any]:
    """Return what the sky and coverage views show for a planning result.

    Parameters
    ----------
    target : astropy.coordinates.SkyCoord
        The target, at the center of the views.
    trajectory : tolteca_simu.planning.Trajectory
        The boresight trajectory.
    result : tolteca_simu.toltec.planning.ToltecPlanningResult
        The TolTEC results.
    unit : {"depth", "time"}
        Unit of the coverage view, mJy/beam or s/pixel.

    Returns
    -------
    dict
        ``center`` (RA, Dec in degrees, ICRS) and ``size_deg`` of the views,
        the trajectory's bounding box padded with the array's, as 61.8 % of
        the view; ``array_name_long``,
        ``sky_title`` and ``coverage_title``; the ``trajectory`` (at most 2000
        RA, Dec vertices); the ``fov_outline`` (vertices of the designed
        array's outline); the coverage ``outline`` (vertices of the 10 %
        coverage contour, empty if there is none); and the ``detectors``
        (``positions`` and the beam ``radius_deg``).
    """
    # Plain ICRS coordinates; the transformed ones keep their AltAz attributes.
    icrs = SkyCoord(trajectory.coords_icrs.ra, trajectory.coords_icrs.dec)
    detectors = SkyCoord(
        result.footprint.coords_icrs.ra, result.footprint.coords_icrs.dec
    )
    target = SkyCoord(target.icrs.ra, target.icrs.dec)
    # As v1: the views span the trajectory's bounding box padded with the
    # array's.
    array_box = SkyBoundingBox.from_lonlat(detectors.ra, detectors.dec)
    box = SkyBoundingBox.from_lonlat(icrs.ra, icrs.dec).pad_with(
        array_box.width, array_box.height
    )
    extent = max(box.width, box.height).to_value(u.deg)
    array = TOLTEC_ARRAYS[result.array_name]
    unit_label = "mJy/beam" if unit == "depth" else "s/pixel"
    return {
        "center": [float(target.ra.degree), float(target.dec.degree)],
        "size_deg": float(extent / _FOV_FILL),
        "array_name_long": array.name_long,
        "sky_title": f"Trajectory and detectors: {array.name_long}",
        "coverage_title": f"Coverage ({unit_label}): {array.name_long}",
        "trajectory": _decimate(
            np.column_stack([icrs.ra.degree, icrs.dec.degree]),
            _TRAJECTORY_POINTS_MAX,
        ).tolist(),
        "fov_outline": np.column_stack(
            [result.fov_outline.ra.degree, result.fov_outline.dec.degree]
        ).tolist(),
        "outline": _outline(result),
        "detectors": {
            "positions": np.column_stack(
                [detectors.ra.degree, detectors.dec.degree]
            ).tolist(),
            "radius_deg": float((array.a_fwhm / 2).to_value(u.deg)),
        },
    }


class ViewsPanel(Template):
    """Sky and coverage views, placed where the page puts them.

    A backend creates its sky view in ``sky_parent`` and its coverage view in
    ``coverage_parent``; the panel itself holds the legend of the sky view's
    overlays and a status line for the drawing and failed states. The sky
    view centers on the target in ``sky_target``. Until a result exists, the
    coverage view is covered by a note.

    Parameters
    ----------
    sky_target : dash_component_template.LazyComponent
        Store holding the RA and Dec of the target, in degrees, or None.
    result : dash_component_template.LazyComponent
        Store holding the current result: the views draw its ``views`` (from
        `make_views`), and the coverage view shows the coverage FITS file of
        its ``downloads``.
    sky_parent : dash_component_template.LazyComponent
        Container of the sky view.
    coverage_parent : dash_component_template.LazyComponent
        Container of the coverage view.
    """

    def __init__(
        self,
        sky_target: LazyComponent,
        result: LazyComponent,
        sky_parent: LazyComponent,
        coverage_parent: LazyComponent,
    ) -> None:
        super().__init__()
        self._sky_target = sky_target
        self._result = result
        self._sky_parent = sky_parent
        self._coverage_parent = coverage_parent
        # The legend after a result; the status while views are drawn or when
        # they fail. Neither takes room while empty.
        row = self.child[dmc.Box](mih=20)
        self.legend = row.child[dmc.Group](gap="lg")
        self._status = row.child[dmc.Text](size="xs", c="dimmed")
        # The coverage view is empty until a result exists; v1 showed an empty
        # frame. The note covers the backend's view, added after it.
        self._coverage_empty = coverage_parent.child[dmc.Overlay](
            dmc.Paper(
                dmc.Center(dmc.Text(_EMPTY_TEXT, size="sm", c="dimmed"), h="100%"),
                withBorder=True,
                w="100%",
                h="100%",
            ),
            color="var(--mantine-color-body)",
            backgroundOpacity=1,
            zIndex=2,
        )

    @staticmethod
    def make_legend(description: dict[str, Any]) -> list[Any]:
        """Return the legend of the sky view's overlays for a result.

        Parameters
        ----------
        description : dict
            A `make_view_description` result.

        Returns
        -------
        list
            One item per overlay of `SKY_OVERLAYS`: a line in its color and
            its name. The name of an overlay hidden at first is dimmed, with a
            tooltip saying how to show it.
        """
        items: list[Any] = []
        for overlay in SKY_OVERLAYS.values():
            name = overlay.name.format(array=description["array_name_long"])
            item = dmc.Group(
                [
                    dmc.Box(w=20, h=3, bg=overlay.color),
                    dmc.Text(name, size="xs")
                    if overlay.visible
                    else dmc.Text(name, size="xs", c="dimmed"),
                ],
                gap=6,
                wrap="nowrap",
            )
            if not overlay.visible:
                item = dmc.Tooltip(item, label=_HIDDEN_OVERLAY_TEXT, withArrow=True)
            items.append(item)
        return items

    def setup_callbacks(self, app: Dash) -> None:
        """Uncover the coverage view once a result exists.

        Parameters
        ----------
        app : dash.Dash
            Application receiving the callbacks.
        """
        app.clientside_callback(
            "function(result) { return result ? 'none' : null; }",
            Output(self._coverage_empty(), "display"),
            Input(self._result(), "data"),
        )

    @staticmethod
    def make_views(description: dict[str, Any]) -> dict[str, Any] | None:
        """Return the view data of a result for a view description.

        Parameters
        ----------
        description : dict
            A `make_view_description` result.

        Returns
        -------
        dict or None
            Backend-specific view data.
        """
        raise NotImplementedError
