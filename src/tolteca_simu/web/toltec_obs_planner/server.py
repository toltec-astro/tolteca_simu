"""Production serving of the planner with gunicorn."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from gunicorn.app.base import BaseApplication

from tolteca_simu.core import Simu

from .app import create_app

if TYPE_CHECKING:
    from flask import Flask
    from gunicorn.config import Config
    from tollan.config import RuntimeContext

__all__ = ["PlannerServer", "serve"]


class PlannerServer(BaseApplication):
    """Gunicorn application serving a planner's Flask server.

    Parameters
    ----------
    application : flask.Flask
        The Dash application's server.
    options : dict
        Gunicorn settings, such as ``bind``, ``workers`` and ``timeout``.
    """

    def __init__(self, application: Flask, options: dict[str, Any]) -> None:
        self._application = application
        self._options = options
        super().__init__()

    def load_config(self) -> None:
        """Apply the settings given at construction."""
        # Gunicorn creates the configuration before calling this method.
        cfg = cast("Config", self.cfg)
        for key, value in self._options.items():
            cfg.set(key, value)

    def load(self) -> Flask:
        """Return the Flask server.

        Returns
        -------
        flask.Flask
            The application each worker serves.
        """
        return self._application


def serve(runtime: RuntimeContext) -> None:
    """Serve the planner with gunicorn until interrupted.

    The application is created once and shared by the forked workers; each
    worker builds its loading models when first used.

    Parameters
    ----------
    runtime : tollan.config.RuntimeContext
        Runtime supplying the ``simu.obs_planner`` settings.
    """
    server = Simu(runtime).config.obs_planner.server
    options = {
        "bind": f"{server.host}:{server.port}",
        "workers": server.workers,
        "timeout": server.timeout,
    }
    PlannerServer(create_app(runtime).server, options).run()
