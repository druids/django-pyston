def allow_tags(func=None, allowed=True):
    """
    Sets 'short_description' attribute (this attribute is used by list_display and forms).
    """
    def decorator(func):
        if isinstance(func, property):
            func = func.fget
        func.allow_tags = allowed
        return func

    if func:
        return decorator(func)
    else:
        return decorator