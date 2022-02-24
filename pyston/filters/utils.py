from pyston.utils import StrEnum


class LogicalOperatorSlug(StrEnum):

    AND = 'AND'
    OR = 'OR'
    NOT = 'NOT'


class OperatorSlug(StrEnum):

    GT = 'gt'
    LT = 'lt'
    EQ = 'eq'
    NEQ = 'neq'
    LTE = 'lte'
    GTE = 'gte'
    CONTAINS = 'contains'
    ICONTAINS = 'icontains'
    RANGE = 'range'
    EXACT = 'exact'
    IEXACT = 'iexact'
    STARTSWITH = 'startswith'
    ISTARTSWITH = 'istartswith'
    ENDSWITH = 'endswith'
    IENDSWITH = 'iendswith'
    IN = 'in'
    ALL = 'all'
    ISNULL = 'isnull'
