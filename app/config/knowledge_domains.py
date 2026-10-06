"""Shared runtime domain names; harvesting code is never imported by the GUI."""
DOMAINS = (
    ('general', 'Без специализации'),
    ('technical-core', 'Общетехническая'),
    ('automotive', 'Автомобили'),
    ('mechanical-engineering', 'Машиностроение'),
    ('manufacturing', 'Производство'),
    ('metallurgy', 'Металлургия'),
    ('materials-science', 'Материаловедение'),
    ('electrical', 'Электротехника'),
    ('electronics', 'Электроника'),
    ('software', 'Программное обеспечение'),
    ('computer-hardware', 'Компьютерное оборудование'),
    ('chemistry-engineering', 'Техническая химия'),
    ('industrial-safety', 'Промышленная безопасность'),
    ('measurement', 'Измерения'),
)


def populate_domain_combo(combo):
    for key, label in DOMAINS:
        combo.addItem(label, key)
    combo.setAccessibleName('Область перевода')
    combo.setToolTip('Область терминологии для текста и файлов. Пакеты предварительные; без специализации отраслевые термины не применяются.')
