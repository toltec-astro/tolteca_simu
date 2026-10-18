"""Sky view layers: coverage image, trajectory, detectors, and outline.

The layers are plain JSON for the Aladin Lite view in the browser, which
draws them over a HiPS survey. The coverage image travels as a FITS data URL,
cropped to the covered pixels and stored as float32.
"""

from __future__ import annotations

import base64
import io
from typing import TYPE_CHECKING, Any

import astropy.units as u
import dash_mantine_components as dmc
import numpy as np
from astropy.coordinates import SkyCoord
from astropy.io import fits
from contourpy import contour_generator
from dash import ClientsideFunction, Input, Output, State, dcc, html
from dash_component_template import Template

from tolteca_simu.toltec import TOLTEC_ARRAYS

if TYPE_CHECKING:
    from dash import Dash

    from tolteca_simu.planning import Trajectory
    from tolteca_simu.toltec.planning import ToltecPlanningResult

__all__ = ["ALADIN_LITE_URL", "SkyViewPanel", "make_sky_layers"]

_TRAJECTORY_POINTS_MAX = 2000
_OUTLINE_POINTS_MAX = 500
# Values below this fraction of the maximum are FFT round-off.
_COVERED_FRACTION = 1e-6
# The outline follows the 10 % coverage level that defines the map area.
_OUTLINE_FRACTION = 0.1
# Show the map within this fraction of the view, as v1 did.
_FOV_FILL = 0.618


def _decimate(values: np.ndarray, n_max: int) -> np.ndarray:
    step = max(1, int(np.ceil(len(values) / n_max)))
    return values[::step]


def _coverage_fits_url(result: ToltecPlanningResult, unit: str) -> str:
    data = result.depth.depth if unit == "depth" else result.coverage.data_on_scan
    covered = data > _COVERED_FRACTION * data.max()
    rows = np.flatnonzero(covered.any(axis=1))
    cols = np.flatnonzero(covered.any(axis=0))
    y = slice(rows[0], rows[-1] + 1)
    x = slice(cols[0], cols[-1] + 1)
    image = np.where(covered, data, np.nan)[y, x].astype(np.float32)
    header = result.coverage.wcs.slice((y, x)).to_header()
    header["BUNIT"] = "mJy / beam" if unit == "depth" else "s / pix"
    buffer = io.BytesIO()
    fits.PrimaryHDU(data=image, header=header).writeto(buffer)
    encoded = base64.b64encode(buffer.getvalue()).decode()
    return f"data:application/fits;base64,{encoded}"


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


def make_sky_layers(
    target: SkyCoord, trajectory: Trajectory, result: ToltecPlanningResult, unit: str
) -> dict[str, Any]:
    """Return the sky view layers of a planning result.

    Parameters
    ----------
    target : astropy.coordinates.SkyCoord
        The target, at the view center.
    trajectory : tolteca_simu.planning.Trajectory
        The boresight trajectory.
    result : tolteca_simu.toltec.planning.ToltecPlanningResult
        The TolTEC results.
    unit : {"depth", "time"}
        Coverage image in mJy/beam or s/pixel.

    Returns
    -------
    dict
        ``target`` and ``fov`` (deg), the coverage ``image`` (FITS data URL,
        name, unit), the ``trajectory`` and ``outline`` as RA/Dec vertex lists,
        and the ``detectors`` (positions and beam radius) of the computed array.
    """
    # Plain ICRS coordinates; the transformed ones keep their AltAz attributes.
    icrs = SkyCoord(trajectory.coords_icrs.ra, trajectory.coords_icrs.dec)
    detectors = SkyCoord(
        result.footprint.coords_icrs.ra, result.footprint.coords_icrs.dec
    )
    target = SkyCoord(target.icrs.ra, target.icrs.dec)
    # The view spans the trajectory with the array around it.
    dx, dy = target.spherical_offsets_to(icrs)
    det_dx, det_dy = target.spherical_offsets_to(detectors)
    extent = max(
        np.ptp(dx.to_value(u.deg)) + np.ptp(det_dx.to_value(u.deg)),
        np.ptp(dy.to_value(u.deg)) + np.ptp(det_dy.to_value(u.deg)),
    )
    array = TOLTEC_ARRAYS[result.array_name]
    trajectory_xy = _decimate(
        np.column_stack([icrs.ra.degree, icrs.dec.degree]), _TRAJECTORY_POINTS_MAX
    )
    return {
        "target": [float(target.ra.degree), float(target.dec.degree)],
        "fov": float(extent / _FOV_FILL),
        "image": {
            "url": _coverage_fits_url(result, unit),
            "name": f"Coverage: {array.name_long}",
            "unit": "mJy/beam" if unit == "depth" else "s/pixel",
        },
        "trajectory": trajectory_xy.tolist(),
        "detectors": {
            "name": f"Detectors: {array.name_long}",
            "radius": float((array.a_fwhm / 2).to_value(u.deg)),
            "coords": np.column_stack(
                [detectors.ra.degree, detectors.dec.degree]
            ).tolist(),
        },
        "outline": _outline(result),
    }


ALADIN_LITE_URL = "https://aladin.cds.unistra.fr/AladinLite/api/v3/3.8.2/aladin.js"
"""Aladin Lite release loaded by the planner page."""


class SkyViewPanel(Template):
    """Aladin Lite sky view; its layers come from the planner page."""

    def __init__(self) -> None:
        super().__init__()
        card = self.child[dmc.Card](withBorder=True, padding="md")
        stack = card.child[dmc.Stack](gap="sm")
        stack.child[dmc.Title]("Sky view", order=5)
        self._status = stack.child[dmc.Text](size="xs", c="dimmed")
        self._viewer = stack.child[html.Div](style={"width": "100%", "height": "480px"})
        self.layers = stack.child[dcc.Store](data=None)

    def setup_callbacks(self, app: Dash) -> None:
        """Draw the layers in the browser whenever they change.

        Parameters
        ----------
        app : dash.Dash
            Application receiving the callbacks.
        """
        app.clientside_callback(
            ClientsideFunction(
                namespace="toltec_obs_planner", function_name="render_sky"
            ),
            Output(self._status(), "children"),
            Input(self.layers(), "data"),
            State(self._viewer(), "id"),
        )
