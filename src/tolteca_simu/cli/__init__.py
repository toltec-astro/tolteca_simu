"""Command-line interface for tolteca_simu."""

import typer

app = typer.Typer()


@app.command()
def main() -> None:
    """Run tolteca_simu."""
    typer.echo("This is the tolteca_simu command line.")
