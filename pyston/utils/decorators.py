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
            return humanized_func(*args, **kwargs, **humanized_func_kwargs)
        func.humanized = _humanized_func
        return func
    return decorator
