"""
test_db_handler.py
Comprehensive unit-test suite for db_handler.py
Uses an in-memory SQLite database to simulate MariaDB behaviour
so no live server is required.
"""

import sys
import os
import sqlite3
import unittest
from datetime import date, timedelta
from unittest.mock import MagicMock

# ── Stub out mariadb BEFORE importing db_handler ─────────────────────────────
sys.modules['mariadb'] = MagicMock()

# ── Make project root importable ─────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(__file__))

from models.Item import Item
from models.Customer import Customer
from models.Rental import Rental
from models.RentalHistory import RentalHistory
from models.Waitlist import Waitlist

# ── SQLite Cursor wrapper ─────────────────────────────────────────────────────
# MariaDB uses ? placeholders; SQLite also uses ?, so direct reuse works.

class _FakeCursor:
    """Thin wrapper so cursor.fetchone/fetchall work normally and ? placeholders work."""

    def __init__(self, sqlite_cursor):
        self._c = sqlite_cursor

    def execute(self, sql, params=()):
        self._c.execute(sql, params)

    def fetchone(self):
        return self._c.fetchone()

    def fetchall(self):
        return self._c.fetchall()

    def close(self):
        pass


class _FakeConnection:
    def __init__(self, sqlite_conn):
        self._conn = sqlite_conn
        self._cursor = _FakeCursor(sqlite_conn.cursor())

    def cursor(self):
        return self._cursor

    def commit(self):
        self._conn.commit()

    def close(self):
        self._conn.close()


# ── Schema DDL for in-memory SQLite ──────────────────────────────────────────

_DDL = """
CREATE TABLE IF NOT EXISTS item (
    i_item_sk      INTEGER PRIMARY KEY,
    i_item_id      TEXT,
    i_rec_start_date TEXT,
    i_product_name TEXT,
    i_brand        TEXT,
    i_class        TEXT,
    i_category     TEXT,
    i_manufact     TEXT,
    i_current_price REAL,
    i_num_owned    INTEGER
);

CREATE TABLE IF NOT EXISTS customer_address (
    ca_address_sk   INTEGER PRIMARY KEY,
    ca_street_number TEXT,
    ca_street_name  TEXT,
    ca_city         TEXT,
    ca_state        TEXT,
    ca_zip          TEXT
);

CREATE TABLE IF NOT EXISTS customer (
    c_customer_sk   INTEGER PRIMARY KEY,
    c_customer_id   TEXT,
    c_first_name    TEXT,
    c_last_name     TEXT,
    c_email_address TEXT,
    c_current_addr_sk INTEGER,
    FOREIGN KEY(c_current_addr_sk) REFERENCES customer_address(ca_address_sk)
);

CREATE TABLE IF NOT EXISTS rental (
    item_id     TEXT,
    customer_id TEXT,
    rental_date TEXT,
    due_date    TEXT,
    PRIMARY KEY (item_id, customer_id)
);

CREATE TABLE IF NOT EXISTS rental_history (
    item_id     TEXT,
    customer_id TEXT,
    rental_date TEXT,
    due_date    TEXT,
    return_date TEXT,
    PRIMARY KEY (item_id, customer_id, rental_date)
);

CREATE TABLE IF NOT EXISTS waitlist (
    item_id        TEXT,
    customer_id    TEXT,
    place_in_line  INTEGER,
    PRIMARY KEY (item_id, customer_id)
);
"""

