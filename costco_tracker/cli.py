"""Command line entry point.

    python -m costco_tracker.cli migrate                          # create or upgrade tables
    python -m costco_tracker.cli check  receipts/2026-11-17.txt   # parse only, no database
    python -m costco_tracker.cli import receipts/*.txt            # parse and save
    python -m costco_tracker.cli categories                       # list allowed categories
    python -m costco_tracker.cli name 1068083 "Organic eggs" --category "Dairy & eggs"
    python -m costco_tracker.cli export-products products.csv [--missing]
    python -m costco_tracker.cli import-products products.csv
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


def cmd_check(args, conn) -> int:
    for path in args.files:
        show(path, parse_receipt(path.read_text()))
    return 0


def cmd_import(args, conn) -> int:
    from .db import save_receipt

    failed = 0
    for path in args.files:
        text = path.read_text()
        receipt = parse_receipt(text)
        show(path, receipt)
        if receipt.warnings and not args.force:
            print("  skipped: fix the warnings above or use --force")
            failed += 1
            continue
        receipt_id = save_receipt(conn, receipt, text)
        print(f"  saved as receipt {receipt_id}" if receipt_id else "  already imported")
    return 1 if failed else 0


def cmd_migrate(args, conn) -> int:
    from .migrate import migrate

    applied = migrate(conn)
    print("Applied: " + ", ".join(applied) if applied else "Database is up to date")
    return 0


def cmd_categories(args, conn) -> int:
    from .products import categories

    print("\n".join(categories(conn)))
    return 0


def cmd_name(args, conn) -> int:
    import psycopg

    from .products import set_one

    try:
        set_one(conn, args.item_number, args.display_name, args.category)
    except LookupError as e:
        print(e)
        return 1
    except psycopg.errors.ForeignKeyViolation:
        print(f"Unknown category '{args.category}'. Run 'categories' to see the list.")
        return 1
    print(f"Updated {args.item_number}")
    return 0


def cmd_export_products(args, conn) -> int:
    from .products import export_csv

    with open(args.file, "w", newline="") as out:
        count = export_csv(conn, out, only_missing=args.missing)
    print(f"Wrote {count} products to {args.file}")
    return 0


def cmd_import_products(args, conn) -> int:
    from .products import apply_updates, categories, read_csv

    with open(args.file, newline="") as source:
        updates, errors = read_csv(source, categories(conn))
    for error in errors:
        print(f"ERROR: {error}")
    if errors:
        print("Nothing saved. Fix the lines above and run it again.")
        return 1
    print(f"Updated {apply_updates(conn, updates)} products")
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="costco_tracker")
    sub = ap.add_subparsers(dest="command", required=True)

    sub.add_parser("migrate", help="create or upgrade the database tables")

    p = sub.add_parser("check", help="parse receipts without saving")
    p.add_argument("files", nargs="+", type=Path)

    p = sub.add_parser("import", help="parse receipts and save them")
    p.add_argument("files", nargs="+", type=Path)
    p.add_argument("--force", action="store_true", help="import even if totals don't match")

    sub.add_parser("categories", help="list the allowed categories")

    p = sub.add_parser("name", help="set one product's name and/or category")
    p.add_argument("item_number")
    p.add_argument("display_name", nargs="?")
    p.add_argument("--category")

    p = sub.add_parser("export-products", help="write products to a CSV for editing")
    p.add_argument("file", type=Path)
    p.add_argument("--missing", action="store_true", help="only products without a name or category")

    p = sub.add_parser("import-products", help="read names and categories back from the CSV")
    p.add_argument("file", type=Path)
    return ap


COMMANDS = {
    "migrate": cmd_migrate,
    "check": cmd_check,
    "import": cmd_import,
    "categories": cmd_categories,
    "name": cmd_name,
    "export-products": cmd_export_products,
    "import-products": cmd_import_products,
}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    conn = None
    if args.command != "check":  # every other command needs the database
        from .db import connect
        conn = connect()
    return COMMANDS[args.command](args, conn)


if __name__ == "__main__":
    sys.exit(main())
