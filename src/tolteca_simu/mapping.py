"""Telescope mapping patterns as offsets in time from a reference point.

Evaluate a pattern at arbitrary times; the result does not depend on the
sampling, which the consumer chooses:

>>> import astropy.units as u
>>> import numpy as np
>>> from tolteca_simu.mapping import RasterPattern
>>> raster = RasterPattern(
...     length="10 arcmin", space="1 arcmin", n_scans=5, rot="0 deg",
...     speed="30 arcsec/s", t_turnaround="5 s",
... )
>>> raster.t_pattern
<Quantity 120. s>
>>> dlon, dlat = raster.offsets(np.array([0, 10]) << u.s)
>>> dlon.to(u.arcmin)
<Quantity [-5., 0.] arcmin>

The pattern functions take explicit quantities; the pattern models carry
validated parameters and name the pattern by its ``type``.
"""

from enum import Flag, auto
from typing import Annotated, ClassVar, Literal, Self

import astropy.units as u
import numpy as np
from pydantic import ConfigDict, Field
from tollan.config import FrozenBaseModel
from tollan.config.types import AngleQuantityField, TimeQuantityField, quantity_field

__all__ = [
    "DoubleLissajousPattern",
    "LissajousPattern",
    "MappingPattern",
    "PatternKind",
    "RastajousPattern",
    "RasterPattern",
    "double_lissajous_offsets",
    "lissajous_average_speed",
    "lissajous_duration",
    "lissajous_offsets",
    "rastajous_offsets",
    "raster_duration",
    "raster_offsets",
    "raster_turnaround_mask",
]

# Tollan has no named field type for angular speeds. Pydantic evaluates this
# alias at runtime; type checkers do not accept a factory call in annotations.
type AngularSpeedQuantityField = quantity_field("angular speed")  # ty: ignore[invalid-type-form]

# The LMT observing tool runs the minor Lissajous pattern at this fraction of
# the major pattern's average speed.
_MINOR_LISSAJOUS_SPEED_FRACTION = 1 / 20


class PatternKind(Flag):
    """Kinds of mapping patterns.

    A raster-like pattern cannot be observed for longer than its duration; a
    Lissajous-like pattern may repeat.
    """

    raster = auto()
    lissajous = auto()
    rastajous = auto()
    raster_like = raster | rastajous


def _rotate(x: u.Quantity, y: u.Quantity, rot: u.Quantity) -> tuple:
    angle = rot.to_value(u.rad)
    matrix = np.array(
        [[np.cos(angle), -np.sin(angle)], [np.sin(angle), np.cos(angle)]],
        dtype=np.float64,
    )
    xy = np.empty((2, *x.shape), dtype=np.float64) << x.unit
    xy[0] = x
    xy[1] = y
    xx, yy = np.einsum("ij...,j...->i...", matrix, xy)
    return xx, yy


def _raster_scan(
    t: u.Quantity,
    *,
    length: u.Quantity,
    space: u.Quantity,
    n_scans: int,
    speed: u.Quantity,
    t_turnaround: u.Quantity,
) -> tuple[u.Quantity, u.Quantity, np.ndarray]:
    """Unrotated raster offsets and the turnaround mask."""
    unit = length.unit
    t_per_scan = length / speed
    turnaround = np.zeros(t.shape, dtype=bool)
    xy = np.empty((2, *t.shape), dtype=np.float64) << unit
    if n_scans == 1:
        xy[0] = (t / t_per_scan - 0.5) * length
        xy[1] = 0 << unit
        return xy[0], xy[1], turnaround
    n_spaces = n_scans - 1
    ratio_scan_to_si = t_per_scan / (t_turnaround + t_per_scan)
    ratio_scan_to_turnaround = t_per_scan / t_turnaround
    _si = t / (t_turnaround + t_per_scan)
    si = _si.astype(int)
    si_frac = _si - si
    scan_frac = np.empty_like(si_frac)
    turnaround_frac = np.empty_like(si_frac)
    turnaround = si_frac > ratio_scan_to_si
    scan_frac[turnaround] = 1.0
    scan_frac[~turnaround] = si_frac[~turnaround] / ratio_scan_to_si
    turnaround_frac[turnaround] = (
        si_frac[turnaround] - (1.0 - si_frac[turnaround]) * ratio_scan_to_turnaround
    )
    turnaround_frac[~turnaround] = 0.0
    xy[0] = (scan_frac - 0.5) * length
    xy[1] = (si / n_spaces - 0.5) * n_spaces * space
    # Turn around on a half circle between consecutive scans.
    radius_t = space / 2
    theta_t = (turnaround_frac[turnaround] * np.pi).to(u.rad, u.dimensionless_angles())
    xy[0, turnaround] += radius_t * np.sin(theta_t)
    xy[1, turnaround] += radius_t * (1.0 - np.cos(theta_t))
    # Alternate the scan direction.
    xy[0] *= (-1) ** si
    return xy[0], xy[1], np.asarray(turnaround)