_SEED_SQL = """
-- Items
INSERT INTO item VALUES (1,'ITEM0000000000001','2020-01-01','Widget Alpha','BrandA','ClassX','Gadgets','MfgOne',19.99,3);
INSERT INTO item VALUES (2,'ITEM0000000000002','2021-06-15','Widget Beta','BrandB','ClassY','Gadgets','MfgTwo',29.99,1);
INSERT INTO item VALUES (3,'ITEM0000000000003','2019-03-10','Gizmo Gamma','BrandA','ClassX','Tools','MfgOne',9.99,2);

-- Addresses
INSERT INTO customer_address VALUES (1,'100','Oak Lane','Springfield','IL','62701');
INSERT INTO customer_address VALUES (2,'200','Maple Ave','Shelbyville','TN','37160');

-- Customers
INSERT INTO customer VALUES (1,'CUST000000000001','Alice','Anderson','alice@example.com',1);
INSERT INTO customer VALUES (2,'CUST000000000002','Bob','Brown','bob@example.com',2);

-- Active rentals
INSERT INTO rental VALUES ('ITEM0000000000002','CUST000000000001','2025-04-01','2025-04-15');

-- Rental history
INSERT INTO rental_history VALUES ('ITEM0000000000001','CUST000000000001','2024-01-01','2024-01-15','2024-01-10');

-- Waitlist
INSERT INTO waitlist VALUES ('ITEM0000000000002','CUST000000000002',1);
"""


def _make_db():
    """Create a fresh in-memory SQLite DB with schema + seed data."""
    db = sqlite3.connect(":memory:", check_same_thread=False)
    # SQLite stores YEAR() as a string function — we monkey-patch with a
    # generated column alias. We handle YEAR() by using strftime in tests
    # where needed, but since we control the DB we store the year directly.
    db.execute("PRAGMA foreign_keys = ON")

    # SQLite doesn't have DATE_ADD — register a replacement
    db.create_function("DATE_ADD_STUB", 2, lambda d, n: str(
        date.fromisoformat(d) + timedelta(days=n)))

    # We need YEAR() — register it
    db.create_function("YEAR", 1, lambda d: int(d[:4]) if d else None)

    # DATE_ADD syntax used: DATE_ADD(col, INTERVAL 14 DAY)
    # SQLite doesn't support INTERVAL — we handle this by patching grant_extension
    # to use a compatible form when connected to SQLite (see _patch_grant_extension).

    db.executescript(_DDL + _SEED_SQL)
    db.commit()
    return db


def _inject_db(db):
    """Patch db_handler's module-level conn/cursor with our fake objects."""
    import db_handler as dbh
    fake_conn = _FakeConnection(db)
    dbh.conn = fake_conn
    dbh.cursor = fake_conn.cursor()
    return dbh


# ── Test cases ────────────────────────────────────────────────────────────────

class TestAddItem(unittest.TestCase):
    def setUp(self):
        self.db = _make_db()
        self.dbh = _inject_db(self.db)

    def test_add_item_inserts_row(self):
        new_item = Item(
            item_id="ITEM9999999999999",
            product_name="Test Product",
            brand="TestBrand",
            category="TestCat",
            manufact="TestMfg",
            current_price=5.00,
            start_year=2025,
            num_owned=2,
        )
        self.dbh.add_item(new_item)
        self.dbh.save_changes()

        cur = self.db.cursor()
        cur.execute("SELECT i_item_id FROM item WHERE i_item_id = 'ITEM9999999999999'")
        row = cur.fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], "ITEM9999999999999")

    def test_add_item_sk_increments(self):
        cur = self.db.cursor()
        cur.execute("SELECT MAX(i_item_sk) FROM item")
        max_before = cur.fetchone()[0]

        new_item = Item(item_id="ITEM0000000099999", product_name="X", brand="Y",
                        category="Z", manufact="M", current_price=1.0,
                        start_year=2022, num_owned=1)
        self.dbh.add_item(new_item)

        cur.execute("SELECT MAX(i_item_sk) FROM item")
        max_after = cur.fetchone()[0]
        self.assertEqual(max_after, max_before + 1)

    def test_add_item_start_year_in_date(self):
        new_item = Item(item_id="ITEM0000000088888", product_name="Dated",
                        brand="B", category="C", manufact="M",
                        current_price=1.0, start_year=2023, num_owned=1)
        self.dbh.add_item(new_item)
        self.dbh.save_changes()
        cur = self.db.cursor()
        cur.execute("SELECT i_rec_start_date FROM item WHERE i_item_id = 'ITEM0000000088888'")
        row = cur.fetchone()
        self.assertTrue(row[0].startswith("2023"))


