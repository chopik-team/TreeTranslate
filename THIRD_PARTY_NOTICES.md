# Third-party notices — TreeTranslate AW 0.6.2-alpha

## Local OCR runtime

- PaddleOCR 3.7.0, PaddleX 3.7.2, Paddle GPU 3.3.1 — Apache-2.0. Изолированы от translation environment из-за NumPy/CUDA dependencies.
- Десять OCR/layout/orientation/table моделей: Apache-2.0 по **отдельным model cards**, сохранённым в `vendor/model-metadata/ocr`. Exact IDs, revisions, file SHA256 и sources: `models_manifest.json` в этом каталоге.
- Полные notices 104 OCR distributions: `vendor/licenses/ocr-runtime`. `inventory.json` содержит версии, license metadata, размеры и пути. Дополнения из SHA256-проверенных sdists/официальных repositories перечислены в `upstream-licenses.json`.
- NVIDIA CUDA/cuDNN libraries имеют собственные условия распространения; их LICENSE texts сохранены из wheels. Публичный installer в этом этапе не выпускается.
- OCR содержит hub/network-related Python dependencies upstream; runtime запрещает их model lookup и сетевые операции. Скачивание artifacts возможно только отдельными developer tools с `--allow-network`.
- Подробный аудит и ограничения: [AW0.6.2_OCR_REPORT](docs/AW0.6.2_OCR_REPORT.md).

## DOCX Document Layer

- python-docx 1.2.0 — MIT. Copyright Steve Canny. Официальный пакет `python-docx`; текст лицензии из установленного wheel сохранён в `vendor/licenses/python-docx/LICENSE`.
- lxml 6.0.2 — BSD-3-Clause; бинарный wheel также содержит libxml2/libxslt и их notices. Оригинальные LICENSE.txt и LICENSES.txt из wheel сохранены в `vendor/licenses/lxml/`.
- typing_extensions 4.16.0 — PSF-2.0; транзитивная зависимость python-docx, включена в runtime lock.

В runtime не добавлены Office, LibreOffice или облачные конвертеры. Проверка DOCX выполняется локально через ZIP, lxml и python-docx.

## Runtime

