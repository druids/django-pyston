from itertools import chain

from pyston.utils import rfs, LOOKUP_SEP

from .utils import DIRECTION


class DefaultSorter:
    """
    Sorter is used to build Django queryset order string
    """

    def __init__(self, identifiers, direction):
        self.identifiers = identifiers
        self.direction = direction
        self.order_string = self._get_order_string()

    def _get_order_string(self):
        return LOOKUP_SEP.join(self.identifiers)

    def get_full_order_string(self):
        return '{direction}{order_string}'.format(
            direction='-' if self.direction == DIRECTION.DESC else '',
            order_string=self.order_string
        )


class ExtraSorter(DefaultSorter):
    """
    Special type of sorter that updates queryset using annotate or extra queryset method.
    For this purpose must be implement updated_queryset method which returns queryset with new column
    that is used for ordering.
    """

    def _get_order_string(self):
        return LOOKUP_SEP.join(chain(('extra_order',), self.identifiers))

    def update_queryset(self, qs):
        raise NotImplementedError
