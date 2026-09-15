# TreeTranslate AW 0.4 — измеренная производительность

Дата UTC: 2026-09-15T15:34:44.485324+00:00

Скорость на синтетическом корпусе; оценок качества нет. Все задержки — мс.
Cold: первый запрос в новом процессе; Warm: медиана повторных запросов без кэша перевода.
RAM: RSS процесса, peak sampled каждые 20 мс. VRAM: общая занятая память GPU в контрольных точках; это не пик VRAM процесса.

| Профиль | Запрошено | Устройство | Корпус | Реальный маршрут | Cold | Warm | Симв/с | Ошибки |
|---|---|---|---|---|---:|---:|---:|---|
| economy | router | cpu | en-ru-technical | argos | 991.7 | 606.6 | 455.0 | 0 |
| economy | router | cpu | ru-en-technical | argos | 586.1 | 270.5 | 1090.6 | 0 |
| economy | router | cpu | zh-ru-technical | argos pivot | 1321.8 | 857.6 | 95.6 | 0 |
| economy | router | cpu | ru-zh-technical | argos pivot | 968.0 | 479.9 | 614.8 | 0 |
| economy | router | cuda | en-ru-technical | argos | 897.9 | 257.6 | 1071.6 | 0 |
| economy | router | cuda | ru-en-technical | argos | 764.2 | 163.3 | 1806.5 | 0 |
| economy | router | cuda | zh-ru-technical | argos pivot | 1247.0 | 441.0 | 185.9 | 0 |
| economy | router | cuda | ru-zh-technical | argos pivot | 1062.7 | 329.9 | 894.3 | 0 |
| economy | router | cpu | en-ru-technical | argos | 1024.4 | 619.7 | 445.4 | 0 |
| economy | router | cpu | ru-en-technical | argos | 596.4 | 257.0 | 1147.8 | 0 |
| economy | router | cpu | zh-ru-technical | argos pivot | 1345.7 | 812.0 | 101.0 | 0 |
| economy | router | cpu | ru-zh-technical | argos pivot | 979.1 | 515.7 | 572.1 | 0 |
| fast | router | cpu | en-ru-technical | argos | 789.6 | 407.1 | 677.9 | 0 |
| fast | router | cpu | ru-en-technical | argos | 509.0 | 143.3 | 2059.2 | 0 |
| fast | router | cpu | zh-ru-technical | m2m100 | 1638.4 | 973.7 | 84.2 | 0 |
| fast | router | cpu | ru-zh-technical | m2m100 | 1740.7 | 951.3 | 310.1 | 0 |
| fast | router | cuda | en-ru-technical | argos | 865.6 | 244.6 | 1128.5 | 0 |
| fast | router | cuda | ru-en-technical | argos | 743.3 | 160.8 | 1834.4 | 0 |
| fast | router | cuda | zh-ru-technical | m2m100 | 1295.2 | 337.7 | 242.8 | 0 |
| fast | router | cuda | ru-zh-technical | m2m100 | 1293.7 | 324.8 | 908.4 | 0 |
| fast | router | cuda | en-ru-technical | argos | 850.6 | 245.0 | 1126.7 | 0 |
| fast | router | cuda | ru-en-technical | argos | 716.8 | 154.1 | 1913.7 | 0 |
| fast | router | cuda | zh-ru-technical | m2m100 | 1353.1 | 362.4 | 226.3 | 0 |
| fast | router | cuda | ru-zh-technical | m2m100 | 1288.3 | 321.2 | 918.5 | 0 |
| balanced | router | cpu | en-ru-technical | argos | 1006.3 | 576.6 | 478.6 | 0 |
| balanced | router | cpu | ru-en-technical | argos | 622.5 | 200.7 | 1469.8 | 0 |
| balanced | router | cpu | zh-ru-technical | m2m100 | 2303.9 | 1580.4 | 51.9 | 0 |
| balanced | router | cpu | ru-zh-technical | m2m100 | 2117.5 | 1315.0 | 224.3 | 0 |
| balanced | router | cuda | en-ru-technical | argos | 925.5 | 339.5 | 812.9 | 0 |
| balanced | router | cuda | ru-en-technical | argos | 795.4 | 202.6 | 1456.4 | 0 |
| balanced | router | cuda | zh-ru-technical | m2m100 | 1378.6 | 430.1 | 190.7 | 0 |
| balanced | router | cuda | ru-zh-technical | m2m100 | 1351.4 | 376.0 | 784.7 | 0 |
| balanced | router | cuda | en-ru-technical | argos | 929.5 | 367.1 | 751.9 | 0 |
| balanced | router | cuda | ru-en-technical | argos | 792.1 | 206.9 | 1426.1 | 0 |
| balanced | router | cuda | zh-ru-technical | m2m100 | 1355.9 | 412.3 | 198.9 | 0 |
| balanced | router | cuda | ru-zh-technical | m2m100 | 1325.5 | 390.7 | 755.1 | 0 |
| turbo | router | cpu | en-ru-technical | argos | 843.5 | 490.1 | 563.2 | 0 |
| turbo | router | cpu | ru-en-technical | argos | 551.0 | 174.8 | 1687.5 | 0 |
| turbo | router | cpu | zh-ru-technical | m2m100 | 1836.4 | 1190.9 | 68.9 | 0 |
| turbo | router | cpu | ru-zh-technical | m2m100 | 1871.0 | 1211.9 | 243.4 | 0 |
| turbo | router | cuda | en-ru-technical | argos | 993.1 | 313.7 | 879.8 | 0 |
| turbo | router | cuda | ru-en-technical | argos | 814.8 | 255.1 | 1156.6 | 0 |
| turbo | router | cuda | zh-ru-technical | m2m100 | 1392.9 | 416.7 | 196.8 | 0 |
| turbo | router | cuda | ru-zh-technical | m2m100 | 1428.0 | 403.2 | 731.7 | 0 |
| turbo | router | cuda | en-ru-technical | argos | 971.5 | 343.8 | 802.9 | 0 |
| turbo | router | cuda | ru-en-technical | argos | 790.7 | 244.3 | 1207.8 | 0 |
| turbo | router | cuda | zh-ru-technical | m2m100 | 1375.8 | 401.6 | 204.2 | 0 |
| turbo | router | cuda | ru-zh-technical | m2m100 | 1421.9 | 377.1 | 782.3 | 0 |
| maximum | router | cpu | en-ru-technical | argos | 1188.2 | 706.3 | 390.8 | 0 |
| maximum | router | cpu | ru-en-technical | argos | 605.4 | 250.5 | 1177.5 | 0 |
| maximum | router | cpu | zh-ru-technical | m2m100 | 2628.4 | 1852.8 | 44.3 | 0 |
| maximum | router | cpu | ru-zh-technical | m2m100 | 2370.1 | 1644.3 | 179.4 | 0 |
| maximum | router | cuda | en-ru-technical | argos | 996.0 | 354.3 | 779.0 | 0 |
| maximum | router | cuda | ru-en-technical | argos | 807.8 | 243.5 | 1211.3 | 0 |
| maximum | router | cuda | zh-ru-technical | m2m100 | 1426.7 | 477.9 | 171.6 | 0 |
| maximum | router | cuda | ru-zh-technical | m2m100 | 1428.4 | 424.9 | 694.3 | 0 |
| maximum | router | cuda | en-ru-technical | argos | 978.4 | 349.6 | 789.6 | 0 |
| maximum | router | cuda | ru-en-technical | argos | 796.6 | 215.7 | 1367.6 | 0 |
| maximum | router | cuda | zh-ru-technical | m2m100 | 1381.8 | 431.1 | 190.2 | 0 |
| maximum | router | cuda | ru-zh-technical | m2m100 | 1333.9 | 387.4 | 761.5 | 0 |
| automatic | router | cpu | en-ru-technical | argos | 976.6 | 553.9 | 498.3 | 0 |
| automatic | router | cpu | ru-en-technical | argos | 567.2 | 207.0 | 1425.4 | 0 |
| automatic | router | cpu | zh-ru-technical | m2m100 | 2260.3 | 1837.5 | 44.6 | 0 |
| automatic | router | cpu | ru-zh-technical | m2m100 | 2293.6 | 1528.7 | 193.0 | 0 |
| automatic | router | cuda | en-ru-technical | argos | 1068.1 | 385.8 | 715.5 | 0 |
| automatic | router | cuda | ru-en-technical | argos | 867.6 | 221.9 | 1329.4 | 0 |
| automatic | router | cuda | zh-ru-technical | m2m100 | 1445.1 | 436.6 | 187.8 | 0 |
| automatic | router | cuda | ru-zh-technical | m2m100 | 1376.6 | 403.8 | 730.5 | 0 |
| automatic | router | cuda | en-ru-technical | argos | 972.5 | 357.0 | 773.1 | 0 |
| automatic | router | cuda | ru-en-technical | argos | 802.0 | 228.9 | 1288.8 | 0 |
| automatic | router | cuda | zh-ru-technical | m2m100 | 1397.8 | 455.9 | 179.9 | 0 |
| automatic | router | cuda | ru-zh-technical | m2m100 | 1521.4 | 414.7 | 711.3 | 0 |
