"""Expand the existing literal, bounded template data (no arbitrary parsing)."""
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tools.aw087_build import save

def build():
    path=ROOT/'assets/config/knowledge-templates.json';config=json.loads(path.read_text('utf-8'))
    forms=json.loads((ROOT/'assets/config/automotive-slot-forms.json').read_text('utf-8'))['forms']
    additions=[
        dict(source='发动机',base='двигатель',nominative='двигатель',genitive='двигателя',accusative='двигатель'),
        dict(source='散热器',base='радиатор',nominative='радиатор',genitive='радиатора',accusative='радиатор'),
        dict(source='排放螺塞',base='сливная пробка',nominative='сливная пробка',genitive='сливной пробки',accusative='сливную пробку'),
        dict(source='集成热管理模块',base='интегрированный модуль управления тепловым режимом',nominative='интегрированный модуль управления тепловым режимом',
             genitive='интегрированного модуля управления тепловым режимом',accusative='интегрированный модуль управления тепловым режимом',instrumental='интегрированным модулем управления тепловым режимом'),
    ]
    indexed={f['source']:f for f in forms};indexed.update({f['source']:f for f in additions});forms=list(indexed.values())
    form_path=ROOT/'assets/config/automotive-slot-forms.json';form_config=json.loads(form_path.read_text('utf-8'));form_config['forms']=forms
    form_path.write_text(json.dumps(form_config,ensure_ascii=False,indent=2)+'\n','utf-8')
    components=[f['source'] for f in forms if not any(t in f['source'] for t in ['浓度','数量','温度','泄漏','液位','腐蚀','裂纹','磨损','间隙','压力','水','气','容量','效率'])]
    fluids=[x for x in ['冷却液','发动机冷却液','冷却水','发动机冷却水','防冻液','制动液','机油','变速器油'] if x in {f['source'] for f in forms}]
    all_slots=[f['source'] for f in forms]
    rules=[r for r in config['templates'] if not r['id'].startswith('aw087-')]
    for rule in rules:
        if rule['id']=='maintain-idle':rule['types']=list(dict.fromkeys([*rule['types'],'WARNING']))
        if rule['id'] in {'drain-plug-loosen','drain-plug-tighten'}:
            rule['target']=rule['target'].replace('охлаждающую воду','охлаждающую жидкость').replace('охлаждающей воды','охлаждающей жидкости')
        if '冷却水' in rule.get('slot_forms',{}):
            rule['slot_forms']['冷却水']['accusative']='охлаждающую жидкость'
            rule['slot_forms']['冷却水']['genitive']='охлаждающей жидкости'
    actions=[]
    types=['PROCEDURE_STEP','WARNING','CONDITION','PROSE']
    def add(uid,source,target,slots=None,forms=None,scope=None,kinds=None,values=None,action=None):
        rules.append(dict(id='aw087-'+uid,status='VERIFIED',domain='general.technical.procedure' if scope is None else 'automotive',
            subdomains=scope or [],types=kinds or types,source=source,target=target,forms=forms or {},allowed_slots=slots or [],
            shared_forms=True,component_marker=True,negative_relation=True,slot_values=values or {},
            provenance='AUTHORED reusable structure; Codex technical/grammar review, not independent human certification',action=action))
    for action,zhs,verb,heading,slots in [
        ('REMOVE',['拆下','拆卸','拆除'],'Снимите','Снятие',components),
        ('INSTALL',['安装'],'Установите','Установка',components),
        ('CHECK',['检查'],'Проверьте','Проверка',all_slots),
        ('INSPECT',['检查外观'],'Осмотрите','Осмотр',components),
        ('REPLACE',['更换'],'Замените','Замена',components+fluids),
        ('FILL',['加注','添加'],'Залейте','Заполнение',fluids),
        ('DRAIN',['排出','排放'],'Слейте','Слив',fluids),
        ('CLEAN',['清洁','清洗'],'Очистите','Очистка',components),
        ('TIGHTEN',['拧紧'],'Затяните','Затяжка',['螺栓','螺母','排放螺塞','散热器排放螺塞']),
        ('LOOSEN',['松开','拧松'],'Ослабьте','Ослабление',['螺栓','螺母','排放螺塞','散热器排放螺塞']),
        ('MEASURE',['测量'],'Измерьте','Измерение',all_slots),
        ('ADJUST',['调整'],'Отрегулируйте','Регулировка',all_slots),
        ('ALIGN',['对齐'],'Совместите','Совмещение',components),
        ('VERIFY',['确认'],'Проверьте','Проверка',all_slots),
    ]:
        actions.append(dict(id='action.'+action.lower(),semantic_id=action,zh=zhs,imperative=verb,heading=heading,review_state='VERIFIED',provenance='AUTHORED'))
        for i,zh in enumerate(zhs):
            for punctuation in ['', '。']:
                add(f'{action.lower()}-{i}-'+('sentence' if punctuation else 'bare'),zh+'{X}'+punctuation,verb+' {X}.' if punctuation else verb+' {X}',
                    slots,dict(X='accusative'),action=action)
                add(f'{action.lower()}-{i}-heading'+('stop' if punctuation else ''),zh+'{X}'+punctuation,heading+' {X}',
                    slots,dict(X='genitive'),kinds=['TITLE','HEADING'],action=action)
    for action,zh,ru in [('START','启动发动机','Запустите двигатель'),('START','起动发动机','Запустите двигатель'),
        ('STOP','关闭发动机','Заглушите двигатель'),('REMOVE_AIR','排出空气','Удалите воздух из системы'),
        ('REMOVE_AIR','排气','Удалите воздух из системы'),('IDLE','保持发动机空转','Дайте двигателю поработать на холостом ходу'),
        ('IDLE','保持发动机怠速运转','Дайте двигателю поработать на холостом ходу')]:
        add('fixed-'+zh,zh+'。',ru+'.',scope=['cooling','engine','service_procedure'],action=action)
        add('fixed-bare-'+zh,zh,ru,scope=['cooling','engine','service_procedure'],action=action)
    for verb,zh in [('Подсоедините','连接'),('Отсоедините','断开'),('Отсоедините','分离')]:
        add('connector-'+zh,zh+'{X}连接器。',verb+' разъём {X}.',components,dict(X='genitive'),action='CONNECT' if zh=='连接' else 'DISCONNECT')
        add('connector-marker-'+zh,zh+'{X}连接器({Y})。',verb+' разъём {X} ({Y}).',components,dict(X='genitive',Y='protected'),action='CONNECT' if zh=='连接' else 'DISCONNECT')
        for tool in ['GDS','ITM']:
            add('tool-'+zh+tool,zh+tool+'。',verb+' '+tool+'.',scope=['diagnostics','cooling','electrical'],action='CONNECT' if zh=='连接' else 'DISCONNECT')
    for zh in ['补充']:
        add('top-up',zh+'{X}。','Долейте {X}.',fluids,dict(X='accusative'),action='FILL')
    conditions={'发动机停止':'двигатель остановлен','发动机关闭':'двигатель выключен','发动机冷却':'двигатель остыл',
        '电源断开':'питание отключено','冷却液不足':'охлаждающей жидкости недостаточно','制动液不足':'тормозной жидкости недостаточно',
        '机油不足':'моторного масла недостаточно','没有泄漏':'утечек нет','无泄漏':'утечек нет','连接器无损坏':'разъём не повреждён'}
    for uid,zh,ru in [('if','如果{X}。','Если {X}.'),('when','当{X}。','Когда {X}.'),
        ('after','在{X}后。','После того как {X}.'),('before','在{X}前。','Перед тем как {X}.'),
        ('until','直到{X}。','Дождитесь состояния: {X}.'),('ensure','确保{X}。','Убедитесь, что {X}.')]:
        add(uid,zh,ru,list(conditions),dict(X='reviewed_condition'),values=conditions,action='ENSURE' if uid=='ensure' else 'WAIT')
    for fluid in fluids:
        add('low-fluid-'+fluid,'如果'+fluid+'不足,则补充{X}。','Если '+next(f['genitive'] for f in forms if f['source']==fluid)+' недостаточно, долейте {X}.',
            [fluid],dict(X='accusative'),action='FILL')
    add('press-hoses','按压{X},以便排出空气。','Сожмите {X}, чтобы удалить воздух из системы.',
        ['散热器的上下软管','散热器软管'],dict(X='accusative'),scope=['cooling'],action='REMOVE_AIR')
    add('check-after-drive','驾驶车辆之后,检查{X}。','После поездки проверьте {X}.',all_slots,dict(X='accusative'),action='CHECK')
    add('check-temperature','确定{X}和{Y}冷却至可触摸的程度。','Убедитесь, что {X} и {Y} остыли настолько, что к ним можно прикоснуться.',
        ['发动机','散热器'],dict(X='nominative',Y='nominative'),scope=['cooling'],action='ENSURE')
    add('remove-drain-clean','拆卸{X},然后排放{Y}的发动机冷却水后,清洁{Z}。',
        'Снимите {X}, затем слейте охлаждающую жидкость двигателя из {Y} и очистите {Z}.',
        ['冷却风扇总成','冷却水箱'],dict(X='accusative',Y='genitive',Z='accusative'),scope=['cooling'],action='DRAIN')
    add('disconnect-restart','断开{X},将发动机关闭之后,重新起动发动机。',
        'Отсоедините {X}, заглушите двигатель, затем запустите его снова.',[],dict(X='protected'),scope=['cooling','diagnostics'],action='START')
    add('connect-after-stop','发动机关闭后连接{X}连接器({Y})。',
        'После выключения двигателя подсоедините разъём {X} ({Y}).',components,dict(X='genitive',Y='protected'),scope=['cooling','electrical'],action='CONNECT')
    add('use-original','只能使用原厂{X}/{Y}。','Используйте только оригинальные {X}/{Y}.',fluids,dict(X='accusative',Y='accusative'),scope=['cooling'],action='VERIFY')
    rules[-1]['target']='Используйте только {X}/{Y} оригинального производства.'
    add('no-mix','不要混合不同品牌的{X}/{Y}。','Не смешивайте {X}/{Y} разных марок.',fluids,dict(X='accusative',Y='accusative'),scope=['cooling'],action='DO_NOT')
    add('no-incompatible','不要使用其他{X}或{Y};这些可能与冷却液不相容。',
        'Не используйте {X} или {Y} иных типов: они могут не сочетаться с охлаждающей жидкостью.',
        ['防锈剂','防锈产品'],dict(X='accusative',Y='accusative'),scope=['cooling'],action='DO_NOT')
    add('no-voltage','注意不要对{X}施加静电和其他电压。','Не подвергайте {X} воздействию статического электричества и другого напряжения.',
        components,dict(X='accusative'),scope=['electrical','cooling'],action='AVOID')
    add('no-magnets','不要将任何磁性物体(例如磁铁)放在{X}附近。','Не размещайте магнитные предметы (например, магниты) рядом с {X}.',
        components,dict(X='instrumental'),scope=['electrical','cooling'],action='DO_NOT')
    add('no-power','在断开{X}时,确保发动机及其他部件没有动力。','При отсоединении {X} убедитесь, что питание двигателя и других компонентов отключено.',
        components,dict(X='genitive'),scope=['electrical','cooling'],action='ENSURE')
    # Negation rendering here is lexical 'отключено'; explicitly accepted only
    # in this reviewed condition. Generic guard otherwise rejects the rule.
    rules[-1]['target']='При отсоединении {X} убедитесь, что двигатель и другие компоненты не получают питания.'
    add('cooling-heading','更换和放气','Замена охлаждающей жидкости и удаление воздуха',scope=['cooling'],kinds=['TITLE','HEADING'])
    # Numeric concentrations are bounded protected slots, not fixture constants.
    add('concentration-maintain','为更好的防止腐蚀,{X}浓度必须至少全年保持{N}。',
        'Для защиты от коррозии концентрацию {X} необходимо поддерживать в пределах {N} круглый год.',fluids,
        dict(X='genitive',N='protected'),scope=['cooling'],action='VERIFY')
    add('concentration-low','浓度小于{N}的{X}不能充分防止腐蚀或冻结。',
        '{X} с концентрацией ниже {N} не обеспечивает достаточной защиты от коррозии или замерзания.',fluids,
        dict(X='nominative',N='protected'),scope=['cooling'],action='DO_NOT')
    rules[-1]['capitalize']=True
    add('concentration-high','如果{X}浓度超过{N},会降低冷却效率,因此不推荐。',
        'Если концентрация {X} превышает {N}, эффективность охлаждения снижается, поэтому такая концентрация не рекомендуется.',fluids,
        dict(X='genitive',N='protected'),scope=['cooling'],action='AVOID')
    for state,rendered in [('有','имеется'),('没有','отсутствует')]:
        add('tool-procedure-'+state,'如果'+state+'{X},则按如下所述,更换{Y}并排气。',
            'Если '+rendered+' {X}, замените {Y} и удалите воздух из системы в следующем порядке.',fluids,
            dict(X='protected',Y='accusative'),scope=['cooling'],action='REPLACE')
    add('after-stop-fill','在关闭发动机和切断部件电源之后,确保加入最大数量的{X}。',
        'После выключения двигателя и отключения питания компонентов убедитесь, что {X} залита до максимального уровня.',
        ['冷却液'],dict(X='nominative'),scope=['cooling'],action='ENSURE')
    add('connector-clean','在连接{X}连接器时,必须从连接器上彻底清除水或油,确保无杂质进入。',
        'Перед подсоединением разъёма {X} полностью удалите с него воду или масло. Не допускайте попадания загрязнений.',
        components,dict(X='genitive'),scope=['electrical','cooling'],action='CLEAN')
    add('connector-replace','更换{X}连接器时,务必使用规定的连接器。',
        'При замене разъёма {X} обязательно используйте разъём предписанного типа.',components,dict(X='genitive'),action='REPLACE')
    add('check-operation','通过听工作声音,检查{X}是否工作。',
        'По звуку работы проверьте, работает ли {X}.',components,dict(X='nominative'),action='CHECK')
    add('start-sound','在发动机起动前后,会出现{X}的工作声音。',
        'До и после запуска двигателя слышен звук работы {X}.',components,dict(X='genitive'),scope=['engine','cooling'],action='CHECK')
    # Reviewed duration condition values avoid accepting arbitrary time prose.
    add('warm-after-fan','在{X}工作一次之后,预热发动机{Y}。',
        'После одного срабатывания {X} прогревайте двигатель {Y}.',['冷却风扇'],dict(X='genitive',Y='reviewed_condition'),
        scope=['cooling'],values={'20分钟':'20 минут','10分钟':'10 минут','5分钟':'5 минут'},action='WAIT')
    add('activate-tool-mode','使用{X}激活"{Y}冷却液补充模式"。',
        'С помощью {X} включите режим долива охлаждающей жидкости {Y}.',components,
        dict(X='protected',Y='genitive'),scope=['diagnostics','cooling'],action='START')
    add('drain-close-protect','在倾倒{X}时,务必关闭{Y},防止{Z}溅到电气零件或油漆上。',
        'При сливе {X} обязательно закройте {Y}, чтобы {Z} не попала на электрические компоненты или окрашенные поверхности.',
        fluids+components,dict(X='genitive',Y='accusative',Z='nominative'),action='DRAIN')
    rules[-1]['slot_allowed']=dict(X=fluids,Y=components,Z=fluids)
    add('spill-wipe','如果{X}溢出,应立即擦掉。','При проливе {X} немедленно вытрите её.',fluids,dict(X='genitive'),action='CLEAN')
    add('follow-fill-guide','当更换{X}和排出空气时,务必遵循{Y}的填充指导要求。',
        'При замене {X} и удалении воздуха обязательно соблюдайте требования инструкции по заполнению {Y}.',
        fluids+components,dict(X='genitive',Y='genitive'),action='VERIFY')
    rules[-1]['slot_allowed']=dict(X=fluids,Y=components)
    for name,zh,ru in [('DISCONNECT',['断开','分离'],'Отсоедините'),('CONNECT',['连接'],'Подсоедините'),('START',['启动','起动'],'Запустите'),
        ('STOP',['关闭'],'Остановите'),('WAIT',['等待'],'Дождитесь'),('REMOVE_AIR',['排出空气'],'Удалите воздух'),
        ('AVOID',['避免'],'Избегайте'),('DO_NOT',['不要','不得','禁止'],'Не выполняйте'),('ENSURE',['确保'],'Убедитесь'),('IDLE',['空转','怠速'],'Холостой ход')]:
        actions.append(dict(id='action.'+name.lower(),semantic_id=name,zh=zh,imperative=ru,review_state='VERIFIED',provenance='AUTHORED'))
    config['templates']=rules;config['version']=2
    path.write_text(json.dumps(config,ensure_ascii=False,indent=2)+'\n','utf-8')
    (ROOT/'assets/config/technical-actions.json').write_text(json.dumps(dict(version='0.8.7',actions=actions),ensure_ascii=False,indent=2)+'\n','utf-8')
    save('candidate_templates.json',rules);save('candidate_phrases.json',actions)
    print('Reviewed templates:',len(rules),'actions:',len(actions))

if __name__=='__main__':build()