def raster_offsets(
    t: u.Quantity,
    *,
    length: u.Quantity,
    space: u.Quantity,
    n_scans: int,
    rot: u.Quantity,
    speed: u.Quantity,
    t_turnaround: u.Quantity,
) -> tuple[u.Quantity, u.Quantity]:
    """Return raster offsets: parallel scans joined by half-circle turnarounds.

    Parameters
    ----------
    t : astropy.units.Quantity
        Times since the pattern start.
    length : astropy.units.Quantity
        Length of each scan.
    space : astropy.units.Quantity
        Spacing between scans.
    n_scans : int
        Number of scans.
    rot : astropy.units.Quantity
        Rotation of the scan direction from the +lon axis.
    speed : astropy.units.Quantity
        Scan speed.
    t_turnaround : astropy.units.Quantity
        Time to turn around between scans.

    Returns
    -------
    tuple of astropy.units.Quantity
        Longitude and latitude offsets, in the unit of ``length``.
    """
    x, y, _ = _raster_scan(
        t,
        length=length,
        space=space,
        n_scans=n_scans,
        speed=speed,
        t_turnaround=t_turnaround,
    )
    return _rotate(x, y, rot)


def raster_turnaround_mask(
    t: u.Quantity,
    *,
    length: u.Quantity,
    space: u.Quantity,
    n_scans: int,
    speed: u.Quantity,
    t_turnaround: u.Quantity,
) -> np.ndarray:
    """Return whether the raster is turning around at each time.

    Parameters
    ----------
    t : astropy.units.Quantity
        Times since the pattern start.
    length : astropy.units.Quantity
        Length of each scan.
    space : astropy.units.Quantity
        Spacing between scans.
    n_scans : int
        Number of scans.
    speed : astropy.units.Quantity
        Scan speed.
    t_turnaround : astropy.units.Quantity
        Time to turn around between scans.

    Returns
    -------
    numpy.ndarray
        Boolean mask, True during turnarounds; all False for a single scan.
    """
    return _raster_scan(
        t,
        length=length,
        space=space,
        n_scans=n_scans,
        speed=speed,
        t_turnaround=t_turnaround,
    )[2]


def raster_duration(
    length: u.Quantity, n_scans: int, speed: u.Quantity, t_turnaround: u.Quantity
) -> u.Quantity:
    """Return the time to execute a raster once.

    Parameters
    ----------
    length : astropy.units.Quantity
        Length of each scan.
    n_scans : int
        Number of scans.
    speed : astropy.units.Quantity
        Scan speed.
    t_turnaround : astropy.units.Quantity
        Time to turn around between scans.

    Returns
    -------
    astropy.units.Quantity
        Scanning time plus the turnarounds between scans, in seconds.
    """
    return (length / speed * n_scans + t_turnaround * (n_scans - 1.0)).to(u.s)


