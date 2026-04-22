"""
db_handler.py
this file handles all direct database work:
items, customers, rentals, waitlist, and queries.
"""

import mariadb
from datetime import date, timedelta

from models.Item import Item
from models.Customer import Customer
from models.Rental import Rental
from models.RentalHistory import RentalHistory
from models.Waitlist import Waitlist

# Try loading credentials from file, otherwise fall back to defaults
try:
    from MARIADB_CREDS import DB_CONFIG
except ImportError:
    DB_CONFIG = {
        "username": "root",
        "password": "",
        "port": 3306,
        "host": "localhost",
        "database": "tpcds_rental",
    }



# Connection handling

conn: mariadb.Connection | None = None
cursor: mariadb.Cursor | None = None


def _get_connection() -> tuple[mariadb.Connection, mariadb.Cursor]:
    """Create a DB connection if we don't already have one."""
    global conn, cursor

    if conn is None:
        conn = mariadb.connect(
            user=DB_CONFIG["username"],
            password=DB_CONFIG["password"],
            host=DB_CONFIG["host"],
            port=DB_CONFIG["port"],
            database=DB_CONFIG["database"],
            autocommit=False,
        )
        cursor = conn.cursor()

    return conn, cursor


def save_changes() -> None:
    """Commit whatever has been done so far."""
    c, _ = _get_connection()
    c.commit()


def close_connection() -> None:
    """Close DB connection cleanly."""
    global conn, cursor

    if cursor:
        cursor.close()
        cursor = None

    if conn:
        conn.close()
        conn = None




def _row_to_item(row) -> Item:
    """Turn a DB row into an Item object."""
    item_id, product_name, brand, category, manufact, current_price, start_year, num_owned = row

    return Item(
        item_id=item_id.strip(),
        product_name=product_name.strip() if product_name else "",
        brand=brand.strip() if brand else "",
        category=category.strip() if category else "",
        manufact=manufact.strip() if manufact else "",
        current_price=float(current_price) if current_price is not None else 0.0,
        start_year=int(start_year) if start_year is not None else 0,
        num_owned=int(num_owned) if num_owned is not None else 0,
    )


_ITEM_COLS = (
    "i_item_id, i_product_name, i_brand, i_category, i_manufact, "
    "i_current_price, YEAR(i_rec_start_date), i_num_owned"
)


def add_item(new_item: Item) -> None:
    """Add a new item into the database."""
    _, cur = _get_connection()

    # simple surrogate key generation
    cur.execute("SELECT MAX(i_item_sk) FROM item")
    row = cur.fetchone()
    new_sk = (row[0] or 0) + 1

    rec_start = f"{new_item.start_year}-01-01"

    cur.execute(
        """
        INSERT INTO item (
            i_item_sk, i_item_id, i_rec_start_date,
            i_product_name, i_brand, i_class, i_category,
            i_manufact, i_current_price, i_num_owned
        ) VALUES (?, ?, ?, ?, ?, NULL, ?, ?, ?, ?)
        """,
        (
            new_sk,
            new_item.item_id,
            rec_start,
            new_item.product_name,
            new_item.brand,
            new_item.category,
            new_item.manufact,
            new_item.current_price,
            new_item.num_owned,
        ),
    )



def _parse_address(address: str) -> dict:
    """
    Split a full address string into parts.

    Expected format:
    "123 Main St, City, ST 12345"
    """
    parts = [p.strip() for p in address.split(",")]

    street_parts = parts[0].split(" ", 1)
    street_number = street_parts[0] if len(street_parts) > 1 else ""
    street_name = street_parts[1] if len(street_parts) > 1 else street_parts[0]

    city = parts[1] if len(parts) > 1 else ""

    state_zip = parts[2] if len(parts) > 2 else ""
    sz = state_zip.split(" ", 1)

    state = sz[0] if sz else ""
    zipcode = sz[1] if len(sz) > 1 else ""

    return {
        "street_number": street_number,
        "street_name": street_name,
        "city": city,
        "state": state,
        "zip": zipcode,
    }


