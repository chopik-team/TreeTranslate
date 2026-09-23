"""Developer diagnostic, using the same explicit local models and offline guard."""
import os
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ['PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK']='True'
from app.ocr.runtime.worker import deny_network
sys.addaudithook(deny_network)
from paddleocr import PPStructureV3
from paddlex.inference import load_pipeline_config
from app.ocr.runtime.ocr_model_manager import OcrModelManager
m=OcrModelManager()
table={'table_classification':'PP-LCNet_x1_0_table_cls','wired_table_structure_recognition':'SLANeXt_wired',
       'wireless_table_structure_recognition':'SLANet_plus','wired_table_cells_detection':'RT-DETR-L_wired_table_cell_det',
       'wireless_table_cells_detection':'RT-DETR-L_wireless_table_cell_det','table_orientation_classify':'PP-LCNet_x1_0_doc_ori',
       'layout_detection':'PP-DocLayout_plus-L','text_detection':'PP-OCRv6_small_det',
       'text_recognition':'cyrillic_PP-OCRv5_mobile_rec','doc_orientation_classify':'PP-LCNet_x1_0_doc_ori'}
args={}
for k,v in table.items():args.update({k+'_model_name':v,k+'_model_dir':m.require(v)})
config=load_pipeline_config('PP-StructureV3')
config['SubPipelines']['TableRecognition']['SubPipelines']['GeneralOCR']['use_textline_orientation']=False
s=PPStructureV3(**args,paddlex_config=config,device='gpu:0',enable_mkldnn=False,use_doc_orientation_classify=True,
    use_doc_unwarping=False,use_textline_orientation=False,use_formula_recognition=False,use_chart_recognition=False,
    use_region_detection=False,use_seal_recognition=False,use_table_recognition=True)
result=s.predict(sys.argv[1])[0]
print('RESULT KEYS',list(result.keys()))
print('OCR ROWS',len(result['overall_ocr_res']['rec_texts']))
