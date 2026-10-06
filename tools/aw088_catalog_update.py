"""Reviewed translations of two existing archive status messages."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
KEYS=['Проверка файлов архива…','Недостаточно свободного места для результата архива и временной обработки документа.']
VALUES={
 'en':['Checking archive files…','Not enough free space for the output archive and temporary document processing.'],
 'de':['Archivdateien werden geprüft…','Nicht genügend freier Speicherplatz für das Ausgabearchiv und die temporäre Dokumentverarbeitung.'],
 'es':['Comprobando los archivos del archivo comprimido…','No hay suficiente espacio libre para el archivo de salida y el procesamiento temporal del documento.'],
 'fr':['Vérification des fichiers de l’archive…','Espace libre insuffisant pour l’archive de sortie et le traitement temporaire du document.'],
 'ja':['アーカイブ内のファイルを確認中…','出力アーカイブと文書の一時処理に必要な空き容量が不足しています。'],
 'zh':['正在检查压缩包中的文件…','没有足够的可用空间来保存输出压缩包和临时处理文档。'],
 'ru':KEYS}
for path in (ROOT/'assets/locales').glob('*.json'):
    code=path.stem.split('-')[0]
    if code not in VALUES:continue
    data=json.loads(path.read_text('utf8'));data.update(zip(KEYS,VALUES[code]))
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n','utf8')
