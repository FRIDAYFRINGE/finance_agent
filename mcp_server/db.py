"""Database connection helper for the MCP Tool Server.

Opens the SQLite database in **read-only** mode so the MCP server can never
accidentally mutate the data.  Provides a singleton-ish helper that tool
modules can import.
"""

import sqlite3
from pathlib import Path

from mcp_server.config import DEFAULT_DB_PATH


def get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    """Return a read-only SQLite connection with Row factory enabled.

    Args:
        db_path: Override path to the database file.  Defaults to
                 ``config.DEFAULT_DB_PATH``.

    Returns:
        A ``sqlite3.Connection`` in read-only mode with ``row_factory``
        set to ``sqlite3.Row`` for dict-like access.

    Raises:
        FileNotFoundError: If the database file does not exist.
        sqlite3.OperationalError: If the connection cannot be opened.
    """
    path = db_path or DEFAULT_DB_PATH
    if not path.exists():
        raise FileNotFoundError(f"Database not found at {path}. Run scripts/build_db.py first.")

    # Open in read-only mode using URI filename syntax
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def row_to_dict(row: sqlite3.Row) -> dict:
    """Convert a sqlite3.Row to a plain dict (JSON-serialisable)."""
    return dict(row)


def rows_to_list(rows: list[sqlite3.Row]) -> list[dict]:
    """Convert a list of sqlite3.Row objects to a list of plain dicts."""
    return [dict(r) for r in rows]
