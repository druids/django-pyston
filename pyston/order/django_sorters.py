from itertools import chain

from django.db.models import F

from pyston.utils import LOOKUP_SEP

from .utils import DirectionSlug
from .sorters import BaseSorter


class DjangoSorter(BaseSorter):
    """
    Sorter is used to build Django queryset order string
    """

    def __init__(self, identifiers, direction):
        super().__init__(identifiers, direction)

    def _get_order_string(self):
        return LOOKUP_SEP.join(self.identifiers)

    def get_order_term(self):
        if self.direction == DirectionSlug.DESC:
            return F(self._get_order_string()).desc(nulls_last=True)
        else:
            return F(self._get_order_string()).asc(nulls_first=True)


class ExtraDjangoSorter(DjangoSorter):
    """
    Special type of sorter that updates queryset using annotate or extra queryset method.
    For this purpose must be implement updated_queryset method which returns queryset with new column
    that is used for ordering.
    """

    def _get_order_string(self):
        return LOOKUP_SEP.join(chain(('extra_order',), self.identifiers))

    def update_queryset(self, qs):
        raise NotImplementedError
