import io

from costco_tracker.products import ProductUpdate, read_csv

CATEGORIES = ["Produce", "Dairy & eggs", "Clothing"]


def read(text):
    return read_csv(io.StringIO(text), CATEGORIES)


def test_reads_names_and_categories():
    updates, errors = read(
        "item_number,receipt_name,display_name,category,times_bought\n"
        "1068083,ORG FR EGGS,Organic eggs,dairy & EGGS,3\n"
        "5623,BROCCOLI,,Produce,1\n"
    )
    assert errors == []
    assert updates == [
        ProductUpdate("1068083", "Organic eggs", "Dairy & eggs"),  # case fixed
        ProductUpdate("5623", None, "Produce"),                    # blank name stays empty
    ]


def test_unknown_category_is_an_error_with_line_number():
    updates, errors = read(
        "item_number,display_name,category\n"
        "5623,Broccoli,Produse\n"
    )
    assert updates == []
    assert errors == ["Line 2: unknown category 'Produse' for item 5623"]


def test_missing_item_number():
    _, errors = read("item_number,display_name,category\n,Eggs,Produce\n")
    assert errors == ["Line 2: missing item_number"]
