# TreeTranslate AW0.8.2 — Settings & Main UI Cleanup

Дата: 29 сентября 2026. База: локальная рабочая копия AW0.8. Версия: **AW 0.8.2**, без `-alpha`.

Статус: завершён. Финальный полный regression: **565 passed, 0 failures, 0 errors, 0 skipped**, 166.34 s. Все 8 каталогов содержат по 713 записей; требуемых ключей 696, отсутствующих — 0.

## Результат

**Область перевода больше не выбирается пользователем. Knowledge domain определяется автоматически. При недостаточной уверенности используется general.**

**Performance Profiles больше не являются пользовательской настройкой. Backend/routing policy выбирается автоматически.**

Главные страницы сохраняют прежнюю структуру: языки, текст или файлы, Auto/CPU/GPU, запуск/состояние/прогресс. Удалены profile selector, domain selector, рекомендации профилей и технический backend status обычного текстового перевода. Предупреждения о неполном применении терминологии остаются; старое предупреждение glossary не показывается для нового успешного результата из TM.

## Аудит и карта связей

| Control / поведение | Persistence | Runtime consumer / итог |
|---|---|---|
| Source/target language | `language/source`, `language/target` | TranslationPreferences → TranslationRequest / DocumentConfig; locale не меняет значения |
| Auto/CPU/GPU | `performance/device` | Единый TranslationPreferences → text/files/Settings → существующий DeviceManager |
| Старый profile | `performance/mode` | Нормализуется к Automatic; UI control удалён |
| Старый manual domain | `translation/domain` | Игнорируется обычным UI; запрос передаёт `domain='auto'` |
| Старые threads/RAM/VRAM/GPU policies | старые ключи сохраняются | UI не показывает и не применяет ручные значения; используются defaults |
| Output folder/naming | `general/output_*` | DocumentConfig → существующая безопасная запись с защитой оригинала |
| Open output | `general/open_output` | TranslationUiController после COMPLETED |
| Remember languages | `general/remember_language` | При OFF следующий запуск использует исходные defaults |
| Restore task | `general/restore_job`, `job/*` | Сохранение путей → повторный scan → READY без автоматического перевода |
| UI locale | `general/ui_language` | Статические каталоги → существующие виджеты; новая locale сохраняется как код |
| ETA / details | `interface/eta`, `interface/detailed_progress` | Живое событие SettingsService → ProgressPanel; сохранение через restart |

Проверены MainWindow, обе страницы перевода, SettingsService, TranslationPreferences, TranslationUiController, TranslationSessionManager, Router, engine_profiles.json, DeviceManager/RuntimeManager, Knowledge/TM/Glossary, document extraction и существующие тесты. UI был тесно связан с русскими display labels; presentation adapters сохраняют canonical combo values при смене отображаемого языка.

## Settings

**General** сохраняет output location/naming, открытие результата, запоминание языков, защиту оригиналов и восстановление задачи. При восстановлении пользователь видит подготовленную очередь и сам запускает перевод. Unknown/corrupt boolean values безопасно заменяются default.

**Language**: ru-RU, en-US, en-GB, de-DE, es-ES, fr-FR, zh-CN, ja-JP. Выбор немедленно обновляет существующие подписи, кнопки, меню, placeholders и диалоги. Редакторы, выбранные файлы, языки перевода, Device и путь результата не пересоздаются. Старые названия локалей читаются как aliases, неизвестное значение даёт ru-RU.

**Performance**: только устройство обработки и фактическое оборудование с кнопкой обнаружения. Удалены профиль, threads, GPU policy, RAM/VRAM limits, рекомендации и переключатели низкоуровневого управления. Обнаружение выполняется в отдельном потоке, без блокирующих PowerShell-вызовов в GUI. CPU/RAM/Windows GPU fallback сохранены; VRAM NVIDIA читается через nvidia-smi. Недостоверная память и неизвестное число потоков не подменяются выдуманными значениями. CUDA availability берётся у существующего DeviceManager, а не из одного имени видеокарты.