def lissajous_offsets(
    t: u.Quantity,
    *,
    x_length: u.Quantity,
    y_length: u.Quantity,
    x_omega: u.Quantity,
    y_omega: u.Quantity,
    delta: u.Quantity,
    rot: u.Quantity,
) -> tuple[u.Quantity, u.Quantity]:
    """Return Lissajous offsets.

    Parameters
    ----------
    t : astropy.units.Quantity
        Times since the pattern start.
    x_length, y_length : astropy.units.Quantity
        Full extent of the pattern along x and y.
    x_omega, y_omega : astropy.units.Quantity
        Angular frequencies along x and y.
    delta : astropy.units.Quantity
        Phase of x with respect to y.
    rot : astropy.units.Quantity
        Rotation of the x axis from the +lon axis.

    Returns
    -------
    tuple of astropy.units.Quantity
        Longitude and latitude offsets, in the unit of ``x_length``.
    """
    x = x_length * 0.5 * np.sin(x_omega * t + delta)
    y = y_length * 0.5 * np.sin(y_omega * t)
    return _rotate(x.to(x_length.unit), y.to(x_length.unit), rot)


def lissajous_duration(x_omega: u.Quantity, y_omega: u.Quantity) -> u.Quantity:
    """Return the time for a Lissajous pattern to close.

    The ratio of the two periods is rounded to two decimals before taking
    their least common multiple.

    Parameters
    ----------
    x_omega, y_omega : astropy.units.Quantity
        Angular frequencies along x and y.

    Returns
    -------
    astropy.units.Quantity
        Pattern period, in seconds.
    """
    t_x = 2 * np.pi * u.rad / x_omega
    t_y = 2 * np.pi * u.rad / y_omega
    r = (t_y / t_x).to_value(u.dimensionless_unscaled)
    s = 100
    r = np.lcm(int(r * s), s) / s
    return (t_x * r).to(u.s)


def lissajous_average_speed(
    x_length: u.Quantity, y_length: u.Quantity, x_omega: u.Quantity, y_omega: u.Quantity
) -> u.Quantity:
    """Return the nominal average speed of a Lissajous pattern.

    Each axis moves ``2 * length`` per cycle; the axes combine in quadrature.

    Parameters
    ----------
    x_length, y_length : astropy.units.Quantity
        Full extent of the pattern along x and y.
    x_omega, y_omega : astropy.units.Quantity
        Angular frequencies along x and y.

    Returns
    -------
    astropy.units.Quantity
        Speed in arcsec/s.
    """
    cycles = [(u.cy / u.s, u.Hz)]
    v_x = 2 * x_length * x_omega.to(u.Hz, equivalencies=cycles)
    v_y = 2 * y_length * y_omega.to(u.Hz, equivalencies=cycles)
    return np.hypot(v_x, v_y).to(u.arcsec / u.s)


def double_lissajous_offsets(
    t: u.Quantity,
    *,
    x_length_0: u.Quantity,
    y_length_0: u.Quantity,
    x_omega_0: u.Quantity,
    y_omega_0: u.Quantity,
    delta_0: u.Quantity,
    x_length_1: u.Quantity,
    y_length_1: u.Quantity,
    x_omega_1: u.Quantity,
    y_omega_1: u.Quantity,
    delta_1: u.Quantity,
    delta: u.Quantity,
    rot: u.Quantity,
) -> tuple[u.Quantity, u.Quantity]:
    """Return offsets of a major Lissajous pattern plus a minor one.

    Parameters
    ----------
    t : astropy.units.Quantity
        Times since the pattern start.
    x_length_0, y_length_0 : astropy.units.Quantity
        Extent of the major pattern along x and y.
    x_omega_0, y_omega_0 : astropy.units.Quantity
        Angular frequencies of the major pattern.
    delta_0 : astropy.units.Quantity
        Phase of x with respect to y in the major pattern.
    x_length_1, y_length_1 : astropy.units.Quantity
        Extent of the minor pattern along x and y.
    x_omega_1, y_omega_1 : astropy.units.Quantity
        Angular frequencies of the minor pattern.
    delta_1 : astropy.units.Quantity
        Phase of x with respect to y in the minor pattern.
    delta : astropy.units.Quantity
        Phase of the major pattern's y with respect to the minor pattern's y.
    rot : astropy.units.Quantity
        Rotation of the x axis from the +lon axis.

    Returns
    -------
    tuple of astropy.units.Quantity
        Longitude and latitude offsets, in the unit of ``x_length_0``.
    """
    unit = x_length_0.unit
    x_0 = x_length_0 * 0.5 * np.sin(x_omega_0 * t + delta + delta_0)
    y_0 = y_length_0 * 0.5 * np.sin(y_omega_0 * t + delta)
    x_1 = x_length_1 * 0.5 * np.sin(x_omega_1 * t + delta_1)
    y_1 = y_length_1 * 0.5 * np.sin(y_omega_1 * t)
    xy = np.empty((2, *t.shape), dtype=np.float64) << unit
    xy[0] = x_0 + x_1
    xy[1] = y_0 + y_1
    return _rotate(xy[0], xy[1], rot)


