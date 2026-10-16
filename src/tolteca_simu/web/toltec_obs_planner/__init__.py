"""TolTEC observation planner.

Create the application from a shared configuration in Python::

    from pathlib import Path
    from tollan.config import RuntimeContext
    from tolteca_simu.web.toltec_obs_planner import create_app

    app = create_app(RuntimeContext(config_sources=Path("simu.yaml")))

Or run the development server with the ``simu.obs_planner`` settings::

    tolteca_simu obs_planner run --config_paths simu.yaml

Enter a target name or coordinate and an observation date and start time to see
the target elevation over that UT day.
"""

from .app import create_app

__all__ = ["create_app"]
