from typer.testing import CliRunner

from tolteca_simu.cli import app


def test_cli() -> None:
    result = CliRunner().invoke(app)
    assert result.exit_code == 0