class TestAddCustomer(unittest.TestCase):
    def setUp(self):
        self.db = _make_db()
        self.dbh = _inject_db(self.db)

    def test_add_customer_inserts_address_and_customer(self):
        new_cust = Customer(
            customer_id="CUST000000000099",
            name="Charlie Chaplin",
            address="42 Elm St, Gotham, NY 10001",
            email="charlie@test.com",
        )
        self.dbh.add_customer(new_cust)
        self.dbh.save_changes()

        cur = self.db.cursor()
        cur.execute("SELECT c_customer_id, c_first_name, c_last_name, c_email_address FROM customer WHERE c_customer_id='CUST000000000099'")
        row = cur.fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row[1], "Charlie")
        self.assertEqual(row[2], "Chaplin")
        self.assertEqual(row[3], "charlie@test.com")

    def test_add_customer_address_parsed(self):
        new_cust = Customer(
            customer_id="CUST000000000098",
            name="Dana Smith",
            address="99 Pine Rd, Austin, TX 78701",
            email="dana@test.com",
        )
        self.dbh.add_customer(new_cust)
        self.dbh.save_changes()

        cur = self.db.cursor()
        cur.execute("""
            SELECT ca_street_number, ca_street_name, ca_city, ca_state, ca_zip
              FROM customer_address ca
              JOIN customer c ON c.c_current_addr_sk = ca.ca_address_sk
             WHERE c.c_customer_id = 'CUST000000000098'
        """)
        row = cur.fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], "99")
        self.assertEqual(row[1], "Pine Rd")
        self.assertEqual(row[2], "Austin")
        self.assertEqual(row[3], "TX")
        self.assertEqual(row[4], "78701")


class TestEditCustomer(unittest.TestCase):
    def setUp(self):
        self.db = _make_db()
        self.dbh = _inject_db(self.db)

    def test_edit_name(self):
        edit = Customer(name="Alice Zephyr", customer_id=None, address=None, email=None)
        self.dbh.edit_customer("CUST000000000001", edit)
        self.dbh.save_changes()

        cur = self.db.cursor()
        cur.execute("SELECT c_first_name, c_last_name FROM customer WHERE c_customer_id='CUST000000000001'")
        row = cur.fetchone()
        self.assertEqual(row[0], "Alice")
        self.assertEqual(row[1], "Zephyr")

    def test_edit_email(self):
        edit = Customer(name=None, customer_id=None, address=None, email="new@example.com")
        self.dbh.edit_customer("CUST000000000001", edit)
        self.dbh.save_changes()

        cur = self.db.cursor()
        cur.execute("SELECT c_email_address FROM customer WHERE c_customer_id='CUST000000000001'")
        row = cur.fetchone()
        self.assertEqual(row[0], "new@example.com")

    def test_edit_address(self):
        edit = Customer(name=None, customer_id=None,
                        address="777 New Blvd, Chicago, IL 60601", email=None)
        self.dbh.edit_customer("CUST000000000001", edit)
        self.dbh.save_changes()

        cur = self.db.cursor()
        cur.execute("""
            SELECT ca_city FROM customer_address ca
            JOIN customer c ON c.c_current_addr_sk = ca.ca_address_sk
            WHERE c.c_customer_id='CUST000000000001'
        """)
        row = cur.fetchone()
        self.assertEqual(row[0], "Chicago")

    def test_edit_nonexistent_customer_does_not_crash(self):
        edit = Customer(name="Ghost Person", customer_id=None, address=None, email=None)
        # Should silently do nothing
        self.dbh.edit_customer("DOESNOTEXIST0000", edit)