def rastajous_offsets(
    t: u.Quantity,
    *,
    length: u.Quantity,
    space: u.Quantity,
    n_scans: int,
    rot: u.Quantity,
    speed: u.Quantity,
    t_turnaround: u.Quantity,
    x_length_0: u.Quantity,
    y_length_0: u.Quantity,
    x_omega_0: u.Quantity,
    y_omega_0: u.Quantity,
    delta_0: u.Quantity,
    x_length_1: u.Quantity,
    y_length_1: u.Quantity,
    x_omega_1: u.Quantity,
    y_omega_1: u.Quantity,
    delta_1: u.Quantity,
    delta: u.Quantity,
) -> tuple[u.Quantity, u.Quantity]:
    """Return offsets of a double Lissajous pattern carried along a raster.

    Parameters
    ----------
    t : astropy.units.Quantity
        Times since the pattern start.
    length, space : astropy.units.Quantity
        Scan length and spacing; see `raster_offsets`.
    n_scans : int
        Number of scans.
    rot : astropy.units.Quantity
        Rotation of the combined pattern from the +lon axis.
    speed, t_turnaround : astropy.units.Quantity
        Scan speed and turnaround time; see `raster_offsets`.
    x_length_0, y_length_0, x_omega_0, y_omega_0, delta_0 : astropy.units.Quantity
        Major Lissajous parameters; see `double_lissajous_offsets`.
    x_length_1, y_length_1, x_omega_1, y_omega_1, delta_1 : astropy.units.Quantity
        Minor Lissajous parameters; see `double_lissajous_offsets`.
    delta : astropy.units.Quantity
        Phase of the major pattern's y with respect to the minor pattern's y.

    Returns
    -------
    tuple of astropy.units.Quantity
        Longitude and latitude offsets, in the unit of ``x_length_0``.
    """
    unit = x_length_0.unit
    x_r, y_r = raster_offsets(
        t,
        length=length,
        space=space,
        n_scans=n_scans,
        rot=0 << u.deg,
        speed=speed,
        t_turnaround=t_turnaround,
    )
    x_l, y_l = double_lissajous_offsets(
        t,
        x_length_0=x_length_0,
        y_length_0=y_length_0,
        x_omega_0=x_omega_0,
        y_omega_0=y_omega_0,
        delta_0=delta_0,
        x_length_1=x_length_1,
        y_length_1=y_length_1,
        x_omega_1=x_omega_1,
        y_omega_1=y_omega_1,
        delta_1=delta_1,
        delta=delta,
        rot=0 << u.deg,
    )
    xy = np.empty((2, *t.shape), dtype=np.float64) << unit
    xy[0] = x_r + x_l
    xy[1] = y_r + y_l
    return _rotate(xy[0], xy[1], rot)


class _PatternBase(FrozenBaseModel):
    model_config = ConfigDict(extra="forbid")
    pattern_kind: ClassVar[PatternKind]

    rot: AngleQuantityField = Field(
        description="Rotation of the pattern from the +lon axis."
    )


