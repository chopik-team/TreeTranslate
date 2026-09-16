# TreeTranslate AW 0.5-alpha — Phase 1: Real DOCX Translation

Дата: 16 сентября 2026. Репозиторий: `C:\TreeTranslate`.

## Результат

DOCX подключён к существующему Hybrid Router: реальные drag/drop, рекурсивная папка, выбор галочками, Auto языка, CPU/GPU/Auto, профили, прогресс, Pause/Resume/Cancel и валидные новые документы. Исходники не перезаписываются. Runtime остаётся offline. PDF/OCR/архивы/TM/Glossary/fine-tuning не реализовывались.

Есть два существенных ограничения: точность перевода остаётся свойством существующей модели; постраничная визуальная проверка DOCX не выполнена из-за отсутствия разрешённого LibreOffice runtime. Ни структурная валидация, ни наличие кириллицы не доказывают лингвистическую точность или идентичную вёрстку.

## Архитектура

| Узел | Ответственность |
|---|---|
| `app/documents/scanner.py` | Рекурсивные DOCX, несколько входов, deduplication, пропуск других форматов, временных Office файлов, symlink/junction. Сохраняет корень и относительный путь. |
| `app/documents/docx_document.py` | Читает ZIP, проверяет python-docx, извлекает логические текстовые группы, распределяет перевод по существующим XML nodes, сохраняет пакет и валидирует результат. |
| `app/documents/job.py` | Предварительный подсчёт сегментов и SHA256, язык документа, вызовы переданной функции перевода, каталоги, временный файл, validation, atomic no-clobber publication. |
| `app/documents/control.py` | Cooperative pause/cancel, время паузы, сериализация отмены и публикации. |
| `app/services/document_translation_service.py` | Qt state machine/signals/timer; связывает Document Layer с существующим executor и engine. |
| `HybridTranslationService` | Текст и DOCX используют один `ThreadPoolExecutor(max_workers=1)`, один Router и те же backend instances. |
| `RuntimeManager.keep_warm()` | Удерживает выбранную модель между сегментами и во время паузы; idle unload возобновляется после задания. |

Document Layer не импортирует Qt и не содержит native inference. Использует только нейтральные request/progress модели и callbacks. Route/device/profile/параметры CPU передаются в действующий Router. Общее ограничение сеансов `max_active_translation_jobs=1` сохранено; отмена не освобождает сеанс до фактического завершения worker. Native resources освобождаются на владеющем worker перед остановкой executor.

## DOCX: что переводится и сохраняется

- Абзацы, заголовки, numbered/bulleted lists, таблицы и вложенные таблицы, header/footer всех найденных частей.
- Word runs не переводятся по одному. Текст внутри логического блока объединяется, включая обычные подписи hyperlink. Длинный блок ограничен 1200 символами; далее действует существующее ограничение токенов движка. URL, field codes/results, табуляция, разрывы и непрозрачные объекты образуют защищённые границы.
- После перевода текст распределяется между исходными `w:t` пропорционально длине spans с предпочтением границ слов. Все существующие run properties сохраняются. Это **не semantic alignment**: жирное/курсивное выделение и подпись внутри ссылки могут сместиться на другие слова.
- Исходные стили, нумерация, paragraph properties, размеры и геометрия таблиц, шрифты, alignment, section/margins, relationships, изображения и бинарные вложения сохраняются. ZIP members за исключением изменяемых `document/header/footer` XML копируются без изменения содержимого; сохраняется и комментарий ZIP.
- IDs, metadata, relationship URLs, видимые HTTP/www/mailto/email, field instructions/results и бинарные данные не отправляются в переводчик. Внешние связи не загружаются.
- Не переводятся текст внутри рисунков/text boxes, content controls, удалённые tracked changes, сноски, комментарии, формулы, результаты полей. Их данные сохраняются. Цифровые подписи после изменения документа недействительны.
- Автоматическое определение языка: до 24 равномерно выбранных блоков, включая конец документа, до 320 символов из каждого; одно определение основного языка на документ. Смешанный документ не разбивается на языки каждого run. Пустые/числовые документы копируются без загрузки detector/model.
- Защитные лимиты: 256 МиБ исходного и суммарного распакованного содержимого, 20 000 ZIP members. Зашифрованные, повреждённые и неподдерживаемые пакеты завершаются ошибкой без записи оригинала.

## Сохранение и имена

По умолчанию `manual.docx` → `manual_ru.docx`. При совпадении имени используется `manual_ru (1).docx` и далее. Настройка `{name}` также не допускает совпадения с source: создаётся свободное имя с номером. Custom output использует существующие настройки.