| Компонент | Проверенная версия | Лицензия / источник |
|---|---|---|
| Argos Translate | 1.11.0 | MIT, LICENSE официального wheel; [upstream](https://github.com/argosopentech/argos-translate) |
| CTranslate2 | 4.8.2 | MIT, [LICENSE v4.8.2](https://github.com/OpenNMT/CTranslate2/blob/v4.8.2/LICENSE) |
| SentencePiece | 0.2.2 | Apache-2.0, [LICENSE v0.2.2](https://github.com/google/sentencepiece/blob/v0.2.2/LICENSE) |
| Sacremoses | 0.1.1 | MIT, LICENSE официального wheel |
| langid.py | 1.1.6 | BSD-3-Clause, [upstream LICENSE](https://github.com/saffsd/langid.py/blob/master/LICENSE); локальная модель определения языка входит в пакет |
| pyspellchecker | 0.9.0 | MIT, [upstream](https://github.com/barrust/pyspellchecker); LICENSE официального wheel сохранена. Частотные словари поставляются в wheel, без загрузки runtime. |
| NumPy | 2.5.3 | BSD-3-Clause и bundled notices; полная коллекция лицензий сохранена |
| Packaging | 26.2 | Apache-2.0 OR BSD-2-Clause |
| PyYAML | 6.0.3 | MIT |
| Click | 8.5.0 | BSD-3-Clause |
| Joblib | 1.6.0 | BSD-3-Clause |
| Cloudpickle | 3.1.2 | BSD-3-Clause |
| Regex | 2026.9.10 | Apache-2.0 AND CNRI-Python |
| tqdm | 4.70.1 | MPL-2.0 AND MIT |
| NVIDIA cuBLAS CUDA 12, optional GPU | 12.9.2.10 | NVIDIA proprietary terms, LICENSE из официального wheel |
| NVIDIA NVRTC CUDA 12, dependency of cuBLAS wheel | 12.9.86 | NVIDIA proprietary terms, LICENSE из официального wheel |

PySide6 / Shiboken 6.11.1 уже использовались в AW 0.3; применяются условия Qt for Python (LGPLv3/GPLv3/commercial в зависимости от использования). Лицензия приложения в этой работе не менялась.

Фактические notices и inventory: [vendor/licenses](vendor/licenses). Названия лицензий библиотек не переносятся автоматически на модельные веса. Для installer потребуется включить применимые notices всех поставляемых нативных библиотек и выполнить отдельную проверку условий распространения NVIDIA/Qt.

## Почему официальный Argos установлен с `--no-deps`

Опубликованный wheel 1.11.0 безусловно импортирует Stanza из `argostranslate.sbd`; стандартный путь SBD допускает загрузку MiniSBD или Stanza ресурсов. Это проверено на самом wheel. Полная установка зависимостей тянет неиспользуемый PyTorch в runtime.

TreeTranslate использует официальный `argostranslate.package.get_installed_packages` и официальные SentencePiece/BPE tokenizers. Небольшой собственный адаптер выполняет CT2 batch inference, ограничивает абзацы по токенам и управляет переводчиками. `argostranslate.translate`, Stanza, SpaCy и MiniSBD не импортируются. Upstream package не модифицируется и не форкается. Это осознанное отклонение от предпочтительного high-level пути Argos, требующее проверки совместимости при обновлении библиотеки.

## Локальный словарь и учебные примеры

- FreeDict / WikDict EN→RU и RU→EN, версия 2025.11.23. Maintainer/publisher: Karl Bartel. Исходные данные Wiktionary через DBnary. Лицензия, указанная непосредственно в TEI header: **CC BY-SA 3.0 Unported**. Attribution headers сохранены в `vendor/lexicon/*-attribution.xml`; официальный текст лицензии — `vendor/licenses/freedict/CC-BY-SA-3.0.txt`.
- Источники: [EN→RU](https://download.freedict.org/dictionaries/eng-rus/2025.11.23/), [RU→EN](https://download.freedict.org/dictionaries/rus-eng/2025.11.23/). Версии, URL, официальные SHA512 архивов, SHA256 и размер полученной базы записаны в `vendor/lexicon/manifest.json`.
- Изменения TreeTranslate: TEI преобразован в отдельную SQLite-базу; добавлены регистронезависимые ключи без знака ударения. Текст определений и переводов сохранён. Эта производная база распространяется на условиях CC BY-SA 3.0; её лицензия не подменяется лицензией программного кода.
- `assets/language/usage.json`: оригинальные учебные примеры и пояснения TreeTranslate, созданные в этой разработке; CC0-1.0. Это отдельный набор, не выдержки из Yandex/FreeDict и не дообученная модель. Имена и ситуации иллюстративные.
- Подсказки не записывают пользовательский ввод в обучающие корпуса. У pyspellchecker частотная модель корректирует отдельные слова, без грамматического анализа предложений.

Стандартный `pip check` ожидаемо сообщает отсутствующие `stanza`, `spacy`, `minisbd`: метаданные upstream пакета описывают также неиспользуемый high-level API. Совместимость используемого подмножества подтверждена тестами реального перевода в окружении без PyTorch/Transformers.

## Веса моделей

| Артефакт | Источник | Установленные сведения о лицензии |
|---|---|---|
| M2M100 418M | [официальная карточка Meta](https://huggingface.co/facebook/m2m100_418M/tree/55c2e61bbf05dfb8d7abccdc3fae6fc8512fd636) | MIT указана в model card. Сохранена карточка и upstream fairseq MIT LICENSE. CT2 INT8 — локальная конвертация этих весов. |
| Argos EN→RU 1.9 | официальный argospm index → argos-net.com | **Не определена однозначно.** README содержит авторство Aleksey Kutashov и условия исходных корпусов, но не однозначную лицензию итоговых весов. |
| Argos RU→EN 1.9 | официальный argospm index → argos-net.com | **Не определена однозначно.** Условия наборов данных в README не заменяют лицензию модели. |
| Argos ZH→EN 1.9 | официальный argospm index → argos-net.com | README указывает CC-BY 4.0 для исходной OPUS модели; отдельные package-wide условия не сформулированы. |
| Argos EN→ZH 1.9 | официальный argospm index → argos-net.com | CC-BY 4.0 для исходной OPUS модели, согласно README. |

Карточки и metadata packages сохранены в [vendor/model-metadata](vendor/model-metadata). SHA256 всех поставляемых файлов — в [manifest](vendor/models/models_manifest.json). [Открытый upstream issue о лицензиях Argos](https://github.com/argosopentech/argos-translate/issues/507) согласуется с обнаруженной неопределённостью; перед распространением EN↔RU её нужно разрешить. Development integration и benchmark выполнены, installer в этой фазе не создаётся.

## Build / development only

- Transformers 4.57.6 — Apache-2.0; официальный M2M100Tokenizer и конвертер CTranslate2. Runtime tokenizer реализует локальный формат SentencePiece; parity проверяется против Transformers.
- PyTorch 2.10.0 — BSD-style и bundled notices; только загрузка исходных весов/конвертация в `.venv-build`.
- Hugging Face Hub, tokenizers, safetensors и прочие зависимости Transformers — только build environment; это окружение не включается в runtime.
- pytest 9.1.1 — MIT; psutil 7.2.2 — BSD-3-Clause; только проверки и developer benchmark.

PyTorch и Transformers отсутствуют в проверенном runtime-окружении `.venv`.

## PDF runtime (AW 0.6)

- pypdfium2 **5.13.0**: wrapper Apache-2.0 OR BSD-3-Clause; документация/примеры CC-BY-4.0. Используется официальный Windows x64 wheel с PDFium **153.0.7999.0**. [Upstream](https://github.com/pypdfium2-team/pypdfium2).
- PDFium: BSD-style и уведомления сторонних компонентов фактического binary build. Полный комплект из установленного wheel сохранён в `vendor/licenses/pypdfium2`, включая `data/windows_x64/BUILD_LICENSES`. Набор включает FreeType, ICU, libjpeg-turbo/IJG, libpng, libtiff, OpenJPEG, zlib, lcms, agg, Abseil, LLVM, fast_float и simdutf. Новые GPL/AGPL или коммерческие PDF-зависимости не добавлены. [PDFium LICENSE](https://raw.githubusercontent.com/chromium/pdfium/main/LICENSE).
- fontTools **4.65.0**, MIT: чтение cmap/метрик и создание подмножеств шрифтов. Лицензии wheel в `vendor/licenses/fonttools`. [LICENSE](https://github.com/fonttools/fonttools/blob/main/LICENSE).
- **TreeTranslate Sans Regular** — модифицированный статический экземпляр Noto Sans SC, SIL OFL-1.1. Исходный commit, URL и SHA256 записаны в `assets/fonts/manifest.json`; полный OFL и copyright — `assets/fonts/OFL-NotoSansSC.txt`. Шрифт переименован, исходное зарезервированное имя не используется как имя производного шрифта. Лицензия разрешает embedding/subsetting; шрифт не продаётся отдельно. [Noto CJK](https://github.com/notofonts/noto-cjk).
- PDF subsets получают уникальные PostScript names, исключающие коллизии Unicode mapping между блоками.

Для тестов только: pypdf **6.19.0** (BSD-3-Clause), Pillow **12.3.0** (MIT-CMU); лицензии wheel в `vendor/licenses/pypdf` и `vendor/licenses/Pillow`. Эти библиотеки не импортируются PDF runtime.
