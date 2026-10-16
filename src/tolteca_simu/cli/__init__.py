"""Command-line interface for tolteca_simu."""

import json
from collections.abc import Sequence
from typing import Annotated

import typer
from rich.console import Console
from tollan.config import RuntimeContext
from tollan.utils.cli import split_cli_args
from tollan.utils.typer import TollanTyper

from tolteca_simu import __version__
from tolteca_simu.core import Simu

app = TollanTyper(
    name="tolteca_simu", no_args_is_help=True, help="TolTEC observation simulator."
)
obs_planner_app = TollanTyper(
    name="obs_planner", no_args_is_help=True, help="TolTEC observation planner."
)
app.add_typer(obs_planner_app)

_RUNTIME_ARGS = {
    "allow_extra_args": True,
    "ignore_unknown_options": True,
    "allow_interspersed_args": True,
}


@obs_planner_app.command(context_settings=_RUNTIME_ARGS)
@RuntimeContext.add_cli_options()
def run(
    ctx: typer.Context,
    host: Annotated[
        str | None, typer.Option(help="Override simu.obs_planner.server.host.")
    ] = None,
    port: Annotated[
        int | None, typer.Option(help="Override simu.obs_planner.server.port.")
    ] = None,
    debug: Annotated[
        bool | None,
        typer.Option(
            "--debug/--no-debug", help="Override simu.obs_planner.server.debug."
        ),
    ] = None,
) -> None:
    """Run the planner on Dash's development server.

    Dotted settings such as --simu.obs_planner.title take precedence over the
    shorthand options.
    """
    from tolteca_simu.web.toltec_obs_planner import create_app  # noqa: PLC0415

    shorthand = []
    for field, value in (("host", host), ("port", port), ("debug", debug)):
        if value is not None:
            shorthand.extend([f"--simu.obs_planner.server.{field}", json.dumps(value)])
    runtime = _runtime(ctx, shorthand)
    server = Simu(runtime).config.obs_planner.server
    create_app(runtime).run(**server.model_dump())


@obs_planner_app.command(context_settings=_RUNTIME_ARGS)
@RuntimeContext.add_cli_options()
def show_config(ctx: typer.Context) -> None:
    """Show the resolved planner settings."""
    simu = Simu(_runtime(ctx))
    Console().print_json(data=simu.config.obs_planner.model_dump(mode="json"))


@app.command()
def version() -> None:
    """Print the installed version."""
    typer.echo(f"tolteca_simu {__version__}")


def _runtime(ctx: typer.Context, shorthand: Sequence[str] = ()) -> RuntimeContext:
    cli_args, unknown = split_cli_args(r"simu\..+", ctx.args)
    if unknown:
        msg = f"Unknown arguments: {', '.join(unknown)}"
        raise typer.BadParameter(msg)
    return RuntimeContext.from_cli_ctx(ctx, cli_args=[*shorthand, *cli_args])
