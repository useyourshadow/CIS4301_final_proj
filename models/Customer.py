class Customer:
    def __init__(self, customer_id=None, name=None, address=None, email=None):
        self.customer_id = customer_id
        self.name = name
        self.address = address
        self.email = email

    def __eq__(self, other):
        if not isinstance(other, Customer):
            return False
        return self.customer_id == other.customer_id

    def __repr__(self):
        return (f"Customer(customer_id={self.customer_id!r}, name={self.name!r}, "
                f"address={self.address!r}, email={self.email!r})")
