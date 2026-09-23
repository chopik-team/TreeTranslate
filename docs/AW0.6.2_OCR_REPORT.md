# TreeTranslate AW 0.6.2-alpha — Hybrid PaddleOCR Router

Дата проверки: 23.09.2026. Проект: `C:\TreeTranslate`. Выполнен рабочий offline OCR → TranslationRouter → существующий PDF writer. Это alpha: качество технического перевода M2M100 и реконструкции сложного скана не считается безошибочным.

## Итог простыми словами

**Этап внедрения локального OCR завершён для проверенных сценариев.** Процент «95%» больше не используем: он не отражает ни качество перевода, ни объём оставшихся ограничений. Это рабочая alpha-версия, а не готовый публичный установщик.

| Что проверено | Результат | Подтверждение |
|---|---|---|
| Распознавание сканов на CPU, GPU и Auto | Работает на этой машине | [Замеры](qa/aw062/verified-benchmark.json) |
| Полный перевод скана, смешанного PDF и повёрнутой страницы | Пять сценариев выполнены, оригиналы сохранены | [Результаты документов](qa/aw062/end-to-end.json) |
| Папка файлов, пауза/продолжение, отмена в интерфейсе | Три сценария пройдены | [UI-проверка](qa/aw062/ui/result.json) |
| Сохранность изображения за пределами заменённого текста | На семи исходных страницах изменений не найдено | [Проверка пикселей](qa/aw062/visual-invariants.json) |
| Работа без загрузок из интернета | В проверенных запусках 0 сетевых попыток; запрет сети проверен отдельно | Раздел 24 и интеграционные тесты |
| Автоматические тесты | 302 успешно, без ошибок и пропусков | [JUnit-отчёт](qa/aw062/full-tests.xml) |

### Как пользоваться

1. На этой подготовленной машине запустить `C:\TreeTranslate\run_dev.bat`.
2. На странице перевода файлов добавить PDF или папку, выбрать язык результата и начать перевод. Поддерживаемые сканы распознаются автоматически.
3. Для первого запуска использовать Balanced и Auto. Economy снижает нагрузку и использует CPU; Fast не включает тяжёлый анализ таблиц. Turbo и Maximum не гарантируют более точного перевода: они меняют параметры обработки, но не обучают переводчик.
4. Дождаться завершения проверки документа, затем открыть результат. При нехватке места часть перевода переносится на дополнительные страницы; предупреждения нужно учитывать при просмотре.