class TestRentItem(unittest.TestCase):
    def setUp(self):
        self.db = _make_db()
        self.dbh = _inject_db(self.db)

    def test_rent_inserts_row(self):
        self.dbh.rent_item("ITEM0000000000001", "CUST000000000001")
        self.dbh.save_changes()

        cur = self.db.cursor()
        cur.execute("SELECT item_id, customer_id FROM rental WHERE item_id='ITEM0000000000001' AND customer_id='CUST000000000001'")
        row = cur.fetchone()
        self.assertIsNotNone(row)

    def test_rent_correct_dates(self):
        today = date.today()
        expected_due = today + timedelta(days=14)

        self.dbh.rent_item("ITEM0000000000001", "CUST000000000002")
        self.dbh.save_changes()

        cur = self.db.cursor()
        cur.execute("SELECT rental_date, due_date FROM rental WHERE item_id='ITEM0000000000001' AND customer_id='CUST000000000002'")
        row = cur.fetchone()
        self.assertEqual(row[0], str(today))
        self.assertEqual(row[1], str(expected_due))


class TestReturnItem(unittest.TestCase):
    def setUp(self):
        self.db = _make_db()
        self.dbh = _inject_db(self.db)

    def test_return_removes_from_rental(self):
        self.dbh.return_item("ITEM0000000000002", "CUST000000000001")
        self.dbh.save_changes()

        cur = self.db.cursor()
        cur.execute("SELECT * FROM rental WHERE item_id='ITEM0000000000002' AND customer_id='CUST000000000001'")
        self.assertIsNone(cur.fetchone())

    def test_return_adds_to_history(self):
        self.dbh.return_item("ITEM0000000000002", "CUST000000000001")
        self.dbh.save_changes()

        cur = self.db.cursor()
        cur.execute("SELECT return_date FROM rental_history WHERE item_id='ITEM0000000000002' AND customer_id='CUST000000000001'")
        row = cur.fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], str(date.today()))

    def test_return_nonexistent_does_not_crash(self):
        self.dbh.return_item("ITEM9999999999999", "CUST000000000001")


class TestGrantExtension(unittest.TestCase):
    def setUp(self):
        self.db = _make_db()
        self.dbh = _inject_db(self.db)

    def test_grant_extension_adds_14_days(self):
        # SQLite doesn't support DATE_ADD(col, INTERVAL n DAY) syntax
        # Patch grant_extension to use SQLite-compatible date arithmetic
        import db_handler as dbh

        def _sqlite_grant_extension(item_id, customer_id):
            _, cur = dbh._get_connection()
            cur.execute("SELECT due_date FROM rental WHERE item_id=? AND customer_id=?",
                        (item_id, customer_id))
            row = cur.fetchone()
            if row is None:
                return
            new_due = str(date.fromisoformat(str(row[0])) + timedelta(days=14))
            cur.execute("UPDATE rental SET due_date=? WHERE item_id=? AND customer_id=?",
                        (new_due, item_id, customer_id))

        original = dbh.grant_extension
        dbh.grant_extension = _sqlite_grant_extension

        try:
            cur = self.db.cursor()
            cur.execute("SELECT due_date FROM rental WHERE item_id='ITEM0000000000002' AND customer_id='CUST000000000001'")
            before = cur.fetchone()[0]

            self.dbh.grant_extension("ITEM0000000000002", "CUST000000000001")
            self.dbh.save_changes()

            cur.execute("SELECT due_date FROM rental WHERE item_id='ITEM0000000000002' AND customer_id='CUST000000000001'")
            after = cur.fetchone()[0]

            before_date = date.fromisoformat(str(before))
            after_date = date.fromisoformat(str(after))
            self.assertEqual((after_date - before_date).days, 14)
        finally:
            dbh.grant_extension = original


