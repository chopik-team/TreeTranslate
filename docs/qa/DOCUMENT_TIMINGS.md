# Журнал замеров TreeTranslate

Данные из локальных логов. Время процессов включительное: вложенные процессы нельзя складывать с родительскими.

Неуспешные прогоны сохраняются для диагностики, но не участвуют в расчёте ETA. Содержимое документов не записывается.

| Дата / run | Результат | Страницы / сегменты | OCR-области | Всего, с | Извлечение, с | Перевод, с | Запись, с | Прогноз, с |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| 2026-10-01 14:41:00,924 / `242b93c1ec96` | ERROR | 4 / 108 | 8 | 291.55 | 247.49 | 22.70 | 12.93 | — |
| 2026-10-01 15:36:19,144 / `b6cf76a3e45f` | COMPLETED | 4 / 108 | 8 | 276.30 | 230.95 | 20.32 | 17.01 | — |
| 2026-10-01 16:24:31,542 / `c120c825e95d` | ERROR | 22 / 365 | 99 | 54.73 | 38.53 | 8.83 | 4.42 | — |
| 2026-10-01 16:26:21,213 / `79d8286a3347` | COMPLETED | 22 / 365 | 99 | 158.03 | 40.48 | 41.55 | 51.42 | — |
| 2026-10-01 16:32:09,748 / `a413b3512dc5` | COMPLETED | 22 / 365 | 99 | 138.59 | 35.71 | 36.76 | 45.08 | — |
| 2026-10-01 17:02:42,051 / `a20bc6f74a87` | COMPLETED | 22 / 365 | 99 | 146.38 | 36.52 | 38.76 | 48.13 | — |
| 2026-10-01 17:14:35,508 / `db196a270435` | COMPLETED | 22 / 365 | 99 | 99.81 | 33.65 | 16.21 | 32.16 | — |
| 2026-10-01 17:18:18,228 / `0cf9ba176ce1` | COMPLETED | 22 / 365 | 99 | 70.53 | 34.24 | 12.60 | 8.07 | — |
| 2026-10-01 17:25:24,755 / `28e8b0b4e3c5` | COMPLETED | 22 / 365 | 99 | 71.44 | 34.97 | 12.15 | 8.71 | — |
| 2026-10-01 17:32:55,525 / `5582364caf97` | COMPLETED | 22 / 365 | 99 | 76.03 | 36.41 | 12.68 | 9.91 | — |

## Формат и способ загрузки документов

Папка не означает ZIP: происхождение из ранее распакованного архива нельзя определить по пути. В старых логах отсутствующие признаки обозначены как неизвестные.

