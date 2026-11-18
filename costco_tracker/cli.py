"""Command line entry point.

    python -m costco_tracker.cli check  receipts/2026-11-17.txt   # parse only, no database
    python -m costco_tracker.cli import receipts/*.txt            # parse and save
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .parser import Receipt, parse_receipt


def show(path: Path, receipt: Receipt) -> None:
    when = receipt.purchased_at.strftime("%Y-%m-%d %H:%M") if receipt.purchased_at else "?"
    print(f"\n{path.name}: {when}, {len(receipt.items)} lines, total {receipt.total}")
    for item in receipt.items:
        saving = f"  (-{item.discount})" if item.discount else ""
        print(f"  {item.item_number:>8}  {item.receipt_name:<20} {item.price:>8}{saving}")
    for warning in receipt.warnings:
        print(f"  WARNING: {warning}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="costco_tracker")
    ap.add_argument("command", choices=["check", "import"])
    ap.add_argument("files", nargs="+", type=Path)
    ap.add_argument("--force", action="store_true", help="import even if totals don't match")
    args = ap.parse_args(argv)

    conn = None
    if args.command == "import":
        from .db import connect, save_receipt
        conn = connect()

    failed = 0
    for path in args.files:
        text = path.read_text()
        receipt = parse_receipt(text)
        show(path, receipt)
        if conn is None:
            continue
        if receipt.warnings and not args.force:
            print("  skipped: fix the warnings above or use --force")
            failed += 1
            continue
        receipt_id = save_receipt(conn, receipt, text)
        print(f"  saved as receipt {receipt_id}" if receipt_id else "  already imported")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
