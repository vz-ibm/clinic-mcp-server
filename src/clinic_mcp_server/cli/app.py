from __future__ import annotations

from pathlib import Path

import typer

from clinic_mcp_server.domain.default_values import DEFAULT_DB_PATH
from clinic_mcp_server.infra.sqlite_repo import SQLiteClinicRepository
from clinic_mcp_server.runtime.runner import McpRunner
from clinic_mcp_server.runtime.settings import ServerSettings
from clinic_mcp_server.tools.clinic_server import mcp as clinic_mcp

app = typer.Typer(add_completion=False)


@app.command("reset-db")
def reset_db(
    db_path: str = typer.Option(
        DEFAULT_DB_PATH,
        "--db-path",
        envvar="CLINIC_DB_PATH",
        help="Path to SQLite DB file (can also be set via CLINIC_DB_PATH).",
    ),
    seed: bool = typer.Option(True, "--seed/--no-seed", help="Seed demo data after reset."),
    force: bool = typer.Option(False, "--force", "-f", help="Do not prompt for confirmation."),
) -> None:
    p = Path(db_path)

    if p.exists() and not force:
        confirm = typer.confirm(f"Reset schema in DB at: {p.resolve()} ?")
        if not confirm:
            typer.echo("Canceled.")
            raise typer.Exit(code=1)

    repo = SQLiteClinicRepository(db_path=db_path)
    repo.reset_database(seed=seed)  # <-- now does DROP+CREATE, not delete file

    typer.echo("✅ Database reset complete.")
    typer.echo(f"DB path: {p.resolve()}")

@app.command()
def run(
    transport: str = typer.Option("streamable-http"),
    host: str = typer.Option("127.0.0.1"),
    port: int = typer.Option(8080),
) -> None:
    transport = transport.strip().lower()
    if transport not in {"stdio", "sse", "streamable-http"}:
        raise typer.BadParameter("transport must be one of: stdio | sse | streamable-http")


    settings = ServerSettings.load(transport=transport, host=host, port=port)
    McpRunner(clinic_mcp).run(settings)