**Interface**: только ETA и Detailed Progress. Compact показывает bar/percent и номер файла очереди; Detailed добавляет файл, стадию, сегменты, страницу при её наличии и elapsed. ETA управляется своим переключателем, включая Compact. Прежние theme/accent/animations/extensions controls убраны; внутренняя theme architecture не удалена.

## Device и внутренняя policy

Используется существующая Automatic policy: она сохраняет прямой Argos для EN↔RU и доступный M2M100 для других поддерживаемых пар. Router, enum профилей, engine_profiles.json, CLI/dev API и явные `TranslationRequest` / `DocumentConfig` параметры сохранены. Нового scheduler и режима CPU+GPU нет.

CPU даёт только CPU candidates. GPU требует совместимый CUDA backend и при его отсутствии выдаёт понятную ошибку; выбор пользователя не переключается незаметно на CPU. Auto использует существующие допустимые GPU/CPU fallback. Idle unload, безопасная выгрузка и OCR/model mutual exclusion сохранены.

## Автоматическая область

`DomainDetector` использует enabled stores существующего GlossaryEngine: user glossary, bundled knowledge и включённые installed packs. База терминов не расширялась. В evidence допускаются CONFIRMED/REVIEWED/IMPORTED/BUILTIN с trust ≥ 0.8; AUTO/REJECTED/DISABLED, FORBIDDEN и context-specific записи не участвуют. Подавленные пользователем bundled terms исключаются.

Сигнал — точное нормализованное совпадение с границами слова. Generic terms исключаются; вес учитывает длину, trust, число областей, содержащих термин, и ограниченную поддержку повторениями. Перекрывающиеся вложенные термины не считаются независимыми. Один повторяемый термин недостаточен.

Порог: минимум 2 независимых термина, score ≥ 4, отрыв ≥ 1.5 и отношение к следующей области ≥ 1.5. Иначе general. Это эвристическая мера evidence, **не вероятностная confidence**. В runtime сохраняются только domain/score/match count/margin и индекс терминов; исходный пользовательский sample не кэшируется и не логируется детектором.

Text: классификация актуального request после определения языка, перед существующим TM lookup. **TM остаётся первым поставщиком перевода**; подтверждённая general/domain memory по-прежнему имеет приоритет перед glossary/model. Explicit domain разработчика обходит auto.

DOCX/native PDF/OCR PDF: один bounded representative sample на документ после извлечения (включая OCR), до terminology translation pass. До 24 равномерно выбранных сегментов, до 8000 символов, с началом/серединой/концом длинных абзацев. Результат лежит в плане документа и используется всеми его сегментами и TM prefetch. Два файла batch могут иметь разные области; все domains одновременно не включаются.

Проверены реальные термины существующих packs: «охлаждающая жидкость и коленчатые валы» → automotive; «азотирование и цементация стали» → metallurgy; их смешение и общий текст → general. Это проверка механизма, не доказательство полноты отраслевой классификации.

## Локализация и UI QA

Восемь статических JSON-каталогов; обязательные ключи покрыты на 100%, missing required keys = 0. Точное количество и template validation зафиксированы в `qa/aw082/validation.json`. Форматные аргументы, HTML, пути и имена файлов не переводятся моделью во время работы. Редакторы и dictionary/example source content не проходят через UI localization. Оригинальные LICENSE/NOTICE не изменены; локализуется только app-owned представление каталога.

Существующие Qt components расширены небольшими presentation adapters; глобального monkey-patching Qt нет. Исходные строки удерживаются только в UI для повторного отображения при смене locale; canonical combo values не заменяются display labels. Для completer переводится подпись действия, само предлагаемое слово остаётся исходным.

Каталоги подготовлены offline на установленной модели, затем основные экраны/действия и критические сообщения отредактированы вручную. Наличие всех ключей не означает независимой лингвистической сертификации восьми языков; редактура носителями длинных исторических описаний остаётся полезной дальнейшей QA.

Визуальные проверки: ru/en/de/zh — text/files, General, Performance, Interface; About на английском. Runtime switch проверен для всех восьми locales. Скриншоты: `docs/qa/aw082/*-settings-*.png`, `*-text.png`, `*-files.png`, `en-US-about.png`. Проверка app-owned labels: `locale-render.json`.

