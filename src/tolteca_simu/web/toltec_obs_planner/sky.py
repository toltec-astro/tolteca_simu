"""Sky view: coverage image, trajectory, detectors, and outline.

The layers are drawn by Aladin Lite over a HiPS survey. The coverage image
travels as a FITS data URL, cropped to the covered pixels and stored as
float32.
"""

from __future__ import annotations

import base64
import io
from typing import TYPE_CHECKING, NamedTuple

import astropy.units as u
import dash_mantine_components as dmc
import numpy as np
from astropy.coordinates import SkyCoord
from astropy.io import fits
from contourpy import contour_generator
from dash_aladin_lite import (
    AladinLite,
    Circle,
    GraphicLayer,
    ImageLayer,
    Layer,
    Polygon,
    Polyline,
)
from dash_component_template import Template

from tolteca_simu.toltec import TOLTEC_ARRAYS

if TYPE_CHECKING:
    from tolteca_simu.planning import Trajectory
    from tolteca_simu.toltec.planning import ToltecPlanningResult

__all__ = ["SkyView", "SkyViewPanel", "make_sky_view"]

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


def _outline(result: ToltecPlanningResult) -> list[Polygon]:
    data = result.coverage.data_on_scan
    mask = (data > _OUTLINE_FRACTION * data.max()).astype(np.float64)
    lines = contour_generator(z=mask).lines(0.5)
    if not lines:
        return []
    longest = max(lines, key=len)
    xy = _decimate(np.asarray(longest), _OUTLINE_POINTS_MAX)
    ra, dec = result.coverage.wcs.pixel_to_world_values(xy[:, 0], xy[:, 1])
    return [Polygon(vertices=np.column_stack([ra, dec]).tolist())]


class SkyView(NamedTuple):
    """Properties of the sky view for a planning result."""

    target: str
    """View center, ``"ra dec"`` in degrees."""

    fov: float
    """Field of view, in degrees."""

    layers: list[Layer]
    """Coverage image, trajectory, coverage outline and detectors."""


def make_sky_view(
    target: SkyCoord, trajectory: Trajectory, result: ToltecPlanningResult, unit: str
) -> SkyView:
    """Return the sky view of a planning result.

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
    SkyView
        The view center and field of view that frame the map, and the layers:
        the coverage image, the trajectory, the coverage outline, and the
        detectors of the computed array (hidden at first).
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
    unit_label = "mJy/beam" if unit == "depth" else "s/pixel"
    radius = array.a_fwhm / 2
    layers: list[Layer] = [
        ImageLayer(
            id="coverage",
            name=f"Coverage ({unit_label}): {array.name_long}",
            url=_coverage_fits_url(result, unit),
            colormap="viridis",
            opacity=0.7,
        ),
        GraphicLayer(
            id="trajectory",
            name="Trajectory",
            color="red",
            line_width=1,
            shapes=[Polyline(vertices=trajectory_xy.tolist())],
        ),
        GraphicLayer(
            id="outline",
            name="Coverage outline",
            color="#66cccc",
            line_width=2,
            shapes=_outline(result),
        ),
        # Many detectors clutter the view; they are a layer to switch on.
        GraphicLayer(
            id="detectors",
            name=f"Detectors: {array.name_long}",
            color="#4dabf7",
            line_width=1,
            shapes=[
                Circle(center=center, radius=radius)
                for center in zip(
                    detectors.ra.degree, detectors.dec.degree, strict=True
                )
            ],
            visible=False,
        ),
    ]
    return SkyView(
        target=f"{target.ra.degree} {target.dec.degree}",
        fov=float(extent / _FOV_FILL),
        layers=layers,
    )


class SkyViewPanel(Template):
    """Aladin Lite sky view; the planner page sets its view and layers."""

    def __init__(self) -> None:
        super().__init__()
        card = self.child[dmc.Card](withBorder=True, padding="md")
        stack = card.child[dmc.Stack](gap="sm")
        stack.child[dmc.Title]("Sky view", order=5)
        stack.child[dmc.Text](
            "Coverage, trajectory, coverage outline, and detectors; use the "
            "layer control to switch them.",
            size="xs",
            c="dimmed",
        )
        self.viewer = stack.child[AladinLite](
            survey="P/DSS2/color",
            options={
                "cooFrame": "icrs",
                "showLayersControl": True,
                "showCooGridControl": True,
                "showSimbadPointerControl": True,
                "showFullscreenControl": True,
            },
            style={"width": "100%", "height": "480px"},
        )
