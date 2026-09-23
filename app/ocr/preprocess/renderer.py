from app.ocr.config import configuration
from app.ocr.errors import OcrError


def render_region(page, region, dpi):
    left, bottom, right, top = region
    limits = configuration()['limits']
    scale = dpi / 72
    width, height = (right-left)*scale, (top-bottom)*scale
    if min(width, height) <= 0 or max(width, height) > limits['dimension'] or width*height > limits['pixels']:
        raise OcrError('limit')
    # Temporarily neutralize the PDF /Rotate: geometry uses unrotated PDF points.
    rotation = page.get_rotation()
    try:
        page.set_rotation(0)
        w, h = page.get_size()
        bitmap = page.render(scale=scale, crop=(left, bottom, w-right, h-top))
        try:
            return bitmap.to_pil().convert('RGB').copy()
        finally:
            bitmap.close()
    except OcrError:
        raise
    except Exception:
        raise OcrError('render') from None
    finally:
        page.set_rotation(rotation)
