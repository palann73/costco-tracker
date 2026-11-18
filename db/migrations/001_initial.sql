-- Costco purchase tracker: step 1 schema (recording purchases).
--
-- Three tables:
--   products    one row per Costco item number (the "what")
--   receipts    one row per shopping trip      (the "when")
--   line_items  what was bought on each trip   (joins the two)
--
-- Keeping products separate means a friendly name or category only has to be
-- set once, and every past and future purchase of that item picks it up.

CREATE TABLE IF NOT EXISTS products (
    item_number   text PRIMARY KEY,          -- Costco's own item number
    receipt_name  text NOT NULL,             -- short name as printed, e.g. "ORG FR EGGS"
    display_name  text,                      -- your name for it, e.g. "Organic eggs"
    category      text,                      -- e.g. "Dairy & eggs"
    created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS receipts (
    id                serial PRIMARY KEY,
    transaction_code  text NOT NULL UNIQUE,  -- stops the same receipt being imported twice
    purchased_at      timestamp NOT NULL,
    subtotal          numeric(10,2),
    tax               numeric(10,2),
    total             numeric(10,2),
    instant_savings   numeric(10,2),
    item_count        integer,
    raw_text          text,                  -- original text, member number removed
    imported_at       timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS line_items (
    id            serial PRIMARY KEY,
    receipt_id    integer NOT NULL REFERENCES receipts(id) ON DELETE CASCADE,
    line_number   integer NOT NULL,          -- order on the receipt
    item_number   text NOT NULL REFERENCES products(item_number),
    quantity      integer NOT NULL DEFAULT 1, -- negative for a return
    price         numeric(10,2) NOT NULL,     -- before instant savings
    discount      numeric(10,2) NOT NULL DEFAULT 0,
    net_price     numeric(10,2) GENERATED ALWAYS AS (price - discount) STORED,
    taxable       boolean NOT NULL DEFAULT false,
    UNIQUE (receipt_id, line_number)
);

CREATE INDEX IF NOT EXISTS line_items_item_number_idx ON line_items (item_number);
CREATE INDEX IF NOT EXISTS receipts_purchased_at_idx ON receipts (purchased_at);

-- A ready-made answer to "what do I buy most often?"
CREATE OR REPLACE VIEW item_summary AS
SELECT
    p.item_number,
    coalesce(p.display_name, p.receipt_name)  AS name,
    p.category,
    count(DISTINCT li.receipt_id)              AS times_bought,
    sum(li.quantity)                           AS units_bought,
    sum(li.net_price)                          AS total_spent,
    min(r.purchased_at)::date                  AS first_bought,
    max(r.purchased_at)::date                  AS last_bought
FROM products p
JOIN line_items li ON li.item_number = p.item_number
JOIN receipts r    ON r.id = li.receipt_id
GROUP BY p.item_number;
