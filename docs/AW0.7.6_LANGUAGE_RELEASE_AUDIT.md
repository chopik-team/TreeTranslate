# TreeTranslate AW 0.7.6 — Language Support Audit & Release Blockers

Дата: 27 сентября 2026. Этап является аудитом и устранением release blockers; новые модели, словари, корпуса и glossary не добавлялись.

## Итог release gate

**Да: текущую языковую систему можно безопасно включить в будущий W 1.0 для семи уникальных кодов `ru`, `en`, `zh`, `de`, `es`, `fr`, `ja`.** Все 42 направления имеют локальный route и прошли реальный inference. Оставшихся blockers в release-facing scope нет.

| Статус всех 100 кодов M2M100 | Количество |
|---|---:|
| RELEASE_READY | 7 |
| EXPERIMENTAL | 83 |
| BROKEN | 10 |
| UNSUPPORTED | 0 |

| Статус 42 release-facing направлений | Количество |
|---|---:|
| RELEASE_READY | 42 |
| EXPERIMENTAL | 0 |
| BROKEN | 0 |
| UNSUPPORTED | 0 |

## Реальные ресурсы и маршруты

`tools/verify_models.py` полностью проверил SHA256 и размеры пяти translation models и десяти OCR models. Установлены Argos EN→RU, RU→EN, ZH→EN, EN→ZH и M2M100 418M INT8 со 100 кодами. Router использует direct M2M100 для любой пары кодов manifest; Argos предоставляет четыре direct и ZH↔RU pivot через EN.

Все семь release-кодов прошли Auto Detect. UI содержит восемь подписей, потому что «Английский» и «Английский (США)» визуально различаются, но обе соответствуют коду `en`.

Машинная матрица содержит backend, direct/pivot route, фактическое устройство, latency, fallback, UI/Auto Detect/document/glossary/dictionary/usage status: `docs/qa/aw076/language-matrix.json`. Пользовательское описание: `docs/LANGUAGE_SUPPORT.md`.

Фактический полный matrix run использовал профиль Fast: 4 direct направления выбрали Argos, 38 — M2M100; fallback не потребовался. Unit gate отдельно подтвердил наличие маршрута для каждой из 42 пар во всех шести performance profiles.

## Найденные и исправленные blockers

1. Target selector предлагал «Определить автоматически», хотя `LanguageResolver` всегда отклоняет target=`auto`. Swap мог сохранить эту нерабочую пару. Auto удалён из target; swap с автоматическим source безопасно не создаёт target Auto; старое сохранённое значение мигрирует на рабочий target.
2. Economy устанавливал `allow_quality=false` и безусловно исключал M2M100. Поэтому DE/ES/FR/JA и любые пары без Argos падали как unsupported. Теперь Economy исключает M2M100 только когда существует рабочий Argos direct/pivot route; иначе M2M100 остаётся локальным fallback/единственным route.

Оставшиеся release blockers: **нет**.

## Полный model-language smoke

Для каждого из 100 кодов выполнен реальный EN→language→EN smoke на RTX 3080. Проверялись завершение inference, непустой Unicode, отсутствие `<unk>`, language/control tokens, исключений и runtime network. Семь release-кодов готовы. 83 скрытых кода получили EXPERIMENTAL. Десять скрытых кодов (`ff`, `jv`, `km`, `lg`, `ln`, `lo`, `ns`, `tn`, `wo`, `yo`) получили BROKEN из-за патологической генерации или TranslationError. Они никогда не были доступны в UI и W 1.0 не блокируют.

CPU и Auto отдельно проверены для всех семи release-кодов. Economy real inference проверен для DE/ES/FR/JA. RU/EN/ZH дополнительно покрыты существующими Argos/M2M100 CPU/GPU/Auto tests.

## Document QA

- DOCX: реальные EN и ZH документы → RU на CPU/GPU/Auto, включая параграфы, таблицы, header/footer и filename translation.
- Native PDF: реальные EN и ZH документы → RU на CPU/GPU/Auto, исходные SHA256 неизменны.
- OCR PDF: реальный локальный Paddle OCR + Translation Router + glossary pipeline прошёл для EN→RU.
- Общая архитектура DOCX/native PDF не содержит per-language backend logic и использует тот же Router; DE/ES/FR/JA подтверждены text inference и считаются document-ready для текстовых документов.
- OCR capabilities заявлены только для EN/RU/ZH. Остальные OCR scripts остаются post-W1.0 quality work и не заявляются готовыми.

Representative document regression: **15 passed**.

## Offline QA

Runtime остаётся fail-closed: `offline_scope` блокирует socket/urllib, Argos изолирован от пользовательских package indexes, M2M100 использует локальный tokenizer/model. CPU/Auto release smoke выполнялся с заблокированными `socket.getaddrinfo` и `socket.create_connection`; network attempts = 0. Model acquisition/download не выполнялись.

## Glossary, dictionary и examples

- RU↔ZH: сильная bundled technical knowledge base.
- EN/RU: Dictionary и Usage Examples.
- DE/ES/FR/JA: базовый model translation работает; bundled technical glossary, Dictionary и Usage Examples отсутствуют.

Это различие качества раскрыто пользователю и не является release blocker.

## Размер

| Runtime data | До | После |
|---|---:|---:|
| Translation models + lexicon + knowledge + usage | 1 386 564 347 B | 1 386 564 347 B |
| С OCR models | 2 204 045 208 B | 2 204 045 208 B |

Увеличение runtime data: **0 B**. AW0.7.6 добавляет только код, tests и документацию.

## Tests и release consistency

- Полный regression: **526 passed** за 168,27 s.
- Targeted language/UI/Router/settings gate: **74 passed**.
- Representative real DOCX/native PDF/OCR gate: **15 passed**.
- Language matrix tests проверяют совпадение model manifest, UI и release codes; 42/42 направления; Auto Detect; disclosures; статусы; size; запрет Auto target.
- Router unit test проверяет каждый из 42 release routes во всех шести performance profiles.
- Model manifest verification: 5 translation + 10 OCR models passed full size/SHA256 validation.
- `python -m compileall -q app tools`: passed.
- `git diff --check`: passed.

## Post-W1.0 quality improvements

- DE/ES/FR: technical terminology, dictionary/examples, domain QA.
- JA: lexical assistance и отдельный script/document/OCR QA.
- ZH: automotive/metallurgy expansion.
- Ten hidden BROKEN M2M100 codes: decoding/quality analysis до любого появления в UI.
- OCR coverage beyond EN/RU/ZH.

Ни одна из этих задач не выполнялась в AW0.7.6.

## Git status

Этап выполнен поверх существующего незакоммиченного `codex/next-cycle`. Предыдущие изменения сохранены; reset/revert/delete не применялись. Коммит и push не выполнялись.
