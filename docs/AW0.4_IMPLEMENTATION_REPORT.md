# TreeTranslate AW 0.4-alpha — итоговый отчёт Phase 1

> Исторический срез до калибровки. Оставленные здесь предварительные профили и mock-словарь уже доработаны: [актуальный отчёт — подсказки, словарь, 153 теста и новые замеры](AW0.4_LANGUAGE_ASSISTANCE_REPORT.md).

Дата: 15 сентября 2026. Репозиторий: `C:\TreeTranslate`.

**Текстовый Hybrid Translation Engine реализован и проверен на настоящих локальных моделях.** Завершены этапы A–K. Итог: **111 тестов проходят**, включая **18 integration cases**, реальные CPU/GPU-переводы и закрытие настоящего Qt-окна. Benchmark: **88 сценариев, 536 запросов, 0 ошибок** на Ryzen 7 5700X / RTX 3080 12 GB. Профили пока предварительные; замеры являются исходными данными для отдельной настройки.

## 1. Аудит AW 0.3 и сохранённая граница

До изменений рабочее дерево было чистым, HEAD `378fe60` (`chore: freeze AW 0.3 UI and architecture`); исходные 53 теста проходили. Проверены interfaces, TranslationService, MockTranslationService, preferences, session manager и TranslationUiController.

В AW 0.3 `QTimer.singleShot(0)` лишь откладывал синхронный mock-перевод в GUI thread. Его нельзя было заменить тяжёлым inference напрямую. Теперь цепочка следующая:

```text
GUI (существующие страницы)
  → TranslationUiController
  → TranslationService / HybridTranslationService
  → TextTranslationEngine Protocol
  → TranslationRouter
  → RuntimeManager
  → ArgosBackend / M2M100Backend
  → CTranslate2
```

Qt остаётся на service/controller уровне. Backend, Router и ModelManager не используют QObject/QWidget. Прежний абстрактный file/job TranslationEngine сохранён совместимым; новый текстовый Protocol не притворяется готовым файловым engine.

## 2. Итоговая структура engine

```text
app/engine/
├── interfaces.py                  # legacy ABC + TextTranslationEngine Protocol
├── types.py                       # request/result/capabilities/options/metrics
├── errors.py                      # neutral errors, безопасные сообщения
├── factory.py
├── languages.py                   # lazy local langid
├── models/manifest.py
├── backends/
│   ├── base_backend.py
│   ├── argos_backend.py
│   ├── m2m100_backend.py
│   ├── m2m100_tokenizer.py
│   └── text_segments.py
├── router/
│   ├── route_decision.py
│   ├── routing_policy.py
│   └── translation_router.py
└── runtime/
    ├── model_manager.py
    ├── device_manager.py
    ├── runtime_manager.py
    ├── cuda_libraries.py
    └── offline.py
```

Параметры — `app/config/engine_profiles.json`; интеграция Qt — `app/services/hybrid_translation_service.py`. Гигантского монолитного engine-файла нет.

## 3. Dependencies и фактическая совместимость

Runtime: PySide6 6.11.1 (существующая), Argos Translate 1.11.0, CTranslate2 4.8.2, SentencePiece 0.2.2, Sacremoses 0.1.1, Packaging и локальный langid 1.1.6. NumPy и другие транзитивные зависимости зафиксированы в `requirements-runtime-lock.txt`.

GPU на этой машине: официальный NVIDIA cuBLAS CUDA 12 `12.9.2.10` и зависимость wheel NVRTC `12.9.86`. Первоначальный GPU-запуск показал отсутствие `cublas64_12.dll`; после установки этих локальных DLL реальный GPU inference работает. Driver: **610.88**. CT2 сообщил CPU types `int8/int8_float32/float32`, CUDA поддерживает в том числе `int8_float16`.

Build: отдельное `.venv-build`, PyTorch 2.10.0, Transformers 4.57.6, CT2 converter и их зависимости. Runtime `.venv` **не содержит PyTorch и Transformers** — проверено отдельно и в fresh-process integration test. Dev: pytest 9.1.1, psutil 7.2.2.

Файлы зависимостей: `requirements-runtime.txt`, `requirements-runtime-lock.txt`, `requirements-argos.txt`, `requirements-gpu.txt`, `requirements-build.txt`, `requirements-dev.txt`. Установка runtime — через `tools/install_runtime.py`, включая offline wheelhouse вариант.