class _RasterParams(FrozenBaseModel):
    length: AngleQuantityField = Field(description="Length of each scan.")
    space: AngleQuantityField = Field(description="Spacing between scans.")
    n_scans: int = Field(ge=1, description="Number of scans.")
    speed: AngularSpeedQuantityField = Field(description="Scan speed.")
    t_turnaround: TimeQuantityField = Field(
        description="Time to turn around between scans."
    )

    def _raster_kwargs(self) -> dict:
        return {name: getattr(self, name) for name in _RasterParams.model_fields}


class _DoubleLissajousParams(FrozenBaseModel):
    x_length_0: AngleQuantityField = Field(description="Major pattern size in x.")
    y_length_0: AngleQuantityField = Field(description="Major pattern size in y.")
    x_omega_0: AngularSpeedQuantityField = Field(
        description="Major pattern angular frequency in x."
    )
    y_omega_0: AngularSpeedQuantityField = Field(
        description="Major pattern angular frequency in y."
    )
    delta_0: AngleQuantityField = Field(
        description="Major pattern phase of x with respect to y."
    )
    x_length_1: AngleQuantityField = Field(description="Minor pattern size in x.")
    y_length_1: AngleQuantityField = Field(description="Minor pattern size in y.")
    x_omega_1: AngularSpeedQuantityField = Field(
        description="Minor pattern angular frequency in x."
    )
    y_omega_1: AngularSpeedQuantityField = Field(
        description="Minor pattern angular frequency in y."
    )
    delta_1: AngleQuantityField = Field(
        description="Minor pattern phase of x with respect to y."
    )
    delta: AngleQuantityField = Field(
        description="Phase of the major pattern's y with respect to the minor's."
    )

    def _double_lissajous_kwargs(self) -> dict:
        return {
            name: getattr(self, name) for name in _DoubleLissajousParams.model_fields
        }

    def _with_major_speed(self, speed: u.Quantity) -> dict:
        average = lissajous_average_speed(
            self.x_length_0, self.y_length_0, self.x_omega_0, self.y_omega_0
        )
        scale_0 = (speed / average).to_value(u.dimensionless_unscaled)
        scale_1 = (speed / average * _MINOR_LISSAJOUS_SPEED_FRACTION).to_value(
            u.dimensionless_unscaled
        )
        return {
            "x_omega_0": (self.x_omega_0 * scale_0).to(u.rad / u.s),
            "y_omega_0": (self.y_omega_0 * scale_0).to(u.rad / u.s),
            "x_omega_1": (self.x_omega_1 * scale_1).to(u.rad / u.s),
            "y_omega_1": (self.y_omega_1 * scale_1).to(u.rad / u.s),
        }

    def _double_lissajous_duration(self) -> u.Quantity:
        t_0 = t_1 = 0 << u.s
        if self.x_length_0 != 0 and self.y_length_0 != 0:
            t_0 = lissajous_duration(self.x_omega_0, self.y_omega_0)
        if self.x_length_1 != 0 and self.y_length_1 != 0:
            t_1 = lissajous_duration(self.x_omega_1, self.y_omega_1)
        return max(t_0, t_1)