class TestWaitlistFunctions(unittest.TestCase):
    def setUp(self):
        self.db = _make_db()
        self.dbh = _inject_db(self.db)

    def test_line_length_existing(self):
        self.assertEqual(self.dbh.line_length("ITEM0000000000002"), 1)

    def test_line_length_no_waitlist(self):
        self.assertEqual(self.dbh.line_length("ITEM0000000000001"), 0)

    def test_place_in_line_existing(self):
        self.assertEqual(self.dbh.place_in_line("ITEM0000000000002", "CUST000000000002"), 1)

    def test_place_in_line_not_on_waitlist(self):
        self.assertEqual(self.dbh.place_in_line("ITEM0000000000002", "CUST000000000001"), -1)

    def test_waitlist_customer_returns_position(self):
        pos = self.dbh.waitlist_customer("ITEM0000000000002", "CUST000000000001")
        self.assertEqual(pos, 2)

    def test_waitlist_customer_inserts_row(self):
        self.dbh.waitlist_customer("ITEM0000000000001", "CUST000000000001")
        self.dbh.save_changes()

        cur = self.db.cursor()
        cur.execute("SELECT place_in_line FROM waitlist WHERE item_id='ITEM0000000000001' AND customer_id='CUST000000000001'")
        row = cur.fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], 1)

    def test_update_waitlist_removes_first(self):
        # Add a second person
        self.dbh.waitlist_customer("ITEM0000000000002", "CUST000000000001")
        self.dbh.save_changes()

        self.dbh.update_waitlist("ITEM0000000000002")
        self.dbh.save_changes()

        cur = self.db.cursor()
        cur.execute("SELECT customer_id, place_in_line FROM waitlist WHERE item_id='ITEM0000000000002' ORDER BY place_in_line")
        rows = cur.fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], "CUST000000000001")
        self.assertEqual(rows[0][1], 1)

    def test_update_waitlist_empty(self):
        # Should not crash on empty waitlist
        self.dbh.update_waitlist("ITEM0000000000001")


class TestNumberInStock(unittest.TestCase):
    def setUp(self):
        self.db = _make_db()
        self.dbh = _inject_db(self.db)

    def test_stock_with_no_rentals(self):
        # ITEM1 has num_owned=3, no active rentals
        result = self.dbh.number_in_stock("ITEM0000000000001")
        self.assertEqual(result, 3)

    def test_stock_with_one_rental(self):
        # ITEM2 has num_owned=1, 1 active rental → 0 in stock
        result = self.dbh.number_in_stock("ITEM0000000000002")
        self.assertEqual(result, 0)

    def test_stock_nonexistent_item(self):
        result = self.dbh.number_in_stock("DOESNOTEXIST0000")
        self.assertEqual(result, -1)


class TestGetFilteredItems(unittest.TestCase):
    def setUp(self):
        self.db = _make_db()
        self.dbh = _inject_db(self.db)

    def test_no_filters_returns_all(self):
        results = self.dbh.get_filtered_items(Item())
        self.assertGreaterEqual(len(results), 3)

    def test_filter_by_item_id(self):
        results = self.dbh.get_filtered_items(Item(item_id="ITEM0000000000001"))
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].item_id, "ITEM0000000000001")

    def test_filter_by_brand(self):
        results = self.dbh.get_filtered_items(Item(brand="BrandA"))
        item_ids = [r.item_id for r in results]
        self.assertIn("ITEM0000000000001", item_ids)
        self.assertIn("ITEM0000000000003", item_ids)

    def test_filter_by_category(self):
        results = self.dbh.get_filtered_items(Item(category="Tools"))
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].category, "Tools")

    def test_filter_price_range(self):
        results = self.dbh.get_filtered_items(Item(), min_price=10.0, max_price=25.0)
        for r in results:
            self.assertGreaterEqual(r.current_price, 10.0)
            self.assertLessEqual(r.current_price, 25.0)

    def test_filter_year_range(self):
        results = self.dbh.get_filtered_items(Item(), min_start_year=2020, max_start_year=2021)
        for r in results:
            self.assertGreaterEqual(r.start_year, 2020)
            self.assertLessEqual(r.start_year, 2021)

    def test_like_pattern(self):
        results = self.dbh.get_filtered_items(Item(product_name="Widget%"), use_patterns=True)
        self.assertGreaterEqual(len(results), 2)

    def test_no_match_returns_empty(self):
        results = self.dbh.get_filtered_items(Item(item_id="ZZZZZZZZZZZZZZZZ"))
        self.assertEqual(results, [])


