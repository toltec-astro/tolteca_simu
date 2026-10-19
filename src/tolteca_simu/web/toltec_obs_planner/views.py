"""Sky and coverage views of a planning result.

The sky view shows the trajectory, the coverage outline and the detectors over
a HiPS survey; the coverage view shows the coverage FITS file of the result,
the same file as its download. A viewer backend draws both: Aladin Lite
(`.views_aladin`) or a Firefly server (`.views_firefly`). This module gives
them the backend-independent view description and the panel layout.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import astropy.units as u
import dash_mantine_components as dmc
import numpy as np
from astropy.coordinates import SkyCoord
from contourpy import contour_generator
from dash import dcc
from dash_component_template import Template

from tolteca_simu.toltec import TOLTEC_ARRAYS

if TYPE_CHECKING:
    from dash_component_template import LazyComponent

    from tolteca_simu.planning import Trajectory
    from tolteca_simu.toltec.planning import ToltecPlanningResult

__all__ = ["ViewsPanel", "make_view_description"]

_TRAJECTORY_POINTS_MAX = 2000
_OUTLINE_POINTS_MAX = 500
# The outline follows the 10 % coverage level that defines the map area.
_OUTLINE_FRACTION = 0.1
# Show the map within this fraction of the view, as v1 did.
_FOV_FILL = 0.618


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
        framing the trajectory and the array; ``sky_title`` and
        ``coverage_title``; the ``trajectory`` (at most 2000 RA, Dec vertices)
        and the coverage ``outline`` (vertices of the 10 % coverage contour,
        empty if there is none); and the ``detectors`` (``positions`` and the
        beam ``radius_deg``).
    """
    # Plain ICRS coordinates; the transformed ones keep their AltAz attributes.
    icrs = SkyCoord(trajectory.coords_icrs.ra, trajectory.coords_icrs.dec)
    detectors = SkyCoord(
        result.footprint.coords_icrs.ra, result.footprint.coords_icrs.dec
    )
    target = SkyCoord(target.icrs.ra, target.icrs.dec)
    # The views span the trajectory with the array around it.
    dx, dy = target.spherical_offsets_to(icrs)
    det_dx, det_dy = target.spherical_offsets_to(detectors)
    extent = max(
        np.ptp(dx.to_value(u.deg)) + np.ptp(det_dx.to_value(u.deg)),
        np.ptp(dy.to_value(u.deg)) + np.ptp(det_dy.to_value(u.deg)),
    )
    array = TOLTEC_ARRAYS[result.array_name]
    unit_label = "mJy/beam" if unit == "depth" else "s/pixel"
    return {
        "center": [float(target.ra.degree), float(target.dec.degree)],
        "size_deg": float(extent / _FOV_FILL),
        "sky_title": f"Trajectory and detectors: {array.name_long}",
        "coverage_title": f"Coverage ({unit_label}): {array.name_long}",
        "trajectory": _decimate(
            np.column_stack([icrs.ra.degree, icrs.dec.degree]),
            _TRAJECTORY_POINTS_MAX,
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
    ``coverage_parent``; the panel itself holds the status line and the data
    of the views.

    Parameters
    ----------
    downloads : dash_component_template.LazyComponent
        Store holding the files of the current result; the coverage view shows
        its coverage FITS file.
    sky_parent : dash_component_template.LazyComponent
        Container of the sky view.
    coverage_parent : dash_component_template.LazyComponent
        Container of the coverage view.
    """

    def __init__(
        self,
        downloads: LazyComponent,
        sky_parent: LazyComponent,
        coverage_parent: LazyComponent,
    ) -> None:
        super().__init__()
        self._downloads = downloads
        self._sky_parent = sky_parent
        self._coverage_parent = coverage_parent
        self._status = self.child[dmc.Text](
            "Press Execute to plan the observation.", size="xs", c="dimmed"
        )
        self.views = self.child[dcc.Store](data=None)

    @staticmethod
    def make_views(description: dict[str, Any]) -> dict[str, Any] | None:
        """Return the data of the views store for a view description.

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
