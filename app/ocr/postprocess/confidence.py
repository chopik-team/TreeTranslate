from app.ocr.config import configuration


def confidence_band(value):
    limits = configuration()['confidence']
    return 'low' if value < limits['low'] else 'medium' if value < limits['high'] else 'high'
