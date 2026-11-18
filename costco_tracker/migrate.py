"""Apply database changes in order, exactly once each.

Every file in db/migrations/ is one change, named with a number so they sort
in the order they were written (001_initial.sql, 002_categories.sql, ...).
The table schema_migrations records which files have already run, so running
`migrate` again only applies the new ones. This is how the database on the
NAS can be upgraded without deleting the purchases already in it.
"""

from __future__ import annotations

from pathlib import Path

import psycopg

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "db" / "migrations"


def pending(conn: psycopg.Connection, directory: Path = MIGRATIONS_DIR) -> list[Path]:
    # Committed right away, so the bookkeeping table exists even if a migration fails.
    with conn.transaction():
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                filename    text PRIMARY KEY,
                applied_at  timestamptz NOT NULL DEFAULT now()
            )
            """
        )
        done = {row[0] for row in conn.execute("SELECT filename FROM schema_migrations")}
    return [p for p in sorted(directory.glob("*.sql")) if p.name not in done]


def migrate(conn: psycopg.Connection, directory: Path = MIGRATIONS_DIR) -> list[str]:
    """Apply every pending migration. Returns the names of the files applied."""
    applied = []
    for path in pending(conn, directory):
        # One transaction per file: a failing migration leaves no half-done change.
        with conn.transaction():
            conn.execute(path.read_text())
            conn.execute("INSERT INTO schema_migrations (filename) VALUES (%s)", (path.name,))
        applied.append(path.name)
    return applied
