"""Typer entrypoint for `ham` CLI."""

from __future__ import annotations

import typer

from src.ham_cli import __version__
from src.ham_cli.commands.api_cmd import run_api_status
from src.ham_cli.commands.desktop import run_package_linux, run_package_win
from src.ham_cli.commands.doctor import run_doctor
from src.ham_cli.commands.status import run_status


def _print_version(value: bool) -> None:
    if value:
        typer.echo(f"ham {__version__}")
        raise typer.Exit(code=0)


app = typer.Typer(
    help="HAM operator CLI (v1): diagnostics, status, API health, desktop packaging.",
    context_settings={"help_option_names": ["-h", "--help"]},
)


@app.callback()
def _root(
    _version: bool = typer.Option(
        False,
        "--version",
        "-V",
        help="Print version and exit.",
        callback=_print_version,
        is_eager=True,
    ),
) -> None:
    pass


@app.command("doctor")
def doctor_cmd(
    json_out: bool = typer.Option(False, "--json", help="Emit JSON for automation."),
) -> None:
    """Check Python, imports, desktop tooling, optional API reachability."""
    run_doctor(json_out=json_out)


@app.command("status")
def status_cmd(
    json_out: bool = typer.Option(False, "--json", help="Emit JSON for automation."),
    api_base: str | None = typer.Option(
        None,
        "--api-base",
        help="Override HAM_API_BASE for remote section only.",
    ),
) -> None:
    """Local repo/run summary; remote /api/status when HAM_API_BASE (or --api-base) is set."""
    run_status(json_out=json_out, api_base=api_base)


api_app = typer.Typer(help="Call Ham HTTP API (thin client; no duplicated server logic).")
app.add_typer(api_app, name="api")


@api_app.command("status")
def api_status_cmd(
    json_out: bool = typer.Option(False, "--json", help="Emit JSON."),
    base: str | None = typer.Option(
        None,
        "--base",
        help="API origin (default: HAM_API_BASE). No trailing slash; no /api suffix.",
    ),
) -> None:
    """GET /api/status from the configured Ham API."""
    run_api_status(json_out=json_out, base=base)


desktop_app = typer.Typer(help="Desktop shell packaging (wraps npm/electron-builder).")
package_app = typer.Typer(help="Build desktop artifacts from this repo.")
desktop_app.add_typer(package_app, name="package")
app.add_typer(desktop_app, name="desktop")


@package_app.command("linux")
def desktop_pack_linux() -> None:
    """Run `npm run pack:linux` in desktop/ (AppImage + deb)."""
    run_package_linux()


@package_app.command("win")
def desktop_pack_win() -> None:
    """Run `npm run pack:win` in desktop/ (Windows portable from Linux)."""
    run_package_win()


def main_entry() -> None:
    """Setuptools / console_scripts entry if added later."""
    app()


if __name__ == "__main__":
    app()
