def restore_point(x, y, width, height, clockwise):
    """Coordinates in a clockwise-rotated image back to original top-left pixels."""
    return {0: (x, y), 90: (y, height-x), 180: (width-x, height-y), 270: (width-y, x)}[clockwise]


def pixel_to_pdf(x, y, region, pixel_size):
    left, bottom, right, top = region
    width, height = pixel_size
    return left + x / width * (right-left), top - y / height * (top-bottom)
