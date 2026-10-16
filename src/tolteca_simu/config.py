"""Simulation settings under the ``simu`` root key."""

import astropy.units as u
from pydantic import ConfigDict, Field
from tollan.config import FrozenBaseModel
from tollan.config.types import AngleQuantityField

__all__ = ["ObsPlannerConfig", "ObsPlannerServerConfig", "SimuConfig"]


class ObsPlannerServerConfig(FrozenBaseModel):
    """Address and mode of the planner's development server."""

    model_config = ConfigDict(extra="forbid")
    host: str = Field(default="127.0.0.1", description="Server bind address.")
    port: int = Field(default=8054, ge=1, le=65535, description="Server port.")
    debug: bool = Field(default=False, description="Enable Dash development mode.")


class ObsPlannerConfig(FrozenBaseModel):
    """TolTEC observation planner settings."""

    model_config = ConfigDict(extra="forbid")
    title: str = Field(
        default="TolTEC Observation Planner", description="Page and header title."
    )
    subtitle: str = Field(
        default="", description="Header text after the title, such as a revision."
    )
    target_alt_min: AngleQuantityField = Field(
        default=20 << u.deg, description="Lowest usable target elevation."
    )
    server: ObsPlannerServerConfig = Field(
        default_factory=ObsPlannerServerConfig, description="Server launch settings."
    )


class SimuConfig(FrozenBaseModel):
    """Simulation settings under the ``simu`` root key."""

    model_config = ConfigDict(extra="forbid")
    obs_planner: ObsPlannerConfig = Field(
        default_factory=ObsPlannerConfig, description="Observation planner settings."
    )
