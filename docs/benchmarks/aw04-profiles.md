# TreeTranslate AW 0.4 — измеренная производительность

Дата UTC: 2026-09-15T07:12:10.664682+00:00

Скорость на синтетическом корпусе; оценок качества нет. Все задержки — мс.
Cold: первый запрос в новом процессе; Warm: медиана повторных запросов без кэша перевода.
RAM: RSS процесса, peak sampled каждые 20 мс. VRAM: общая занятая память GPU в контрольных точках; это не пик VRAM процесса.

| Профиль | Запрошено | Устройство | Корпус | Реальный маршрут | Cold | Warm | Симв/с | Ошибки |
|---|---|---|---|---|---:|---:|---:|---|
| economy | router | cpu | en-ru-technical | argos | 1225.0 | 268.0 | 1030.0 | 0 |
| economy | router | cpu | ru-en-technical | argos | 621.9 | 143.8 | 2051.2 | 0 |
| economy | router | cpu | zh-ru-technical | argos pivot | 940.3 | 349.2 | 234.8 | 0 |
| economy | router | cpu | ru-zh-technical | argos pivot | 828.1 | 223.9 | 1317.8 | 0 |
| economy | router | cuda | en-ru-technical | argos | 1737.5 | 92.7 | 2977.8 | 0 |
| economy | router | cuda | ru-en-technical | argos | 617.5 | 69.6 | 4241.0 | 0 |
| economy | router | cuda | zh-ru-technical | argos pivot | 921.6 | 139.9 | 586.3 | 0 |
| economy | router | cuda | ru-zh-technical | argos pivot | 873.5 | 119.5 | 2467.6 | 0 |
| fast | router | cpu | en-ru-technical | argos | 558.2 | 191.7 | 1440.1 | 0 |
| fast | router | cpu | ru-en-technical | argos | 431.8 | 88.9 | 3319.3 | 0 |
| fast | router | cpu | zh-ru-technical | m2m100 | 1543.0 | 537.0 | 152.7 | 0 |
| fast | router | cpu | ru-zh-technical | m2m100 | 1251.1 | 519.0 | 568.4 | 0 |
| fast | router | cuda | en-ru-technical | argos | 698.2 | 91.6 | 3011.9 | 0 |
| fast | router | cuda | ru-en-technical | argos | 632.6 | 61.0 | 4836.1 | 0 |
| fast | router | cuda | zh-ru-technical | m2m100 | 1070.6 | 131.6 | 622.9 | 0 |
| fast | router | cuda | ru-zh-technical | m2m100 | 1179.3 | 143.5 | 2055.2 | 0 |
| turbo | router | cpu | en-ru-technical | argos | 566.1 | 180.5 | 1529.1 | 0 |
| turbo | router | cpu | ru-en-technical | argos | 434.9 | 86.9 | 3394.0 | 0 |
| turbo | router | cpu | zh-ru-technical | m2m100 | 1171.5 | 441.5 | 185.7 | 0 |
| turbo | router | cpu | ru-zh-technical | m2m100 | 1204.7 | 522.5 | 564.6 | 0 |
| turbo | router | cuda | en-ru-technical | argos | 760.5 | 92.1 | 2995.3 | 0 |
| turbo | router | cuda | ru-en-technical | argos | 628.4 | 64.2 | 4598.0 | 0 |
| turbo | router | cuda | zh-ru-technical | m2m100 | 1081.5 | 145.7 | 562.7 | 0 |
| turbo | router | cuda | ru-zh-technical | m2m100 | 1095.4 | 145.9 | 2021.6 | 0 |
| maximum | router | cpu | en-ru-technical | m2m100 | 1622.3 | 916.6 | 301.1 | 0 |
| maximum | router | cpu | ru-en-technical | m2m100 | 1750.0 | 948.1 | 311.2 | 0 |
| maximum | router | cpu | zh-ru-technical | m2m100 | 1727.6 | 922.1 | 88.9 | 0 |
| maximum | router | cpu | ru-zh-technical | m2m100 | 1622.0 | 943.8 | 312.6 | 0 |
| maximum | router | cuda | en-ru-technical | m2m100 | 1154.6 | 151.7 | 1819.7 | 0 |
| maximum | router | cuda | ru-en-technical | m2m100 | 1118.1 | 168.1 | 1755.1 | 0 |
| maximum | router | cuda | zh-ru-technical | m2m100 | 1087.9 | 181.7 | 451.4 | 0 |
| maximum | router | cuda | ru-zh-technical | m2m100 | 1145.7 | 176.2 | 1674.6 | 0 |
| automatic | router | cpu | en-ru-technical | argos | 688.5 | 316.8 | 871.3 | 0 |
| automatic | router | cpu | ru-en-technical | argos | 482.5 | 144.9 | 2035.9 | 0 |
| automatic | router | cpu | zh-ru-technical | m2m100 | 1613.4 | 1042.2 | 78.7 | 0 |
| automatic | router | cpu | ru-zh-technical | m2m100 | 1556.9 | 1023.0 | 288.4 | 0 |
| automatic | router | cuda | en-ru-technical | argos | 798.5 | 114.7 | 2406.7 | 0 |
| automatic | router | cuda | ru-en-technical | argos | 643.6 | 75.5 | 3908.3 | 0 |
| automatic | router | cuda | zh-ru-technical | m2m100 | 1158.7 | 159.7 | 513.6 | 0 |
| automatic | router | cuda | ru-zh-technical | m2m100 | 1080.8 | 167.5 | 1761.0 | 0 |
