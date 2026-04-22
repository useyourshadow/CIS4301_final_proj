class Rental:
    def __init__(self, item_id=None, customer_id=None, rental_date=None, due_date=None):
        self.item_id = item_id
        self.customer_id = customer_id
        self.rental_date = rental_date
        self.due_date = due_date

    def __eq__(self, other):
        if not isinstance(other, Rental):
            return False
        return self.item_id == other.item_id and self.customer_id == other.customer_id

    def __repr__(self):
        return (f"Rental(item_id={self.item_id!r}, customer_id={self.customer_id!r}, "
                f"rental_date={self.rental_date!r}, due_date={self.due_date!r})")
