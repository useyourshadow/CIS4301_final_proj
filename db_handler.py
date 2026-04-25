import mariadb
from datetime import date, timedelta

from models.Item import Item
from models.Customer import Customer
from models.Rental import Rental
from models.RentalHistory import RentalHistory
from models.Waitlist import Waitlist

# try to load credentials, fall back to defaults if the file isn't there
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

# single connection and cursor reused for the whole session
conn: mariadb.Connection | None = None
cursor: mariadb.Cursor | None = None


def _get_connection() -> tuple[mariadb.Connection, mariadb.Cursor]:
    # open a new connection only if we don't have one yet
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
    # commit all pending changes
    c, _ = _get_connection()
    c.commit()


def close_connection() -> None:
    # close cursor then connection
    global conn, cursor

    if cursor:
        cursor.close()
        cursor = None

    if conn:
        conn.close()
        conn = None


# columns we always pull when selecting items
_ITEM_COLS = (
    "i_item_id, i_product_name, i_brand, i_category, i_manufact, "
    "i_current_price, YEAR(i_rec_start_date), i_num_owned"
)


def _row_to_item(row) -> Item:
    # unpack a db row and strip trailing spaces from CHAR columns
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


def add_item(new_item: Item) -> None:
    # insert a new item, generating its surrogate key with MAX + 1
    _, cur = _get_connection()

    cur.execute("SELECT MAX(i_item_sk) FROM item")
    row = cur.fetchone()
    new_sk = (row[0] or 0) + 1

    # use jan 1 of the given year as the record start date
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
    # split "123 Main St, City, ST 12345" into its individual parts
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
    # insert the address row first, then the customer row that references it
    _, cur = _get_connection()

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

    cur.execute("SELECT MAX(c_customer_sk) FROM customer")
    row = cur.fetchone()
    cust_sk = (row[0] or 0) + 1

    # split full name on first space to get first and last
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
    # only update the fields that were actually provided, skip anything that's None
    _, cur = _get_connection()

    cur.execute(
        "SELECT c_customer_sk, c_current_addr_sk FROM customer WHERE c_customer_id = ?",
        (original_customer_id,),
    )
    row = cur.fetchone()

    if not row:
        return

    cust_sk, addr_sk = row

    # update address if a new one was given
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

    # build the SET clause dynamically so we only touch changed fields
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
    # create a rental starting today, due in 14 days
    _, cur = _get_connection()

    today = date.today()
    due = today + timedelta(days=14)

    cur.execute(
        "INSERT INTO rental (item_id, customer_id, rental_date, due_date) VALUES (?, ?, ?, ?)",
        (item_id, customer_id, str(today), str(due)),
    )


def return_item(item_id: str, customer_id: str) -> None:
    # move the rental record into history and remove it from the active table
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
        "INSERT INTO rental_history VALUES (?, ?, ?, ?, ?)",
        (item_id, customer_id, str(rental_date), str(due_date), return_date),
    )

    cur.execute(
        "DELETE FROM rental WHERE item_id = ? AND customer_id = ?",
        (item_id, customer_id),
    )


def grant_extension(item_id: str, customer_id: str) -> None:
    # push the due date back 14 days
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
    # add the customer to the end of the waitlist and return their position
    _, cur = _get_connection()

    position = line_length(item_id) + 1

    cur.execute(
        "INSERT INTO waitlist VALUES (?, ?, ?)",
        (item_id, customer_id, position),
    )

    return position


def update_waitlist(item_id: str) -> None:
    # remove whoever is first in line, then shift everyone else up by one
    _, cur = _get_connection()

    cur.execute(
        "DELETE FROM waitlist WHERE item_id = ? AND place_in_line = 1",
        (item_id,),
    )

    cur.execute(
        "UPDATE waitlist SET place_in_line = place_in_line - 1 WHERE item_id = ?",
        (item_id,),
    )


def number_in_stock(item_id: str) -> int:
    # return copies owned minus copies currently rented out, -1 if item doesn't exist
    _, cur = _get_connection()

    cur.execute("SELECT i_num_owned FROM item WHERE i_item_id = ?", (item_id,))
    row = cur.fetchone()

    if not row:
        return -1

    num_owned = row[0]

    cur.execute("SELECT COUNT(*) FROM rental WHERE item_id = ?", (item_id,))
    rented = cur.fetchone()[0]

    return num_owned - rented


