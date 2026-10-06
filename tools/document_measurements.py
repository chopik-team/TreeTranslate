"""Export the durable local timing journal; does not run translation or models."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.documents.measurements import collect, MEASUREMENTS_DIR


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=Path('docs/qa/DOCUMENT_TIMINGS.md'))
    args = parser.parse_args()
    collect()
    runs = sorted((json.loads(p.read_text('utf-8')) for p in MEASUREMENTS_DIR.glob('*.json')),
                  key=lambda r: r.get('date', ''))
    runs = [r for r in runs if r.get('operation') == 'translate']
    lines = ['# Журнал замеров TreeTranslate', '',
             'Данные из локальных логов. Время процессов включительное: вложенные процессы нельзя складывать с родительскими.', '',
             'Неуспешные прогоны сохраняются для диагностики, но не участвуют в расчёте ETA. Содержимое документов не записывается.', '',
             '| Дата / run | Результат | Страницы / сегменты | OCR-области | Всего, с | Извлечение, с | Перевод, с | Запись, с | Прогноз, с |',
             '|---|---|---:|---:|---:|---:|---:|---:|---:|']
    for run in runs:
        sources = run['sources']
        processes = run['processes']
        sums = [sum(processes.get(p, [])) for p in ('preflight_open_extract', 'engine_translation', 'document_write')]
        prediction = f"{run['predicted_seconds']:.2f}" if 'predicted_seconds' in run else '—'
        lines.append(f"| {run.get('date', '')} / `{run['run']}` | {run['state']} | {sum(s['pages'] for s in sources)} / {sum(s['segments'] for s in sources)} | {len(run['ocr'])} | {run['elapsed']:.2f} | " + ' | '.join(f'{v:.2f}' for v in sums) + f' | {prediction} |')
    lines.extend(['', '## Формат и способ загрузки документов', '',
                  'Папка не означает ZIP: происхождение из ранее распакованного архива нельзя определить по пути. '
                  'В старых логах отсутствующие признаки обозначены как неизвестные.', '',
                  '| Run | Документ | Формат / тип | Вход | Контейнер / относительный путь | Байты / символы |',
                  '|---|---|---|---|---|---:|'])
    labels = {'docx': 'DOCX', 'pdf_native': 'PDF с текстом', 'pdf_ocr': 'PDF с OCR', 'pdf_mixed': 'PDF смешанный: текст + OCR', 'pdf_no_text': 'PDF без извлечённого текста'}
    def cell(value):
        return str(value or '—').replace('|', '\\|').replace('\n', ' ')
    for run in runs:
        documents = run.get('documents', [])
        if not documents:
            documents = [dict(s, format=Path(s['path']).suffix.lower().lstrip('.'), kind='неизвестен', input_kind='неизвестен') for s in run['sources']]
        for doc in documents:
            kind = labels.get(doc.get('kind'), doc.get('kind', 'неизвестен'))
            container = f"{doc.get('container') or '—'} / {doc.get('relative_path') or '—'}"
            values = (run['run'], doc['path'], f"{doc.get('format', '—')} / {kind}", doc.get('input_kind', 'неизвестен'), container,
                      f"{doc.get('bytes', '—')} / {doc.get('chars', '—')}")
            lines.append('| ' + ' | '.join(cell(v) for v in values) + ' |')
    lines.extend(['', '## Следующие ручные прогоны', '',
                  '1. Обычный PDF с текстовым слоем: 1, 5 и 10 страниц, по возможности с сопоставимым количеством текста на странице.',
                  '2. PDF со сканами: 1 и 5 страниц, с одинаковым разрешением и похожей плотностью текста.',
                  '3. Пакет из нескольких PDF для проверки общей ETA и последовательного заполнения строк.', '',
                  'Держать одинаковые язык, устройство и профиль OCR. Первый холодный запуск и повторный тёплый запуск записывать отдельно. '
                  'Количество страниц само по себе недостаточно: учитываются сегменты, символы и OCR-области. '
                  'Точность начальной оценки проверять по отношению фактического времени к прогнозу `eta calibration_runs=… estimated_seconds=…`.', '',
                  f'Подробные записи по run: `{MEASUREMENTS_DIR}`. '
                  'После прогона запустить `python tools/document_measurements.py`, чтобы обновить этот отчёт.'])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text('\n'.join(lines) + '\n', 'utf-8')
    print(f'{len(runs)} runs; {args.output.resolve()}')


if __name__ == '__main__':
    main()
