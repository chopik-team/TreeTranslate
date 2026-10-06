"""Authored translations for the existing progress panel and failure warnings."""
import json
from pathlib import Path
import shutil
ROOT=Path(__file__).resolve().parents[1]
keys=[': ошибка ','; оригинал сохранён в архиве без перевода.','Документ ',
      'Документ {0}: ошибка {1}; оригинал сохранён в архиве без перевода.',
      'Завершено с ошибками; оригиналы сохранены',
      'Известное наложение текста в таблице PDF: результат требует визуальной проверки.',
      'Проверка ZIP не пройдена: не все документы обработаны.']
values={
'en-US':[': error ','; original preserved in the archive without translation.','Document ',
 'Document {0}: error {1}; original preserved in the archive without translation.',
 'Completed with errors; originals preserved','Known overlapping text in a PDF table: visual review is required.',
 'ZIP validation failed: not all documents were processed.'],
'de-DE':[': Fehler ','; Original ohne Übersetzung im Archiv erhalten.','Dokument ',
 'Dokument {0}: Fehler {1}; Original ohne Übersetzung im Archiv erhalten.',
 'Mit Fehlern abgeschlossen; Originale erhalten','Bekannte Textüberlagerung in einer PDF-Tabelle: Sichtprüfung erforderlich.',
 'ZIP-Prüfung fehlgeschlagen: nicht alle Dokumente wurden verarbeitet.'],
'es-ES':[': error ','; original conservado en el archivo sin traducir.','Documento ',
 'Documento {0}: error {1}; original conservado en el archivo sin traducir.',
 'Finalizado con errores; originales conservados','Superposición de texto conocida en una tabla PDF: requiere revisión visual.',
 'Falló la validación del ZIP: no se procesaron todos los documentos.'],
'fr-FR':[' : erreur ',' ; original conservé dans l’archive sans traduction.','Document ',
 'Document {0} : erreur {1} ; original conservé dans l’archive sans traduction.',
 'Terminé avec des erreurs ; originaux conservés','Chevauchement de texte connu dans un tableau PDF : vérification visuelle requise.',
 'Échec de la validation ZIP : tous les documents n’ont pas été traités.'],
'zh-CN':['：错误 ','；原始文件已保留在压缩包中，未翻译。','文档 ',
 '文档 {0}：错误 {1}；原始文件已保留在压缩包中，未翻译。',
 '已完成，但有错误；原始文件已保留','PDF 表格中存在已知文字重叠：结果需要目视检查。',
 'ZIP 验证失败：并非所有文档均已处理。'],
'ja-JP':['：エラー ','。原本は翻訳せずにアーカイブ内に保存しました。','文書 ',
 '文書 {0}：エラー {1}。原本は翻訳せずにアーカイブ内に保存しました。',
 'エラーありで完了、原本を保存済み','PDF 表に既知の文字の重なりがあります。目視確認が必要です。',
 'ZIP 検証に失敗：すべての文書は処理されていません。']}
values['en-GB']=values['en-US'];values['ru-RU']=keys
for locale,translations in values.items():
    path=ROOT/'assets/locales'/f'{locale}.json'
    backup=ROOT/'qa/aw081/iterations/15_diagnostic_live_readiness/before/assets/locales'/path.name
    backup.parent.mkdir(parents=True,exist_ok=True)
    if not backup.exists():shutil.copy2(path,backup)
    data=json.loads(path.read_text('utf8'));data.update(zip(keys,translations))
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n','utf8')
