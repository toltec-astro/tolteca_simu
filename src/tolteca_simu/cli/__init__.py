"""Command-line interface for tolteca_simu."""

import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal

import typer
from rich.console import Console
from tollan.config import RuntimeContext
from tollan.utils.cli import split_cli_args
from tollan.utils.typer import TollanTyper
from tollan.utils.yaml import yaml_load

from tolteca_simu import __version__
from tolteca_simu.core import Simu
from tolteca_simu.planning import ObservationDescription

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
    create_app(runtime).run(host=server.host, port=server.port, debug=server.debug)


@obs_planner_app.command(context_settings=_RUNTIME_ARGS)
@RuntimeContext.add_cli_options()
def serve(ctx: typer.Context) -> None:
    """Serve the planner with gunicorn, for production.

    The simu.obs_planner.server settings set the address, the URL path, the
    worker processes and their timeout; dotted settings override them.
    """
    from tolteca_simu.web.toltec_obs_planner.server import (  # noqa: PLC0415
        serve as serve_planner,
    )

    serve_planner(_runtime(ctx))


@obs_planner_app.command(context_settings=_RUNTIME_ARGS)
@RuntimeContext.add_cli_options()
def show_config(ctx: typer.Context) -> None:
    """Show the resolved planner settings."""
    simu = Simu(_runtime(ctx))
    Console().print_json(data=simu.config.obs_planner.model_dump(mode="json"))


@obs_planner_app.command(context_settings=_RUNTIME_ARGS)
@RuntimeContext.add_cli_options()
def plan(
    ctx: typer.Context,
    inputs: Annotated[
        list[str] | None,
        typer.Argument(
            help="Observation description (.yaml) or planner results (.ecsv).",
            show_default=False,
        ),
    ] = None,
    *,
    output_path: Annotated[
        Path, typer.Option(help="Directory to write the files to.")
    ] = Path(),
    coverage_unit: Annotated[
        Literal["depth", "time"],
        typer.Option(help="Coverage map as depth (mJy/beam) or time (s/pixel)."),
    ] = "depth",
    overwrite: Annotated[bool, typer.Option(help="Replace files that exist.")] = False,
) -> None:
    """Plan an observation and write the planner's files.

    The observation is a description in YAML, or a results file written by
    the planner, whose description is planned again. The command writes the
    LMT observing tool script, the results table and the coverage map, as the
    planner's downloads. Place the file after -- when it follows a
    multi-value option such as --config_paths.
    """
    from tolteca_simu.toltec.exports import (  # noqa: PLC0415
        make_export_files,
        read_results_metadata,
    )
    from tolteca_simu.toltec.planning import plan_observation  # noqa: PLC0415

    cli_args, paths = split_cli_args(r"simu\..+", [*(inputs or []), *ctx.args])
    paths = [path for path in paths if path != "--"]
    unknown = [path for path in paths if path.startswith("-")]
    if unknown:
        msg = f"Unknown arguments: {', '.join(unknown)}"
        raise typer.BadParameter(msg)
    if len(paths) != 1:
        msg = f"Expected one observation file, got {len(paths)}"
        raise typer.BadParameter(msg)
    path = Path(paths[0])
    if path.suffix == ".ecsv":
        description, _ = read_results_metadata(path.read_text())
    elif path.suffix in {".yaml", ".yml"}:
        description = ObservationDescription.model_validate(yaml_load(path))
    else:
        msg = f"Expected a .yaml or .ecsv file: {path}"
        raise typer.BadParameter(msg)
    simu = Simu(RuntimeContext.from_cli_ctx(ctx, cli_args=cli_args))
    files = make_export_files(
        plan_observation(description, simu.make_toltec_planner()),
        apt_path=simu.config.obs_planner.toltec.apt,
        coverage_unit=coverage_unit,
        created_at=datetime.now(UTC),
    )
    entries = [files["lmtot"], files["results"], files["coverage"]]
    existing = [
        str(output_path / name) for name, _ in entries if (output_path / name).exists()
    ]
    if existing and not overwrite:
        msg = f"Files exist (use --overwrite to replace them): {', '.join(existing)}"
        raise typer.BadParameter(msg)
    output_path.mkdir(parents=True, exist_ok=True)
    for name, content in entries:
        target = output_path / name
        if isinstance(content, bytes):
            target.write_bytes(content)
        else:
            target.write_text(content)
        typer.echo(target)


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
