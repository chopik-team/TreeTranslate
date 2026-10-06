"""Explicit local TM administration; normal translation never invokes imports/exports."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.translation_memory.engine import TranslationMemoryEngine
from app.translation_memory.exporter import export_memory, export_tmx, export_dataset
from app.translation_memory.importer import import_memory, import_tmx
from app.translation_memory.maintenance import integrity, duplicates, optimize, backup, restore
from app.translation_memory.errors import MemoryError


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', type=Path, help='Default: TreeTranslate AppData, or TREETRANSLATE_TM_PATH')
    parser.add_argument('action', choices=['stats','integrity','duplicates','optimize','vacuum','backup','restore',
                                           'import','export','import-tmx','export-tmx','dataset'])
    parser.add_argument('file', nargs='?', type=Path)
    parser.add_argument('--trusted', action='store_true', help='Explicitly trust imported units (IMPORTED, never CONFIRMED)')
    parser.add_argument('--source-language')
    parser.add_argument('--target-language')
    args = parser.parse_args()
    memory = TranslationMemoryEngine(args.db)
    if args.action not in {'stats','integrity','duplicates','optimize','vacuum'} and args.file is None:
        parser.error('Для этой операции требуется файл.')
    if args.file and args.file.resolve() == memory.db.path.resolve():
        parser.error('Файл обмена должен отличаться от рабочей базы.')
    operations = {
        'stats': memory.stats,
        'integrity': lambda: integrity(memory.db),
        'duplicates': lambda: duplicates(memory.db),
        'optimize': lambda: optimize(memory.db),
        'vacuum': lambda: optimize(memory.db, vacuum=True),
        'backup': lambda: backup(memory.db, args.file),
        'restore': lambda: str(restore(memory.db, args.file)),
        'import': lambda: import_memory(memory.repository, args.file, trusted=args.trusted),
        'export': lambda: export_memory(memory.repository, args.file),
        'import-tmx': lambda: import_tmx(memory.repository, args.file, trusted=args.trusted,
                                        source_language=args.source_language,target_language=args.target_language),
        'export-tmx': lambda: export_tmx(memory.repository, args.file),
        'dataset': lambda: export_dataset(memory.repository, args.file),
    }
    try:
        result = operations[args.action]()
    except (MemoryError, OSError, ValueError):
        parser.exit(1, 'Операция памяти не выполнена. Исходная база не удаляется автоматически.\n')
    print(json.dumps({'action': args.action, 'result': result}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