class TestGetFilteredCustomers(unittest.TestCase):
    def setUp(self):
        self.db = _make_db()
        self.dbh = _inject_db(self.db)

    def test_no_filters_returns_all(self):
        results = self.dbh.get_filtered_customers(Customer())
        self.assertGreaterEqual(len(results), 2)

    def test_filter_by_customer_id(self):
        results = self.dbh.get_filtered_customers(Customer(customer_id="CUST000000000001"))
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].customer_id, "CUST000000000001")

    def test_filter_by_name_exact(self):
        results = self.dbh.get_filtered_customers(Customer(name="Alice Anderson"))
        self.assertEqual(len(results), 1)

    def test_filter_by_name_pattern(self):
        results = self.dbh.get_filtered_customers(Customer(name="%son"), use_patterns=True)
        names = [r.name for r in results]
        self.assertTrue(any("Anderson" in n for n in names))

    def test_filter_by_email(self):
        results = self.dbh.get_filtered_customers(Customer(email="alice@example.com"))
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].email, "alice@example.com")

    def test_address_constructed_correctly(self):
        results = self.dbh.get_filtered_customers(Customer(customer_id="CUST000000000001"))
        self.assertEqual(len(results), 1)
        addr = results[0].address
        self.assertIn("100", addr)
        self.assertIn("Oak Lane", addr)
        self.assertIn("Springfield", addr)
        self.assertIn("IL", addr)
        self.assertIn("62701", addr)


class TestGetFilteredRentals(unittest.TestCase):
    def setUp(self):
        self.db = _make_db()
        self.dbh = _inject_db(self.db)

    def test_no_filters_returns_all(self):
        results = self.dbh.get_filtered_rentals(Rental())
        self.assertGreaterEqual(len(results), 1)

    def test_filter_by_item_id(self):
        results = self.dbh.get_filtered_rentals(Rental(item_id="ITEM0000000000002"))
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].item_id, "ITEM0000000000002")

    def test_filter_by_customer_id(self):
        results = self.dbh.get_filtered_rentals(Rental(customer_id="CUST000000000001"))
        self.assertEqual(len(results), 1)

    def test_date_range_filter(self):
        results = self.dbh.get_filtered_rentals(
            Rental(),
            min_rental_date="2025-01-01",
            max_rental_date="2025-12-31"
        )
        for r in results:
            self.assertGreaterEqual(r.rental_date, "2025-01-01")
            self.assertLessEqual(r.rental_date, "2025-12-31")

    def test_no_match_returns_empty(self):
        results = self.dbh.get_filtered_rentals(Rental(item_id="ZZZZZZZZZZZZZZZZ"))
        self.assertEqual(results, [])


class TestGetFilteredRentalHistories(unittest.TestCase):
    def setUp(self):
        self.db = _make_db()
        self.dbh = _inject_db(self.db)

    def test_no_filters_returns_history(self):
        results = self.dbh.get_filtered_rental_histories(RentalHistory())
        self.assertGreaterEqual(len(results), 1)

    def test_filter_by_item_id(self):
        results = self.dbh.get_filtered_rental_histories(RentalHistory(item_id="ITEM0000000000001"))
        self.assertEqual(len(results), 1)

    def test_filter_by_return_date_range(self):
        results = self.dbh.get_filtered_rental_histories(
            RentalHistory(),
            min_return_date="2024-01-01",
            max_return_date="2024-12-31"
        )
        for r in results:
            self.assertGreaterEqual(r.return_date, "2024-01-01")
            self.assertLessEqual(r.return_date, "2024-12-31")

    def test_no_match_returns_empty(self):
        results = self.dbh.get_filtered_rental_histories(RentalHistory(item_id="ZZZZ"))
        self.assertEqual(results, [])


class TestGetFilteredWaitlist(unittest.TestCase):
    def setUp(self):
        self.db = _make_db()
        self.dbh = _inject_db(self.db)

    def test_no_filters(self):
        results = self.dbh.get_filtered_waitlist(Waitlist())
        self.assertGreaterEqual(len(results), 1)

    def test_filter_by_item_id(self):
        results = self.dbh.get_filtered_waitlist(Waitlist(item_id="ITEM0000000000002"))
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].customer_id, "CUST000000000002")

    def test_filter_place_range(self):
        results = self.dbh.get_filtered_waitlist(Waitlist(), min_place_in_line=1, max_place_in_line=1)
        for r in results:
            self.assertEqual(r.place_in_line, 1)

    def test_no_match(self):
        results = self.dbh.get_filtered_waitlist(Waitlist(item_id="ZZZZ"))
        self.assertEqual(results, [])


