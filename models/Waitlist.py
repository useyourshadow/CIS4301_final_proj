class Waitlist:
    def __init__(self, item_id=None, customer_id=None, place_in_line=None):
        self.item_id = item_id
        self.customer_id = customer_id
        self.place_in_line = place_in_line

    def __eq__(self, other):
        if not isinstance(other, Waitlist):
            return False
        return self.item_id == other.item_id and self.customer_id == other.customer_id

    def __repr__(self):
        return (f"Waitlist(item_id={self.item_id!r}, customer_id={self.customer_id!r}, "
                f"place_in_line={self.place_in_line})")
