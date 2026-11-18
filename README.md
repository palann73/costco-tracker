# Costco purchase tracker

A self-hosted tool that turns Costco receipts into a searchable purchase history,
so I can see what I buy, how often, what it costs over time, and what I should
still have at home. It runs in Docker on my TrueNAS server.

## Why I built it

Costco keeps every receipt online, but only as separate pages. I wanted the data
in one place where I could ask questions like "how often do I buy eggs?" or
"has the price of chicken thighs gone up?". It was also a way to practice the
whole path from messy text to a database to dashboards, on hardware I run myself.

## How it works

```
costco.com receipt text ──► parser ──► Postgres ──► Grafana dashboards
        (copy/paste)       (Python)    (on NAS)      (charts, top items)
```

1. **Parser** (`costco_tracker/parser.py`) reads the text of one receipt and
   returns structured items. It checks its own work: the parsed items must add
   up to the receipt's subtotal, and the item count must match, or it reports a
   warning instead of saving bad data.
2. **Database** (`db/schema.sql`) stores products, receipts and line items in
   Postgres. A receipt's transaction number is unique, so importing the same
   receipt twice does nothing.
3. **Dashboards** (coming in step 3) read straight from Postgres.

## Design decisions

| Decision | Why |
|---|---|
| Postgres instead of a spreadsheet or SQLite | Grafana connects to it directly, and it runs well as a container on the NAS. |
| Parser has no database code | It can be tested with plain text, no database needed. |
| Instant savings stored on the item, not as separate rows | Each discount names the item it belongs to, so the real price paid per item is easy to query. |
| `products` table separate from `line_items` | A friendly name or category is set once and applies to every past purchase. |
| Import refuses receipts whose totals don't match | Wrong data is worse than missing data. `--force` exists for the rare exception. |
| Membership number removed before storing | The raw text is kept for re-parsing later, without personal identifiers. |

## Running it

Requirements: Docker with Compose (TrueNAS SCALE 24.10 or later works).

```bash
cp .env.example .env            # then set a real password
docker compose up -d db         # starts Postgres and creates the tables
```

Save a receipt's text from costco.com into `receipts/`, for example
`receipts/2026-11-17.txt`, then:

```bash
docker compose run --rm importer check  receipts/2026-11-17.txt   # preview only
docker compose run --rm importer import receipts/2026-11-17.txt   # save it
```

Example output:

```
2026-11-17.txt: 2026-11-17 12:00, 11 lines, total 142.31
   1116045  PRAWN HACAO             15.39  (-4.60)
      5623  BROCCOLI                 6.99
   ...
  saved as receipt 1
```

## Tests

```bash
pip install -r requirements.txt
python -m pytest
```

The tests use a real receipt (membership number replaced) in
`tests/fixtures/sample_receipt.txt`.

## Roadmap

- [x] **Step 1: record purchases.** Parse receipt text, store it in Postgres.
- [ ] **Step 2: names and categories.** Give items friendly names and categories.
- [ ] **Step 3: Grafana dashboards.** Spending by month, most bought items, price history.
- [ ] **Step 4: home inventory.** Mark items as used, see what's on hand, get "time to restock" hints.
- [ ] **Step 5: small web page** for pasting receipts instead of saving files.
- [ ] **Step 6: semi-automatic fetch.** A bookmarklet or userscript, run while
  I'm already logged in on costco.com, reads the receipt data the order
  history page loads and sends it to the receipt app. Chosen over full
  Selenium login automation: no stored password, no fighting bot detection or
  two-factor prompts, and far less likely to break when the site changes.
