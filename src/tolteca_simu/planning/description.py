"""The observation description that planning results derive from."""

from typing import Literal

import astropy.units as u
from astropy.coordinates import SkyCoord
from pydantic import ConfigDict, Field, TypeAdapter
from tollan.config import FrozenBaseModel
from tollan.config.types import (
    SkyCoordField,
    TimeField,
    TimeQuantityField,
    quantity_field,
)

from tolteca_simu.lmt import LmtAtmModelName
from tolteca_simu.mapping import MappingPattern
from tolteca_simu.toltec.settings import ToltecSettings

# Tollan has no named field type for flux densities. Pydantic evaluates this
# alias at runtime; type checkers do not accept a factory call in annotations.
type FluxDensityQuantityField = quantity_field("spectral flux density")  # ty: ignore[invalid-type-form]

__all__ = ["ObservationDescription", "parse_target"]

_target_adapter = TypeAdapter(SkyCoordField)


def parse_target(text: str) -> SkyCoord:
    """Return the ICRS coordinate of a target given by coordinate or name.

    Parameters
    ----------
    text : str
        A coordinate such as ``"17.7d -2.1d"`` or ``"10h09m08s +20d19m18s"``, or a
        source name such as ``"M1"``. Names are resolved through
        `tollan.config.types.SkyCoordField`, which queries a name lookup service.

    Returns
    -------
    astropy.coordinates.SkyCoord
        The resolved ICRS coordinate, without the source name.

    Raises
    ------
    pydantic.ValidationError
        If the text is neither a coordinate nor a resolvable name.
    """
    icrs = _target_adapter.validate_python(text).icrs
    return SkyCoord(ra=icrs.ra, dec=icrs.dec, frame="icrs")


class ObservationDescription(FrozenBaseModel):  # numpydoc ignore=PR02
    """Target, time, mapping, conditions, and instrument of one observation.

    The description records the resolved coordinate and the mapping parameters
    actually used, so reloading a saved description reproduces its results
    without resolving the name or applying a preset again.

    Parameters
    ----------
    target_name : str
        The target as the user entered it.
    target : astropy.coordinates.SkyCoord
        The target's ICRS coordinate.
    t0 : astropy.time.Time
        The observation start time.
    mapping : tolteca_simu.mapping.MappingPattern
        The mapping pattern.
    ref_frame : {"altaz", "icrs"}
        Frame in which the pattern offsets are interpreted.
    t_exp : astropy.units.Quantity, optional
        Exposure time; None observes the pattern once.
    atm_model_name : {"am_q25", "am_q50", "am_q75"}
        LMT atmosphere model: the quartile of the am conditions.
    instrument : tolteca_simu.toltec.settings.ToltecSettings
        Instrument settings.
    desired_sens : astropy.units.Quantity
        Desired coadded map depth.
    """

    model_config = ConfigDict(extra="forbid")
    target_name: str = Field(description="The target as the user entered it.")
    target: SkyCoordField = Field(description="The target's ICRS coordinate.")
    t0: TimeField = Field(description="The observation start time.")
    mapping: MappingPattern = Field(description="The mapping pattern.")
    ref_frame: Literal["altaz", "icrs"] = Field(
        description="Frame in which the pattern offsets are interpreted."
    )
    t_exp: TimeQuantityField | None = Field(
        default=None, description="Exposure time; None observes the pattern once."
    )
    atm_model_name: LmtAtmModelName = Field(description="LMT atmosphere model.")
    instrument: ToltecSettings = Field(description="Instrument settings.")
    desired_sens: FluxDensityQuantityField = Field(
        description="Desired coadded map depth."
    )

    def get_t_exp(self) -> u.Quantity:
        """Return the exposure time, or the pattern duration when unset.

        Returns
        -------
        astropy.units.Quantity
            ``t_exp``, or the duration of one pass of ``mapping``.
        """
        return self.mapping.t_pattern if self.t_exp is None else self.t_exp
