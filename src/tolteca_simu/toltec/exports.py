"""Files exported from TolTEC planning results.

The results table keeps the v1 planner's columns, so files made for proposals
read the same; its metadata carries the observation description, which
reproduces the results when the file is loaded again.
"""

from __future__ import annotations

from io import StringIO
from typing import TYPE_CHECKING, Any

import astropy.units as u
import numpy as np
from astropy.io import fits
from astropy.table import QTable

from tolteca_simu import __version__
from tolteca_simu.planning import ObservationDescription

from .info import TOLTEC_ARRAYS
from .sensitivity import POLARIZED_NOISE_FACTOR

if TYPE_CHECKING:
    from datetime import datetime

    from .planning import ToltecPlanningResult
    from .time_cost import TimeCost

__all__ = [
    "make_coverage_hdulist",
    "make_results_table",
    "read_results_metadata",
    "write_results_ecsv",
]

_DESCRIPTION_KEY = "observation_description"


def _mapping_speed_text(value: u.Quantity) -> str:
    return f"{value.value:.1f} {value.unit:s}"


def make_results_table(
    description: ObservationDescription,
    result: ToltecPlanningResult,
    time_cost: TimeCost,
    apt_path: str,
    created_at: datetime,
) -> QTable:
    """Return the planning results as a table with one row per array.

    Parameters
    ----------
    description : tolteca_simu.planning.ObservationDescription
        The observation.
    result : tolteca_simu.toltec.planning.ToltecPlanningResult
        Its TolTEC results.
    time_cost : tolteca_simu.toltec.time_cost.TimeCost
        Its project time.
    apt_path : str
        Array property table used, relative to the calibration data store.
    created_at : datetime.datetime
        Creation time, in UTC.

    Returns
    -------
    astropy.table.QTable
        Sensitivity, depth, and project time per array, with the description,
        APT, and package version in the metadata.
    """
    stokes = "Polarized (Q/U)" if result.polarized else "Total Intensity (I)"
    rows = []
    for name, s in result.summaries.items():
        nefd_i = s.noise.nefd
        nefd_qu = POLARIZED_NOISE_FACTOR * nefd_i
        noise_factor = POLARIZED_NOISE_FACTOR if result.polarized else 1.0
        mapping_speed_i = s.mapping_speed * noise_factor**2
        rows.append(
            {
                "array_name": name,
                "alt_mean": s.alt_mean.to(u.deg),
                "P": s.power,
                "n_dets_info": (
                    f"{s.n_dets} / {s.n_dets_designed} "
                    f"({s.n_dets / s.n_dets_designed:.0%})"
                ),
                "net_cmb": s.noise.net_cmb,
                "nefd": nefd_i,
                "nep": s.noise.nep,
                "nefd_I": nefd_i,
                "nefd_QU": nefd_qu,
                "dsens_I": np.sqrt(2.0) * nefd_i.to(u.mJy * u.s**0.5),
                "dsens_QU": np.sqrt(2.0) * nefd_qu.to(u.mJy * u.s**0.5),
                "mapping_speed_I": _mapping_speed_text(mapping_speed_i),
                "mapping_speed_QU": _mapping_speed_text(
                    mapping_speed_i / POLARIZED_NOISE_FACTOR**2
                ),
                "polarized": result.polarized,
                "depth_stokes_params": stokes,
                "depth_rms": s.depth_rms,
                "t_exp": result.t_exp,
                "t_exp_eff": result.t_exp_eff,
                "map_area": result.depth.map_area,
                "n_passes": result.n_passes,
                "depth_rms_coadd_desired": result.desired_sens,
                "depth_rms_coadd_actual": s.depth_rms_coadd,
                "proj_science_time": time_cost.science_time,
                "proj_science_time_per_night": time_cost.science_time_per_night,
                "proj_n_nights": time_cost.n_nights,
                "proj_science_overhead_time": time_cost.science_overhead,
                "proj_total_time": time_cost.total_time,
                "proj_overhead_time": time_cost.overhead_time,
                "proj_overhead_percent": f"{time_cost.overhead_fraction:.1%}",
            }
        )
    table = QTable(rows=rows)
    table.meta["created_at"] = created_at.isoformat()
    table.meta[_DESCRIPTION_KEY] = description.model_dump(mode="json")
    table.meta["apt"] = apt_path
    table.meta["tolteca_simu_version"] = __version__
    return table


