"""Shared retrieval strategy types; PDF placement never decides Knowledge policy."""
from enum import StrEnum
from functools import lru_cache
import re
from app.documents.pdf_ocr_policy import protected_kind

class SegmentType(StrEnum):
    TITLE='TITLE';HEADING='HEADING';FILENAME='FILENAME';FOLDER_NAME='FOLDER_NAME'
    PROSE='PROSE';DEFINITION='DEFINITION';PROCEDURE_STEP='PROCEDURE_STEP';WARNING='WARNING';CONDITION='CONDITION'
    TABLE_HEADER='TABLE_HEADER';TABLE_CELL='TABLE_CELL';DIAGRAM_LABEL='DIAGRAM_LABEL';COMPONENT_LABEL='COMPONENT_LABEL'
    CROSS_REFERENCE='CROSS_REFERENCE';DIAGNOSTIC_LABEL='DIAGNOSTIC_LABEL'
    MEASUREMENT='MEASUREMENT';DIMENSION='DIMENSION';UI_LABEL='UI_LABEL';ABBREVIATION='ABBREVIATION';IDENTIFIER='IDENTIFIER';UNKNOWN='UNKNOWN'

class SegmentClassifier:
    @staticmethod
    def classify(text,*,hint='',segment=None):
        return SegmentClassifier._classify(text,hint,getattr(segment,'region_kind',''))

    @staticmethod
    @lru_cache(maxsize=4096)
    def _classify(text,hint,region):
        if hint in SegmentType.__members__:return SegmentType[hint]
        if region in ('title','heading','table_header','ui_label'):
            return SegmentType[region.upper()]
        if region in ('numbered_step','warning'):
            return SegmentType.PROCEDURE_STEP if region=='numbered_step' else SegmentType.WARNING
        protected=protected_kind(text)
        if protected=='measurement':return SegmentType.MEASUREMENT
        if protected=='identifier':return SegmentType.IDENTIFIER
        if re.match(r'^\s*[（(]?\s*(?:请)?(?:参考|参阅|参见)',text):return SegmentType.CROSS_REFERENCE
        if re.search(r'绝不|禁止|不得|不要|warning|do not',text,re.I):return SegmentType.WARNING
        if re.search(r'如果|若|if\b',text,re.I):return SegmentType.CONDITION
        if re.match(r'\s*(?:\d+[.)、]|[•●▪])',text) or re.match(r'(?:请)?检查|确保|先|更换',text):return SegmentType.PROCEDURE_STEP
        if re.match(r'(?:拆下|拆卸|拆除|安装|断开|连接|分离|加注|补充|排出|排放|清洁|拧紧|拧下|启动|起动|关闭|等待|测量|调整|对齐|保持)',text):return SegmentType.PROCEDURE_STEP
        if region=='table_cell':return SegmentType.TABLE_CELL
        if len(text)<35 and not re.search(r'[。.!?]',text):
            if re.search(r'概述|方法|尺寸|注意事项|overview',text,re.I):return SegmentType.HEADING
            if re.search(r'孔|支架|车门|铰链|面板|散热器|冷却液|螺栓',text):return SegmentType.COMPONENT_LABEL
            return SegmentType.DIAGRAM_LABEL
        if re.search(r'是.*(?:尺寸|距离|指)|定义|defined as',text,re.I):return SegmentType.DEFINITION
        return SegmentType.PROSE if text.strip() else SegmentType.UNKNOWN

    @staticmethod
    def clear():SegmentClassifier._classify.cache_clear()
