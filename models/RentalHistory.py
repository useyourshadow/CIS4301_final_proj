class RentalHistory:
    def __init__(self, item_id=None, customer_id=None, rental_date=None,
                 due_date=None, return_date=None):
        self.item_id = item_id
        self.customer_id = customer_id
        self.rental_date = rental_date
        self.due_date = due_date
        self.return_date = return_date

    def __eq__(self, other):
        if not isinstance(other, RentalHistory):
            return False
        return (self.item_id == other.item_id and
                self.customer_id == other.customer_id and
                self.rental_date == other.rental_date)

    def __repr__(self):
        return (f"RentalHistory(item_id={self.item_id!r}, customer_id={self.customer_id!r}, "
                f"rental_date={self.rental_date!r}, due_date={self.due_date!r}, "
                f"return_date={self.return_date!r})")
