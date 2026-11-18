-- Step 2: a fixed list of categories.
--
-- Categories live in their own table instead of free text so that typos like
-- "Produse" can't split one category into two on the dashboards. Adding a new
-- category is one INSERT; renaming one updates every product automatically.

CREATE TABLE categories (
    name        text PRIMARY KEY,
    sort_order  integer NOT NULL DEFAULT 100
);

INSERT INTO categories (name, sort_order) VALUES
    ('Produce',          10),
    ('Meat & seafood',   20),
    ('Dairy & eggs',     30),
    ('Bakery',           40),
    ('Frozen',           50),
    ('Pantry',           60),
    ('Snacks',           70),
    ('Beverages',        80),
    ('Prepared food',    90),
    ('Household',       100),
    ('Health & beauty', 110),
    ('Clothing',        120),
    ('Pets',            130),
    ('Other',           999);

-- Any category typed in before this step must exist in the list.
INSERT INTO categories (name)
SELECT DISTINCT category FROM products WHERE category IS NOT NULL
ON CONFLICT DO NOTHING;

ALTER TABLE products
    ADD CONSTRAINT products_category_fk
    FOREIGN KEY (category) REFERENCES categories(name) ON UPDATE CASCADE;
