"""Simulation settings from a shared runtime configuration.

Read the ``simu`` section of a configuration::

    from pathlib import Path
    from tollan.config import RuntimeContext
    from tolteca_simu.core import Simu

    simu = Simu(RuntimeContext(config_sources=Path("simu.yaml")))
    simu.config.obs_planner.title

Construction validates the settings; it opens no files and starts no server.
`Simu.make_toltec_planner` builds the planning objects the settings describe.
"""

from typing import Literal

from tollan.config import ConfigHandler, SubConfigKeyTransformer

from .cal_data import CalDataStore
from .config import SimuConfig
from .toltec.planning import ToltecPlanner

__all__ = ["Simu"]


class Simu(SubConfigKeyTransformer[Literal["simu"]], ConfigHandler[SimuConfig]):
    """Validated ``simu`` settings of a runtime configuration."""

    def make_toltec_planner(self) -> ToltecPlanner:
        """Return the TolTEC planner of the ``simu.obs_planner`` settings.

        Returns
        -------
        tolteca_simu.toltec.planning.ToltecPlanner
            Planning with the calibration data store, array property table,
            LMT surface RMS and detector noise factors of the settings.
        """
        config = self.config.obs_planner
        return ToltecPlanner(
            CalDataStore(config.cal_data_path),
            apt_path=config.toltec.apt,
            tel_surface_rms=config.lmt.tel_surface_rms,
            det_noise_factors=config.toltec.det_noise_factors,
        )
