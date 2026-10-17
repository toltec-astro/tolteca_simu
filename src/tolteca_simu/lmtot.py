"""LMT observing tool (OT) scripts for an observation description.

The script follows v1 tolteca ``simu/exports``: a header, the TolTEC science
goal, the source, and the mapping lines. Double Lissajous and Rastajous
patterns lose their minor frequencies, which the OT derives itself.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import astropy.units as u
import numpy as np

from tolteca_simu.mapping import (
    DoubleLissajousPattern,
    LissajousPattern,
    RastajousPattern,
    RasterPattern,
)

if TYPE_CHECKING:
    from datetime import datetime

    from astropy.coordinates import SkyCoord

    from tolteca_simu.planning import ObservationDescription

__all__ = ["make_lmtot_script"]

_SOURCE_NAME_SPECIAL_CHARS = set(" ,:")
_SOURCE_LINE = (
    "Source Source;  Source  -BaselineList [] -CoordSys Eq"
    " -DecProperMotionCor 0"
    " -Dec[0] {Dec} -Dec[1] {Dec}"
    " -El[0] 0.000000 -El[1] 0.000000 -EphemerisTrackOn 0"
    " -Epoch 2000.0"
    " -GoToZenith 1 -L[0] 0.0 -L[1] 0.0 -LineList [] -Planet None"
    " -RaProperMotionCor 0 -Ra[0] {RA} -Ra[1] {RA}"
    " -SourceName {Name}"
    " -VelSys Lsr -Velocity 0.000000 -Vmag 0.0"
)
_LISSAJOUS_LINE = (
    "Lissajous -ExecMode {ExecMode} -RotateWithElevation 0 -TunePeriod 0"
    " -TScan {TScan} -ScanRate {ScanRate}"
    " -XLength {XLength} -YLength {YLength} -XOmega {XOmega}"
    " -YOmega {YOmega} -XDelta {XDelta}"
    " -XLengthMinor {XLengthMinor} -YLengthMinor {YLengthMinor}"
    " -XDeltaMinor {XDeltaMinor}"
)
_RASTER_LINE = (
    "RasterMap Map; Map -ExecMode {ExecMode} -HPBW 1 -HoldDuringTurns 0"
    " -MapMotion Continuous -NumPass 1 -NumRepeats 1 -NumScans 0"
    " -RowsPerScan 1000000 -ScansPerCal 0 -ScansToSkip 0"
    " -TCal 0 -TRef 0 -TSamp 1"
    " -MapCoord {MapCoord} -ScanAngle {ScanAngle}"
    " -XLength {XLength} -XOffset 0 -XRamp 0 -XStep {XStep}"
    " -YLength {YLength} -YOffset 0 -YRamp 0 -YStep {YStep}"
)
_MAP_COORD = {"icrs": "Ra", "altaz": "Az"}


def _lissajous_params(  # noqa: PLR0913
    *,
    x_length: u.Quantity,
    y_length: u.Quantity,
    x_omega: u.Quantity,
    y_omega: u.Quantity,
    delta: u.Quantity,
    t_exp: u.Quantity,
) -> dict[str, float]:
    cycles = [(u.cy / u.s, u.Hz)]
    v_x = 2 * x_length * x_omega.to(u.Hz, equivalencies=cycles)
    v_y = 2 * y_length * y_omega.to(u.Hz, equivalencies=cycles)
    return {
        "XLength": x_length.to_value(u.arcmin),
        "YLength": y_length.to_value(u.arcmin),
        "XOmega": x_omega.to_value(u.rad / u.s),
        "YOmega": y_omega.to_value(u.rad / u.s),
        "XDelta": delta.to_value(u.deg),
        "TScan": t_exp.to_value(u.s),
        "ScanRate": np.hypot(v_x, v_y).to_value(u.arcsec / u.s),
    }


def _double_lissajous_line(
    pattern: DoubleLissajousPattern | RastajousPattern,
    t_exp: u.Quantity,
    exec_mode: int,
) -> str:
    major = _lissajous_params(
        x_length=pattern.x_length_0,
        y_length=pattern.y_length_0,
        x_omega=pattern.x_omega_0,
        y_omega=pattern.y_omega_0,
        delta=pattern.delta_0,
        t_exp=t_exp,
    )
    minor = _lissajous_params(
        x_length=pattern.x_length_1,
        y_length=pattern.y_length_1,
        x_omega=pattern.x_omega_1,
        y_omega=pattern.y_omega_1,
        delta=pattern.delta_1,
        t_exp=0 << u.s,
    )
    return _LISSAJOUS_LINE.format(
        ExecMode=exec_mode,
        XLengthMinor=minor["XLength"],
        YLengthMinor=minor["YLength"],
        XDeltaMinor=minor["XDelta"],
        **major,
    )


def _raster_line(
    pattern: RasterPattern | RastajousPattern, ref_frame: str, exec_mode: int
) -> str:
    return _RASTER_LINE.format(
        ExecMode=exec_mode,
        MapCoord=_MAP_COORD[ref_frame],
        ScanAngle=pattern.rot.to_value(u.deg),
        XLength=pattern.length.to_value(u.arcsec),
        XStep=pattern.speed.to_value(u.arcsec / u.s),
        YLength=(pattern.n_scans * pattern.space).to_value(u.arcsec),
        YStep=pattern.space.to_value(u.arcsec),
    )


def get_source_name(target_name: str, target: SkyCoord) -> str:
    """Return the OT source name for a target.

    Parameters
    ----------
    target_name : str
        The target as the user entered it.
    target : astropy.coordinates.SkyCoord
        The target coordinate.

    Returns
    -------
    str
        ``target_name``, or the compact hms/dms coordinate when the name
        contains spaces, commas or colons.
    """
    if _SOURCE_NAME_SPECIAL_CHARS.intersection(target_name):
        return target.to_string(style="hmsdms", precision=0).replace(" ", "")
    return target_name


def make_lmtot_script(
    description: ObservationDescription, author: str, created_at: datetime
) -> str:
    """Return the LMT OT script for an observation description.

    Parameters
    ----------
    description : tolteca_simu.planning.ObservationDescription
        The observation.
    author : str
        Author recorded in the script header.
    created_at : datetime.datetime
        Creation time recorded in the header, in UTC.

    Returns
    -------
    str
        The script lines joined by newlines.
    """
    target = description.target.icrs
    source_name = get_source_name(description.target_name, target)
    timestamp = created_at.strftime("%a %b %d %H:%M:%S %Z %Y")
    steps = [
        (
            f'#ObservingScript -Name "{source_name}.txt" -Author "{author}"'
            f' -Date "{timestamp}"'
        ),
        "ObsGoal Dcs; Dcs -ObsGoal Science",
        _SOURCE_LINE.format(
            RA=target.ra.to_string(
                unit=u.hour, pad=True, decimal=False, fields=3, sep=":"
            ),
            Dec=target.dec.to_string(
                unit=u.degree,
                pad=True,
                alwayssign=True,
                decimal=False,
                fields=3,
                sep=":",
            ),
            Name=source_name,
        ),
    ]
    pattern = description.mapping
    t_exp = description.get_t_exp()
    if isinstance(pattern, LissajousPattern):
        steps.append(
            _LISSAJOUS_LINE.format(
                ExecMode=0,
                XLengthMinor=0.0,
                YLengthMinor=0.0,
                XDeltaMinor=0.0,
                **_lissajous_params(
                    x_length=pattern.x_length,
                    y_length=pattern.y_length,
                    x_omega=pattern.x_omega,
                    y_omega=pattern.y_omega,
                    delta=pattern.delta,
                    t_exp=t_exp,
                ),
            )
        )
    elif isinstance(pattern, DoubleLissajousPattern):
        steps.append(_double_lissajous_line(pattern, t_exp, exec_mode=0))
    elif isinstance(pattern, RasterPattern):
        steps.append(_raster_line(pattern, description.ref_frame, exec_mode=0))
    else:
        steps.append(_double_lissajous_line(pattern, t_exp, exec_mode=1))
        steps.append(_raster_line(pattern, description.ref_frame, exec_mode=1))
    return "\n".join(steps)
