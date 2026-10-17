"""Simulation settings under the ``simu`` root key."""

import astropy.units as u
from pydantic import ConfigDict, Field
from tollan.config import FrozenBaseModel
from tollan.config.types import (
    AbsDirectoryPath,
    AbsFilePath,
    AngleQuantityField,
    LengthQuantityField,
    TimeQuantityField,
)

from tolteca_simu.lmt import LmtAtmModelName
from tolteca_simu.planning.presets import get_default_presets_path
from tolteca_simu.toltec.info import ToltecArrayName

__all__ = [
    "LmtPlannerConfig",
    "ObsPlannerConfig",
    "ObsPlannerServerConfig",
    "SimuConfig",
    "ToltecPlannerConfig",
]

# Production planner settings (unity-toltec4, revision 20250303.0).
_TOLTEC_APT = "toltec/apt/apt_GW_v8_with_fg_pg_loc_ori_flipped_flag_fixed.ecsv"
_TOLTEC_DET_NOISE_FACTORS: dict[LmtAtmModelName, dict[ToltecArrayName, float]] = {
    "am_q25": {"a1100": 2.0, "a1400": 2.0, "a2000": 2.0},
    "am_q50": {"a1100": 2.19, "a1400": 2.19, "a2000": 2.19},
    "am_q75": {"a1100": 2.34, "a1400": 2.34, "a2000": 2.34},
}


class ObsPlannerServerConfig(FrozenBaseModel):
    """Address and mode of the planner's development server."""

    model_config = ConfigDict(extra="forbid")
    host: str = Field(default="127.0.0.1", description="Server bind address.")
    port: int = Field(default=8054, ge=1, le=65535, description="Server port.")
    debug: bool = Field(default=False, description="Enable Dash development mode.")


class LmtPlannerConfig(FrozenBaseModel):
    """LMT settings of the planner."""

    model_config = ConfigDict(extra="forbid")
    tel_surface_rms: LengthQuantityField = Field(
        default=100 << u.um,
        description="RMS of the primary surface; defaults to the production value.",
    )


class ToltecPlannerConfig(FrozenBaseModel):
    """TolTEC settings of the planner."""

    model_config = ConfigDict(extra="forbid")
    apt: str = Field(
        default=_TOLTEC_APT,
        description="Array property table of the enabled detectors, relative to "
        "the calibration data store; defaults to the production table.",
    )
    det_noise_factors: dict[LmtAtmModelName, dict[ToltecArrayName, float]] = Field(
        default_factory=lambda: _TOLTEC_DET_NOISE_FACTORS,
        description="Detector noise factor by atmosphere model and array; "
        "defaults to the production values.",
    )


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
    t_exp_max: TimeQuantityField = Field(
        default=1 << u.h, description="Longest pattern a raster-like preset may take."
    )
    presets_path: AbsFilePath = Field(
        default_factory=get_default_presets_path,
        description="Mapping presets file; defaults to the packaged presets.",
    )
    cal_data_path: AbsDirectoryPath = Field(
        description="Root of the calibration data store."
    )
    lmt: LmtPlannerConfig = Field(
        default_factory=LmtPlannerConfig, description="LMT settings."
    )
    toltec: ToltecPlannerConfig = Field(
        default_factory=ToltecPlannerConfig, description="TolTEC settings."
    )
    server: ObsPlannerServerConfig = Field(
        default_factory=ObsPlannerServerConfig, description="Server launch settings."
    )


class SimuConfig(FrozenBaseModel):
    """Simulation settings under the ``simu`` root key."""

    model_config = ConfigDict(extra="forbid")
    obs_planner: ObsPlannerConfig = Field(description="Observation planner settings.")
