from app.documents.pdf_layout import group_spans
from app.documents.pdf_types import PdfSegment


def span(text, x, y, index, *, cell=None):
    s = PdfSegment(0, str(index), text, (x, y, x+40, y+9), index, ('fixture',), 10,
                   baseline=y, object_indices=(index,))
    if cell:
        s.region_kind, s.region_key = 'table_cell', cell
    return s


def test_separate_table_rows_keep_individual_object_identity():
    spans = [span('上限位置', 20, 100, 0, cell=(0,)),
             span('下限位置', 20, 86, 1, cell=(1,))]
    grouped = group_spans(0, spans, 2000)
    assert [s.text for s in grouped] == ['上限位置', '下限位置']
    assert [s.object_indices for s in grouped] == [(0,), (1,)]


def test_separate_diagram_identifiers_do_not_become_a_word():
    grouped = group_spans(0, [span('K', 20, 100, 0), span('L', 20, 86, 1)], 2000)
    assert [s.text for s in grouped] == ['K', 'L']


def test_wrapped_prose_still_forms_a_single_block():
    grouped = group_spans(0, [span('检查连接器是否', 20, 100, 0), span('存在损坏。', 20, 86, 1)], 2000)
    assert len(grouped) == 1
    assert grouped[0].object_indices == (0, 1)


def test_horizontally_adjacent_distinct_cells_are_not_merged():
    grouped = group_spans(0, [span('参数', 20, 100, 0, cell=(0,)),
                            span('数值', 62, 100, 1, cell=(1,))], 2000)
    assert len(grouped) == 2


def test_native_quality_ignores_navigation_and_preserved_markers():
    from app.ocr.pdf_extractor import usable_native_chars
    labels = [span('A', 20, 100, 0), span('12.5 mm',20,86,1),
              span('2024 > Manual > 图纸',20,72,2)]
    assert usable_native_chars(labels) == 0
    assert usable_native_chars([span('冷却液',20,100,0)]) == 3
    assert usable_native_chars([span('Inspect the connector.',20,100,0)]) > 0
def test_parenthesized_point_codes_are_protected_without_accepting_labels():
    from app.documents.pdf_ocr_policy import protected_kind
    for code in ['(Q)', '（Z）', '（ Q12 ）', '(BC-XY)', '(R′)', '[PQ]', '［ T24 ］', '[AB-CD]']:
        assert protected_kind(code)=='identifier'
    for label in ['(Снятие)', '（位置）', '(Q位置)', '(Q）', '(温度 25 °C)', '[位置]', '[AB位置]', '[AB］', '［AB]', '[AB][CD]']:
        assert protected_kind(label) is None

def test_retained_source_block_splits_flow_without_moving_its_neighbors_over_it():
    from app.documents.pdf_regions import flow_boxes
    class Face:
        def width(self,text,size):
            return len(text)*size*.5
        def vertical(self,text):
            return .8,-.2
    class Fonts:
        def resolve(self,text):
            return Face()
    above, anchor, below = [span(text,20,y,i) for i,(text,y) in enumerate(
        [('检查。',100),('原始标题',86),('拆下。',72)])]
    for s in [above,anchor,below]:
        s.available_bbox=(20,0,300,120)
        s.region_key=('column',)
    above.translated='Проверьте.'
    anchor.translated=anchor.text
    below.translated='Снимите.'
    flow_boxes([above,anchor,below],Fonts())
    assert above.rendered_bbox[1]>=anchor.bbox[3]+1.5
    assert below.rendered_bbox[3]<=anchor.bbox[1]-1.5
    assert anchor.rendered_bbox is None
