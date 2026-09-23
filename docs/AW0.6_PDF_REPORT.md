# TreeTranslate AW 0.6-alpha — PDF Phase 1

Дата: 22 сентября 2026. Рабочий проект: `C:\TreeTranslate`.

## Результат и границы готовности

Реальный перевод видимого текстового слоя PDF добавлен к существующему Document Layer. Создаётся новый проверенный PDF, исходные байты не меняются. Общая очередь принимает DOCX/PDF и смешанные папки. Реальные Argos и M2M100 418M INT8 работают через прежний Hybrid Router на CPU/Auto/GPU.

Это Phase 1 для обычных текстовых PDF, а не универсальная реконструкция издательской вёрстки. OCR, TM, Glossary и дообучение не реализовывались. Ограничения сложных PDF и качества модели перечислены ниже; они не скрыты за успешными синтетическими тестами.

## Аудит и переиспользование

Изучены `DocumentJob`, DOCX backend, scanner, naming/publication, JobControl, DocumentTranslationService, TranslationSessionManager, HybridTranslationService/Router/RuntimeManager, настройки, file picker, FileTranslationPage и ProgressPanel.

Сохранены один executor/одно активное задание, local language detector, выбор профиля/устройства, keep_warm, защищённая публикация и настройки имён/каталогов AW0.5.1. Второй translation backend или файловый движок не создавался. Исходный полный набор: 213 passed.

Новые модули:

- `app/documents/backends.py`: небольшой lazy-dispatch DOCX/PDF.
- `pdf_types.py`: классификация, лимиты, PdfSegment, PdfPageInfo, ExtractedPage.
- `pdf_document.py`: NativeTextExtractor, чтение/замена/проверка PDFium.
- `pdf_layout.py`: геометрическая группировка, порядок чтения, перенос и fitting.
- `pdf_fonts.py`: локальные метрики, cmap, разрешение/встраивание шрифтов.

Существующий DocumentJob расширен только различиями форматов; DOCX write/validate остаются прежними. Новый `stage` добавлен в конец TranslationProgress, сохраняя старые вызовы. UI-компоненты переиспользованы; отдельного PDF-экрана нет.

## Библиотеки и лицензии

| Компонент | Версия | Назначение / лицензия |
|---|---|---|
| pypdfium2 | 5.13.0 | PDF read/edit/render, wrapper Apache-2.0 OR BSD-3-Clause |
| PDFium, Windows x64 wheel | 153.0.7999.0 | BSD-style + реальные bundled third-party notices |
| fontTools | 4.65.0 | cmap/метрики/subsetting, MIT |
| TreeTranslate Sans | static weight 400 | производный Noto Sans SC, SIL OFL-1.1 |
| pypdf, только QA | 6.19.0 | независимое чтение/fixtures, BSD-3-Clause |
| Pillow, только QA | 12.3.0 | изображения/PNG сравнения, MIT-CMU |

Runtime requirements и lock обновлены. Все license files фактически установленного pypdfium2 wheel, включая Windows BUILD_LICENSES, скопированы в `vendor/licenses/pypdfium2`; fontTools/pypdf/Pillow — в соседние каталоги. Полный font OFL — `assets/fonts/OFL-NotoSansSC.txt`. PyMuPDF/GPL/AGPL/commercial PDF engine не добавлялся.