Перевод названий файлов управляется отдельным сохранённым параметром `translate_filenames` и не зависит от `translate_directories`. При включении только base filename проходит через тот же Router и тёплый backend текущего job; extension сохраняется без изменений. После перевода удаляются запрещённые Windows-символы и trailing dots/spaces, а зарезервированные, пустые или непригодные результаты откатываются к исходному base filename.

Для выбранной папки создаётся отдельная выходная ветвь, сохраняются вложенные каталоги. Перевод каталогов проходит через тот же Router, результат очищается от Windows forbidden/reserved names; коллизии каталогов разделяются. Имя каждого исходного каталога кэшируется на задание. Базовые имена файлов не переводятся — добавляется выбранный suffix/template.

Порядок на файл: исходный SHA256 → извлечение/перевод → временный `.treetranslate-*.docx` в выходной папке → ZIP CRC + непустой файл + python-docx open + доступ к tables/sections → повторный SHA256 → atomic publication без замены существующего пути. На Windows используется `os.rename`, на POSIX — no-clobber hard link с удалением temp. Windows-ветвь проверена в этой среде; POSIX-ветвь здесь не запускалась.

При cancel/error собственный временный файл удаляется. Уже успешно опубликованные документы пакета остаются доступны; повреждённый final не создаётся. Пустые новые выходные каталоги могут остаться после отмены. Если оригинал изменил другой процесс, приложение отказывается публиковать результат для него. Приложение никогда не открывает source для записи.

## Прогресс и UX

Использованы существующие FileTranslationPage, FileTree, DropZone, ProgressPanel и state machine. Полного редизайна и новых UI-компонентов нет.

- Файловая демонстрация заменена реальными DOCX. Другие форматы получают честный статус о неподдерживаемом формате.
- Реальные counters: current file, X/N, обработанные/всего сегментов, %, elapsed и приблизительный ETA без времени паузы. На предварительном чтении показывается текущий файл; 100% появляется только после проверки и публикации последнего результата.
- Pause не прерывает native C++ принудительно: текущий ограниченный запрос может закончиться, следующий ждёт Resume. Cancel прекращает новые запросы и ждёт безопасного возврата текущего.
- Ввод файлов, дерево и параметры блокируются во время работы. Кнопки «Открыть файл» и «Открыть папку» активны при наличии валидного результата; отображается путь последнего результата. «Открыть файл» открывает последний показанный файл, папка — расположение результатов.
- UI actions открытия проверены на корректную передачу пути в QDesktopServices/Explorer. Внешний Word не запускался автоматическим тестом.

Это локальные изменения существующих компонентов: замена фиктивных статусов, реальные paths/галочки, дополнительная кнопка и строка пути. Их причина — сделать уже существующий файловый workflow рабочим.

## Зависимости и приватность

Добавлены python-docx 1.2.0, lxml 6.0.2; typing_extensions 4.16.0 закреплён как транзитивная зависимость. Обновлены runtime requirements/lock, notices и wheel licenses. Office/LibreOffice/облачные конвертеры в runtime не добавлены.

Document logging содержит только source/output path, размер, количество сегментов, language pair, длительность, error type. Содержимое документа и перевода не логируется. Router сохраняет существующие безопасные backend/device metrics. Тесты запрещают socket DNS/connect и подтверждают отсутствие сетевых обращений при настоящем DOCX-переводе.

## Реальные результаты

Windows / Python 3.12.13 / PySide6 6.11.1; Ryzen 7 5700X / RTX 3080 12 ГБ. Локальные Argos EN→RU и M2M100 418M CT2 INT8. Профиль «Баланс». Ниже — время небольших синтетических файлов, включая подготовку; это smoke, а не сопоставимый cold/warm throughput benchmark.

| GUI сценарий | Маршрут | Состояние | Время |
|---|---|---|---|
| EN→RU, CPU, Auto source | Argos / CPU | COMPLETED | 2.218 с |
| ZH→RU, Auto, Auto source | M2M100 / CUDA | COMPLETED | 1.687 с |
| ZH→RU, GPU, Auto source | M2M100 / CUDA | COMPLETED | 0.734 с |
| Папка с 2 DOCX + вложенность + перевод каталогов | Argos / CUDA | COMPLETED | 1.234 с |
| Pause/Resume | Argos / CPU | COMPLETED | 1.719 с |
| Cancel во время реального задания | Argos / CPU | CANCELLED | 0.250 с |

GUI smoke использует реальный `QApplication.exec()`/Windows platform, MainWindow и Qt drag/drop events. Он работает со скрытым нативным тестовым окном и изолированными QA settings. Скриншоты окна сохранены и просмотрены; ошибок GUI/завершения native worker нет. Отмена произошла после первого сегмента во время следующего bounded запроса; final/temp отсутствуют. Пауза проверяет остановку новых запросов и активный warm pin.

Фактические примеры из синтетических fixtures:

