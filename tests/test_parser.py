from datetime import datetime
from decimal import Decimal
from pathlib import Path

from costco_tracker.parser import parse_receipt, redact

SAMPLE = (Path(__file__).parent / "fixtures" / "sample_receipt.txt").read_text()


def test_reads_header_and_totals():
    r = parse_receipt(SAMPLE)
    assert r.purchased_at == datetime(2026, 11, 17, 12, 0)
    assert r.transaction_code == "226252137752"
    assert r.subtotal == Decimal("141.71")
    assert r.tax == Decimal("0.60")
    assert r.total == Decimal("142.31")
    assert r.instant_savings == Decimal("13.40")
    assert r.item_count == 11


def test_reads_every_item():
    r = parse_receipt(SAMPLE)
    assert len(r.items) == 11
    first = r.items[0]
    assert (first.item_number, first.receipt_name, first.price) == (
        "1116045", "PRAWN HACAO", Decimal("15.39"))
    assert r.items[-1].receipt_name == "RAO'S 2/31.7"  # digits and "/" in a name


def test_savings_attach_to_their_item():
    r = parse_receipt(SAMPLE)
    by_number = {i.item_number: i for i in r.items}
    assert by_number["1116045"].discount == Decimal("4.60")
    assert by_number["306221"].discount == Decimal("1.50")  # "/ 306221" with a space
    assert sum(i.discount for i in r.items) == r.instant_savings


def test_tax_codes():
    r = parse_receipt(SAMPLE)
    taxed = [i.receipt_name for i in r.items if i.taxable]
    assert taxed == ["GAP JOGGER"]


def test_totals_match_so_no_warnings():
    assert parse_receipt(SAMPLE).warnings == []


def test_space_separated_copy_works_too():
    r = parse_receipt(SAMPLE.replace("\t", "   "))
    assert len(r.items) == 11 and r.warnings == []


def test_missing_line_is_reported():
    broken = SAMPLE.replace("E\t5623\tBROCCOLI\t6.99 N\n", "")
    warnings = parse_receipt(broken).warnings
    assert any("add up" in w for w in warnings)
    assert any("Counted 10" in w for w in warnings)


def test_return_line_is_negative():
    r = parse_receipt("E 5623 BROCCOLI 6.99- N\nSUBTOTAL 6.99-\n")
    assert r.items[0].quantity == -1 and r.items[0].price == Decimal("-6.99")


def test_redact_member_number():
    assert redact("Member 111122223333\nE 1 X 1.00 N") == "Member [redacted]\nE 1 X 1.00 N"
