"""Readable source-based reference translations, separate from model outputs."""
from pathlib import Path
import sys,json
from html import escape
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
ROOT=Path(__file__).resolve().parents[1];QA=ROOT/'qa/aw088'
def save(name,value):(QA/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n','utf8')
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,PageBreak
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.pagesizes import A4
from hashlib import sha256

font='TreeTranslateReference';pdfmetrics.registerFont(TTFont(font,str(ROOT/'assets/fonts/TreeTranslateSans-Regular.ttf')))
text=ParagraphStyle('text',fontName=font,fontSize=10,leading=15,spaceAfter=7)
heading=ParagraphStyle('heading',parent=text,fontSize=16,leading=22,spaceAfter=15)
small=ParagraphStyle('small',parent=text,fontSize=8,leading=12,textColor='#555555')
rows=json.loads((QA/'holdout_semantic_review.json').read_text('utf8'))['rows'];story=[]
for doc in range(18):
    selected=[r for r in rows if int(r['id'].split(':')[0])==doc]
    if doc:story.append(PageBreak())
    story.append(Paragraph(f'CN7C — эталон {doc+1:02}',heading))
    story.append(Paragraph(escape(selected[0]['member']),small));story.append(Spacer(1,10))
    if doc==0:
        story.append(Paragraph('Авторские переводы для сравнения: Codex, AW0.8.8. Это контрольный набор из 18 документов, а не перевод всего корпуса. Неоднозначные подписи отмечены явно. Соседние фрагменты одного абзаца следует читать вместе. Переводы программы находятся в отдельном архиве и могут отличаться от эталона.',small))
    for r in selected:
        story.append(Paragraph(escape(r['id'])+' — '+escape(r['reference']),text))
path=ROOT/'output/aw088/comparison/Эталон_CN7C.pdf'
def footer(canvas,document):
    canvas.setFont(font,8);canvas.drawString(42,24,'TreeTranslate · контрольный эталон · только для сравнения');canvas.drawRightString(A4[0]-42,24,str(document.page))
SimpleDocTemplate(str(path),pagesize=A4,rightMargin=42,leftMargin=42,topMargin=40,bottomMargin=42).build(story,onFirstPage=footer,onLaterPages=footer)
save('reference_pdf.json',dict(path=str(path),sha256=sha256(path.read_bytes()).hexdigest(),knowledge_import_forbidden=True,author='Codex, independently authored source-based comparison; not OEM-certified'))
print(path)