- EN: `Save the configuration file before restarting the application.` → `Сохраните файл конфигурации перед перезагрузкой приложения.`
- ZH: `请在重新启动应用程序之前保存配置文件。` → `Защитите файлы профиля до перезапуска приложения.` Это реальный результат M2M100, **с лексической неточностью**: ожидается сохранение файла конфигурации. Document Layer не улучшает модель и не подменяет результат ручной фразой.
- Каталоги: `User guide/Installation` → `Руководство пользователя_ru/установка`.

Дополнительные integration tests покрывают EN→RU и ZH→RU для каждого CPU/GPU/Auto, document-level detection, paragraphs/tables/header/footer, валидный output, unchanged SHA256 и отсутствие сетевых обращений. Без установленных weights такие тесты SKIP; в этой среде они выполнены.

Полные hashes before/after, фактические пути, вызовы backend/device и длительности: [aw05-docx-gui.json](qa/aw05-docx-gui.json). Во всех семи входных файлах шести GUI сценариев исходные SHA256 совпали; каждый опубликованный output повторно открылся python-docx. Коллизии уже существовавших QA результатов также реально дали суффиксы `(2)`.

## Проверки

- `pytest -q --junitxml=docs/qa/aw05-final-tests.xml`: **189 passed**, без skip/failure. Финальное время зафиксировано в [JUnit XML](qa/aw05-final-tests.xml).
- `python -m compileall -q app tools`: успешно.
- `git diff --check`: успешно.
- `python tools/smoke_docx_ui.py`: 6 успешных сценариев, `errors: []`, без fallback. Валидные результаты EN/ZH/папки/паузы; корректная отмена.
- Unit fixtures включают paragraph, heading, lists, mixed runs, nested tables, header/footer, Chinese/Unicode, PNG, opaque binary, hyperlinks/URLs/field protection, empty/numeric, corrupted DOCX, PDF, collisions, output validation failure, cancel перед публикацией, pause/resume, изменённый внешним процессом source и private logging.
- Проверены session admission при отмене, shared-worker lifetime, запрет idle unload во время file job, выбор файлов и UI open actions.

### Невыполненный визуальный gate DOCX

Штатный `render_docx.py` завершился `FileNotFoundError: LibreOffice soffice.exe was not found on PATH`. Поиск в bundled dependencies также не нашёл LibreOffice. [Навык documents SKILL.md](C:/Users/PC/.codex/plugins/cache/openai-primary-runtime/documents/26.909.12148/skills/documents/SKILL.md) требует: “never use the user's installed desktop LibreOffice even if the bundled version fails”. Поэтому системный Office/LibreOffice не использовался как обход. Структурные проверки выполнены; **постраничная вёрстка DOCX не проверена визуально**. Это ограничение QA среды, а не зависимость runtime TreeTranslate.

## Technical debt

1. Semantic run/hyperlink alignment; точное сохранение выделенных слов после перестановки слов.
2. Лингвистическая оценка и дальнейшее улучшение ZH→RU модели — текущий этап без обучения.
3. Семантический перевод имён файлов. Сейчас базовое имя сохраняется, меняется только output template/suffix.
4. Текстовые поля, content controls, footnotes/comments/field results и иные сложные элементы остаются без перевода.
5. Постраничная проверка на разрешённом renderer, включая реальные многостраничные пользовательские документы; проверка POSIX publication.
6. На смешанных языках используется основной язык документа; язык каталога берётся из первого обрабатываемого документа этой ветви.
7. После отмены могут остаться собственные пустые выходные каталоги; готовые файлы пакета намеренно сохраняются.

## Изменённые файлы и Git

Код: `app/documents/` (6 файлов), `app/services/document_translation_service.py`, Hybrid/TranslationService, RuntimeManager, TranslationUiController, FileTranslationPage, FileTree, DropZone, ProgressPanel, FilePicker, FileItem, TranslationProgress, constants и changelog dialog.

Проверки: `tests/test_documents.py`, `tests/test_documents_integration.py`, `tests/test_document_service.py`, `tests/test_runtime_lifecycle.py`, `tools/smoke_docx_ui.py`.

Документация/артефакты: README, CHANGELOG, THIRD_PARTY_NOTICES, runtime requirements/lock, vendor licenses, этот отчёт, JUnit XML, GUI metadata и 6 скриншотов `docs/qa/aw05-*`.

Ветка на момент финальной проверки: `codex/aw0.4-alpha`. Коммиты, merge, installer и deployment не выполнялись. Изменения оставлены в рабочем дереве. Точный snapshot: [AW0.5_DOCX_GIT_STATUS.txt](AW0.5_DOCX_GIT_STATUS.txt). Репозиторий Velora в исходном cwd не менялся.