def add_customer(new_customer: Customer) -> None:
    """Insert a customer and their address."""
    _, cur = _get_connection()

    # address key
    cur.execute("SELECT MAX(ca_address_sk) FROM customer_address")
    row = cur.fetchone()
    addr_sk = (row[0] or 0) + 1

    addr = _parse_address(new_customer.address)

    cur.execute(
        """
        INSERT INTO customer_address (
            ca_address_sk, ca_street_number, ca_street_name,
            ca_city, ca_state, ca_zip
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            addr_sk,
            addr["street_number"],
            addr["street_name"],
            addr["city"],
            addr["state"],
            addr["zip"],
        ),
    )

    # customer key
    cur.execute("SELECT MAX(c_customer_sk) FROM customer")
    row = cur.fetchone()
    cust_sk = (row[0] or 0) + 1

    first, *rest = new_customer.name.split(" ", 1)
    last = rest[0] if rest else ""

    cur.execute(
        """
        INSERT INTO customer (
            c_customer_sk, c_customer_id,
            c_first_name, c_last_name,
            c_email_address, c_current_addr_sk
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            cust_sk,
            new_customer.customer_id,
            first,
            last,
            new_customer.email,
            addr_sk,
        ),
    )


def edit_customer(original_customer_id: str, new_customer: Customer) -> None:
    """Update customer fields that were actually provided."""
    _, cur = _get_connection()

    cur.execute(
        "SELECT c_customer_sk, c_current_addr_sk FROM customer WHERE c_customer_id = ?",
        (original_customer_id,),
    )
    row = cur.fetchone()

    if not row:
        return

    cust_sk, addr_sk = row

    # update address if needed
    if new_customer.address:
        addr = _parse_address(new_customer.address)
        cur.execute(
            """
            UPDATE customer_address
               SET ca_street_number = ?,
                   ca_street_name = ?,
                   ca_city = ?,
                   ca_state = ?,
                   ca_zip = ?
             WHERE ca_address_sk = ?
            """,
            (
                addr["street_number"],
                addr["street_name"],
                addr["city"],
                addr["state"],
                addr["zip"],
                addr_sk,
            ),
        )

    # update only fields that exist
    updates = []
    params = []

    if new_customer.customer_id:
        updates.append("c_customer_id = ?")
        params.append(new_customer.customer_id)

    if new_customer.name:
        first, *rest = new_customer.name.split(" ", 1)
        updates.append("c_first_name = ?")
        params.append(first)

        updates.append("c_last_name = ?")
        params.append(rest[0] if rest else "")

    if new_customer.email:
        updates.append("c_email_address = ?")
        params.append(new_customer.email)

    if updates:
        params.append(cust_sk)
        cur.execute(
            f"UPDATE customer SET {', '.join(updates)} WHERE c_customer_sk = ?",
            tuple(params),
        )


def rent_item(item_id: str, customer_id: str) -> None:
    """Create a rental (2 week default)."""
    _, cur = _get_connection()

    today = date.today()
    due = today + timedelta(days=14)

    cur.execute(
        "INSERT INTO rental (item_id, customer_id, rental_date, due_date) VALUES (?, ?, ?, ?)",
        (item_id, customer_id, str(today), str(due)),
    )


def return_item(item_id: str, customer_id: str) -> None:
    """Move a rental into history and remove it from active rentals."""
    _, cur = _get_connection()

    cur.execute(
        "SELECT rental_date, due_date FROM rental WHERE item_id = ? AND customer_id = ?",
        (item_id, customer_id),
    )
    row = cur.fetchone()

    if not row:
        return

    rental_date, due_date = row
    return_date = str(date.today())

    cur.execute(
        """
        INSERT INTO rental_history
        VALUES (?, ?, ?, ?, ?)
        """,
        (item_id, customer_id, str(rental_date), str(due_date), return_date),
    )

    cur.execute(
        "DELETE FROM rental WHERE item_id = ? AND customer_id = ?",
        (item_id, customer_id),
    )


def grant_extension(item_id: str, customer_id: str) -> None:
    """Push due date back by 2 weeks."""
    _, cur = _get_connection()

    cur.execute(
        """
        UPDATE rental
           SET due_date = DATE_ADD(due_date, INTERVAL 14 DAY)
         WHERE item_id = ? AND customer_id = ?
        """,
        (item_id, customer_id),
    )



def waitlist_customer(item_id: str, customer_id: str) -> int:
    """Add someone to the waitlist and return their position."""
    _, cur = _get_connection()

    position = line_length(item_id) + 1

    cur.execute(
        "INSERT INTO waitlist VALUES (?, ?, ?)",
        (item_id, customer_id, position),
    )

    return position


def update_waitlist(item_id: str) -> None:
    """Pop first person and shift everyone up."""
    _, cur = _get_connection()

    cur.execute(
        "DELETE FROM waitlist WHERE item_id = ? AND place_in_line = 1",
        (item_id,),
    )

    cur.execute(
        "UPDATE waitlist SET place_in_line = place_in_line - 1 WHERE item_id = ?",
        (item_id,),
    )