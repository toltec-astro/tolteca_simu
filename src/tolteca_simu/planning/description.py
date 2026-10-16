"""The observation description that planning results derive from."""

from astropy.coordinates import SkyCoord
from pydantic import ConfigDict, Field, TypeAdapter
from tollan.config import FrozenBaseModel
from tollan.config.types import SkyCoordField, TimeField

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
    """Target and start time of one observation.

    The description records the resolved coordinate, so reloading a saved
    description reproduces its results without resolving the name again.

    Parameters
    ----------
    target_name : str
        The target as the user entered it.
    target : astropy.coordinates.SkyCoord
        The target's ICRS coordinate.
    t0 : astropy.time.Time
        The observation start time.
    """

    model_config = ConfigDict(extra="forbid")
    target_name: str = Field(description="The target as the user entered it.")
    target: SkyCoordField = Field(description="The target's ICRS coordinate.")
    t0: TimeField = Field(description="The observation start time.")
