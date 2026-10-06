import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional, Sequence


DATABASE_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "insurance_claims.db"
)


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    """Yield a configured SQLite connection and close it after use.

    Transactions are committed on success and rolled back if an operation fails.
    """
    if not DATABASE_PATH.is_file():
        raise FileNotFoundError(f"SQLite database not found: {DATABASE_PATH}")

    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")

    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def fetch_all(
    query: str, parameters: Sequence[object] = ()
) -> list[sqlite3.Row]:
    """Execute a parameterized query and return all matching rows."""
    with get_connection() as connection:
        return connection.execute(query, parameters).fetchall()


def fetch_one(
    query: str, parameters: Sequence[object] = ()
) -> Optional[sqlite3.Row]:
    """Execute a parameterized query and return one row, or None."""
    with get_connection() as connection:
        return connection.execute(query, parameters).fetchone()


def execute_query(
    query: str, parameters: Sequence[object] = ()
) -> tuple[Optional[int], int]:
    """Execute a parameterized write query and return (last row ID, row count)."""
    with get_connection() as connection:
        cursor = connection.execute(query, parameters)
        return cursor.lastrowid, cursor.rowcount