## 4. Реально доступные модели и пути

Все артефакты получены на development/build стадии с явного разрешения пользователя. Приложение их не загружает из сети.

| ID | Реальный путь относительно `C:\TreeTranslate\vendor\models` | Размер подготовленного дерева |
|---|---|---:|
| argos-en-ru | `argos/argos-en-ru` | 217 259 288 байт |
| argos-ru-en | `argos/argos-ru-en` | 173 455 367 байт |
| argos-zh-en | `argos/argos-zh-en` | 86 137 496 байт |
| argos-en-zh | `argos/argos-en-zh` | 85 640 765 байт |
| m2m100-418m-int8 | `m2m100-418m-int8` | 499 882 152 байта |

Всего: **1 062 375 068 байт** подготовленных моделей, без build sources и DLL.

Argos: official index `argosopentech/argospm-index` → HTTPS artifacts `argos-net.com/v1`, package version 1.9. Источник M2M100: `facebook/m2m100_418M`, revision `55c2e61bbf05dfb8d7abccdc3fae6fc8512fd636`, локальная конвертация в CT2 INT8. M2M100 runtime использует `model/model.bin`, CT2 config/vocabulary и `tokenizer/sentencepiece.bpe.model`, `vocab.json`, `languages.json`.

Исходники находятся в игнорируемом `build/model-sources`. Подготовленные бинарники и окружения исключены из Git; manifest, metadata, licenses и scripts доступны для review.

## 5. Manifest / ModelManager

`vendor/models/models_manifest.json` хранит model id, backend, version, source, languages/pairs, format, quantization, expected files, size, SHA256 и license. ModelManager читает инвентарь лениво, проверяет наличие и размеры, предоставляет путь и состояния AVAILABLE/MISSING/CORRUPTED/LOADING/READY/ERROR.

SHA256 не считается при старте GUI. `tools/verify_models.py` выполняет полную ручную проверку; **все пять моделей прошли её**. Пути проверяются на выход за model root; известное повреждение не снимается дешёвой повторной проверкой размера.

При отсутствии модели нет загрузки из сети: появляется «Компонент локального перевода отсутствует или повреждён». Обычные unit tests работают с временными маленькими файлами и fake backend.

## 6. Argos: важное архитектурное решение

Использован **официальный пакет argostranslate**, без форка. Пары получаются из его Package API, а токенизация/детокенизация выполняется официальными классами. Имя директории не является источником сведений о паре.

Однако high-level `argostranslate.translate` в опубликованном wheel 1.11.0 импортирует Stanza/PyTorch, а SBD может скачивать дополнительные модели. Поэтому TreeTranslate использует небольшой CT2 adapter поверх официальных packages/tokenizers и детерминированное punctuation splitting. Это осознанное отклонение от предпочтительной схемы из ТЗ ради обязательных offline/PyTorch-free требований. Измеряется именно **ArgosBackend TreeTranslate**, а не сторонний CLI с нейронным SBD.

`ARGOS_PACKAGE_DIR` и фактически используемый в 1.11 `ARGOS_PACKAGES_DIR` задаются на bundle. У `get_installed_packages(path=...)` опубликованная аннотация расходится с реализацией: эта версия ожидает список roots; учтено и проверено. XDG config/cache изолированы в каталоге данных TreeTranslate; глобальная конфигурация Argos не нужна. Настройки синхронизированы lock; при смене device/options старый CT2 translator выгружается и создаётся новый.

## 7. Router V1

| Профиль | Детерминированное правило |
|---|---|
| Economy | Argos direct, затем Argos pivot; Quality backend выключен; Auto предпочитает CPU |
| Fast | Argos direct → M2M100 direct → Argos pivot |
| Balanced | Argos direct для EN↔RU; M2M100 для ZH↔RU и остальных непроверенных пар; затем разрешённые fallback |
| Turbo | Правила Balanced; отдельные предварительные threads/beam/batch параметры |
| Maximum | M2M100 direct → Argos direct → Argos pivot |
| Automatic | Правила Balanced с доступными capabilities и выбором Auto устройства |

Source == target возвращает исходный текст без backend/device initialization. Прямой путь предшествует pivot. ZH↔RU в Balanced/Automatic/Maximum реально выбирает **прямой M2M100**. Список предпочтительных пар предварительный и не является заявлением об измеренном качестве.

## 8. CPU / GPU / Auto и fallback

