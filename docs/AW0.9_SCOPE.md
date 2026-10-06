# AW0.9 — preliminary scope

Этот документ открывает следующий цикл и не утверждает roadmap. Выполнение задач начнётся только после отдельного согласования пользователя. Production reference — tag `AW0.86`; новая ветка следует существующей convention `codex/aw0.9`, current development marker `AW0.9-dev`.

## MUST

Release-readiness audit; Windows packaging strategy; clean-machine launch; dependencies/models packaging; offline verification; paths/temp cleanup; user-facing errors; diagnostics; progress/pause/cancel UX; system requirements; licensing; triage известных 24 failure cases. Оценить причины и приоритеты до обещания исправлений.

## SHOULD

Quality и language support audit; системные document failures; installer/portable decisions; небольшой UX polish; согласованный release corpus и критерии приёмки.

## MAY

Доказанные quality/performance patches и дополнительные безопасные format fixes с соответствующими equivalence gates.

## NOT NOW

Speculative architecture; rejected NMT batching в нынешнем виде; multi-GPU; cloud; accounts; telemetry; несвязанные refactors. Не возобновлять эксперименты без нового задания.

## Version philosophy

AW0.86 закрывает engineering cycle 0.8. AW0.9 — stabilization / release preparation. 1.0 — первая полноценная публичная Windows version, а не обещание идеальности или прекращения изменений. После 1.0 версии 1.1+ могут исправлять known issues, quality, compatibility, performance, document edge cases и UX. Не требуется закрывать все возможные проблемы до 1.0.
