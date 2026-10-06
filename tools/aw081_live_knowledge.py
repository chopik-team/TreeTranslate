"""Explicit diagnostic-only terminology review; no full-sentence entries."""
from pathlib import Path
import json
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.aw081_publish_terminology import run
review = dict(revision='AW0.81', references_evaluation_only=True,
              review_origin='CODEX_AUTHORISED_DIAGNOSTIC_REVIEW',
              review_source='User authorises Diagnostic A development, 2026-10-04; unambiguous action/object semantics, no independent OEM certification.',
              manuals={'diagnostic': dict(verification='Diagnostic A documents 5 and 9: lifting device, support location, bleed screw tightening, press and hold pedal.')},
              entries=[], templates=[])
def entry(source, target, genitive, accusative, key, branches, **extras):
    review['entries'].append(dict(source=source, target=target, genitive=genitive,
        accusative=accusative, semantic_key=key, subdomain=branches[0], subdomains=branches,
        manual='diagnostic', **extras))
entry('千斤顶', 'домкрат', 'домкрата', 'домкрат', 'jack', ['engine','transmission','common'])
entry('油底壳', 'масляный поддон', 'масляного поддона', 'масляный поддон', 'engine_oil_pan', ['engine'],
      aliases=['油盘'], alias_context_terms={'油盘':['千斤顶']})
entry('变速驱动桥', 'Коробка передач с главной передачей', 'коробки передач с главной передачей',
      'коробку передач с главной передачей', 'transaxle', ['common'],
      instrumental='коробкой передач с главной передачей')
entry('放气螺钉', 'винт прокачки', 'винта прокачки', 'винт прокачки', 'bleed_screw', ['brakes'])
entry('制动液储液罐', 'бачок тормозной жидкости', 'бачка тормозной жидкости', 'бачок тормозной жидкости',
      'brake_fluid_reservoir', ['brakes'], aliases=['储液箱'],
      alias_context_terms={'储液箱':['制动液']}, locative='бачке тормозной жидкости')
authored = ROOT/'assets/knowledge/aw081-diagnostic-cata-review.json'
authored.write_text(json.dumps(review, ensure_ascii=False, indent=2)+'\n', 'utf8')
run(authored.name, '15_diagnostic_live_readiness/knowledge', 'diagnostic_cata_terminology_review.json')
path=ROOT/'assets/config/automotive-slot-forms.json'
forms=json.loads(path.read_text('utf8'))
roles={'千斤顶':dict(safety_role='lifting_device'), '制动踏板':dict(safety_role='pedal', held_accusative='нажатой'),
       '制动液':dict(safety_role='brake_fluid'), '储液箱':dict(safety_role='brake_fluid_reservoir'),
       '制动液储液罐':dict(safety_role='brake_fluid_reservoir')}
for form in forms['forms']:
    if form['source'] in roles:
        form.update(roles[form['source']])
path.write_text(json.dumps(forms, ensure_ascii=False, indent=2)+'\n','utf8')
