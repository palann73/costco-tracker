"""Give products friendly names and categories.

Receipts only print short names like "ORG FR EGGS". Two ways to fix that:

* One at a time:   costco_tracker name 1068083 "Organic eggs" --category "Dairy & eggs"
* In bulk:         export to a CSV, fill it in with any spreadsheet app, import it back.

The CSV round trip is the friendlier option for dozens of items, and it needs
no web app yet.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from typing import IO, Iterable

import psycopg

CSV_COLUMNS = ["item_number", "receipt_name", "display_name", "category", "times_bought"]


@dataclass
class ProductUpdate:
    item_number: str
    display_name: str | None
    category: str | None


def categories(conn: psycopg.Connection) -> list[str]:
    rows = conn.execute("SELECT name FROM categories ORDER BY sort_order, name")
    return [r[0] for r in rows]


def export_csv(conn: psycopg.Connection, out: IO[str], only_missing: bool = False) -> int:
    """Write every product (most bought first) as CSV. Returns the row count."""
    sql = """
        SELECT p.item_number, p.receipt_name, p.display_name, p.category,
               count(DISTINCT li.receipt_id) AS times_bought
        FROM products p
        LEFT JOIN line_items li ON li.item_number = p.item_number
        {where}
        GROUP BY p.item_number
        ORDER BY times_bought DESC, p.receipt_name
    """.format(where="WHERE p.display_name IS NULL OR p.category IS NULL" if only_missing else "")
    writer = csv.writer(out)
    writer.writerow(CSV_COLUMNS)
    count = 0
    for row in conn.execute(sql):
        writer.writerow(["" if v is None else v for v in row])
        count += 1
    return count


def read_csv(source: IO[str], allowed_categories: Iterable[str]) -> tuple[list[ProductUpdate], list[str]]:
    """Read an edited CSV. Returns (updates, errors).

    Kept separate from the database so it can be tested with plain strings.
    Blank cells mean "leave empty". Category matching ignores upper/lower case.
    """
    by_lower = {c.lower(): c for c in allowed_categories}
    updates, errors = [], []
    for line_number, row in enumerate(csv.DictReader(source), start=2):  # line 1 is the header
        item = (row.get("item_number") or "").strip()
        if not item:
            errors.append(f"Line {line_number}: missing item_number")
            continue
        name = (row.get("display_name") or "").strip() or None
        category = (row.get("category") or "").strip() or None
        if category is not None:
            if category.lower() not in by_lower:
                errors.append(f"Line {line_number}: unknown category '{category}' for item {item}")
                continue
            category = by_lower[category.lower()]
        updates.append(ProductUpdate(item, name, category))
    return updates, errors


def apply_updates(conn: psycopg.Connection, updates: list[ProductUpdate]) -> int:
    """Save names and categories. Returns how many products changed."""
    changed = 0
    with conn.transaction():
        for u in updates:
            cur = conn.execute(
                """
                UPDATE products SET display_name = %s, category = %s
                WHERE item_number = %s
                  AND (display_name IS DISTINCT FROM %s OR category IS DISTINCT FROM %s)
                """,
                (u.display_name, u.category, u.item_number, u.display_name, u.category),
            )
            changed += cur.rowcount
    return changed


def set_one(conn: psycopg.Connection, item_number: str, display_name: str | None,
            category: str | None) -> None:
    """Update a single product; only the fields given are changed."""
    if category is not None:
        # Accept any upper/lower case, store the official spelling.
        by_lower = {c.lower(): c for c in categories(conn)}
        category = by_lower.get(category.lower(), category)
    with conn.transaction():
        cur = conn.execute(
            """
            UPDATE products
            SET display_name = coalesce(%s, display_name),
                category     = coalesce(%s, category)
            WHERE item_number = %s
            """,
            (display_name, category, item_number),
        )
        if cur.rowcount == 0:
            raise LookupError(f"No product with item number {item_number}")
