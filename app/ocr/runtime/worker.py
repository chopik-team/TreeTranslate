"""Private offline Paddle process. stdout is exclusively the bounded JSON protocol."""
import json
import os
import sys
from time import perf_counter

NETWORK_ATTEMPTS = 0


def deny_network(event, args):
    global NETWORK_ATTEMPTS
    if event.startswith(('socket.connect', 'socket.getaddrinfo', 'socket.bind', 'socket.sendto',
                         'socket.gethostby', 'urllib.Request')):
        NETWORK_ATTEMPTS += 1
        raise PermissionError('OCR_OFFLINE')


def main():
    # Before importing any third-party module; even model-host availability probes
    # are forbidden. Explicit paths below are the only supported model source.
    os.environ.update(PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK='True', HF_HUB_OFFLINE='1',
                      HF_HUB_DISABLE_TELEMETRY='1', DISABLE_MODEL_SOURCE_CHECK='True')
    sys.addaudithook(deny_network)
    # urllib3 probes IPv6 availability by binding a local socket at import time.
    # OCR has no networking, so do not even perform that harmless socket probe.
    import socket
    socket.has_ipv6 = False
    protocol = os.fdopen(os.dup(sys.stdout.fileno()), 'w', encoding='utf-8', buffering=1)
    with open(os.devnull, 'w') as quiet:
        os.dup2(quiet.fileno(), sys.stdout.fileno())
        os.dup2(quiet.fileno(), sys.stderr.fileno())
    cached, cache_key = None, None
    for line in sys.stdin:
        try:
            command = json.loads(line)
            if command['op'] == 'shutdown':
                break
            if command['op'] == 'network_test':
                import urllib.request
                urllib.request.urlopen('https://huggingface.co', timeout=1)
            import paddle
            from paddleocr import PaddleOCR, PPStructureV3
            from paddlex.inference.utils.official_models import official_models
            def local_only(manager, *args, **kwargs):
                raise PermissionError('OCR_OFFLINE_MODEL_LOOKUP')
            type(official_models).__getitem__ = local_only
            type(official_models).get_model_path = local_only
            device = command['device']
            if device == 'gpu' and (not paddle.is_compiled_with_cuda() or paddle.device.cuda.device_count() == 0):
                protocol.write(json.dumps({'error': 'gpu'}) + '\n')
                continue
            options = command['options']
            models = command['models']
            key = (device, command['backend'], command['recognizer'], tuple(sorted(options.items())))
            started = perf_counter()
            if key != cache_key:
                cached = None
                import gc
                gc.collect()
                if device == 'gpu' and paddle.is_compiled_with_cuda():
                    paddle.device.cuda.empty_cache()
                args = dict(device='gpu:0' if device == 'gpu' else 'cpu',
                            cpu_threads=options['threads'], enable_mkldnn=False,
                            text_detection_model_name='PP-OCRv6_small_det',
                            text_detection_model_dir=models['PP-OCRv6_small_det'],
                            text_recognition_model_name=command['recognizer'],
                            text_recognition_model_dir=models[command['recognizer']],
                            text_recognition_batch_size=options['batch'],
                            use_doc_orientation_classify=options['orientation'],
                            doc_orientation_classify_model_name='PP-LCNet_x1_0_doc_ori',
                            doc_orientation_classify_model_dir=models.get('PP-LCNet_x1_0_doc_ori'),
                            use_doc_unwarping=False, use_textline_orientation=False,
                            text_det_limit_side_len=2560, text_det_limit_type='max')
                if command['backend'] == 'structure':
                    from paddlex.inference import load_pipeline_config
                    structure_config = load_pipeline_config('PP-StructureV3')
                    # PaddleOCR's public flag only reaches the outer OCR. Table
                    # orientation can lazily instantiate a second OCR from this
                    # backup config; disable its implicit hub-backed classifier.
                    structure_config['SubPipelines']['TableRecognition']['SubPipelines']['GeneralOCR']['use_textline_orientation'] = False
                    args['paddlex_config'] = structure_config
                    args.update(layout_detection_model_name='PP-DocLayout_plus-L',
                                layout_detection_model_dir=models['PP-DocLayout_plus-L'],
                                use_table_recognition=True, use_seal_recognition=False,
                                use_formula_recognition=False, use_chart_recognition=False,
                                use_region_detection=False)
                    table_models = {'table_classification':'PP-LCNet_x1_0_table_cls',
                        'wired_table_structure_recognition':'SLANeXt_wired',
                        'wireless_table_structure_recognition':'SLANet_plus',
                        'wired_table_cells_detection':'RT-DETR-L_wired_table_cell_det',
                        'wireless_table_cells_detection':'RT-DETR-L_wireless_table_cell_det',
                        'table_orientation_classify':'PP-LCNet_x1_0_doc_ori'}
                    for key,name in table_models.items():
                        args[key+'_model_name'] = name
                        args[key+'_model_dir'] = models[name]
                    cached = PPStructureV3(**args)
                else:
                    cached = PaddleOCR(**args)
                cache_key = key
            loaded = perf_counter()
            results = cached.predict(command['image'])
            result = results[0]
            ocr = result.get('overall_ocr_res', result)
            angle = result.get('doc_preprocessor_res', ocr.get('doc_preprocessor_res', {})).get('angle', 0)
            if angle == -1:
                angle = 0
            rows = []
            for text, score, poly in zip(ocr.get('rec_texts', []), ocr.get('rec_scores', []), ocr.get('rec_polys', [])):
                rows.append(dict(text=text, confidence=float(score), polygon=poly.tolist()))
            layout = result.get('layout_det_res', {}).get('boxes', [])
            layout = [dict(label=b['label'], bbox=[float(v) for v in b['coordinate']]) for b in layout]
            for table in result.get('table_res_list', []):
                for box in table.get('cell_box_list', []):
                    layout.append(dict(label='table_cell',bbox=[float(v) for v in box]))
            import psutil
            reply = dict(rows=rows, angle=int(angle), layout=layout, device=device,
                         load_seconds=loaded-started, inference_seconds=perf_counter()-loaded,
                         rss_bytes=psutil.Process().memory_info().rss)
            reply['network_attempts'] = NETWORK_ATTEMPTS
            reply['gpu_peak_allocated_bytes'] = int(paddle.device.cuda.max_memory_allocated()) if device == 'gpu' else None
            reply['gpu_peak_reserved_bytes'] = int(paddle.device.cuda.max_memory_reserved()) if device == 'gpu' else None
            protocol.write(json.dumps(reply, ensure_ascii=True) + '\n')
        except Exception as error:
            # No OCR text, file paths or raw vendor exceptions in the protocol/log.
            code = 'network' if isinstance(error, PermissionError) else 'inference'
            protocol.write(json.dumps({'error': code, 'exception_type': type(error).__name__}) + '\n')


if __name__ == '__main__':
    main()
