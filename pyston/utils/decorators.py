__all__ = (
    'allow_tags',
    'humanized',
    'filter_class',
    'filter_by',
    'order_by',
    'sorter_class',
)


def allow_tags(func):
    """Allows HTML tags to be returned from resource without escaping"""
    if isinstance(func, property):
        func = func.fget
    func.allow_tags = True
    return func


def humanized(humanized_func, **humanized_func_kwargs):
    """Sets 'humanized' function to method or property."""
    def decorator(func):
        if isinstance(func, property):
            func = func.fget

        def _humanized_func(*args, **kwargs):
            kwargs.update(humanized_func_kwargs)
            return humanized_func(*args, **kwargs)
        func.humanized = _humanized_func
        return func
    return decorator


def filter_class(filter_class):
    """Sets 'filter' class (this attribute is used inside grid and rest)."""
    def decorator(func):
        if isinstance(func, property):
            func = func.fget
        func.filter = filter_class
        return func
    return decorator


def filter_by(field_name):
    """Sets 'field name' (this is used for grid filtering)"""
    def decorator(func):
        if isinstance(func, property):
            func = func.fget
        func.filter_by = field_name
        return func
    return decorator


def order_by(field_name):
    """Sets 'field name' (this is used for grid ordering)"""
    def decorator(func):
        if isinstance(func, property):
            func = func.fget
        func.order_by = field_name
        return func
    return decorator


def sorter_class(sorter_class):
    """Sets 'sorter' class (this attribute is used inside grid and rest)."""
    def decorator(func):
        if isinstance(func, property):
            func = func.fget
        func.sorter = sorter_class
        return func
    return decorator
