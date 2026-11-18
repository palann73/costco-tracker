"""Save a parsed receipt to Postgres.

Everything for one receipt happens in a single transaction: either the whole
receipt is saved, or nothing is. A half-imported receipt would make every
total wrong, so this matters.
"""

from __future__ import annotations

import os

import psycopg

from .parser import Receipt, redact


def connect() -> psycopg.Connection:
    # DATABASE_URL looks like postgresql://user:password@host:5432/dbname
    #
    # autocommit=True: each statement is saved on its own unless it runs inside
    # `with conn.transaction():`, which then commits or rolls back as one unit.
    # Without it, psycopg silently opens a transaction on the first query and
    # nothing is saved unless we remember to call commit().
    return psycopg.connect(os.environ["DATABASE_URL"], autocommit=True)


def save_receipt(conn: psycopg.Connection, receipt: Receipt, raw_text: str) -> int | None:
    """Insert the receipt. Returns its id, or None if it was already imported."""
    if receipt.transaction_code is None or receipt.purchased_at is None:
        raise ValueError("Receipt has no date line, so it can't be saved")

    with conn.transaction(), conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO receipts (transaction_code, purchased_at, subtotal, tax, total,
                                  instant_savings, item_count, raw_text)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (transaction_code) DO NOTHING
            RETURNING id
            """,
            (receipt.transaction_code, receipt.purchased_at, receipt.subtotal,
             receipt.tax, receipt.total, receipt.instant_savings,
             receipt.item_count, redact(raw_text)),
        )
        row = cur.fetchone()
        if row is None:
            return None  # duplicate
        receipt_id = row[0]

        for line_number, item in enumerate(receipt.items, start=1):
            # Create the product the first time we see it; keep any name you set later.
            cur.execute(
                """
                INSERT INTO products (item_number, receipt_name) VALUES (%s, %s)
                ON CONFLICT (item_number) DO NOTHING
                """,
                (item.item_number, item.receipt_name),
            )
            cur.execute(
                """
                INSERT INTO line_items (receipt_id, line_number, item_number, quantity,
                                        price, discount, taxable)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (receipt_id, line_number, item.item_number, item.quantity,
                 item.price, item.discount, item.taxable),
            )
    return receipt_id
