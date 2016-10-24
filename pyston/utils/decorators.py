def allow_tags(func):
    """Allows HTML tags to be returned from resource without escaping"""
    if isinstance(func, property):
        func = func.fget
    func.allow_tags = True
    return func
