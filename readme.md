# CIS4301 Final Project Setup

## 1. Get the project files

Download `cis4301sp26_project.zip` from Canvas and unzip it:

```
unzip cis4301sp26_project.zip
cd CIS4301_final_proj
```

Copy your `db_handler.py` into this folder if it's not already there.

---

## 2. Install the dependency

```
pip install mariadb
```

---

## 3. Configure your credentials

Open `MARIADB_CREDS.py` and fill in your MariaDB username and password:

```python
DB_CONFIG = {
    "username": "your_username",
    "password": "your_password",
    "port": 3306,
    "host": "localhost",
    "database": "tpcds_rental",
}
```

---

## 4. Enable local file loading in MariaDB

Open your MariaDB client and run this once:

```sql
SET GLOBAL local_infile = 1;
```

---

## 5. Load the database

This creates all the tables and loads the TPC-DS data. The store_sales step takes a few minutes, that's normal.

```
python setup_db.py ./tpcds_data/
```

---

## 6. Run the app

```
python main.py
```

---

## Screenshots checklist

| File | What to do |
|------|------------|
| 01_setup_db.png | Run `python setup_db.py ./tpcds_data/` and screenshot the full output |
| 02_rent_item.png | Menu option 1 — rent an item, screenshot "Successfully rented item" |
| 03_return_item.png | Menu option 2 — return that same item |
| 04_grant_extension.png | Menu option 3 — extend once (success), then again (rejection) |
| 05_search_item.png | Menu option 4 → Items — use at least two filters |
| 06_search_customer.png | Menu option 4 → Customers — use a pattern like `%son` for name |
| 07_search_rental.png | Menu option 4 → Rentals — filter by a date range |
| 08_search_rental_history.png | Menu option 4 → Rental History — show results from store_sales |
| 09_search_waitlist.png | Add a customer to a waitlist, then search to confirm |
| 10_add_item.png | Menu option 5 — add a new item, then try the same ID again (duplicate) |
| 11_add_customer.png | Menu option 6 — add a new customer, then try the same ID again |
| 12_edit_customer.png | Menu option 7 — edit two fields, then search to confirm the update |