| Run | Документ | Формат / тип | Вход | Контейнер / относительный путь | Байты / символы |
|---|---|---|---|---|---:|
| 242b93c1ec96 | C:\Users\PC\Downloads\维修程序.pdf.pdf | pdf / неизвестен | неизвестен | — / — | 192879 / — |
| b6cf76a3e45f | C:\Users\PC\Downloads\维修程序.pdf.pdf | pdf / неизвестен | неизвестен | — / — | 192879 / — |
| c120c825e95d | C:\Users\PC\AppData\Local\Temp\TreeTranslate-zip-j5w_iwo5\input\一般事项.pdf | pdf / PDF смешанный: текст + OCR | zip | C:\Users\PC\Downloads\车身尺寸.zip / 一般事项.pdf | 65267 / 385 |
| c120c825e95d | C:\Users\PC\AppData\Local\Temp\TreeTranslate-zip-j5w_iwo5\input\内部\车身维修.pdf | pdf / PDF смешанный: текст + OCR | zip | C:\Users\PC\Downloads\车身尺寸.zip / 内部\车身维修.pdf | 820623 / 718 |
| c120c825e95d | C:\Users\PC\AppData\Local\Temp\TreeTranslate-zip-j5w_iwo5\input\前车身\车身维修.pdf | pdf / PDF смешанный: текст + OCR | zip | C:\Users\PC\Downloads\车身尺寸.zip / 前车身\车身维修.pdf | 697390 / 433 |
| c120c825e95d | C:\Users\PC\AppData\Local\Temp\TreeTranslate-zip-j5w_iwo5\input\后车身\车身维修.pdf | pdf / PDF смешанный: текст + OCR | zip | C:\Users\PC\Downloads\车身尺寸.zip / 后车身\车身维修.pdf | 245729 / 167 |
| c120c825e95d | C:\Users\PC\AppData\Local\Temp\TreeTranslate-zip-j5w_iwo5\input\车身侧面\车身维修.pdf | pdf / PDF смешанный: текст + OCR | zip | C:\Users\PC\Downloads\车身尺寸.zip / 车身侧面\车身维修.pdf | 252380 / 380 |
| c120c825e95d | C:\Users\PC\AppData\Local\Temp\TreeTranslate-zip-j5w_iwo5\input\车身底部\车身维修.pdf | pdf / PDF смешанный: текст + OCR | zip | C:\Users\PC\Downloads\车身尺寸.zip / 车身底部\车身维修.pdf | 360072 / 594 |
| c120c825e95d | C:\Users\PC\AppData\Local\Temp\TreeTranslate-zip-j5w_iwo5\input\车身面板间隙\车身维修.pdf | pdf / PDF смешанный: текст + OCR | zip | C:\Users\PC\Downloads\车身尺寸.zip / 车身面板间隙\车身维修.pdf | 128071 / 266 |
| 79d8286a3347 | C:\Users\PC\AppData\Local\Temp\TreeTranslate-zip-fgd970tz\input\一般事项.pdf | pdf / PDF смешанный: текст + OCR | zip | C:\Users\PC\Downloads\车身尺寸.zip / 一般事项.pdf | 65267 / 385 |
| 79d8286a3347 | C:\Users\PC\AppData\Local\Temp\TreeTranslate-zip-fgd970tz\input\内部\车身维修.pdf | pdf / PDF смешанный: текст + OCR | zip | C:\Users\PC\Downloads\车身尺寸.zip / 内部\车身维修.pdf | 820623 / 718 |
| 79d8286a3347 | C:\Users\PC\AppData\Local\Temp\TreeTranslate-zip-fgd970tz\input\前车身\车身维修.pdf | pdf / PDF смешанный: текст + OCR | zip | C:\Users\PC\Downloads\车身尺寸.zip / 前车身\车身维修.pdf | 697390 / 433 |
| 79d8286a3347 | C:\Users\PC\AppData\Local\Temp\TreeTranslate-zip-fgd970tz\input\后车身\车身维修.pdf | pdf / PDF смешанный: текст + OCR | zip | C:\Users\PC\Downloads\车身尺寸.zip / 后车身\车身维修.pdf | 245729 / 167 |
| 79d8286a3347 | C:\Users\PC\AppData\Local\Temp\TreeTranslate-zip-fgd970tz\input\车身侧面\车身维修.pdf | pdf / PDF смешанный: текст + OCR | zip | C:\Users\PC\Downloads\车身尺寸.zip / 车身侧面\车身维修.pdf | 252380 / 380 |
| 79d8286a3347 | C:\Users\PC\AppData\Local\Temp\TreeTranslate-zip-fgd970tz\input\车身底部\车身维修.pdf | pdf / PDF смешанный: текст + OCR | zip | C:\Users\PC\Downloads\车身尺寸.zip / 车身底部\车身维修.pdf | 360072 / 594 |
| 79d8286a3347 | C:\Users\PC\AppData\Local\Temp\TreeTranslate-zip-fgd970tz\input\车身面板间隙\车身维修.pdf | pdf / PDF смешанный: текст + OCR | zip | C:\Users\PC\Downloads\车身尺寸.zip / 车身面板间隙\车身维修.pdf | 128071 / 266 |
| a413b3512dc5 | C:\Users\PC\AppData\Local\Temp\TreeTranslate-zip-6axbeln0\input\一般事项.pdf | pdf / PDF смешанный: текст + OCR | zip | C:\Users\PC\Downloads\车身尺寸.zip / 一般事项.pdf | 65267 / 385 |
| a413b3512dc5 | C:\Users\PC\AppData\Local\Temp\TreeTranslate-zip-6axbeln0\input\内部\车身维修.pdf | pdf / PDF смешанный: текст + OCR | zip | C:\Users\PC\Downloads\车身尺寸.zip / 内部\车身维修.pdf | 820623 / 718 |
| a413b3512dc5 | C:\Users\PC\AppData\Local\Temp\TreeTranslate-zip-6axbeln0\input\前车身\车身维修.pdf | pdf / PDF смешанный: текст + OCR | zip | C:\Users\PC\Downloads\车身尺寸.zip / 前车身\车身维修.pdf | 697390 / 433 |
| a413b3512dc5 | C:\Users\PC\AppData\Local\Temp\TreeTranslate-zip-6axbeln0\input\后车身\车身维修.pdf | pdf / PDF смешанный: текст + OCR | zip | C:\Users\PC\Downloads\车身尺寸.zip / 后车身\车身维修.pdf | 245729 / 167 |
| a413b3512dc5 | C:\Users\PC\AppData\Local\Temp\TreeTranslate-zip-6axbeln0\input\车身侧面\车身维修.pdf | pdf / PDF смешанный: текст + OCR | zip | C:\Users\PC\Downloads\车身尺寸.zip / 车身侧面\车身维修.pdf | 252380 / 380 |
| a413b3512dc5 | C:\Users\PC\AppData\Local\Temp\TreeTranslate-zip-6axbeln0\input\车身底部\车身维修.pdf | pdf / PDF смешанный: текст + OCR | zip | C:\Users\PC\Downloads\车身尺寸.zip / 车身底部\车身维修.pdf | 360072 / 594 |
| a413b3512dc5 | C:\Users\PC\AppData\Local\Temp\TreeTranslate-zip-6axbeln0\input\车身面板间隙\车身维修.pdf | pdf / PDF смешанный: текст + OCR | zip | C:\Users\PC\Downloads\车身尺寸.zip / 车身面板间隙\车身维修.pdf | 128071 / 266 |
| a20bc6f74a87 | C:\Users\PC\AppData\Local\Temp\TreeTranslate-zip-s7aubwvq\input\一般事项.pdf | pdf / PDF смешанный: текст + OCR | zip | C:\Users\PC\Downloads\车身尺寸.zip / 一般事项.pdf | 65267 / 385 |
| a20bc6f74a87 | C:\Users\PC\AppData\Local\Temp\TreeTranslate-zip-s7aubwvq\input\内部\车身维修.pdf | pdf / PDF смешанный: текст + OCR | zip | C:\Users\PC\Downloads\车身尺寸.zip / 内部\车身维修.pdf | 820623 / 718 |
| a20bc6f74a87 | C:\Users\PC\AppData\Local\Temp\TreeTranslate-zip-s7aubwvq\input\前车身\车身维修.pdf | pdf / PDF смешанный: текст + OCR | zip | C:\Users\PC\Downloads\车身尺寸.zip / 前车身\车身维修.pdf | 697390 / 433 |
| a20bc6f74a87 | C:\Users\PC\AppData\Local\Temp\TreeTranslate-zip-s7aubwvq\input\后车身\车身维修.pdf | pdf / PDF смешанный: текст + OCR | zip | C:\Users\PC\Downloads\车身尺寸.zip / 后车身\车身维修.pdf | 245729 / 167 |
| a20bc6f74a87 | C:\Users\PC\AppData\Local\Temp\TreeTranslate-zip-s7aubwvq\input\车身侧面\车身维修.pdf | pdf / PDF смешанный: текст + OCR | zip | C:\Users\PC\Downloads\车身尺寸.zip / 车身侧面\车身维修.pdf | 252380 / 380 |
| a20bc6f74a87 | C:\Users\PC\AppData\Local\Temp\TreeTranslate-zip-s7aubwvq\input\车身底部\车身维修.pdf | pdf / PDF смешанный: текст + OCR | zip | C:\Users\PC\Downloads\车身尺寸.zip / 车身底部\车身维修.pdf | 360072 / 594 |
| a20bc6f74a87 | C:\Users\PC\AppData\Local\Temp\TreeTranslate-zip-s7aubwvq\input\车身面板间隙\车身维修.pdf | pdf / PDF смешанный: текст + OCR | zip | C:\Users\PC\Downloads\车身尺寸.zip / 车身面板间隙\车身维修.pdf | 128071 / 266 |
| db196a270435 | C:\Users\PC\AppData\Local\Temp\TreeTranslate-zip-hbhs8r6j\input\一般事项.pdf | pdf / PDF смешанный: текст + OCR | zip | C:\Users\PC\Downloads\车身尺寸.zip / 一般事项.pdf | 65267 / 385 |
| db196a270435 | C:\Users\PC\AppData\Local\Temp\TreeTranslate-zip-hbhs8r6j\input\内部\车身维修.pdf | pdf / PDF смешанный: текст + OCR | zip | C:\Users\PC\Downloads\车身尺寸.zip / 内部\车身维修.pdf | 820623 / 718 |
| db196a270435 | C:\Users\PC\AppData\Local\Temp\TreeTranslate-zip-hbhs8r6j\input\前车身\车身维修.pdf | pdf / PDF смешанный: текст + OCR | zip | C:\Users\PC\Downloads\车身尺寸.zip / 前车身\车身维修.pdf | 697390 / 433 |
| db196a270435 | C:\Users\PC\AppData\Local\Temp\TreeTranslate-zip-hbhs8r6j\input\后车身\车身维修.pdf | pdf / PDF смешанный: текст + OCR | zip | C:\Users\PC\Downloads\车身尺寸.zip / 后车身\车身维修.pdf | 245729 / 167 |
| db196a270435 | C:\Users\PC\AppData\Local\Temp\TreeTranslate-zip-hbhs8r6j\input\车身侧面\车身维修.pdf | pdf / PDF смешанный: текст + OCR | zip | C:\Users\PC\Downloads\车身尺寸.zip / 车身侧面\车身维修.pdf | 252380 / 380 |
| db196a270435 | C:\Users\PC\AppData\Local\Temp\TreeTranslate-zip-hbhs8r6j\input\车身底部\车身维修.pdf | pdf / PDF смешанный: текст + OCR | zip | C:\Users\PC\Downloads\车身尺寸.zip / 车身底部\车身维修.pdf | 360072 / 594 |
| db196a270435 | C:\Users\PC\AppData\Local\Temp\TreeTranslate-zip-hbhs8r6j\input\车身面板间隙\车身维修.pdf | pdf / PDF смешанный: текст + OCR | zip | C:\Users\PC\Downloads\车身尺寸.zip / 车身面板间隙\车身维修.pdf | 128071 / 266 |
| 0cf9ba176ce1 | C:\Users\PC\AppData\Local\Temp\TreeTranslate-zip-87f1hgl8\input\一般事项.pdf | pdf / PDF смешанный: текст + OCR | zip | C:\Users\PC\Downloads\车身尺寸.zip / 一般事项.pdf | 65267 / 385 |
| 0cf9ba176ce1 | C:\Users\PC\AppData\Local\Temp\TreeTranslate-zip-87f1hgl8\input\内部\车身维修.pdf | pdf / PDF смешанный: текст + OCR | zip | C:\Users\PC\Downloads\车身尺寸.zip / 内部\车身维修.pdf | 820623 / 718 |
| 0cf9ba176ce1 | C:\Users\PC\AppData\Local\Temp\TreeTranslate-zip-87f1hgl8\input\前车身\车身维修.pdf | pdf / PDF смешанный: текст + OCR | zip | C:\Users\PC\Downloads\车身尺寸.zip / 前车身\车身维修.pdf | 697390 / 433 |
| 0cf9ba176ce1 | C:\Users\PC\AppData\Local\Temp\TreeTranslate-zip-87f1hgl8\input\后车身\车身维修.pdf | pdf / PDF смешанный: текст + OCR | zip | C:\Users\PC\Downloads\车身尺寸.zip / 后车身\车身维修.pdf | 245729 / 167 |
| 0cf9ba176ce1 | C:\Users\PC\AppData\Local\Temp\TreeTranslate-zip-87f1hgl8\input\车身侧面\车身维修.pdf | pdf / PDF смешанный: текст + OCR | zip | C:\Users\PC\Downloads\车身尺寸.zip / 车身侧面\车身维修.pdf | 252380 / 380 |
| 0cf9ba176ce1 | C:\Users\PC\AppData\Local\Temp\TreeTranslate-zip-87f1hgl8\input\车身底部\车身维修.pdf | pdf / PDF смешанный: текст + OCR | zip | C:\Users\PC\Downloads\车身尺寸.zip / 车身底部\车身维修.pdf | 360072 / 594 |
| 0cf9ba176ce1 | C:\Users\PC\AppData\Local\Temp\TreeTranslate-zip-87f1hgl8\input\车身面板间隙\车身维修.pdf | pdf / PDF смешанный: текст + OCR | zip | C:\Users\PC\Downloads\车身尺寸.zip / 车身面板间隙\车身维修.pdf | 128071 / 266 |
| 28e8b0b4e3c5 | C:\Users\PC\AppData\Local\Temp\TreeTranslate-zip-otot74l9\input\一般事项.pdf | pdf / PDF смешанный: текст + OCR | zip | C:\Users\PC\Downloads\车身尺寸.zip / 一般事项.pdf | 65267 / 385 |
| 28e8b0b4e3c5 | C:\Users\PC\AppData\Local\Temp\TreeTranslate-zip-otot74l9\input\内部\车身维修.pdf | pdf / PDF смешанный: текст + OCR | zip | C:\Users\PC\Downloads\车身尺寸.zip / 内部\车身维修.pdf | 820623 / 718 |
| 28e8b0b4e3c5 | C:\Users\PC\AppData\Local\Temp\TreeTranslate-zip-otot74l9\input\前车身\车身维修.pdf | pdf / PDF смешанный: текст + OCR | zip | C:\Users\PC\Downloads\车身尺寸.zip / 前车身\车身维修.pdf | 697390 / 433 |
| 28e8b0b4e3c5 | C:\Users\PC\AppData\Local\Temp\TreeTranslate-zip-otot74l9\input\后车身\车身维修.pdf | pdf / PDF смешанный: текст + OCR | zip | C:\Users\PC\Downloads\车身尺寸.zip / 后车身\车身维修.pdf | 245729 / 167 |
| 28e8b0b4e3c5 | C:\Users\PC\AppData\Local\Temp\TreeTranslate-zip-otot74l9\input\车身侧面\车身维修.pdf | pdf / PDF смешанный: текст + OCR | zip | C:\Users\PC\Downloads\车身尺寸.zip / 车身侧面\车身维修.pdf | 252380 / 380 |
| 28e8b0b4e3c5 | C:\Users\PC\AppData\Local\Temp\TreeTranslate-zip-otot74l9\input\车身底部\车身维修.pdf | pdf / PDF смешанный: текст + OCR | zip | C:\Users\PC\Downloads\车身尺寸.zip / 车身底部\车身维修.pdf | 360072 / 594 |
| 28e8b0b4e3c5 | C:\Users\PC\AppData\Local\Temp\TreeTranslate-zip-otot74l9\input\车身面板间隙\车身维修.pdf | pdf / PDF смешанный: текст + OCR | zip | C:\Users\PC\Downloads\车身尺寸.zip / 车身面板间隙\车身维修.pdf | 128071 / 266 |
| 5582364caf97 | C:\Users\PC\AppData\Local\Temp\TreeTranslate-zip-i1pyxwgv\input\一般事项.pdf | pdf / PDF смешанный: текст + OCR | zip | C:\Users\PC\Downloads\车身尺寸.zip / 一般事项.pdf | 65267 / 385 |
| 5582364caf97 | C:\Users\PC\AppData\Local\Temp\TreeTranslate-zip-i1pyxwgv\input\内部\车身维修.pdf | pdf / PDF смешанный: текст + OCR | zip | C:\Users\PC\Downloads\车身尺寸.zip / 内部\车身维修.pdf | 820623 / 718 |
| 5582364caf97 | C:\Users\PC\AppData\Local\Temp\TreeTranslate-zip-i1pyxwgv\input\前车身\车身维修.pdf | pdf / PDF смешанный: текст + OCR | zip | C:\Users\PC\Downloads\车身尺寸.zip / 前车身\车身维修.pdf | 697390 / 433 |
| 5582364caf97 | C:\Users\PC\AppData\Local\Temp\TreeTranslate-zip-i1pyxwgv\input\后车身\车身维修.pdf | pdf / PDF смешанный: текст + OCR | zip | C:\Users\PC\Downloads\车身尺寸.zip / 后车身\车身维修.pdf | 245729 / 167 |
| 5582364caf97 | C:\Users\PC\AppData\Local\Temp\TreeTranslate-zip-i1pyxwgv\input\车身侧面\车身维修.pdf | pdf / PDF смешанный: текст + OCR | zip | C:\Users\PC\Downloads\车身尺寸.zip / 车身侧面\车身维修.pdf | 252380 / 380 |
| 5582364caf97 | C:\Users\PC\AppData\Local\Temp\TreeTranslate-zip-i1pyxwgv\input\车身底部\车身维修.pdf | pdf / PDF смешанный: текст + OCR | zip | C:\Users\PC\Downloads\车身尺寸.zip / 车身底部\车身维修.pdf | 360072 / 594 |
| 5582364caf97 | C:\Users\PC\AppData\Local\Temp\TreeTranslate-zip-i1pyxwgv\input\车身面板间隙\车身维修.pdf | pdf / PDF смешанный: текст + OCR | zip | C:\Users\PC\Downloads\车身尺寸.zip / 车身面板间隙\车身维修.pdf | 128071 / 266 |

## Следующие ручные прогоны

1. Обычный PDF с текстовым слоем: 1, 5 и 10 страниц, по возможности с сопоставимым количеством текста на странице.
2. PDF со сканами: 1 и 5 страниц, с одинаковым разрешением и похожей плотностью текста.
3. Пакет из нескольких PDF для проверки общей ETA и последовательного заполнения строк.

Держать одинаковые язык, устройство и профиль OCR. Первый холодный запуск и повторный тёплый запуск записывать отдельно. Количество страниц само по себе недостаточно: учитываются сегменты, символы и OCR-области. Точность начальной оценки проверять по отношению фактического времени к прогнозу `eta calibration_runs=… estimated_seconds=…`.

Подробные записи по run: `C:\Users\PC\AppData\Local\CHOPIK Team\TreeTranslate\measurements`. После прогона запустить `python tools/document_measurements.py`, чтобы обновить этот отчёт.