Небольшие сопутствующие UI-правки: перенос длинной подсказки DropZone и минимальная высота «Подробнее» с общим stylesheet. Причина — обрезание текста после локализации. Сетка языковых плиток, порядок вкладок и общая визуальная концепция сохранены; новых декоративных панелей нет.

## Проверки

- Адресные tests: Settings/locales/migration, UI sync, auto-domain, TM priority, per-document cache/batch, restore и language support. Результат в `qa/aw082/targeted-tests.xml`.
- Полный pytest: итог в `qa/aw082/full-tests.xml` и `validation.json`; включает реальные локальные engine/OCR проверки и unavailable GPU scenario.
- `python -m compileall -q app tools`, `git diff --check`: успешно; Git может сообщать advisory LF→CRLF, ошибок whitespace нет.
- Отдельный процесс write → exit → read для **каждой из 8 локалей**: сохранена locale, восстановлена очередь READY, перевод автоматически не стартует, ETA/details OFF сохранены. Всего 16 процессных фаз.

Промежуточные полные запуски выявили native access violation Qt в UI smoke; отдельно весь UI smoke и связка с native lexical smoke проходили (36 и 37 tests). Исправлена изоляция Qt-тестов: один QApplication на сессию, явное закрытие и deferred deletion созданных тестом корневых виджетов, принадлежащих Python. Qt-owned popup объекты освобождаются только их владельцем. Проверка Settings/UI/coordination/documents после этой правки: 69 passed. Точный native стек сбоя не установлен; изменение устраняет накопление закрытых тестовых окон и недетерминированное освобождение их ресурсов между тестами.

Ещё один промежуточный полный запуск дал 564 passed и одно падение проверки анимации: первый таймерный кадр под нагрузкой совпал с исходным. Проверка кадров теперь использует фиксированные моменты шкалы QPropertyAnimation, сохраняет проверку запуска по клику, промежуточных отрисованных положений и конечного состояния. Другие проверки анимации через реальный event loop сохранены.

Реальный smoke на Ryzen 7 5700X, 16 logical threads, 32 GB RAM, RTX 3080 12 GB, CUDA available:

| Requested | Actual | Backend | Compute type | Fallback |
|---|---|---|---|---|
| CPU | cpu | argos | int8 | false |
| GPU | cuda | argos | int8_float16 | false |
| Auto | cuda | argos | int8_float16 | false |

Все три переводят контрольную инструкцию с сохранением запрета. DOCX, native PDF и OCR PDF — 3/3 completed; SHA256 оригиналов совпали, выходные документы прошли встроенную validation. OCR фактически использовал paddle/gpu. Реальная обработка документа прошла pause/resume; cancel завершился TranslationCancelledError без публикации результата. Наблюдаемых сетевых попыток в smoke — 0, включая OCR worker. Полные факты: [real-smoke.json](qa/aw082/real-smoke.json).

## Ограничения и границы этапа

Существующие bundled technical packs преимущественно RU↔ZH: для других пар auto-domain часто корректно возвращает general. Неоднозначные/общие слова не принуждают область; metadata packs могут содержать широкие классификации. Метод не добавляет понимания смысла, morphology и новых терминов. Известные ограничения качества переводческих моделей из AW0.8 сохраняются.

Не выполнялись OCR/PDF/cache/batch optimizations, Google comparison, benchmark matrix, новые модели/словари, light/system theme development, installer или packaging. Из OCR изменён только текст сообщения timeout: оно больше не предлагает отсутствующий пользовательский профиль. Следующий цикл не начат.

## Сохранность

До изменений сохранены `build/aw082/baseline.zip`, SHA256-манифест, git status/diff — 1226 исходных файлов. Текущая ветка `codex/next-cycle`; существующие незакоммиченные изменения сохранены. Commit/push/reset/revert не выполнялись. Исторические отчёты и payload моделей/словарей не переписывались. Итоговая сверка: `qa/aw082/preservation.json`, Git status: `qa/aw082/git-status.txt`.
