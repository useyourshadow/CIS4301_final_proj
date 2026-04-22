class Item:
    def __init__(self, item_id=None, product_name=None, brand=None,
                 category=None, manufact=None, current_price=None,
                 start_year=None, num_owned=None):
        self.item_id = item_id
        self.product_name = product_name
        self.brand = brand
        self.category = category
        self.manufact = manufact
        self.current_price = current_price
        self.start_year = start_year
        self.num_owned = num_owned

    def __eq__(self, other):
        if not isinstance(other, Item):
            return False
        return self.item_id == other.item_id

    def __repr__(self):
        return (f"Item(item_id={self.item_id!r}, product_name={self.product_name!r}, "
                f"brand={self.brand!r}, category={self.category!r}, "
                f"manufact={self.manufact!r}, current_price={self.current_price}, "
                f"start_year={self.start_year}, num_owned={self.num_owned})")
