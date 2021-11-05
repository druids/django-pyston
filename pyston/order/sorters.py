class BaseSorter:

    def __init__(self, identifiers, direction):
        self.identifiers = identifiers
        self.direction = direction

    def update_queryset(self, qs):
        return qs

    def get_order_term(self):
        raise NotImplementedError