Повторно скачивать или устанавливать модели для обычного запуска не требуется. Подготовка другой машины описана в [README](../README.md#ocr-компонент-aw-062).

### Скорость и оставшиеся ограничения

На Ryzen 7 5700X / RTX 3080 распознавание четырёх страниц автомобильного документа заняло около **62 секунд на CPU и 9,5 секунды на GPU**. Сложная страница таблицы — около **81 и 22,5 секунды** соответственно. Это время OCR с загрузкой и подготовкой страниц, **не всего перевода и сохранения PDF**. Это единичные замеры, а не обещание скорости для любого файла.

Технические термины могут переводиться неточно. Сложная вёрстка, текст на фактурном фоне и произвольный наклон требуют дальнейшего улучшения. Отмена ожидает завершения текущего ограниченного вызова модели. Сохранённые без замены растровые подписи не обязательно становятся доступными для поиска в PDF. Полный список ограничений — в разделе 30.

Отдельными будущими работами остаются публичный установщик, расширенный размеченный набор документов для оценки качества и улучшение терминологии перевода. В этом этапе дообучение, новые модели перевода и AW0.7 не выполнялись.

### Завершающие доработки

- Исправлена установка OCR: папка `.venv-ocr` по умолчанию создаётся у проекта, даже если инструмент вызван из другого каталога. Явный `--destination` сохранён.
- Проверка сохранности PDF берёт реальные пути из отчёта перевода, а не предполагает суффикс `(1)`. Работает из другого каталога и больше не удаляет файлы предпросмотра.
- В README устранено устаревшее утверждение об отсутствии распознавания сканов; добавлен обычный путь запуска без повторной установки.
- Логика перевода, обработки файлов и интерфейс в этой завершающей доработке не менялись.

Повторная проверка после этих доработок: **302 теста пройдены за 126,10 секунды**, 0 ошибок и пропусков; `compileall` и `git diff --check` успешны. Полная проверка SHA256 всех 15 моделей (5 перевода и 10 OCR) успешна. Проверка PDF запущена из `C:\`, повторно подтверждены 7 страниц без изменений вне областей текста. Вызовы установщика проверены с подменой запуска процессов: путь по умолчанию, явный каталог и параметры установки без сети; повторная установка не выполнялась. Результаты трёх UI-сценариев выше относятся к предыдущему прогону этого этапа; после завершающей правки служебных инструментов UI smoke повторно не запускался.

## 1. Версии и аудит среды

Windows, Python 3.12.13, PySide6 6.11.1; Ryzen 7 5700X, RTX 3080 12 GB, драйвер 610.88. PaddleOCR 3.7.0, PaddleX 3.7.2, paddlepaddle-gpu 3.3.1 / CUDA 12.6. CPU сначала отдельно проверен на paddlepaddle 3.3.1, затем на GPU-wheel с `device=cpu`. Основной переводчик остаётся на NumPy 2.5.3; PaddleX требует NumPy <2.4 и работает с 2.3.5 в `.venv-ocr`. `pip check` проходит.

Официальный GPU wheel устанавливает cuDNN 9.5, при этом Paddle предупреждает, что собран с 9.9. На этой машине реальные CPU/GPU тесты проходят; совместимость другого GPU/драйвера не предполагается автоматически. DLL/Paddle не импортируются в процесс CTranslate2.

## 2. Точные модели

| Модель | Байт | Revision |
|---|---:|---|
| PP-OCRv6_small_det | 10,071,314 | `106c97591b235f607453300d9fc8c1cad1b25488` |
| PP-OCRv6_small_rec | 21,456,674 | `bd619643acac4b9650c040234da8d944476ee3f1` |
| cyrillic_PP-OCRv5_mobile_rec | 8,204,341 | `712d2d65556ccc1ea7b5d2bb232b018838b6a3ab` |
| PP-DocLayout_plus-L | 130,398,558 | `aa52b8528c84f9b1a34ac3a88fe0e576edb9d11d` |
| PP-LCNet_x1_0_doc_ori | 6,866,223 | `d3b95a6dff5fe8a94f2748e12b61cb26818a0df8` |
| PP-LCNet_x1_0_table_cls | 6,860,750 | `2fa6323e7dab88fa883081db1460995f46af2922` |
| SLANeXt_wired | 365,745,793 | `763069fcda6a065f2171753205a32bf899a88d15` |
| SLANet_plus | 7,999,557 | `bae6e5f8c3c4e7da0c0b7639fdf3228fe76184e2` |
| RT-DETR-L_wired_table_cell_det | 129,938,458 | `e2bd53c06b3a815d86acbf5c6779dada58819cfe` |
| RT-DETR-L_wireless_table_cell_det | 129,939,193 | `25ca86356a601c877476bb0dcc5fd09153d9d64d` |

## 3. Размеры

Все десять inference artifacts: **817,480,861 байт**. Python OCR environment: 104 distribution, 4 250 582 855 байт файлов по inventory (не размер сжатого installer). Базовые det+ZH/EN rec+Cyrillic rec+orientation ≈46,6 MB; layout ≈130,4 MB; полный набор таблиц добавляет ≈640,5 MB. Пакеты для formula/chart входят в upstream extra-зависимости, но соответствующие модели и функции отключены.

## 4. SHA256 и воспроизводимость

`vendor/model-metadata/ocr/models_manifest.json` и `vendor/models/ocr/models_manifest.json`: source URL, pinned revision, роль, language/script, format, FP32, размер и SHA256 **каждого файла**. `tools/verify_models.py` успешно проверил все OCR и прежние translation artifacts. `requirements-ocr-lock.txt` фиксирует все 104 пакета. `prepare_paddleocr_models.py` — единственное место загрузки моделей, требует `--allow-network` либо `--local`; runtime его не импортирует.

## 5. Лицензии

Каждая модель имеет собственный сохранённый upstream README с `license: apache-2.0`; библиотечная лицензия не использована вместо лицензии весов. Неизвестная декларация лицензии блокирует публикацию manifest подготовщиком. PaddleOCR/PaddleX/Paddle — Apache-2.0. Полные notices зависимостей: `vendor/licenses/ocr-runtime/`, версии/метаданные: `inventory.json`; отсутствовавшие в wheels тексты получены из проверенных SHA256 sdists или официальных repositories, с provenance в `upstream-licenses.json`. NVIDIA runtime имеет собственные лицензионные условия, сохранённые из wheels. Создания публичного installer/его публикации не было.

## 6. Архитектура

`app/ocr/`: contracts, errors, backends, runtime, router, preprocess, postprocess, PDF adapter. `HybridPdfExtractor` сначала вызывает `NativeTextExtractor`, затем добавляет `PdfSegment(origin='ocr')`. `DocumentJob` остаётся единым для DOCX/native PDF/scans. Второй document engine/writer не создан. Подготовленные extraction contracts кэшируются между planning и translation: OCR не запускается дважды; исходные PDF bytes всех файлов одновременно не удерживаются.

## 7. Правила Router

Конфигурация `assets/config/ocr.json`. Простой фрагмент → PP-OCRv6. Векторные/растровые линии ≥8, regions ≥55 либо две явные колонки → PP-StructureV3 в Balanced/Turbo/Maximum/Automatic. Economy/Fast используют обычный OCR. Часть признаков уточняется после первого OCR, поэтому сложная страница иногда требует дополнительного прохода. Причина маршрута сохраняется в безопасной metadata (`last_results`); распознанный текст там не хранится.

## 8. PP-StructureV3 и найденный upstream дефект

Полный вариант реально запущен: layout detection, table classification, wired/wireless structure и cells. Formula, chart, seal, doc unwarping, region detection, textline classifier отключены. Табличные cell boxes передаются существующему `available_bbox`/reflow. HTML таблиц не превращается в отдельный документ.

При первоначальном прогоне `TableRecognition` лениво создавал внутренний GeneralOCR с `use_textline_orientation=True`, хотя публичный внешний flag был False. Это приводило к попытке hub lookup для PP-LCNet_x1_0_textline_ori. Сеть была заблокирована, pipeline завершался ошибкой. Исправлена **вложенная** конфигурация `SubPipelines.TableRecognition.SubPipelines.GeneralOCR.use_textline_orientation=False`, все включённые модули получают local paths; hub manager дополнительно запрещён целиком. Полный Structure работает, downgrade до заглушки не делался.

## 9. Выбор языка

Ручные русские UI-названия нормализуются через существующий `language_code`. RU использует официальный `cyrillic_PP-OCRv5_mobile_rec`: базовый PP-OCRv6 small не объявляется русской моделью. ZH/EN используют PP-OCRv6. Auto ограничен двумя recognizer-кандидатами и сравнением confidence; рекурсии/retry loop нет. После OCR sample используется существующий локальный LanguageResolver. Проверен Auto для кириллицы и сквозной Auto EN→RU. Confidence моделей не гарантирует лингвистически безошибочного выбора на коротком/смешанном тексте.

## 10. CPU / GPU / Auto

CPU скрывает CUDA через окружение дочернего процесса и не вызывает CUDA memory/device APIs. Explicit GPU не переходит на CPU, отсутствие GPU возвращает DeviceUnavailableError-совместимую ошибку. Auto пробует GPU, затем CPU при недоступности/ошибке inference; переход явен в предупреждении. Economy/Auto сразу CPU. Реальные CPU/GPU/Auto прошли на обоих контрольных документах.

## 11. Lazy load и idle unload

Запуск GUI не импортирует Paddle и не загружает OCR weights. Один локальный subprocess, один кэш выбранной pipeline на ключ device/backend/recognizer/profile. Idle timer 30 s синхронизирован с inference lock. Процесс закрывается после extraction и в finally при ошибке/отмене; на смене устройства перезапускается. Никаких локальных HTTP-серверов.

## 12. Ресурсы, pause/cancel

Существующий RuntimeManager получил `release_models()` без закрытия translation engine. Перед OCR выгружается прогретая translation model; перед переводом закрывается OCR process. Одновременное удержание Paddle/M2M100 VRAM не используется. Изображения освобождаются после фрагмента. Pause/cancel — кооперативные checkpoints; уже начатый native вызов завершается, результат не публикуется после cancel. Watchdog 240 s ограничивает вызов отдельного процесса; timeout завершает worker. Отмена не равна мгновенному прерыванию CUDA kernel.

## 13. PDFium / DPI / координаты

144 / 168 / 200 / 200 / 240 / 200 DPI (Economy/Fast/Balanced/Turbo/Maximum/Automatic). Лимиты до выделения bitmap: 18 MP, 12000 px по стороне; PDF 128 MiB, 500 pages; до 3000 OCR regions на документ, 2M characters, PNG temp до 80 MB. `/Rotate` нейтрализуется только на время рендера; координаты возвращаются в исходные PDF points. Model orientation 0/90/180/270 включён в Balanced и выше. Все четыре поворота проверены реальной моделью. Произвольный skew/perspective не исправляется.

## 14. Confidence

<0.45: блок оставляется растровым, с предупреждением; исчезновение текста не выдаётся за перевод. Если во всём скане нет пригодного текста, возвращается понятная OCR confidence error. Пустая картинка внутри многостраничного документа сохраняется. Порог 0.85 хранится как ориентир high confidence, не является доказанной вероятностью правильности. Отдельного статистического калибровочного корпуса confidence пока нет.

## 15. Dedup и reading order

NFKC/casefold/alphanumeric comparison + spatial intersection/min-area, thresholds 0.65/0.65: требуются и геометрия, и сходство текста. Native имеет приоритет. Соседние строки объединяются только при совпадающем фоне/выравнивании и ограниченном зазоре; список исходных raster boxes сохраняется отдельно. Явные две колонки читаются слева сверху вниз, затем справа; пересекающие колонки блоки отменяют этот простой режим. Универсальная издательская reading-order reconstruction не заявляется.

## 16. Удаление растрового текста

Изображение source не переписывается. Только распознанные glyph boxes закрываются непрозрачной подложкой, цвет оценён по perimeter; добавлено 0.65 pt для anti-alias fringe. Все masks рисуются **до** всех replacement glyphs, поэтому соседняя mask не стирает уже переложенную строку. На сложном фоне применяется консервативная solid box и предупреждение, не генеративная дорисовка. Contrast text чёрный/белый, общий лицензированный fallback font. Свободное соседнее место ищется лишь по равномерному фону, границы/графика останавливают расширение. Переполнение уходит в существующие continuation pages с marker.

## 17. Mixed PDF и ограничения классификации

Реальный mixed fixture с native text и текстом внутри отдельного JPEG прошёл end-to-end, 3 сегмента, 0 continuations. OCR получает только crop изображения. Uniform raster пропускается. Pure native fixture не вызывает backend. Полноразмерная картинка с уже пригодным native layer получает native priority; частично неполный текстовый слой на таком полноразмерном фоне остаётся ограничением эвристики и требует отдельной проверки.

## 18. Chinese CER

Автомобильное руководство: 4 страницы, native ground truth 1671 символ после NFKC/удаления whitespace, 76 известных native блоков. **CER 1.616%** в этих областях, bbox recall 100%. CER по страницам: 1.821 / 0.422 / 1.900 / 1.711%. Изменение пунктуации учитывается. Полный OCR также распознаёт текст внутри иллюстраций, которого нет в native truth: полный последовательный CER в JSON не следует трактовать как чистую ошибку модели. Ручной эталон для текста всех фотографий/скриншотов не создан.

## 19. Числа и идентификаторы

В автомобильном corpus numeric/uppercase-token multiset recall **100%** на всех четырёх страницах: в частности GDS/ITM/IVT, 6.6, 45 и 60, 20. Это recall значений, не гарантия точного dash/punctuation или качества перевода. SilverStone: **95.56%**, ошибки признаны и не скрыты. Числовые-only blocks не отправляются в translator, их исходный raster сохраняется. Прежний fidelity guard проверяет перевод и сохраняет source при несоответствии; он не исправляет уже допущенные OCR ошибки автоматически.

## 20. Automotive end-to-end

`output/pdf/aw062/automotive-scan_ru (1).pdf`: 4 исходные страницы + 2 продолжения, 80 translatable segments, 21 warning. После визуальной проверки тесные line boxes переработаны: до исправления было 7 продолжений/111 warnings. Реальные Argos/M2M100 результаты сохранены в developer cache; повторный QA использует явно учтённые cache hits. Тайминг такого повторного translation-run не выдаётся за свежий inference benchmark.

## 21. SilverStone и прочие outputs

`silverstone-scan_en (1).pdf`: 1 исходная + 1 continuation, 87 сегментов, 3 warnings, native-region CER 1.977%, bbox recall 100%. Чёрный фон сохранён, перевод контрастный. English и rotated EN scans: по одной странице, без continuations. `mixed_ru.pdf`: native + raster, одна страница. Все outputs находятся в `output/pdf/aw062`; transient failures не публиковались как готовые результаты.

## 22. Реальные времена OCR

Один cold-document прогон, далее runtime warm внутри документа; includes process/model loading, raster rendering и OCR/adapter. Windows background load не нормализована; это не статистическая оценка и не гарантия скорости.

| Документ | Устройство | Секунд / документ | RSS, MiB | GPU reserved peak, MiB |
|---|---|---:|---:|---:|
| automotive | cpu | 61.64 | 894 | 0 |
| automotive | gpu | 9.48 | 1691 | 898 |
| automotive | auto | 9.50 | 1495 | 898 |
| silverstone | cpu | 81.03 | 1664 | 0 |
| silverstone | gpu | 22.49 | 2018 | 1168 |
| silverstone | auto | 23.03 | 2304 | 1168 |


Шесть профилей, Auto, automotive:

| Профиль Auto | Фактическое устройство | Секунд, 4 стр. | CER в известных областях |
|---|---|---:|---:|
| economy | cpu | 35.03 | 1.62% |
| fast | gpu | 8.78 | 1.56% |
| balanced | gpu | 9.57 | 1.62% |
| turbo | gpu | 10.67 | 1.56% |
| maximum | gpu | 9.67 | 1.62% |
| automatic | gpu | 10.12 | 1.62% |


На этом маленьком corpus Turbo/Maximum не гарантируют выигрыша: Turbo расходует больше batch memory, Maximum больше пикселей. Не подменяем результаты рекламным ранжированием. Translation profile settings не изменялись.

## 23. RAM / VRAM

Таблица выше: RSS дочернего процесса после inference (не peak всей системы) и реально возвращённый Paddle `max_memory_reserved()` (не общий nvidia-smi VRAM с desktop). `gpu_peak_allocated_bytes` также в JSON. Economy CPU: нет CUDA memory calls. Полные JSON: `docs/qa/aw062/verified-benchmark.json`, `profiles.json`; финальная проверка column-routing — `final-routing.json`.

## 24. Offline / privacy

До импорта third-party установлен process-wide Python audit hook, запрещены DNS/connect/bind/sendto/urllib, HF telemetry/offline flags, Paddle source checks отключены. Hub `get_model_path` заблокирован даже до сети. Отключён import-time IPv6 loopback bind probe urllib3. Финальные успешные прогоны показывают **0 network attempts**; отдельный negative test с urllib получает запрет. Это Python process guard, не заявление о системном firewall/packet capture. stdout worker — только JSON protocol, vendor stdout/stderr в devnull; OCR text не попадает в runtime logs. Явные developer QA transcripts в `docs/qa` содержат только проверочный corpus.

## 25. Источники и atomic output

SHA256 всех реальных source проверены до/после, неизменны. Writer/validation завершаются до atomic publish; коллизии дают новое имя. Temporary PNG существует только внутри TemporaryDirectory и удаляется после вызова/ошибки/cancel; unfinished output удаляется finally. GUI cancel проверил отсутствие временного output.

## 26. Visual QA и UI

Output отрисован PDFium и Poppler. Просмотрены automotive, тёмная таблица, rotated и mixed. Автоматическая pixel-проверка семи исходных страниц: **0 изменённых пикселей вне явных mask/text regions** (3 px allowance для рендера), см. `visual-invariants.json`; фотографии отдельно проверены по pixel equality. Старые preview pages сверх новой длины удалены.

Реальный Qt MainWindow + application theme + file page: смешанная папка DOCX/native PDF/scan, CPU Pause/Resume и GPU Cancel прошли; `ui/result.json`, PNG в `ui/`. Это реальные services/models, не демонстрационный progress. Header/стили страницы и translation/file business rules не переделывались; переиспользован ProgressPanel с OCR/render/layout stage и страницами. ETA OCR строится из законченных page timings; до первого замера не выдумывается.

## 27. Тесты

Финальный полный `pytest`: **302 passed**, 0 failed, 0 skipped; XML: `docs/qa/aw062/full-tests.xml`. Дополнительно real OCR integration: 9 passed (CPU/GPU/Auto, offline negative, 4 orientations, Auto Cyrillic). UI smoke: 3 сценария passed. Unit coverage включает lazy/cancel, crop limits, masks/writer validation, extraction cache, geometry+text dedup, policy, native skip, low confidence, theme/file-page regression, reading order.

## 28. Compileall

`python -m compileall -q app tools`: успешно; повторено в финальной проверке.

## 29. Diff check

`git diff --check`: успешно. Windows LF/CRLF informational messages не являются ошибками whitespace. Commit не создан.

## 30. Известные ограничения и решения

- Alpha не объявляется идеальной OCR/translation/layout системой. M2M100 порой неточно переводит технические термины; OCR внедрение не дообучает переводчик.
- Solid masks могут быть заметны на текстуре/градиенте; цель — убрать double text, сохранив остальную графику. Низкая confidence сохраняет raster.
- Full-page partially searchable scans, nested Form XObject raster, arbitrary skew/perspective и сложное межколоночное течение не имеют универсального решения; сохранены conservative policies.
- Runtime timeout/cancel ждёт bounded native call; instant cancellation внутри GPU kernel не обещается.
- Распознавание RU/Auto может требовать второй recognizer, медленнее ручного языка. Economy/Fast не включают model orientation classifier.
- CPU PP-Structure существенно дороже базового OCR (81 s на SilverStone здесь). Полный вариант оставлен рабочим; лёгкие профили доступны без него.
- Нет независимой ручной разметки всех boxes/order/illustration text, no statistical confidence calibration. CER относится только к явно описанному truth.
- Готовый публичный installer не собирался: локальная environment + artifacts + reproducible build scripts подготовлены.
- Glossary, Translation Memory, fine-tuning, новые translation models и AW0.7 не внедрялись.

## 31. Изменённые файлы этого этапа

Новые: `app/ocr/**`, `assets/config/ocr.json`, `requirements-ocr-lock.txt`, OCR prepare/audit/benchmark/QA tools, `tests/test_ocr*.py`, manifests/notices/report/QA artifacts. Расширены: `app/documents/{backends,job,pdf_document,pdf_types}.py`, `app/engine/runtime/runtime_manager.py`, `app/services/document_translation_service.py`, `app/models/translation_job.py`, `app/gui/widgets/progress_panel.py`, version/changelog/README/THIRD_PARTY_NOTICES, `.gitignore`, `tools/verify_models.py`.

Предыдущие незакоммиченные AW0.6/0.6.1/toggle изменения сохранены; полный dirty status не означает, что весь этот diff создан OCR-этапом.

## 32. Git status и источники

Снимок: `docs/qa/aw062/git-status.txt`. Нет commit/reset/revert чужих изменений.

Основные upstream источники: [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR), [OCR pipeline](https://github.com/PaddlePaddle/PaddleOCR/blob/main/docs/version3.x/pipeline_usage/OCR.en.md), [официальные Paddle GPU wheels](https://www.paddlepaddle.org.cn/packages/stable/cu126/paddlepaddle-gpu/). Точные модельные source URLs и revisions находятся в manifest. Дополнительные license provenance: [BCE SDK](https://github.com/baidubce/bce-sdk-python), [latex2mathml](https://github.com/roniemartinez/latex2mathml).
