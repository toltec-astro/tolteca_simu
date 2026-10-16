"""Simulation settings from a shared runtime configuration.

Read the ``simu`` section of a configuration::

    from pathlib import Path
    from tollan.config import RuntimeContext
    from tolteca_simu.core import Simu

    simu = Simu(RuntimeContext(config_sources=Path("simu.yaml")))
    simu.config.obs_planner.title

Construction validates the settings; it opens no files and starts no server.
"""

from typing import Literal

from tollan.config import ConfigHandler, SubConfigKeyTransformer

from .config import SimuConfig

__all__ = ["Simu"]


class Simu(SubConfigKeyTransformer[Literal["simu"]], ConfigHandler[SimuConfig]):
    """Validated ``simu`` settings of a runtime configuration."""
