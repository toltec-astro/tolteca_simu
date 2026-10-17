"""TolTEC settings of an observation description."""

from typing import Literal

from pydantic import ConfigDict, Field
from tollan.config import FrozenBaseModel

from .info import ToltecArrayName

__all__ = ["ToltecSettings"]


class ToltecSettings(FrozenBaseModel):  # numpydoc ignore=PR02
    """TolTEC settings of an observation.

    Parameters
    ----------
    name : {"toltec"}
        Instrument name.
    polarized : bool
        Whether the observation measures polarized intensity (Stokes Q/U).
    array_name : {"a1100", "a1400", "a2000"}
        Array whose coverage and depth set the number of passes.
    """

    model_config = ConfigDict(extra="forbid")
    name: Literal["toltec"] = "toltec"
    polarized: bool = Field(description="Whether to measure polarized intensity.")
    array_name: ToltecArrayName = Field(
        description="Array whose depth sets the number of passes."
    )