def place_in_line(item_id: str, customer_id: str) -> int:
    # return the customer's position, or -1 if they're not on the waitlist
    _, cur = _get_connection()

    cur.execute(
        "SELECT place_in_line FROM waitlist WHERE item_id = ? AND customer_id = ?",
        (item_id, customer_id),
    )
    row = cur.fetchone()

    return row[0] if row else -1


def line_length(item_id: str) -> int:
    # count how many people are waiting for this item
    _, cur = _get_connection()

    cur.execute(
        "SELECT COUNT(*) FROM waitlist WHERE item_id = ?",
        (item_id,),
    )
    row = cur.fetchone()

    return row[0] if row else 0


def get_filtered_items(
    filter_attributes: Item,
    use_patterns: bool = False,
    min_price: float = -1,
    max_price: float = -1,
    min_start_year: int = -1,
    max_start_year: int = -1,
) -> list[Item]:
    # search items by any combination of fields and ranges, skip filters that aren't set
    _, cur = _get_connection()

    conditions = []
    params = []

    # use LIKE for pattern searches, = for exact matches
    op = "LIKE" if use_patterns else "="

    if filter_attributes.item_id is not None:
        conditions.append(f"i_item_id {op} ?")
        params.append(filter_attributes.item_id)

    if filter_attributes.product_name is not None:
        conditions.append(f"i_product_name {op} ?")
        params.append(filter_attributes.product_name)

    if filter_attributes.brand is not None:
        conditions.append(f"i_brand {op} ?")
        params.append(filter_attributes.brand)

    if filter_attributes.category is not None:
        conditions.append(f"i_category {op} ?")
        params.append(filter_attributes.category)

    if filter_attributes.manufact is not None:
        conditions.append(f"i_manufact {op} ?")
        params.append(filter_attributes.manufact)

    if min_price != -1:
        conditions.append("i_current_price >= ?")
        params.append(min_price)

    if max_price != -1:
        conditions.append("i_current_price <= ?")
        params.append(max_price)

    if min_start_year != -1:
        conditions.append("YEAR(i_rec_start_date) >= ?")
        params.append(min_start_year)

    if max_start_year != -1:
        conditions.append("YEAR(i_rec_start_date) <= ?")
        params.append(max_start_year)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    cur.execute(f"SELECT {_ITEM_COLS} FROM item {where}", tuple(params))
    return [_row_to_item(row) for row in cur.fetchall()]


def get_filtered_customers(
    filter_attributes: Customer,
    use_patterns: bool = False,
) -> list[Customer]:
    # search customers and join their address, skip any field that's None
    _, cur = _get_connection()

    conditions = []
    params = []

    op = "LIKE" if use_patterns else "="

    if filter_attributes.customer_id is not None:
        conditions.append(f"c_customer_id {op} ?")
        params.append(filter_attributes.customer_id)

    if filter_attributes.name is not None:
        # match on the full name since that's what the user sees
        conditions.append(f"CONCAT(c_first_name, ' ', c_last_name) {op} ?")
        params.append(filter_attributes.name)

    if filter_attributes.email is not None:
        conditions.append(f"c_email_address {op} ?")
        params.append(filter_attributes.email)

    if filter_attributes.address is not None:
        # filter by city since address is split across columns
        addr = _parse_address(filter_attributes.address)
        if addr["city"]:
            conditions.append(f"ca_city {op} ?")
            params.append(addr["city"])

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    query = f"""
        SELECT c_customer_id,
               CONCAT(c_first_name, ' ', c_last_name),
               c_email_address,
               ca_street_number, ca_street_name, ca_city, ca_state, ca_zip
          FROM customer
          JOIN customer_address ON c_current_addr_sk = ca_address_sk
        {where}
    """

    cur.execute(query, tuple(params))

    results = []
    for row in cur.fetchall():
        cid, name, email, snum, sname, city, state, zipcode = row

        # reassemble the address string the same way it was entered
        address = f"{snum.strip()} {sname.strip()}, {city.strip()}, {state.strip()} {zipcode.strip()}"

        results.append(Customer(
            customer_id=cid.strip(),
            name=name.strip(),
            email=email.strip() if email else "",
            address=address,
        ))

    return results


