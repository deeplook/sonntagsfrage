"""Shared Typer configuration for the project commands."""

import typer


def create_app(help_text: str | None) -> typer.Typer:
    return typer.Typer(
        help=help_text,
        add_completion=False,
        context_settings={"help_option_names": ["-h", "--help"]},
    )


def fail(message: str, exit_code: int = 1) -> None:
    typer.echo(f"error: {message}", err=True)
    raise typer.Exit(exit_code)