- CPU: только CPU, без GPU probe для inference.
- GPU: только CUDA. Если устройство или inference недоступны, понятная ошибка с предложением выбрать CPU/Auto.
- Auto: при допустимости по профилю CUDA → CPU. Fallback на другое устройство разрешён только в Auto.
- Явный GPU имеет приоритет перед рекомендацией Economy использовать CPU. Это решение сохраняет USER CONTROL.
- Compute type выбирается из capabilities. На этой машине фактически использованы `int8` на CPU и `int8_float16` на CUDA.

Маршрут содержит backend, reason, profile, device preference и fallback chain; результат — фактическое устройство/compute type, model IDs и fallback_used. При ошибке backend используется следующий разрешённый вариант. При отмене fallback не продолжается. Benchmark backend-only запрещает переход к другому backend, чтобы ошибки Argos не измерялись как скорость M2M100.

## 9. Lazy loading / idle / shutdown

Fresh-process тест подтверждает отсутствие импортов Argos, CT2, SentencePiece, Transformers, PyTorch и langid при создании GUI. До первого запроса ни одна модель не загружена.

Первый запрос загружает необходимые модели; следующие используют translator повторно. RuntimeManager сохраняет один выбранный backend тёплым. При переключении backend старый освобождается. Idle timeout по умолчанию **180 секунд**, изменяемый в JSON. Переключатель «Освобождать модель после простоя» может отключить idle unload.

Timer/lock не позволяют выгрузке совпасть с активным native inference. Реально проверены reuse, idle unload, reload и shutdown. В Qt smoke idle timeout временно сокращён до 0.2 секунды, чтобы проверить GPU unload/reload автоматически.

Найден и исправлен Windows CUDA crash при выходе: завершение worker до освобождения его native ресурсов приводило к аварийному коду выхода. Теперь engine.shutdown выполняется **на worker перед остановкой executor**. Fresh-process тест настоящего Qt окна проверяет нормальный exit code 0.

Веса освобождаются; CUDA context и загруженные библиотеки могут сохранять служебный RAM/VRAM до завершения процесса. Обещания возврата абсолютно всей памяти после idle нет.

## 10. Async service / stale requests / sessions

Debounce **420 мс** сохранён. Сервис допускает один выполняющийся native запрос и один заменяемый ожидающий запрос. Новый текст/язык/device/profile помечает старый результат неактуальным; очистка поля удаляет старый результат. C++ thread не прерывается принудительно. Отмена проверяется между ограниченными пакетами токенов.

Result/error возвращаются queued Qt signal в GUI thread. SessionManager сохраняет `max_active_translation_jobs=1`: после отмены text session освобождается только после физического завершения native call, поэтому файлы и текст не переводятся одновременно.

Число CPU threads учитывает ручную настройку и доступные logical cores. Остальные неподключённые ограничения AW 0.3 перечислены ниже и отмечены в настройках.

## 11. Offline / logging / metrics

Runtime не импортирует инструменты подготовки. Он использует локальные пути, HF offline flags, отключённые telemetry/debug и thread-scoped Python audit guard для socket/HTTP. Реальные fresh-process initialization + inference проверены дополнительным audit observer: **0 сетевых попыток**, включая импорт зависимостей; установка чужого Argos provider/debug в тесте не меняет поведение.

Защита не является OS firewall и не утверждает перехват произвольного стороннего native кода. Проверены фактически используемые пути библиотек. GitHub/Boosty открываются только действием пользователя.

Логируются backend, route, device, model id, duration, input length, fallback и error type. Исключения native библиотек не выводятся целиком: они могут содержать токены пользователя. Текст и результат не входят в логи/metrics. Метрики — bounded deque последних 1000 попыток в памяти, без отправки и обучения Router.

## 12. Реальные результаты benchmark

Оборудование: **AMD Ryzen 7 5700X, 8 cores / 16 threads; NVIDIA RTX 3080, 12 288 MiB, driver 610.88; Windows, Python 3.12.13**.

Balanced: 3 backend × 2 устройства × 8 примеров = **48 сценариев**. В каждом — cold + 1 warmup + 5 warm repeats: **336 запросов**. Остальные пять профилей Router: 5 × 2 × 4 технических примера = **40 сценариев**, cold + warmup + 3 repeats: **200 запросов**. **Ошибок: 0.**

Ниже — медиана повторных запросов, **мс**, на технических фразах одинакового корпуса в Balanced:

| Направление | Argos CPU | M2M100 CPU | Argos GPU | M2M100 GPU |
|---|---:|---:|---:|---:|
| EN→RU | 300.9 | 758.5 | 114.7 | 150.8 |
| RU→EN | 134.9 | 766.1 | 79.6 | 170.9 |
| ZH→RU | 416.4 | 815.9 | 173.3 | 155.7 |
| RU→ZH | 272.7 | 778.7 | 145.3 | 167.0 |

**Argos ZH↔RU здесь является pivot через EN; M2M100 — direct.** Они выполняют разные цепочки перевода, поэтому скорость не доказывает равное качество.

Профили Router на тех же технических примерах, warm median мс:

| Профиль | EN→RU CPU | EN→RU GPU | ZH→RU CPU | ZH→RU GPU |
|---|---:|---:|---:|---:|
| Economy | 268.0 | 92.7 | 349.2 | 139.9 |
| Fast | 191.7 | 91.6 | 537.0 | 131.6 |
| Balanced | 308.7 | 106.0 | 745.4 | 169.4 |
| Turbo | 180.5 | 92.1 | 441.5 | 145.7 |
| Maximum | 916.6 | 151.7 | 922.1 | 181.7 |
| Automatic | 316.8 | 114.7 | 1042.2 | 159.7 |

В Economy ZH→RU использует Argos pivot, в остальных строках — M2M100. Maximum для EN→RU тоже использует M2M100. GPU в этой таблице выбран явно, в том числе для Economy. Automatic profile с explicit CPU/GPU — не то же самое, что device Auto.

Первые технические запросы Balanced: Argos CPU около 466–945 мс, Argos GPU 638–987 мс; M2M100 CPU 1433–1484 мс, GPU 1103–1124 мс. Это cold latency внутри свежего процесса, включая импорт/discovery/loading, но не запуск интерпретатора.

Peak RSS sampled для технических сценариев: Argos CPU примерно 228–369 MiB, M2M100 CPU 627–631 MiB; Argos GPU 451–656 MiB, M2M100 GPU 785–804 MiB. VRAM записана как **общая память GPU в контрольных точках**, не peak VRAM процесса. В M2M100 GPU примерах после shutdown общая занятая память снижалась примерно с 2025 до 1481 MiB при baseline около 1274–1281 MiB; служебный CUDA context сохраняется до выхода.

Замеры выполнены последовательно. Модельная конвертация, тесты и другие наши inference-задачи не запускались параллельно benchmark. Windows/другие приложения и частоты CPU/GPU не фиксировались; samples немного, между запусками есть разброс. Поэтому различие Balanced и Automatic с одинаковыми параметрами не следует трактовать как отдельную гарантию скорости. Китайский words/sec не вычисляется; используются chars/sec.

Полные данные и корпус:

- [Balanced Markdown](benchmarks/aw04-balanced.md), [JSON с raw samples](benchmarks/aw04-balanced.json), [CSV](benchmarks/aw04-balanced.csv).
- [Profiles Markdown](benchmarks/aw04-profiles.md), [JSON](benchmarks/aw04-profiles.json), [CSV](benchmarks/aw04-profiles.csv).
- `tools/benchmark_corpus.json`, `tools/benchmark_translation.py`.

Никаких оценок BLEU/качества нет. Контрольное `你好世界` у M2M100 дало «Добрый мир»; техническое `请重新启动应用程序。` в настоящем UI — «Пожалуйста, перезагрузите приложение». Корректный inference и высокая скорость не заменяют будущую оценку качества на корпусе.

## 13. Тесты и результаты

Финальный запуск: **111 passed in 26.86s**, без failed/skip на этой машине. Из них 18 integration cases и 93 остальные проверки. Исходные AW 0.3 UI/service проверки сохранены; там, где проверялись mock ответы, mock теперь внедряется явно. Production MainWindow использует HybridTranslationService.

Добавлены проверки Router направлений/профилей, fallback/backend-only benchmark, CPU/GPU/Auto, passthrough, cancellation, privacy metrics, manifest containment/checksums, idle concurrency, worker coalescing, debounce, stale language changes, session exclusivity, startup imports, отсутствие сети, preparation opt-in и безопасное извлечение Argos. Реальные tests проверяют EN→RU, RU→EN, ZH→RU, RU→ZH, CPU/GPU и lifecycle. Отсутствие моделей даёт integration SKIP; повреждённые присутствующие artifacts вызывают ошибку.