class RasterPattern(_RasterParams, _PatternBase):  # numpydoc ignore=PR02
    """Parallel scans joined by half-circle turnarounds.

    Parameters
    ----------
    type : {"raster"}
        Pattern name.
    length, space : astropy.units.Quantity
        Scan length and spacing.
    n_scans : int
        Number of scans.
    speed : astropy.units.Quantity
        Scan speed.
    t_turnaround : astropy.units.Quantity
        Time to turn around between scans.
    rot : astropy.units.Quantity
        Rotation of the pattern from the +lon axis.
    """

    pattern_kind: ClassVar[PatternKind] = PatternKind.raster
    type: Literal["raster"] = "raster"

    @property
    def t_pattern(self) -> u.Quantity:
        """Time to execute the pattern once."""
        return raster_duration(self.length, self.n_scans, self.speed, self.t_turnaround)

    def offsets(self, t: u.Quantity) -> tuple[u.Quantity, u.Quantity]:
        """Return the offsets at times since the pattern start.

        Parameters
        ----------
        t : astropy.units.Quantity
            Times since the pattern start.

        Returns
        -------
        tuple of astropy.units.Quantity
            Longitude and latitude offsets.
        """
        return raster_offsets(t, rot=self.rot, **self._raster_kwargs())

    def turnaround_mask(self, t: u.Quantity) -> np.ndarray:
        """Return whether the telescope is turning around at each time.

        Parameters
        ----------
        t : astropy.units.Quantity
            Times since the pattern start.

        Returns
        -------
        numpy.ndarray
            Boolean mask, True during turnarounds.
        """
        return raster_turnaround_mask(t, **self._raster_kwargs())

    def with_lissajous_speed(self, speed: u.Quantity) -> Self:  # noqa: ARG002
        """Return the pattern unchanged; a raster has no Lissajous part.

        Parameters
        ----------
        speed : astropy.units.Quantity
            Ignored.

        Returns
        -------
        RasterPattern
            This pattern.
        """
        return self


class LissajousPattern(_PatternBase):  # numpydoc ignore=PR02
    """A Lissajous figure.

    Parameters
    ----------
    type : {"lissajous"}
        Pattern name.
    x_length, y_length : astropy.units.Quantity
        Full extent along x and y.
    x_omega, y_omega : astropy.units.Quantity
        Angular frequencies along x and y.
    delta : astropy.units.Quantity
        Phase of x with respect to y.
    rot : astropy.units.Quantity
        Rotation of the pattern from the +lon axis.
    """

    pattern_kind: ClassVar[PatternKind] = PatternKind.lissajous
    type: Literal["lissajous"] = "lissajous"
    x_length: AngleQuantityField = Field(description="Pattern size in x.")
    y_length: AngleQuantityField = Field(description="Pattern size in y.")
    x_omega: AngularSpeedQuantityField = Field(description="Angular frequency in x.")
    y_omega: AngularSpeedQuantityField = Field(description="Angular frequency in y.")
    delta: AngleQuantityField = Field(description="Phase of x with respect to y.")

    @property
    def t_pattern(self) -> u.Quantity:
        """Time for the figure to close."""
        return lissajous_duration(self.x_omega, self.y_omega)

    def offsets(self, t: u.Quantity) -> tuple[u.Quantity, u.Quantity]:
        """Return the offsets at times since the pattern start.

        Parameters
        ----------
        t : astropy.units.Quantity
            Times since the pattern start.

        Returns
        -------
        tuple of astropy.units.Quantity
            Longitude and latitude offsets.
        """
        return lissajous_offsets(
            t,
            x_length=self.x_length,
            y_length=self.y_length,
            x_omega=self.x_omega,
            y_omega=self.y_omega,
            delta=self.delta,
            rot=self.rot,
        )

    def with_lissajous_speed(self, speed: u.Quantity) -> Self:
        """Return the pattern with its frequencies scaled to an average speed.

        Parameters
        ----------
        speed : astropy.units.Quantity
            Target average speed; see `lissajous_average_speed`.

        Returns
        -------
        LissajousPattern
            The pattern with both angular frequencies scaled by one factor.
        """
        average = lissajous_average_speed(
            self.x_length, self.y_length, self.x_omega, self.y_omega
        )
        scale = (speed / average).to_value(u.dimensionless_unscaled)
        return self.model_copy(
            update={
                "x_omega": (self.x_omega * scale).to(u.rad / u.s),
                "y_omega": (self.y_omega * scale).to(u.rad / u.s),
            }
        )