def write_results_ecsv(table: QTable) -> str:
    """Return a results table as ECSV text.

    Parameters
    ----------
    table : astropy.table.QTable
        Table from `make_results_table`.

    Returns
    -------
    str
        The ECSV content.
    """
    content = StringIO()
    table.write(content, format="ascii.ecsv")
    return content.getvalue()


def read_results_metadata(
    content: str,
) -> tuple[ObservationDescription, dict[str, Any]]:
    """Read the observation description from a results ECSV file.

    Parameters
    ----------
    content : str
        ECSV text written by `write_results_ecsv`.

    Returns
    -------
    tuple
        The observation description, and the remaining metadata.

    Raises
    ------
    ValueError
        If the content is not a results table with a description.
    """
    try:
        table = QTable.read(content, format="ascii.ecsv")
    except Exception as error:
        msg = "Not an ECSV table"
        raise ValueError(msg) from error
    meta = dict(table.meta)
    if _DESCRIPTION_KEY not in meta:
        msg = "The table has no observation description"
        raise ValueError(msg)
    description = ObservationDescription.model_validate(meta.pop(_DESCRIPTION_KEY))
    return description, meta


def make_coverage_hdulist(result: ToltecPlanningResult, unit: str) -> fits.HDUList:
    """Return the coverage of the computed array as FITS images.

    Parameters
    ----------
    result : tolteca_simu.toltec.planning.ToltecPlanningResult
        The TolTEC results.
    unit : {"depth", "time"}
        Map depth in mJy/beam, or coverage in s/pixel.

    Returns
    -------
    astropy.io.fits.HDUList
        A primary header with the exposure and mean altitude, then the coverage
        without turnarounds (``cov_nooverhead``) and with them (``cov_raw``).
    """
    array = TOLTEC_ARRAYS[result.array_name]
    t_exp_s = result.t_exp.to_value(u.s)
    alt_mean = result.summaries[result.array_name].alt_mean
    primary = fits.Header()
    primary.append(
        ("ORIGIN", "The TolTEC Project", "Organization generating this FITS file")
    )
    primary.append(
        ("CREATOR", "tolteca_simu", "The software used to create this FITS file")
    )
    primary.append(("TELESCOP", "LMT", "Large Millimeter Telescope"))
    primary.append(("INSTRUME", "TolTEC", "TolTEC Camera"))
    primary.append(("EXPTIME", f"{t_exp_s:.3g}", "Exposure time (s)"))
    primary.append(("OBSDUR", f"{t_exp_s:g}", "Observation duration (s)"))
    primary.append(
        (
            "MEANALT",
            f"{alt_mean.to_value(u.deg):f}",
            # v1's comment overflowed the 80-character card and was truncated.
            "Mean target altitude during observation (deg)",
        )
    )
    if unit == "depth":
        images = [result.depth.depth, result.depth.depth_all]
        bunit = "mJy / beam"
    else:
        images = [result.coverage.data_on_scan, result.coverage.data]
        bunit = "s / pix"
    hdus: list[fits.PrimaryHDU | fits.ImageHDU] = [fits.PrimaryHDU(header=primary)]
    for data, extname in zip(images, ["cov_nooverhead", "cov_raw"], strict=True):
        header = result.coverage.wcs.to_header()
        header["BUNIT"] = bunit
        header.append(("ARRAYNAM", array.name, "The name of the TolTEC array"))
        header.append(("BAND", array.name, "The name of the TolTEC array"))
        header.append(("EXTNAME", extname, "The name of this extension"))
        hdus.append(fits.ImageHDU(data=data, header=header))
    return fits.HDUList(hdus)