Дополнительно:

- `compileall app tools`: успешно.
- `tools/verify_models.py`: SHA256 всех пяти моделей совпадает.
- `tools/verify_tokenizer.py`: 5 parity cases против официального Transformers tokenizer, успешно.
- `git diff --check`: без ошибок.
- Реальный скрытый Qt window с Windows platform plugin: autotranslation, GPU idle/reload, local language detection, нормальный выход процесса. [Проверенный снимок](qa/aw04-real-text.png).

Промежуточные проверки: baseline 53, contracts/model manager 5, router/lifecycle/offline 29, затем полный suite 102 → 104 → 110 → 111. Обнаруженный при дополнительном native UI smoke crash устранён, regression test включён в окончательный suite.

## 14. Изменения интерфейса

Полных UI rework нет. Существующие страницы, layouts, цвета и компоненты сохранены. Минимальные изменения:

1. Статус подготовки/результата/backend/device/ошибки в существующей строке под текстом.
2. Сброс устаревшего результата при изменении запроса.
3. Фиксированные AW 0.3 словарь/примеры скрыты, поскольку не описывают реальный текст.
4. Явная маркировка демонстрации файлов.
5. Текст idle unload и статус неподключённых resource limits уточнены в существующих настройках.
6. Добавлена запись AW 0.4 в существующую историю изменений.

Новых GUI-компонентов и редизайна нет. Новые компоненты относятся к engine/service и переиспользуются для всех поддерживаемых языковых пар.

## 15. Лицензии

Сохранены реальные upstream README/metadata и notices библиотек. M2M100 model card указывает MIT. Argos ZH↔EN README указывает CC-BY 4.0 для исходной OPUS модели. **Лицензии итоговых весов Argos EN↔RU не определены однозначно по доступным artifacts**; перед распространением это требует уточнения. MIT библиотеки Argos не выдана за лицензию весов.

Подробности и ссылки: [THIRD_PARTY_NOTICES](../THIRD_PARTY_NOTICES.md), `vendor/model-metadata`, `vendor/licenses`.

## 16. Что остаётся mock / planned

File Translation Engine, файловое дерево/прогресс/скорости, PDF, DOCX, OCR, ZIP/RAR processing, Translation Memory, Glossary и восстановление файловых задач. Hardware recommendation остаётся предварительной; RAM/VRAM caps, дополнительная настройка GPU usage и reduce_load сохраняются, но ещё не управляют real inference. Это отмечено в UI/README.

## 17. Технический долг и пределы Phase 1

- Отдельная оценка качества, затем настройка пяти профилей на основании corpus + benchmark. Параметры после этого замера намеренно не перенастроены.
- Проверка abbreviation/sentence splitting и длинных token chunks. Вход не обрезается молча; alpha делит его на ограниченные части. Лимит одного text request — 50 000 символов.
- Поддержка коротких/смешанных текстов в local language detection требует corpus review; целевой Auto не угадывается, UI просит выбрать язык.
- Argos Package/tokenizer adapter и отдельная `--no-deps` установка требуют повторной compatibility проверки при обновлении upstream. `pip check` видит отсутствующие неиспользуемые Stanza/SpaCy/MiniSBD.
- Сборка installer, включение CUDA DLL/models/notices и окончательное разрешение лицензионных вопросов — отдельный build/release этап.
- RSS sampled и общая VRAM не являются точными per-process GPU memory peaks. Полный hardware/thermal profiling не проводился.
- Завершение приложения кооперативно ждёт текущую ограниченную native batch; принудительного уничтожения C++ thread нет.

## 18. Git и завершение

Текущая существующая ветка: `codex/aw0.3-alpha`. Автоматических commits, push или смены ветки не было. Изменены engine/service integration, минимальные статусы UI, requirements, README/CHANGELOG/tests; добавлены backend/runtime/router modules, developer tools, manifest/metadata/licenses, benchmark reports и QA artifact. Snapshot: [git status](AW0.4_GIT_STATUS.txt).

Проверено, что model binaries, source models, CUDA environment и virtualenv не попадают в обычный Git diff. Максимальный новый отслеживаемый по умолчанию artifact на проверке — benchmark JSON около 155 KB. Репозиторий Velora в исходном каталоге задачи не изменялся.

**Работа остановлена в границах AW 0.4 Phase 1. К PDF/OCR/AW 0.5 перехода нет.**