class DoubleLissajousPattern(
    _DoubleLissajousParams, _PatternBase
):  # numpydoc ignore=PR02
    """A major Lissajous figure plus a minor one.

    Parameters
    ----------
    type : {"double_lissajous"}
        Pattern name.
    x_length_0, y_length_0, x_omega_0, y_omega_0, delta_0 : astropy.units.Quantity
        Major pattern; see `double_lissajous_offsets`.
    x_length_1, y_length_1, x_omega_1, y_omega_1, delta_1 : astropy.units.Quantity
        Minor pattern; see `double_lissajous_offsets`.
    delta : astropy.units.Quantity
        Phase of the major pattern's y with respect to the minor pattern's y.
    rot : astropy.units.Quantity
        Rotation of the pattern from the +lon axis.
    """

    pattern_kind: ClassVar[PatternKind] = PatternKind.lissajous
    type: Literal["double_lissajous"] = "double_lissajous"

    @property
    def t_pattern(self) -> u.Quantity:
        """Time for the slower of the two figures to close."""
        return self._double_lissajous_duration()

    def offsets(self, t: u.Quantity) -> tuple[u.Quantity, u.Quantity]:
        """Return the offsets at times since the pattern start.

        Parameters
        ----------
        t : astropy.units.Quantity
            Times since the pattern start.

        Returns
        -------
        tuple of astropy.units.Quantity
            Longitude and latitude offsets.
        """
        return double_lissajous_offsets(
            t, rot=self.rot, **self._double_lissajous_kwargs()
        )

    def with_lissajous_speed(self, speed: u.Quantity) -> Self:
        """Return the pattern with the major figure at an average speed.

        Parameters
        ----------
        speed : astropy.units.Quantity
            Target average speed of the major figure.

        Returns
        -------
        DoubleLissajousPattern
            The pattern with the major frequencies scaled to ``speed`` and the
            minor frequencies scaled to 1/20 of it, as the LMT observing tool does.
        """
        return self.model_copy(update=self._with_major_speed(speed))


class RastajousPattern(  # numpydoc ignore=PR02
    _DoubleLissajousParams, _RasterParams, _PatternBase
):
    """A double Lissajous figure carried along a raster.

    Parameters
    ----------
    type : {"rastajous"}
        Pattern name.
    length, space : astropy.units.Quantity
        Raster scan length and spacing.
    n_scans : int
        Number of raster scans.
    speed, t_turnaround : astropy.units.Quantity
        Raster scan speed and turnaround time.
    rot : astropy.units.Quantity
        Rotation of the combined pattern from the +lon axis.
    x_length_0, y_length_0, x_omega_0, y_omega_0, delta_0 : astropy.units.Quantity
        Major Lissajous pattern; see `double_lissajous_offsets`.
    x_length_1, y_length_1, x_omega_1, y_omega_1, delta_1 : astropy.units.Quantity
        Minor Lissajous pattern; see `double_lissajous_offsets`.
    delta : astropy.units.Quantity
        Phase of the major pattern's y with respect to the minor pattern's y.
    """

    pattern_kind: ClassVar[PatternKind] = PatternKind.rastajous
    type: Literal["rastajous"] = "rastajous"

    @property
    def t_pattern(self) -> u.Quantity:
        """Time to execute the raster once."""
        return raster_duration(self.length, self.n_scans, self.speed, self.t_turnaround)

    def offsets(self, t: u.Quantity) -> tuple[u.Quantity, u.Quantity]:
        """Return the offsets at times since the pattern start.

        Parameters
        ----------
        t : astropy.units.Quantity
            Times since the pattern start.

        Returns
        -------
        tuple of astropy.units.Quantity
            Longitude and latitude offsets.
        """
        return rastajous_offsets(
            t,
            rot=self.rot,
            **self._raster_kwargs(),
            **self._double_lissajous_kwargs(),
        )

    def with_lissajous_speed(self, speed: u.Quantity) -> Self:
        """Return the pattern with the major figure at an average speed.

        Parameters
        ----------
        speed : astropy.units.Quantity
            Target average speed of the major figure.

        Returns
        -------
        RastajousPattern
            The pattern with the major frequencies scaled to ``speed`` and the
            minor frequencies scaled to 1/20 of it, as the LMT observing tool does.
        """
        return self.model_copy(update=self._with_major_speed(speed))


type MappingPattern = Annotated[
    RasterPattern | LissajousPattern | DoubleLissajousPattern | RastajousPattern,
    Field(discriminator="type"),
]
