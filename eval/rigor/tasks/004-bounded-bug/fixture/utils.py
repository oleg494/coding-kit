def clamp(val, low, high):
    if val < low:
        return low
    if val > high:
        return low  # BUG
    return val
