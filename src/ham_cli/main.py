"""Typer entrypoint for `ham` CLI."""

from __future__ import annotations

import typer

from src.ham_cli import __version__
from src.ham_cli.commands.api_cmd import run_api_status
from src.ham_cli.commands.desktop import (
    run_desktop_local_control_status,
    run_package_linux,
    run_package_win,
)
from src.ham_cli.commands.doctor import run_doctor
from src.ham_cli.commands.readiness import run_readiness
from src.ham_cli.commands.status import run_status
from src.ham_cli.launcher import run_interactive_menu


def _print_version(value: bool) -> None:
    if value:
        typer.echo(f"ham {__version__}")
        raise typer.Exit(code=0)


app = typer.Typer(
    help="HAM operator CLI (v1): diagnostics, status, API health, desktop packaging.",
    context_settings={"help_option_names": ["-h", "--help"]},
)


@app.callback(invoke_without_command=True)
def _root(
    ctx: typer.Context,
    _version: bool = typer.Option(
        False,
        "--version",
        "-V",
        help="Print version and exit.",
        callback=_print_version,
        is_eager=True,
    ),
) -> None:
    if ctx.invoked_subcommand is not None:
        return
    run_interactive_menu()


@app.command("doctor")
def doctor_cmd(
    json_out: bool = typer.Option(False, "--json", help="Emit JSON for automation."),
) -> None:
    """Check Python, imports, desktop tooling, optional API reachability."""
    run_doctor(json_out=json_out)


@app.command("check")
def check_cmd(
    json_out: bool = typer.Option(False, "--json", help="Emit JSON for automation."),
) -> None:
    """Friendly alias for `ham doctor` — same checks, human-oriented name."""
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


@app.command("readiness")
def readiness_cmd() -> None:
    """Checklist-style summary: Python, imports, desktop scripts, git, API (local; read-only)."""
    run_readiness()


release_app = typer.Typer(help="Shipping and release helpers.")
app.add_typer(release_app, name="release")


@release_app.command("readiness")
def release_readiness_cmd() -> None:
    """Same as `ham readiness` (for `ham release readiness`)."""
    run_readiness()


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
local_control_app = typer.Typer(
    help="Desktop Local Control read-only doctor (spec + OS; use desktop app for live IPC).",
)
desktop_app.add_typer(package_app, name="package")
desktop_app.add_typer(local_control_app, name="local-control")
app.add_typer(desktop_app, name="desktop")


@package_app.command("linux")
def desktop_pack_linux() -> None:
    """Run `npm run pack:linux` in desktop/ (AppImage + deb)."""
    run_package_linux()


@package_app.command("win")
def desktop_pack_win() -> None:
    """Run `npm run pack:win` in desktop/ (Windows portable from Linux)."""
    run_package_win()


@local_control_app.command("status")
def desktop_local_control_status_cmd(
    json_out: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
    """Show Local Control Phase 1 CLI doctor (no Electron required)."""
    run_desktop_local_control_status(json_out=json_out)


friendly_package = typer.Typer(
    help="Shorthand for `ham desktop package` — same behavior.",
)
app.add_typer(friendly_package, name="package")


@friendly_package.command("linux")
def friendly_pack_linux() -> None:
    """Alias: same as `ham desktop package linux`."""
    run_package_linux()


@friendly_package.command("win")
def friendly_pack_win() -> None:
    """Alias: same as `ham desktop package win`."""
    run_package_win()


@friendly_package.command("windows")
def friendly_pack_windows() -> None:
    """Alias: same as `ham desktop package win`."""
    run_package_win()


def main_entry() -> None:
    """Setuptools / console_scripts entry if added later."""
    app()


if __name__ == "__main__":
    app()
