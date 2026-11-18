"""Tests that run against a real Postgres.

They are skipped unless TEST_DATABASE_URL points at an empty, throwaway
database, because they create and drop tables:

    TEST_DATABASE_URL=postgresql://costco:pw@localhost:5432/costco_test python -m pytest
"""

import io
import os
from decimal import Decimal
from pathlib import Path

import pytest

psycopg = pytest.importorskip("psycopg")

from costco_tracker.db import save_receipt  # noqa: E402
from costco_tracker.migrate import migrate  # noqa: E402
from costco_tracker.parser import parse_receipt  # noqa: E402
from costco_tracker.products import (  # noqa: E402
    apply_updates, categories, export_csv, read_csv, set_one)

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="TEST_DATABASE_URL not set")

SAMPLE = (Path(__file__).parent / "fixtures" / "sample_receipt.txt").read_text()


@pytest.fixture
def conn():
    # Wipe the throwaway database, then connect the same way the app does.
    with psycopg.connect(URL, autocommit=True) as admin:
        admin.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
    with psycopg.connect(URL, autocommit=True) as c:
        migrate(c)
        yield c


def test_migrate_is_saved_and_safe_to_run_twice(conn):
    with psycopg.connect(URL, autocommit=True) as fresh:  # only sees committed work
        assert migrate(fresh) == []


def test_import_once_only(conn):
    receipt = parse_receipt(SAMPLE)
    assert save_receipt(conn, receipt, SAMPLE) is not None
    assert save_receipt(conn, receipt, SAMPLE) is None
    total = conn.execute("SELECT sum(net_price) FROM line_items").fetchone()[0]
    assert total == Decimal("141.71")


def test_member_number_is_not_stored(conn):
    save_receipt(conn, parse_receipt(SAMPLE), SAMPLE.replace("000000000000", "123456789012"))
    raw = conn.execute("SELECT raw_text FROM receipts").fetchone()[0]
    assert "123456789012" not in raw


def test_csv_round_trip(conn):
    save_receipt(conn, parse_receipt(SAMPLE), SAMPLE)
    out = io.StringIO()
    assert export_csv(conn, out) == 11
    edited = out.getvalue().replace("ORG FR EGGS,,", "ORG FR EGGS,Organic eggs,Dairy & eggs")
    updates, errors = read_csv(io.StringIO(edited), categories(conn))
    assert errors == []
    assert apply_updates(conn, updates) == 1
    row = conn.execute(
        "SELECT name, category FROM item_summary WHERE item_number = '1068083'").fetchone()
    assert row == ("Organic eggs", "Dairy & eggs")
    # Only products still missing a name or category are exported with --missing.
    assert export_csv(conn, io.StringIO(), only_missing=True) == 10


def test_set_one_keeps_fields_not_given(conn):
    save_receipt(conn, parse_receipt(SAMPLE), SAMPLE)
    set_one(conn, "5623", "Broccoli", "Produce")
    set_one(conn, "5623", None, "other")  # any case is accepted
    with psycopg.connect(URL) as fresh:  # check it was really saved
        row = fresh.execute(
            "SELECT display_name, category FROM products WHERE item_number = '5623'").fetchone()
    assert row == ("Broccoli", "Other")


def test_unknown_category_rejected(conn):
    save_receipt(conn, parse_receipt(SAMPLE), SAMPLE)
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        set_one(conn, "5623", None, "Produse")
