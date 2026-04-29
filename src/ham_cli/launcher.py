"""Interactive operator menu when `ham` is run with no subcommand."""

from __future__ import annotations

import sys

import typer

from src.ham_cli.commands.api_cmd import run_api_status
from src.ham_cli.commands.desktop import run_package_win
from src.ham_cli.commands.doctor import run_doctor
from src.ham_cli.commands.readiness import run_readiness
from src.ham_cli.commands.status import run_status
from src.ham_cli.util import get_api_base


def _pause() -> None:
    try:
        input("\nPress Enter to return to the menu… ")
    except EOFError:
        pass


def _confirm(message: str) -> bool:
    try:
        ans = input(f"{message} [y/N] ").strip().lower()
    except EOFError:
        return False
    return ans in ("y", "yes")


def run_interactive_menu() -> None:
    while True:
        print()
        print("HAM operator launcher")
        print("—" * 44)
        print("Pick a number. Each option runs the same checks as the expert CLI.\n")
        print("  1  Check HAM health          (Python, imports, desktop tooling, optional API)")
        print("  2  Show HAM status          (local summary; remote if HAM_API_BASE is set)")
        print("  3  Check API connection     (GET /api/status — needs HAM_API_BASE)")
        print("  4  Package Windows desktop (npm run pack:win in desktop/)")
        print("  5  Show release readiness   (checklist: git, scripts, API, …)")
        print("  6  Exit")
        print()
        try:
            choice = input("Choose [1–6]: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            raise typer.Exit(code=0) from None

        if choice == "6":
            raise typer.Exit(code=0)
        if choice == "1":
            try:
                run_doctor(json_out=False)
            except typer.Exit:
                pass
            _pause()
        elif choice == "2":
            try:
                run_status(json_out=False, api_base=None)
            except typer.Exit:
                pass
            _pause()
        elif choice == "3":
            base = get_api_base()
            if not base:
                print(
                    "HAM_API_BASE is not set. Export your API origin (no /api suffix), e.g.\n"
                    "  export HAM_API_BASE=https://your-ham-api.example\n"
                    "Expert: ham api status --base <url>",
                    file=sys.stderr,
                )
            else:
                try:
                    run_api_status(json_out=False, base=None)
                except typer.Exit:
                    pass
            _pause()
        elif choice == "4":
            if _confirm("Run Windows desktop packaging now?"):
                try:
                    run_package_win()
                except typer.Exit:
                    pass
            _pause()
        elif choice == "5":
            try:
                run_readiness()
            except typer.Exit:
                pass
            _pause()
        elif choice in ("",):
            continue
        else:
            print("Unknown choice. Enter a number from 1 to 6.", file=sys.stderr)