Источники: [PDFium public editing API](https://github.com/chromium/pdfium/blob/main/public/fpdf_edit.h), [PDFium LICENSE](https://github.com/chromium/pdfium/blob/main/LICENSE), [pypdfium2 API](https://pypdfium2.readthedocs.io/en/stable/python_api.html), [fontTools LICENSE](https://github.com/fonttools/fonttools/blob/main/LICENSE), [Noto CJK](https://github.com/notofonts/noto-cjk).

У PDFium нет гарантии thread-safety даже для разных документов. Все вызовы backend/QA сериализованы общим RLock; реальная обработка идёт в существующем worker. Использован pinned API InsertObjectAtIndex с явной передачей ownership, чтобы сохранить порядок рисования. Обновление PDFium требует повторных native tests.

## Классификация и извлечение

Поддержаны категории TEXT_PDF/MIXED_PDF и безопасные отказы IMAGE_ONLY_PDF, EMPTY_PDF, ENCRYPTED_PDF, CORRUPTED_PDF, UNSUPPORTED_PDF. Классификация выполняется при preflight до запросов перевода. Зашифрованные документы отклоняются и при пустом пароле.

Достаточность текста — эвристика: минимум 4 значимых буквенных символа без изображений и 20 при наличии изображения; URL не считаются текстом. Несколько случайных букв на скане не запускают фиктивный перевод. Это не распознавание и не оценка семантического качества OCR.

Извлекаются видимые top-level fill text objects с пригодным Unicode. Отдельные spans/буквы собираются по baseline, размеру/цвету и геометрии в строки и близкие абзацы. Чтение использует рекурсивное разделение по межколоночным пробелам и горизонтальным полосам. Для обычных двух колонок сначала читается левая, затем правая. Номера/URL-only объекты не отправляются в модель.

Контракт содержит page, block_id, text, bbox, reading_order, font_names/size, alignment, rotation/direction, source_language, status, source object indices, optional confidence. В текущей фазе alignment остаётся `left`, direction — `ltr`; точное восстановление right/center/justified и вертикального CJK не реализовано. Это осознанное ограничение, а не надёжно определённая исходная семантика PDF.

`ExtractedPage` и инъекция extractor оставляют простой extension point. Будущий OCR сможет использовать сегменты/layout/font-fitting; стратегия удаления текста из растрового изображения потребует отдельного Phase 2 дополнения. Пустой OCR framework не создавался.

## Перевод и замена

Один representative sample на документ (до 24 распределённых блоков) определяет основной язык через существующий detector. Все блоки используют эту пару и прежний Router/profile/device. URL/email/UUID и распознаваемые идентификаторы с цифрами защищены. Длинные части ограничены 4000 символов на запрос, далее действуют токенные лимиты движка.

PDFium открывает исходные байты, создаёт новые текстовые объекты и удаляет только использованные исходные text objects. Перевод не нарисован поверх оставшегося видимого оригинала. Новые объекты вставляются в позицию исходного объекта, чтобы не переносить текст поверх графики по z-order. Неизменившийся текст остаётся исходным объектом.

Сохраняются число/размер/поворот страниц, top-level изображения/векторы/Form объекты, ссылки и существующие аннотации. Hyperlink URI проверен независимым pypdf. Кроп изображения/векторного фона сравнивается попиксельно. Это не обещание сохранения цифровых подписей, PDF/A, tagged accessibility или произвольных интерактивных форм.

## Шрифты, fitting и overflow

Разрешение шрифта: подходящий embedded TrueType с cmap всех символов и допустимыми embedding flags, иначе bundled TreeTranslate Sans. ОС-шрифты и сеть не используются. Нет символа в локальном fallback — безопасная ошибка без публикации. В каждом PDF встраиваются нужные подмножества; уникальные PostScript names предотвращают коллизии ToUnicode.

Шрифт подготовлен developer tool из официального Noto CJK commit `f8d157532fbfaeda587e826d4cd5b21a49186f7c`, static weight 400, переименован. 30 890 cmap entries; Latin/кириллица/китайский проверены. SHA256 поставляемого TTF: `3dbb9ce88257046f3ce2ce7300402080c053f7d48c7b16a389c37e77d550f89c`. Исходный URL/hash и модификация — в font manifest.

Внутри исходного bbox: wrap, затем уменьшение по 0.5 pt до 6 pt. Повороты 0/90/180/270 поддержаны. Блоки не расширяются поверх соседей. Если весь перевод не помещается, видимая часть заканчивается `[...]`, полный Unicode перевод находится в PDF Text annotation и показывается предупреждение. Если блок меньше даже одной строки, весь перевод остаётся в примечании. Значок выбирает свободное место рядом; если места нет, аннотация остаётся доступна через список примечаний без перекрытия страницы. Поэтому часть длинного текста требует открытия примечания — это явное ограничение fitting.

## Безопасность и управление заданием

Оригинал читается, SHA256 сверяется перед публикацией. Запись в temp в каталоге назначения → повторное открытие/validation → атомарная публикация без перезаписи. Сохраняется расширение, очищаются Windows имена, коллизии получают `(1)` и далее. Ошибка/отмена удаляет текущий temp; уже опубликованные файлы остаются.

Validation проверяет размер/открываемость, число/размер/поворот страниц, сигнатуру non-text objects, число аннотаций, наличие видимого перевода и полного overflow Contents. Unit tests дополнительно проверяют отсутствие заменённого исходного текста. Проверка не является полным ISO PDF validator.

Настраиваемые лимиты в `assets/config/pdf_limits.json`: 128 MiB, 500 страниц, 20 000 top-level объектов/страницу, 2 млн извлекаемых символов, группировка до 4000 символов, минимум 6 pt, максимум стороны 14 400 points. Native parser не изолирован отдельным процессом: лимиты уменьшают риск/нагрузку, но не служат sandbox и не доказывают защиту от всех malformed PDF.

Стадии: SCANNING через существующий JobState, EXTRACTING/TRANSLATING/WRITING/VALIDATING/COMPLETED через progress.stage. ETA только время. Пауза не запускает новый сегмент; один уже выполняемый native inference может закончиться. Warm pin сохраняется при паузе. Cancel не убивает C++ thread и завершает работу на checkpoint.

Runtime не импортирует downloader; модели и шрифт локальные. В real integration monkeypatch запрещает socket getaddrinfo/create_connection, сетевых попыток не было. Логи приложения содержат metadata/type errors, не extracted/translated PDF text. Примеры ниже — специально созданные QA-данные.

## Реальные результаты моделей

EN: `Save the configuration file before restarting the application.` → `Сохранить файл конфигурации перед перезагрузкой приложения.` (Argos).

ZH: `请在重新启动应用程序之前保存配置文件。` → `Сохраните профиль до перезапуска приложения.` (M2M100 418M INT8).

Китайский пример показывает неточность «配置文件» → «профиль». В смешанном по языку fixture английский заголовок, обработанный с основной парой zh→ru, дал `User Guide / Пользователь`. Это результат модели, не оставшийся под переводом исходный text object. Автоопределение одного языка на весь документ не решает multilingual routing. Качество не объявляется эталонным; обучение не выполнялось.

CPU/Auto/GPU пройдены для EN и ZH в шести integration tests. В native GUI Auto на этой машине выбрал CUDA, fallback не потребовался. Замеры ниже — длительность конкретных smoke-сценариев с записью/проверкой, не throughput benchmark и не основание перенастраивать профили AW0.4.

| GUI сценарий | Устройство | Итог | Секунды |
|---|---|---|---:|
| en_cpu | CPU | COMPLETED | 3.359 |
| zh_auto | Auto | COMPLETED | 1.969 |
| zh_gpu | GPU | COMPLETED | 0.922 |
| folder | Auto | COMPLETED | 1.422 |
| mixed | Auto | COMPLETED | 0.813 |
| imageonly | CPU | ERROR | 0.031 |
| pause | CPU | COMPLETED | 2.094 |
| cancel | CPU | CANCELLED | 0.078 |

Image-only ERROR — ожидаемый отказ до вызова модели (0 вызовов), не сбой теста. Смешанная папка дала PDF+DOCX, переведённые имена и вложенный каталог. Пауза проверяла `_pins == 1`, отмена выполнялась после первого реального запроса. Ошибок GUI smoke: 0. Native QApplication выполнялся с WA_DontShowOnScreen, screenshot получен через QWidget.grab; это автоматизированный Qt smoke, не ручная проверка внешнего PDF viewer.

## Оригиналы: SHA256 до/после

Полные пути/хеши всех source files и outputs: `docs/qa/aw06-pdf-gui.json`. Ниже основные примеры; пары совпали byte-for-byte.

- en_cpu: `71ac5e6b517fffb017abdb933eaf1ca1a46966b6a3d7f517c200b0b5d9a38d58` (до = после).
- zh_auto: `c424d2d8c7a8eb5e7cb5f6ce47a8fb7ba1ea535d241e944243a88df3d29099bd` (до = после).
- zh_gpu: `15c8fad6c38da34c280b065b2ea7cf0c40baf05d40e8f03dab983fa4b031c3c2` (до = после).

## Visual QA и исправленные регрессии

PDFium renderer доступен. Input/output PNG сохранены в `docs/qa/aw06-pages/`: columns, rotation, overflow, chinese. Реальные переводы отрендерены в `build/aw06-gui-smoke/rendered/`; native UI screenshots — `docs/qa/aw06-*.png`. Проверены кириллица, поворот, колонки, полное переполнение, сохранение изображения/цветного фона. OCR не использовался.

При проверке исправлены:

1. Буквы сортировались по верхней границе glyph bbox, из-за чего менялся порядок; теперь используется baseline и сохраняются PDFium spaces.
2. Подмножества шрифта с одним PostScript name повреждали ToUnicode последующих блоков; введены уникальные имена.
3. Значок overflow-примечания закрывал первое слово; теперь выбирается свободная позиция, добавлена регрессионная проверка пересечений.
4. Последовательное создание/закрытие Qt окон выявило access violation в Qt6Core. При закрытии остановлены дочерние таймеры, поздние service callbacks игнорируются. Последующие полные наборы и GUI smoke проходят; это подтверждение проверенных сценариев, не универсальное доказательство отсутствия native race.

## Ограничения Phase 1

- OCR отсутствует; изображения и текст в них не переводятся.
- Form XObject text, clipped/invisible/stroked text, произвольный угол/скос, RTL, replacement glyphs сохраняются с предупреждением; полностью неподдерживаемый PDF отклоняется.
- Вертикальное CJK, точная типографика/кернинг, смысловые таблицы, графические маски, right/center/justified alignment и произвольная сложная вёрстка не восстановлены.
- Классификация и reading order эвристические; редкие шрифты/нестандартный Unicode mapping могут потребовать отказа. Источник не изменяется.
- Overflow сохраняется полностью в примечании, а не на дополнительных страницах; отображение значка/панели зависит от PDF viewer.
- Подписи и специальные PDF conformance/interactive features не аттестованы. Native parser не sandboxed.
- Для будущего OCR понадобятся обработка изображения и связывание его результата с writer; сейчас оставлен только простой extractor/segment contract.
- Проверки покрывают программные fixtures и действующие модели на этой машине. Большой внешний корпус издательских PDF не тестировался.

## Проверки и изменения UI

Новые 19 PDF unit cases + 6 real-model integration cases. Сохранились DOCX, настройки, история/восстановление, text/dictionary/profile tests. Полный pytest, compileall и diff check выполнены; окончательные цифры приведены ниже после последнего запуска.

Редизайна нет. Расширены надписи/фильтр DOCX→DOCX/PDF, добавлены стадии и предупреждения в существующий status/progress, версия/история обновлены до AW0.6-alpha. Архитектурные отклонения: консервативное сохранение сложных text objects вместо их потенциально разрушительной реконструкции; overflow-note вместо расширения страницы. Это сохраняет оригинал/геометрию ценой неполного визуального перевода сложного PDF.

Обновлены README, CHANGELOG, THIRD_PARTY_NOTICES, runtime requirements/lock, dev requirements, font artifacts/licenses. Коммиты автоматически не создавались.

## Финальный контроль

- `.venv\Scripts\python -m pytest -q --junitxml=docs/qa/aw06-final-tests.xml`: **238 passed, 79.15 s**, без пропусков/ошибок, после последней правки overflow icon.
- Отдельный real PDF matrix: **6 passed, 18.24 s**, `docs/qa/aw06-real-pdf.xml`.
- Native Qt smoke: **8 сценариев, 0 ошибок**, `docs/qa/aw06-pdf-gui.json`.
- `.venv\Scripts\python -m compileall -q app tools`: exit 0.
- `git diff --check` с настройками репозитория: exit 0. Дополнительный запуск с отключённым autocrlf ошибочно трактовал Windows CRLF как trailing whitespace; это не изменение исходного текста.
- Исторические AW0.4 screenshots, перезаписанные старыми тестами, восстановлены из HEAD; новые AW0.6 QA artifacts сохранены отдельно.

Итог: обычные поддержанные text-layer PDF обрабатываются полностью offline в существующей системе. Оставшиеся ограничения перечислены явно; OCR/обучение и поддержка всей сложности PDF не объявлены завершёнными.
