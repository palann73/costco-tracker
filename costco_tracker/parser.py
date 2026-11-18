"""Turn the text of a Costco receipt into Python objects.

The parser only reads text. It never talks to the database, which keeps it
easy to test: give it a string, check what comes back.

A Costco text receipt has three parts:

1. Item lines        E   1116045   PRAWN HACAO    15.39 N
2. Savings lines     397637   /1116045   4.60-
3. Footer lines      SUBTOTAL, TAX, Total, the date line, card details...

Savings lines always point back to an item number ("/1116045"), so we attach
each discount to the item it belongs to instead of storing it as its own row.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

# --- Patterns ---------------------------------------------------------------
# Columns can be separated by tabs or by spaces depending on how the text was
# copied, so every gap is matched with \s+.

# Optional flag letter, item number, description, price, optional "-", tax code.
ITEM_LINE = re.compile(
    r"^(?:(?P<flag>[A-Z])\s+)?"      # "E" at the start of many food lines
    r"(?P<item>\d{1,9})\s+"          # Costco item number
    r"(?P<name>.+?)\s+"              # short name, may contain digits and "/"
    r"(?P<price>\d+\.\d{2})"         # price, always two decimals
    r"(?P<refund>-)?"                # a trailing minus means a return
    r"(?:\s+(?P<tax>[A-Z0-9]))?\s*$"  # tax code: N = not taxed
)

# Coupon number, "/" + the item number it applies to, amount with a minus.
SAVINGS_LINE = re.compile(
    r"^(?P<coupon>\d+)\s+/\s*(?P<item>\d+)\s+(?P<amount>\d+\.\d{2})-"
)

# Optional quantity line some receipts print for multiples, e.g. "3 @ 4.99".
QUANTITY_LINE = re.compile(r"^(?P<qty>\d+)\s*@\s*(?P<unit>\d+\.\d{2})")

# "11/17/2026 12:00 226252137752", sometimes copied with no spaces at all.
DATE_LINE = re.compile(
    r"(?P<date>\d{2}/\d{2}/\d{4})\s*(?P<time>\d{2}:\d{2})\s*(?P<code>\d{8,})"
)

MONEY = r"\$?(?P<amount>\d+\.\d{2})"
SUBTOTAL_LINE = re.compile(rf"^SUBTOTAL\s+{MONEY}", re.I)
TAX_LINE = re.compile(rf"^TAX\s+{MONEY}", re.I)
TOTAL_LINE = re.compile(rf"^\**\s*TOTAL\s+{MONEY}\s*$", re.I)
SAVINGS_TOTAL_LINE = re.compile(rf"^INSTANT SAVINGS\s+{MONEY}", re.I)
ITEM_COUNT_LINE = re.compile(r"TOTAL NUMBER OF ITEMS SOLD\s*=\s*(?P<count>\d+)", re.I)
MEMBER_LINE = re.compile(r"(Member\s*#?\s*)\d+", re.I)


# --- Data shapes ------------------------------------------------------------

@dataclass
class LineItem:
    item_number: str
    receipt_name: str
    price: Decimal               # what the shelf price added up to
    quantity: int = 1
    discount: Decimal = Decimal("0.00")
    taxable: bool = False
    flag: str | None = None

    @property
    def net(self) -> Decimal:
        """What you actually paid for this line before tax."""
        return self.price - self.discount


@dataclass
class Receipt:
    transaction_code: str | None = None
    purchased_at: datetime | None = None
    items: list[LineItem] = field(default_factory=list)
    subtotal: Decimal | None = None
    tax: Decimal | None = None
    total: Decimal | None = None
    instant_savings: Decimal | None = None
    item_count: int | None = None
    warnings: list[str] = field(default_factory=list)


# --- Parsing ----------------------------------------------------------------

def redact(text: str) -> str:
    """Remove the membership number before the raw text is stored anywhere."""
    return MEMBER_LINE.sub(r"\1[redacted]", text)


def parse_receipt(text: str) -> Receipt:
    receipt = Receipt()
    in_items = True  # everything after SUBTOTAL is footer, not items

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        if in_items:
            if m := SUBTOTAL_LINE.match(line):
                receipt.subtotal = Decimal(m["amount"])
                in_items = False
            elif m := SAVINGS_LINE.match(line):
                _apply_savings(receipt, m["item"], Decimal(m["amount"]))
            elif m := QUANTITY_LINE.match(line):
                _apply_quantity(receipt, int(m["qty"]), Decimal(m["unit"]))
            elif m := ITEM_LINE.match(line):
                receipt.items.append(_make_item(m))
            continue

        # Footer lines
        if m := TAX_LINE.match(line):
            receipt.tax = Decimal(m["amount"])
        elif m := TOTAL_LINE.match(line):
            receipt.total = Decimal(m["amount"])
        elif m := SAVINGS_TOTAL_LINE.match(line):
            receipt.instant_savings = Decimal(m["amount"])
        elif m := ITEM_COUNT_LINE.search(line):
            receipt.item_count = int(m["count"])
        elif (m := DATE_LINE.search(line)) and receipt.purchased_at is None:
            receipt.purchased_at = datetime.strptime(
                f"{m['date']} {m['time']}", "%m/%d/%Y %H:%M"
            )
            receipt.transaction_code = m["code"]

    _check(receipt)
    return receipt


def _make_item(m: re.Match) -> LineItem:
    price = Decimal(m["price"])
    quantity = 1
    if m["refund"]:
        price, quantity = -price, -1
    return LineItem(
        item_number=m["item"],
        receipt_name=m["name"].strip(),
        price=price,
        quantity=quantity,
        taxable=(m["tax"] or "N") != "N",
        flag=m["flag"],
    )


def _apply_savings(receipt: Receipt, item_number: str, amount: Decimal) -> None:
    # Attach to the most recent line with that item number.
    for item in reversed(receipt.items):
        if item.item_number == item_number:
            item.discount += amount
            return
    receipt.warnings.append(f"Savings of {amount} for item {item_number} had no matching item")


def _apply_quantity(receipt: Receipt, qty: int, unit: Decimal) -> None:
    if receipt.items and receipt.items[-1].price == unit * qty:
        receipt.items[-1].quantity = qty
    else:
        receipt.warnings.append(f"Could not place quantity line {qty} @ {unit}")


def _check(receipt: Receipt) -> None:
    """Compare what we parsed with the totals printed on the receipt."""
    if not receipt.items:
        receipt.warnings.append("No items found")
    if receipt.purchased_at is None:
        receipt.warnings.append("No date found")
    if receipt.subtotal is not None:
        parsed = sum((i.net for i in receipt.items), Decimal("0"))
        if parsed != receipt.subtotal:
            receipt.warnings.append(
                f"Items add up to {parsed} but the receipt says {receipt.subtotal}"
            )
    if receipt.item_count is not None:
        counted = sum(i.quantity for i in receipt.items)
        if counted != receipt.item_count:
            receipt.warnings.append(
                f"Counted {counted} items but the receipt says {receipt.item_count}"
            )
