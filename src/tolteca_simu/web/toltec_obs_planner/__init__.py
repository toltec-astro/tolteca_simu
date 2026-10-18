"""TolTEC observation planner.

Create the application from a shared configuration in Python::

    from pathlib import Path
    from tollan.config import RuntimeContext
    from tolteca_simu.web.toltec_obs_planner import create_app

    app = create_app(RuntimeContext(config_sources=Path("simu.yaml")))

Run Dash's development server, or serve it with gunicorn in production, using
the ``simu.obs_planner`` settings::

    tolteca_simu obs_planner run --config_paths simu.yaml
    tolteca_simu obs_planner serve --config_paths simu.yaml

In a deployment location, the ``tolteca_simu`` run profile provides these as
``just run tolteca_simu obs_planner`` and ``just run tolteca_simu obs_planner_serve``.

Enter a target, a start time, the LMT conditions, TolTEC settings and a mapping
preset to see the target visibility, the trajectory, the coverage and
sensitivity, and the project time; then download the LMT observing tool script,
the results for a proposal, or the coverage map. Loading a results file
reproduces its results.
"""

from .app import create_app

__all__ = ["create_app"]
