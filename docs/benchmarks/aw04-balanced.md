# TreeTranslate AW 0.4 — измеренная производительность

Дата UTC: 2026-09-14T23:48:21.369996+00:00

Скорость на синтетическом корпусе; оценок качества нет. Все задержки — мс.
Cold: первый запрос в новом процессе; Warm: медиана повторных запросов без кэша перевода.
RAM: RSS процесса, peak sampled каждые 20 мс. VRAM: общая занятая память GPU в контрольных точках; это не пик VRAM процесса.

| Профиль | Запрошено | Устройство | Корпус | Реальный маршрут | Cold | Warm | Симв/с | Ошибки |
|---|---|---|---|---|---:|---:|---:|---|
| balanced | argos | cpu | en-ru-short | argos | 460.8 | 70.9 | 169.3 | 0 |
| balanced | argos | cpu | ru-en-short | argos | 394.0 | 42.0 | 285.7 | 0 |
| balanced | argos | cpu | zh-ru-short | argos pivot | 673.1 | 94.8 | 42.2 | 0 |
| balanced | argos | cpu | ru-zh-short | argos pivot | 550.6 | 63.8 | 391.8 | 0 |
| balanced | argos | cpu | en-ru-technical | argos | 652.4 | 300.9 | 917.1 | 0 |
| balanced | argos | cpu | ru-en-technical | argos | 466.0 | 134.9 | 2186.6 | 0 |
| balanced | argos | cpu | zh-ru-technical | argos pivot | 944.7 | 416.4 | 196.9 | 0 |
| balanced | argos | cpu | ru-zh-technical | argos pivot | 773.5 | 272.7 | 1081.9 | 0 |
| balanced | argos | cuda | en-ru-short | argos | 661.4 | 40.2 | 298.2 | 0 |
| balanced | argos | cuda | ru-en-short | argos | 592.9 | 27.0 | 445.3 | 0 |
| balanced | argos | cuda | zh-ru-short | argos pivot | 817.6 | 61.0 | 65.6 | 0 |
| balanced | argos | cuda | ru-zh-short | argos pivot | 758.0 | 53.2 | 470.2 | 0 |
| balanced | argos | cuda | en-ru-technical | argos | 714.6 | 114.7 | 2407.2 | 0 |
| balanced | argos | cuda | ru-en-technical | argos | 637.8 | 79.6 | 3704.6 | 0 |
| balanced | argos | cuda | zh-ru-technical | argos pivot | 986.9 | 173.3 | 473.2 | 0 |
| balanced | argos | cuda | ru-zh-technical | argos pivot | 891.3 | 145.3 | 2030.6 | 0 |
| balanced | m2m100 | cpu | en-ru-short | m2m100 | 829.9 | 139.5 | 86.0 | 0 |
| balanced | m2m100 | cpu | ru-en-short | m2m100 | 857.0 | 177.3 | 67.7 | 0 |
| balanced | m2m100 | cpu | zh-ru-short | m2m100 | 812.0 | 140.3 | 28.5 | 0 |
| balanced | m2m100 | cpu | ru-zh-short | m2m100 | 835.8 | 166.5 | 150.1 | 0 |
| balanced | m2m100 | cpu | en-ru-technical | m2m100 | 1433.0 | 758.5 | 363.9 | 0 |
| balanced | m2m100 | cpu | ru-en-technical | m2m100 | 1438.9 | 766.1 | 385.1 | 0 |
| balanced | m2m100 | cpu | zh-ru-technical | m2m100 | 1483.6 | 815.9 | 100.5 | 0 |
| balanced | m2m100 | cpu | ru-zh-technical | m2m100 | 1452.0 | 778.7 | 378.8 | 0 |
| balanced | m2m100 | cuda | en-ru-short | m2m100 | 1011.3 | 51.2 | 234.5 | 0 |
| balanced | m2m100 | cuda | ru-en-short | m2m100 | 1003.2 | 61.2 | 196.0 | 0 |
| balanced | m2m100 | cuda | zh-ru-short | m2m100 | 985.7 | 51.3 | 77.9 | 0 |
| balanced | m2m100 | cuda | ru-zh-short | m2m100 | 997.9 | 61.1 | 409.5 | 0 |
| balanced | m2m100 | cuda | en-ru-technical | m2m100 | 1102.6 | 150.8 | 1829.8 | 0 |
| balanced | m2m100 | cuda | ru-en-technical | m2m100 | 1106.5 | 170.9 | 1726.3 | 0 |
| balanced | m2m100 | cuda | zh-ru-technical | m2m100 | 1103.5 | 155.7 | 526.8 | 0 |
| balanced | m2m100 | cuda | ru-zh-technical | m2m100 | 1123.6 | 167.0 | 1766.1 | 0 |
| balanced | router | cpu | en-ru-short | argos | 422.0 | 63.6 | 188.6 | 0 |
| balanced | router | cpu | ru-en-short | argos | 353.0 | 29.4 | 408.1 | 0 |
| balanced | router | cpu | zh-ru-short | m2m100 | 833.5 | 120.7 | 33.1 | 0 |
| balanced | router | cpu | ru-zh-short | m2m100 | 834.3 | 173.1 | 144.4 | 0 |
| balanced | router | cpu | en-ru-technical | argos | 659.4 | 308.7 | 894.1 | 0 |
| balanced | router | cpu | ru-en-technical | argos | 455.6 | 134.3 | 2196.0 | 0 |
| balanced | router | cpu | zh-ru-technical | m2m100 | 1473.5 | 745.4 | 110.0 | 0 |
| balanced | router | cpu | ru-zh-technical | m2m100 | 1477.2 | 762.2 | 387.0 | 0 |
| balanced | router | cuda | en-ru-short | argos | 647.4 | 39.9 | 300.6 | 0 |
| balanced | router | cuda | ru-en-short | argos | 578.5 | 27.2 | 440.7 | 0 |
| balanced | router | cuda | zh-ru-short | m2m100 | 974.9 | 50.7 | 79.0 | 0 |
| balanced | router | cuda | ru-zh-short | m2m100 | 1003.8 | 62.6 | 399.5 | 0 |
| balanced | router | cuda | en-ru-technical | argos | 683.0 | 106.0 | 2603.6 | 0 |
| balanced | router | cuda | ru-en-technical | argos | 633.7 | 79.7 | 3699.5 | 0 |
| balanced | router | cuda | zh-ru-technical | m2m100 | 1102.7 | 169.4 | 484.0 | 0 |
| balanced | router | cuda | ru-zh-technical | m2m100 | 1150.9 | 169.5 | 1740.3 | 0 |