def get_filtered_rentals(
    filter_attributes: Rental,
    min_rental_date: str = None,
    max_rental_date: str = None,
    min_due_date: str = None,
    max_due_date: str = None,
) -> list[Rental]:
    # search active rentals, all date ranges inclusive, None means skip that filter
    _, cur = _get_connection()

    conditions = []
    params = []

    if filter_attributes.item_id is not None:
        conditions.append("item_id = ?")
        params.append(filter_attributes.item_id)

    if filter_attributes.customer_id is not None:
        conditions.append("customer_id = ?")
        params.append(filter_attributes.customer_id)

    if min_rental_date is not None:
        conditions.append("rental_date >= ?")
        params.append(min_rental_date)

    if max_rental_date is not None:
        conditions.append("rental_date <= ?")
        params.append(max_rental_date)

    if min_due_date is not None:
        conditions.append("due_date >= ?")
        params.append(min_due_date)

    if max_due_date is not None:
        conditions.append("due_date <= ?")
        params.append(max_due_date)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    cur.execute(
        f"SELECT item_id, customer_id, rental_date, due_date FROM rental {where}",
        tuple(params),
    )

    return [
        Rental(
            item_id=row[0].strip(),
            customer_id=row[1].strip(),
            rental_date=str(row[2]),
            due_date=str(row[3]),
        )
        for row in cur.fetchall()
    ]


def get_filtered_rental_histories(
    filter_attributes: RentalHistory,
    min_rental_date: str = None,
    max_rental_date: str = None,
    min_due_date: str = None,
    max_due_date: str = None,
    min_return_date: str = None,
    max_return_date: str = None,
) -> list[RentalHistory]:
    # same as get_filtered_rentals but hits rental_history and also filters by return date
    _, cur = _get_connection()

    conditions = []
    params = []

    if filter_attributes.item_id is not None:
        conditions.append("item_id = ?")
        params.append(filter_attributes.item_id)

    if filter_attributes.customer_id is not None:
        conditions.append("customer_id = ?")
        params.append(filter_attributes.customer_id)

    if min_rental_date is not None:
        conditions.append("rental_date >= ?")
        params.append(min_rental_date)

    if max_rental_date is not None:
        conditions.append("rental_date <= ?")
        params.append(max_rental_date)

    if min_due_date is not None:
        conditions.append("due_date >= ?")
        params.append(min_due_date)

    if max_due_date is not None:
        conditions.append("due_date <= ?")
        params.append(max_due_date)

    if min_return_date is not None:
        conditions.append("return_date >= ?")
        params.append(min_return_date)

    if max_return_date is not None:
        conditions.append("return_date <= ?")
        params.append(max_return_date)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    cur.execute(
        f"SELECT item_id, customer_id, rental_date, due_date, return_date FROM rental_history {where}",
        tuple(params),
    )

    return [
        RentalHistory(
            item_id=row[0].strip(),
            customer_id=row[1].strip(),
            rental_date=str(row[2]),
            due_date=str(row[3]),
            return_date=str(row[4]),
        )
        for row in cur.fetchall()
    ]


def get_filtered_waitlist(
    filter_attributes: Waitlist,
    min_place_in_line: int = -1,
    max_place_in_line: int = -1,
) -> list[Waitlist]:
    # search the waitlist by item, customer, or position range
    _, cur = _get_connection()

    conditions = []
    params = []

    if filter_attributes.item_id is not None:
        conditions.append("item_id = ?")
        params.append(filter_attributes.item_id)

    if filter_attributes.customer_id is not None:
        conditions.append("customer_id = ?")
        params.append(filter_attributes.customer_id)

    if min_place_in_line != -1:
        conditions.append("place_in_line >= ?")
        params.append(min_place_in_line)

    if max_place_in_line != -1:
        conditions.append("place_in_line <= ?")
        params.append(max_place_in_line)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    cur.execute(
        f"SELECT item_id, customer_id, place_in_line FROM waitlist {where} ORDER BY place_in_line",
        tuple(params),
    )

    return [
        Waitlist(
            item_id=row[0].strip(),
            customer_id=row[1].strip(),
            place_in_line=int(row[2]),
        )
        for row in cur.fetchall()
    ]