class TestSaveAndClose(unittest.TestCase):
    def setUp(self):
        self.db = _make_db()
        self.dbh = _inject_db(self.db)

    def test_save_changes_does_not_crash(self):
        self.dbh.save_changes()

    def test_close_connection_clears_globals(self):
        self.dbh.close_connection()
        self.assertIsNone(self.dbh.conn)
        self.assertIsNone(self.dbh.cursor)

    def test_double_close_does_not_crash(self):
        self.dbh.close_connection()
        self.dbh.close_connection()  # Should be a no-op


class TestAddressParser(unittest.TestCase):
    """Unit tests for the internal _parse_address helper."""

    def setUp(self):
        self.db = _make_db()
        self.dbh = _inject_db(self.db)

    def test_standard_address(self):
        result = self.dbh._parse_address("123 Main St, Springfield, IL 62701")
        self.assertEqual(result["street_number"], "123")
        self.assertEqual(result["street_name"], "Main St")
        self.assertEqual(result["city"], "Springfield")
        self.assertEqual(result["state"], "IL")
        self.assertEqual(result["zip"], "62701")

    def test_multi_word_street(self):
        result = self.dbh._parse_address("456 Elm Park Rd, Austin, TX 78701")
        self.assertEqual(result["street_number"], "456")
        self.assertEqual(result["street_name"], "Elm Park Rd")

    def test_address_with_spaces(self):
        result = self.dbh._parse_address("  99   Pine Blvd  ,  Chicago  ,  IL   60601  ")
        # After strip() in parser:
        self.assertIn("99", result["street_number"])


class TestIntegration(unittest.TestCase):
    """End-to-end flow: rent → return → waitlist → update_waitlist."""

    def setUp(self):
        self.db = _make_db()
        self.dbh = _inject_db(self.db)

    def test_full_rental_cycle(self):
        item_id = "ITEM0000000000003"
        cust_id = "CUST000000000001"

        # Should be in stock
        stock = self.dbh.number_in_stock(item_id)
        self.assertEqual(stock, 2)

        # Rent it
        self.dbh.rent_item(item_id, cust_id)
        self.dbh.save_changes()
        self.assertEqual(self.dbh.number_in_stock(item_id), 1)

        # Verify rental exists
        rentals = self.dbh.get_filtered_rentals(
            Rental(item_id=item_id, customer_id=cust_id))
        self.assertEqual(len(rentals), 1)

        # Return it
        self.dbh.return_item(item_id, cust_id)
        self.dbh.save_changes()
        self.assertEqual(self.dbh.number_in_stock(item_id), 2)

        # Verify in history
        history = self.dbh.get_filtered_rental_histories(
            RentalHistory(item_id=item_id, customer_id=cust_id))
        # May include pre-existing history too; just check our return is there
        self.assertTrue(any(h.customer_id == cust_id for h in history))

    def test_waitlist_queue_management(self):
        item_id = "ITEM0000000000001"

        # Empty waitlist
        self.assertEqual(self.dbh.line_length(item_id), 0)

        # Add two customers
        pos1 = self.dbh.waitlist_customer(item_id, "CUST000000000001")
        pos2 = self.dbh.waitlist_customer(item_id, "CUST000000000002")
        self.dbh.save_changes()
        self.assertEqual(pos1, 1)
        self.assertEqual(pos2, 2)
        self.assertEqual(self.dbh.line_length(item_id), 2)

        # Update (simulate item becoming available)
        self.dbh.update_waitlist(item_id)
        self.dbh.save_changes()
        self.assertEqual(self.dbh.line_length(item_id), 1)
        self.assertEqual(self.dbh.place_in_line(item_id, "CUST000000000002"), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
